"""Phase 3 RBAC — CRUD templates ``roles``, propagation users, garde-fous admin."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from access_control import (
    PERMISSION_CATALOG,
    PERMISSION_KEYS,
    PERM_ROLES_MANAGE,
    PERM_USERS_MANAGE,
    ROLE_ADMIN,
    ROLE_CONSEILLER,
    ROLE_LABELS,
    ROLES,
    ROLES_COLLECTION,
    SYSTEM_ROLE_IDS,
    User,
    default_permissions,
    default_see_all_dossiers,
    prune_redundant_overrides,
    resolve_effective_permissions,
    sanitize_permission_overrides,
    sanitize_permissions,
)

logger = logging.getLogger("roles_service")

# Flags qui ne doivent jamais disparaître du dernier administrateur effectif.
ADMIN_CRITICAL_KEYS = (PERM_USERS_MANAGE, PERM_ROLES_MANAGE)


class RoleCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    id: Optional[str] = Field(default=None, max_length=64)
    permissions: Optional[Dict[str, bool]] = None
    see_all_dossiers_default: Optional[bool] = None
    active: bool = True


class RoleUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)
    permissions: Optional[Dict[str, bool]] = None
    see_all_dossiers_default: Optional[bool] = None
    active: Optional[bool] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_role_id(label: str) -> str:
    """Identifiant stable ASCII à partir d'un libellé."""
    raw = unicodedata.normalize("NFKD", (label or "").strip())
    ascii_only = raw.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    if not slug:
        slug = "role"
    if slug[0].isdigit():
        slug = f"role_{slug}"
    return slug[:64]


def is_system_role(role_id: str) -> bool:
    return (role_id or "") in SYSTEM_ROLE_IDS


def sanitize_role_permissions(raw: Optional[dict], *, base_role: str = ROLE_CONSEILLER) -> Dict[str, bool]:
    """Ne conserve que les clés du catalogue ; LAMal reste non assignable via template."""
    return sanitize_permissions(raw, base_role if base_role in ROLES else ROLE_CONSEILLER)


def role_public_dict(doc: dict, *, user_count: int = 0) -> dict:
    role_id = doc.get("id") or ""
    perms = sanitize_role_permissions(doc.get("permissions"), base_role=role_id if role_id in ROLES else ROLE_CONSEILLER)
    return {
        "id": role_id,
        "label": doc.get("label") or ROLE_LABELS.get(role_id, role_id),
        "active": doc.get("active") is not False,
        "system": bool(doc.get("system")) or is_system_role(role_id),
        "permissions": perms,
        "see_all_dossiers_default": bool(
            doc["see_all_dossiers_default"]
            if "see_all_dossiers_default" in doc and doc.get("see_all_dossiers_default") is not None
            else default_see_all_dossiers(role_id if role_id in ROLES else ROLE_CONSEILLER)
        ),
        "user_count": int(user_count),
        "updated_at": doc.get("updated_at"),
        "created_at": doc.get("created_at"),
    }


async def count_users_for_role(db, role_id: str) -> int:
    try:
        return int(await db.users.count_documents({"role": role_id}))
    except Exception:
        # Fallback drivers / fakes sans count_documents
        n = 0
        cursor = db.users.find({"role": role_id}, {"_id": 1})
        async for _ in cursor:
            n += 1
        return n


async def list_roles_with_counts(db) -> List[dict]:
    rows: List[dict] = []
    cursor = db[ROLES_COLLECTION].find({}, {"_id": 0})
    async for doc in cursor:
        rows.append(doc)
    rows.sort(key=lambda r: (0 if is_system_role(r.get("id") or "") else 1, (r.get("label") or "").lower()))
    out = []
    for doc in rows:
        rid = doc.get("id") or ""
        out.append(role_public_dict(doc, user_count=await count_users_for_role(db, rid)))
    return out


async def get_role_doc(db, role_id: str) -> Optional[dict]:
    return await db[ROLES_COLLECTION].find_one({"id": role_id}, {"_id": 0})


def lock_admin_template_permissions(role_id: str, permissions: Dict[str, bool]) -> Dict[str, bool]:
    """Règle claire : le template système ``admin`` conserve toujours users.manage + roles.manage."""
    if role_id != ROLE_ADMIN:
        return permissions
    locked = dict(permissions)
    for key in ADMIN_CRITICAL_KEYS:
        if not locked.get(key):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Impossible de retirer « {key} » du rôle Administrateur (template système). "
                    "Au moins un administrateur doit pouvoir gérer les utilisateurs et les rôles."
                ),
            )
        locked[key] = True
    return locked


async def _iter_active_users(db) -> List[dict]:
    rows: List[dict] = []
    cursor = db.users.find({}, {"_id": 0, "password_hash": 0})
    async for doc in cursor:
        if doc.get("active") is False:
            continue
        rows.append(doc)
    return rows


def _effective_critical_flags(doc: dict, *, role_perms_override: Optional[Dict[str, bool]] = None) -> Dict[str, bool]:
    """Calcule users.manage / roles.manage effectifs (template simulé + overrides)."""
    simulated = dict(doc)
    if role_perms_override is not None and not (
        isinstance(doc.get("permission_overrides"), dict) and doc.get("permission_overrides")
    ):
        # Sans overrides : le snapshot user suit le template après propagation.
        # On simule le snapshot aligné sur le template pour les clés critiques absentes des overrides.
        stored = dict(doc.get("permissions") or {})
        for key, value in role_perms_override.items():
            overrides = doc.get("permission_overrides") if isinstance(doc.get("permission_overrides"), dict) else {}
            if key not in overrides:
                stored[key] = bool(value)
        simulated["permissions"] = stored
    elif role_perms_override is not None:
        stored = dict(doc.get("permissions") or {})
        overrides = doc.get("permission_overrides") if isinstance(doc.get("permission_overrides"), dict) else {}
        for key, value in role_perms_override.items():
            if key not in overrides:
                stored[key] = bool(value)
        simulated["permissions"] = stored
    perms = resolve_effective_permissions(simulated)
    return {
        PERM_USERS_MANAGE: bool(perms.get(PERM_USERS_MANAGE)),
        PERM_ROLES_MANAGE: bool(perms.get(PERM_ROLES_MANAGE)),
    }


def _raise_missing_critical_admin(missing: List[str]) -> None:
    raise HTTPException(
        status_code=400,
        detail=(
            "Garde-fou admin : cette modification laisserait le système sans aucun utilisateur "
            f"actif capable de « {' » / « '.join(missing)} ». "
            "Conservez ces droits sur le rôle Administrateur ou sur au moins un compte."
        ),
    )


async def assert_critical_admin_access_remains(
    db,
    *,
    role_id: str,
    proposed_permissions: Optional[Dict[str, bool]] = None,
    proposed_active: Optional[bool] = None,
) -> None:
    """Empêche de laisser le tenant sans aucun user capable de gérer users et rôles."""
    users = await _iter_active_users(db)
    role_active = True if proposed_active is None else bool(proposed_active)

    has_users_manage = False
    has_roles_manage = False
    for doc in users:
        if doc.get("role") == role_id:
            if not role_active:
                # Users du rôle désactivé : on ne compte plus leurs droits hérités du template
                # (ils gardent leur snapshot, mais la désactivation d'un rôle custom soft
                # ne retire pas les snapshots — on vérifie quand même via snapshot courant).
                flags = _effective_critical_flags(doc, role_perms_override=None)
            else:
                flags = _effective_critical_flags(
                    doc,
                    role_perms_override=proposed_permissions,
                )
        else:
            flags = _effective_critical_flags(doc, role_perms_override=None)
        if flags[PERM_USERS_MANAGE]:
            has_users_manage = True
        if flags[PERM_ROLES_MANAGE]:
            has_roles_manage = True
        if has_users_manage and has_roles_manage:
            return

    missing = []
    if not has_users_manage:
        missing.append(PERM_USERS_MANAGE)
    if not has_roles_manage:
        missing.append(PERM_ROLES_MANAGE)
    _raise_missing_critical_admin(missing)


async def assert_critical_admin_after_user_change(
    db,
    *,
    target_user_id: str,
    proposed_doc: dict,
) -> None:
    """Garde-fou Phase 4 : overrides / rôle / désactivation ne doivent pas retirer les derniers admins."""
    users = await _iter_active_users(db)
    has_users_manage = False
    has_roles_manage = False
    target_seen = False
    for doc in users:
        if doc.get("user_id") == target_user_id:
            target_seen = True
            if proposed_doc.get("active") is False:
                continue
            flags = _effective_critical_flags(proposed_doc, role_perms_override=None)
        else:
            flags = _effective_critical_flags(doc, role_perms_override=None)
        if flags[PERM_USERS_MANAGE]:
            has_users_manage = True
        if flags[PERM_ROLES_MANAGE]:
            has_roles_manage = True
        if has_users_manage and has_roles_manage:
            return

    # Cible inactive dans la boucle (déjà désactivée) : évaluer quand même la proposition.
    if not target_seen and proposed_doc.get("active") is not False:
        flags = _effective_critical_flags(proposed_doc, role_perms_override=None)
        if flags[PERM_USERS_MANAGE]:
            has_users_manage = True
        if flags[PERM_ROLES_MANAGE]:
            has_roles_manage = True
        if has_users_manage and has_roles_manage:
            return

    missing = []
    if not has_users_manage:
        missing.append(PERM_USERS_MANAGE)
    if not has_roles_manage:
        missing.append(PERM_ROLES_MANAGE)
    _raise_missing_critical_admin(missing)


async def resolve_role_template_permissions(db, role_id: str) -> Dict[str, bool]:
    """Template permissions Mongo (sinon défauts code)."""
    doc = await get_role_doc(db, role_id)
    base = role_id if role_id in ROLES else ROLE_CONSEILLER
    if doc and isinstance(doc.get("permissions"), dict) and doc.get("permissions"):
        return sanitize_role_permissions(doc.get("permissions"), base_role=base)
    return default_permissions(base)


def prepare_overrides_for_role_change(
    current_overrides: Optional[dict],
    new_role_permissions: Dict[str, bool],
) -> Dict[str, bool]:
    """Changement de rôle : conserve les overrides encore significatifs (≠ nouveau template).

    Les overrides redondants (égale au nouvel héritage) sont retirés. Pas de reset forcé.
    """
    return prune_redundant_overrides(current_overrides, new_role_permissions)


def apply_override_state_to_user_fields(
    *,
    role: str,
    role_permissions: Dict[str, bool],
    overrides: Dict[str, bool],
    see_all_dossiers: Optional[bool],
    access_by_account_id_only: bool,
) -> Dict[str, Any]:
    """Réaligne le snapshot ``permissions`` sur le template ; stocke les overrides à part.

    ``see_all_dossiers`` / dual-strict restent hors matrice modules.
    """
    from access_control import permission_storage_fields

    cleaned = sanitize_permission_overrides(overrides)
    fields = permission_storage_fields(
        role if role in ROLES else ROLE_CONSEILLER,
        role_permissions,
        see_all_dossiers,
        access_by_account_id_only=access_by_account_id_only,
    )
    fields["permission_overrides"] = cleaned
    return fields


async def propagate_role_permissions_to_users(
    db,
    role_id: str,
    new_permissions: Dict[str, bool],
) -> Dict[str, int]:
    """Applique le template rôle aux users de ce rôle sans écraser ``permission_overrides``.

    Pour chaque clé du catalogue présente dans ``new_permissions`` :
    - si la clé est dans ``user.permission_overrides`` → ignorée (Phase 4) ;
    - sinon ``user.permissions[key]`` est aligné sur le template.
    """
    users_updated = 0
    override_keys_skipped = 0
    now = _now()
    cursor = db.users.find({"role": role_id}, {"_id": 1, "user_id": 1, "permissions": 1, "permission_overrides": 1})
    async for doc in cursor:
        stored = dict(doc.get("permissions") or {}) if isinstance(doc.get("permissions"), dict) else {}
        overrides = (
            doc.get("permission_overrides")
            if isinstance(doc.get("permission_overrides"), dict)
            else {}
        )
        changed = False
        for key in PERMISSION_KEYS:
            if key not in new_permissions:
                continue
            if key in overrides:
                override_keys_skipped += 1
                continue
            desired = bool(new_permissions[key])
            if stored.get(key) != desired:
                stored[key] = desired
                changed = True
        if not changed:
            continue
        filter_q = {"_id": doc["_id"]} if doc.get("_id") is not None else {"user_id": doc.get("user_id")}
        await db.users.update_one(
            filter_q,
            {
                "$set": {
                    "permissions": stored,
                    "can_manage_users": bool(stored.get(PERM_USERS_MANAGE)),
                    "can_manage_settings": bool(stored.get(PERM_USERS_MANAGE)),
                    "permissions_role_propagated_at": now,
                }
            },
        )
        users_updated += 1
    return {"users_updated": users_updated, "override_keys_skipped": override_keys_skipped}


async def create_role(db, payload: RoleCreate, *, actor: User) -> dict:
    label = (payload.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Libellé obligatoire")
    role_id = (payload.id or "").strip() or slugify_role_id(label)
    role_id = slugify_role_id(role_id)
    if is_system_role(role_id) or await get_role_doc(db, role_id):
        raise HTTPException(status_code=400, detail="Cet identifiant de rôle existe déjà")
    base = ROLE_CONSEILLER
    # Base restrictive (conseiller) : pas d'auto-grant des flags admin sensibles.
    raw_perms = payload.permissions if payload.permissions is not None else default_permissions(base)
    perms = sanitize_role_permissions(raw_perms, base_role=base)
    if payload.permissions is None:
        perms[PERM_USERS_MANAGE] = False
        perms[PERM_ROLES_MANAGE] = False
    see_all = (
        bool(payload.see_all_dossiers_default)
        if payload.see_all_dossiers_default is not None
        else False
    )
    now = _now()
    doc = {
        "id": role_id,
        "label": label,
        "active": bool(payload.active),
        "system": False,
        "permissions": perms,
        "see_all_dossiers_default": see_all,
        "created_at": now,
        "updated_at": now,
    }
    await db[ROLES_COLLECTION].insert_one(doc)
    try:
        from access_policy_journal import log_access_event

        await log_access_event(
            db,
            event_type="role_create",
            actor_account_id=actor.account_id,
            actor_email=actor.email,
            detail={"role_id": role_id, "label": label, "permissions": perms},
        )
    except Exception:
        logger.warning("Journal role_create indisponible (create OK : %s)", role_id)
    return role_public_dict(doc, user_count=0)


async def update_role(db, role_id: str, payload: RoleUpdate, *, actor: User) -> dict:
    existing = await get_role_doc(db, role_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rôle introuvable")

    updates: Dict[str, Any] = {"updated_at": _now()}
    before_perms = sanitize_role_permissions(
        existing.get("permissions"),
        base_role=role_id if role_id in ROLES else ROLE_CONSEILLER,
    )
    new_perms = before_perms
    perms_changed = False

    if payload.label is not None:
        label = payload.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="Libellé obligatoire")
        updates["label"] = label

    if payload.active is not None:
        if is_system_role(role_id) and payload.active is False:
            raise HTTPException(status_code=400, detail="Impossible de désactiver un rôle système")
        updates["active"] = bool(payload.active)

    if payload.see_all_dossiers_default is not None:
        updates["see_all_dossiers_default"] = bool(payload.see_all_dossiers_default)

    if payload.permissions is not None:
        new_perms = sanitize_role_permissions(
            payload.permissions,
            base_role=role_id if role_id in ROLES else ROLE_CONSEILLER,
        )
        new_perms = lock_admin_template_permissions(role_id, new_perms)
        updates["permissions"] = new_perms
        perms_changed = True

    proposed_active = updates.get("active", existing.get("active") is not False)
    await assert_critical_admin_access_remains(
        db,
        role_id=role_id,
        proposed_permissions=new_perms if perms_changed else None,
        proposed_active=proposed_active if payload.active is not None else None,
    )

    await db[ROLES_COLLECTION].update_one({"id": role_id}, {"$set": updates})
    propagation = {"users_updated": 0, "override_keys_skipped": 0}
    if perms_changed:
        propagation = await propagate_role_permissions_to_users(db, role_id, new_perms)

    try:
        from access_policy_journal import log_access_event

        event_type = "role_permissions_change" if perms_changed else "role_update"
        await log_access_event(
            db,
            event_type=event_type,
            actor_account_id=actor.account_id,
            actor_email=actor.email,
            detail={
                "role_id": role_id,
                "before": before_perms if perms_changed else None,
                "after": new_perms if perms_changed else None,
                "updates": {k: v for k, v in updates.items() if k != "permissions"},
                "propagation": propagation,
            },
        )
    except Exception:
        logger.warning("Journal role_update indisponible (update OK : %s)", role_id)

    fresh = await get_role_doc(db, role_id) or {**existing, **updates}
    return {
        **role_public_dict(fresh, user_count=await count_users_for_role(db, role_id)),
        "propagation": propagation,
    }


async def delete_or_disable_role(db, role_id: str, *, actor: User) -> dict:
    existing = await get_role_doc(db, role_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Rôle introuvable")
    if is_system_role(role_id) or existing.get("system"):
        raise HTTPException(
            status_code=400,
            detail="Les rôles système (Administrateur, Direction, Gestionnaire offres, Conseiller) ne peuvent pas être supprimés",
        )
    user_count = await count_users_for_role(db, role_id)
    if user_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de supprimer ce rôle : {user_count} utilisateur(s) y sont encore rattachés",
        )
    await assert_critical_admin_access_remains(
        db,
        role_id=role_id,
        proposed_permissions=None,
        proposed_active=False,
    )
    await db[ROLES_COLLECTION].update_one(
        {"id": role_id},
        {"$set": {"active": False, "updated_at": _now()}},
    )
    try:
        from access_policy_journal import log_access_event

        await log_access_event(
            db,
            event_type="role_disable",
            actor_account_id=actor.account_id,
            actor_email=actor.email,
            detail={"role_id": role_id, "before_active": existing.get("active") is not False},
        )
    except Exception:
        logger.warning("Journal role_disable indisponible (disable OK : %s)", role_id)
    fresh = await get_role_doc(db, role_id)
    return role_public_dict(fresh or {**existing, "active": False}, user_count=0)


async def list_assignable_role_options(db) -> List[dict]:
    """Options pour l'UI Utilisateurs (rôles actifs, Mongo ou seed code)."""
    rows = await list_roles_with_counts(db)
    active = [r for r in rows if r.get("active") is not False]
    if active:
        return [{"id": r["id"], "label": r["label"]} for r in active]
    return [{"id": r, "label": ROLE_LABELS[r]} for r in ROLES]


async def role_id_is_assignable(db, role_id: str) -> bool:
    if not role_id:
        return False
    if role_id in ROLES:
        doc = await get_role_doc(db, role_id)
        return doc is None or doc.get("active") is not False
    doc = await get_role_doc(db, role_id)
    return bool(doc) and doc.get("active") is not False


def catalog_for_roles_ui() -> List[dict]:
    """Catalogue groupé module×action pour la matrice (copie shallow)."""
    return PERMISSION_CATALOG
