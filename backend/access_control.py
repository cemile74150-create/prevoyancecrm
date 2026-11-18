"""Auth helpers: roles, passwords, conseiller scoping."""
from __future__ import annotations

import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from itertools import permutations, product
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import bcrypt
from fastapi import HTTPException, Request, Header
from pydantic import BaseModel, Field, EmailStr

# Cache court session→User (évite 2 finds Mongo par requête sous charge).
_SESSION_USER_CACHE: Dict[str, Tuple[float, "User"]] = {}
_SESSION_USER_CACHE_TTL_S = float(os.environ.get("SESSION_USER_CACHE_TTL_S") or "30")
_SESSION_USER_CACHE_MAX = int(os.environ.get("SESSION_USER_CACHE_MAX") or "512")


def invalidate_session_user_cache(token: Optional[str] = None) -> None:
    """Invalide une entrée (logout) ou tout le cache."""
    if token:
        _SESSION_USER_CACHE.pop(token, None)
        return
    _SESSION_USER_CACHE.clear()


def _session_cache_get(token: str) -> Optional["User"]:
    hit = _SESSION_USER_CACHE.get(token)
    if not hit:
        return None
    expires_at, user = hit
    if expires_at < time.monotonic():
        _SESSION_USER_CACHE.pop(token, None)
        return None
    return user


def _session_cache_put(token: str, user: "User") -> None:
    if _SESSION_USER_CACHE_TTL_S <= 0:
        return
    if len(_SESSION_USER_CACHE) >= _SESSION_USER_CACHE_MAX:
        now = time.monotonic()
        expired = [k for k, (exp, _) in _SESSION_USER_CACHE.items() if exp < now]
        for k in expired:
            _SESSION_USER_CACHE.pop(k, None)
        while len(_SESSION_USER_CACHE) >= _SESSION_USER_CACHE_MAX:
            _SESSION_USER_CACHE.pop(next(iter(_SESSION_USER_CACHE)), None)
    _SESSION_USER_CACHE[token] = (time.monotonic() + _SESSION_USER_CACHE_TTL_S, user)

TENANT_USER_ID = os.environ.get("TENANT_USER_ID", "local-dev")
# legacy (défaut prod) | dual (account_id si présent, sinon nom) | strict (account_id seul)
ACCESS_MODE = (os.environ.get("ACCESS_MODE") or "legacy").strip().lower()
if ACCESS_MODE not in ("legacy", "dual", "strict"):
    ACCESS_MODE = "legacy"

# Surcharge runtime (Mongo app_settings) — None = suivre ACCESS_MODE env / défaut.
_runtime_access_mode_override: Optional[str] = None
ACCESS_POLICY_SETTINGS_KEY = "access_policy"
ACCESS_POLICY_JOURNAL = "access_policy_journal"

ROLE_ADMIN = "admin"
ROLE_CEO = "ceo"
ROLE_GESTIONNAIRE_OFFRES = "gestionnaire_offres"
ROLE_CONSEILLER = "conseiller"
ROLES = [ROLE_ADMIN, ROLE_CEO, ROLE_GESTIONNAIRE_OFFRES, ROLE_CONSEILLER]
# Rôles seedés Phase 1 — non supprimables (Phase 3).
SYSTEM_ROLE_IDS = frozenset(ROLES)

ROLE_LABELS = {
    ROLE_ADMIN: "Administrateur",
    ROLE_CEO: "Direction",
    ROLE_GESTIONNAIRE_OFFRES: "Gestionnaire offres",
    ROLE_CONSEILLER: "Conseiller",
}

DEFAULT_CONSEILLERS = [
    "Alberto Mendes",
    "Valentin Lugnier",
    "Emric Laugerette",
    "Tony D'Andrea",
]

PERM_CLIENTS_VIEW = "clients.view"
PERM_CLIENTS_CREATE = "clients.create"
PERM_CLIENTS_EDIT = "clients.edit"
PERM_CLIENTS_DELETE = "clients.delete"
PERM_DOSSIERS_VIEW = "dossiers.view"
PERM_DOSSIERS_CREATE = "dossiers.create"
PERM_DOSSIERS_EDIT = "dossiers.edit"
PERM_DOSSIERS_DELETE = "dossiers.delete"
PERM_DOCUMENTS_VIEW = "documents.view"
PERM_DOCUMENTS_ADD = "documents.add"
PERM_DOCUMENTS_DELETE = "documents.delete"
PERM_SUIVI_3P_VIEW = "suivi_3p.view"
PERM_SUIVI_3P_EDIT = "suivi_3p.edit"
PERM_DEMANDES_OFFRES_VIEW = "demandes_offres.view"
PERM_DEMANDES_OFFRES_EDIT = "demandes_offres.edit"
PERM_DEMANDES_OFFRES_PROCESS = "demandes_offres.process"
PERM_RAPPELS_VIEW = "rappels.view"
PERM_RAPPELS_EDIT = "rappels.edit"
PERM_AGENDA_VIEW = "agenda.view"
PERM_FORMULAIRES_VIEW = "formulaires.view"
PERM_ANALYSES_VIEW = "analyses.view"
PERM_ANALYSES_EDIT = "analyses.edit"
PERM_USERS_MANAGE = "users.manage"
# Phase 2 RBAC — modules admin autrefois couverts uniquement par users.manage.
PERM_MESSAGERIE_VIEW = "messagerie.view"
PERM_ENTREPRISES_VIEW = "entreprises.view"
PERM_ENTREPRISES_CREATE = "entreprises.create"
PERM_ENTREPRISES_UPDATE = "entreprises.update"
PERM_SUIVI_TECHNIQUE_VIEW = "suivi_technique.view"
# Réservé Phase 3 (UI Rôles) — catalogue deny-by-default, pas d'héritage users.manage.
PERM_ROLES_MANAGE = "roles.manage"
# Accès module Congés : domaine e-mail (voir email_domain_access). Pas assignable en UI.
PERM_LEAVES_ACCESS = "leaves.access"
# Décisions RH (valider / refuser) : leaves.manage + domaine obligatoire.
PERM_LEAVES_MANAGE = "leaves.manage"
PERM_LAMAL_MODULE_ACCESS = "lamal_module_access"
# Compte administrateur existant (Cemile Demirtas). Le rôle admin ne suffit pas.
LAMAL_OWNER_EMAIL = "cdemirtas@agencemendes.ch"

# Flags admin scindés : hérités de users.manage si absents du snapshot (compat Phase 2).
PHASE2_USERS_MANAGE_INHERITED_KEYS = (
    PERM_MESSAGERIE_VIEW,
    PERM_ENTREPRISES_VIEW,
    PERM_ENTREPRISES_CREATE,
    PERM_ENTREPRISES_UPDATE,
    PERM_SUIVI_TECHNIQUE_VIEW,
)

PERMISSION_KEYS = [
    PERM_CLIENTS_VIEW,
    PERM_CLIENTS_CREATE,
    PERM_CLIENTS_EDIT,
    PERM_CLIENTS_DELETE,
    PERM_DOSSIERS_VIEW,
    PERM_DOSSIERS_CREATE,
    PERM_DOSSIERS_EDIT,
    PERM_DOSSIERS_DELETE,
    PERM_DOCUMENTS_VIEW,
    PERM_DOCUMENTS_ADD,
    PERM_DOCUMENTS_DELETE,
    PERM_SUIVI_3P_VIEW,
    PERM_SUIVI_3P_EDIT,
    PERM_DEMANDES_OFFRES_VIEW,
    PERM_DEMANDES_OFFRES_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
    PERM_RAPPELS_VIEW,
    PERM_RAPPELS_EDIT,
    PERM_AGENDA_VIEW,
    PERM_FORMULAIRES_VIEW,
    PERM_ANALYSES_VIEW,
    PERM_ANALYSES_EDIT,
    PERM_USERS_MANAGE,
    PERM_MESSAGERIE_VIEW,
    PERM_ENTREPRISES_VIEW,
    PERM_ENTREPRISES_CREATE,
    PERM_ENTREPRISES_UPDATE,
    PERM_SUIVI_TECHNIQUE_VIEW,
    PERM_ROLES_MANAGE,
    PERM_LEAVES_MANAGE,
    PERM_LAMAL_MODULE_ACCESS,
]

# Catalogue actif (Phase 1 historique + Phase 2 modules admin).
# - Clé du catalogue absente du snapshot user.permissions → default-allow (comportement legacy).
# - Clé hors catalogue (nouvelle / inconnue) → deny-by-default via has_perm.
LEGACY_PERMISSION_KEYS = frozenset(PERMISSION_KEYS)

# Collection Mongo des templates de rôle (seed Phase 1 ; CRUD UI = Phase 3).
ROLES_COLLECTION = "roles"

# Actions canoniques module×action (métadonnées catalogue).
PERMISSION_ACTIONS = (
    "view",
    "create",
    "edit",
    "update",
    "delete",
    "add",
    "process",
    "manage",
    "access",
)


def split_permission_key(key: str) -> Dict[str, str]:
    """Convention de nommage module.action pour évolutions Phase 2+.

    Ex. ``clients.view`` → module=clients, action=view.
    Clés plates (ex. ``lamal_module_access``) → module=clé, action=access.
    """
    raw = (key or "").strip()
    if "." in raw:
        module, action = raw.split(".", 1)
        return {"module": module, "action": action or "access"}
    return {"module": raw, "action": "access"}

PERMISSION_CATALOG = [
    {
        "id": "clients",
        "label": "Clients",
        "items": [
            {"key": PERM_CLIENTS_VIEW, "label": "Voir les clients"},
            {"key": PERM_CLIENTS_CREATE, "label": "Créer un client"},
            {"key": PERM_CLIENTS_EDIT, "label": "Modifier un client"},
            {"key": PERM_CLIENTS_DELETE, "label": "Supprimer un client"},
        ],
    },
    {
        "id": "dossiers",
        "label": "Dossiers",
        "items": [
            {"key": PERM_DOSSIERS_VIEW, "label": "Voir les dossiers"},
            {"key": PERM_DOSSIERS_CREATE, "label": "Créer un dossier"},
            {"key": PERM_DOSSIERS_EDIT, "label": "Modifier un dossier"},
            {"key": PERM_DOSSIERS_DELETE, "label": "Supprimer un dossier"},
        ],
    },
    {
        "id": "documents",
        "label": "Documents",
        "items": [
            {"key": PERM_DOCUMENTS_VIEW, "label": "Voir les documents"},
            {"key": PERM_DOCUMENTS_ADD, "label": "Ajouter des documents"},
            {"key": PERM_DOCUMENTS_DELETE, "label": "Supprimer des documents"},
        ],
    },
    {
        "id": "suivi_3p",
        "label": "Suivi 3e pilier",
        "items": [
            {"key": PERM_SUIVI_3P_VIEW, "label": "Voir le suivi 3e pilier"},
            {"key": PERM_SUIVI_3P_EDIT, "label": "Modifier le suivi 3e pilier"},
        ],
    },
    {
        "id": "demandes_offres",
        "label": "Demandes d'offres 3P",
        "items": [
            {"key": PERM_DEMANDES_OFFRES_VIEW, "label": "Voir les demandes d'offres"},
            {"key": PERM_DEMANDES_OFFRES_EDIT, "label": "Créer/modifier les demandes d'offres"},
            {
                "key": PERM_DEMANDES_OFFRES_PROCESS,
                "label": "Traiter les réponses aux offres (gestionnaire)",
            },
        ],
    },
    {
        "id": "rappels",
        "label": "Rappels",
        "items": [
            {"key": PERM_RAPPELS_VIEW, "label": "Voir les rappels"},
            {"key": PERM_RAPPELS_EDIT, "label": "Créer/modifier des rappels"},
        ],
    },
    {
        "id": "agenda",
        "label": "Ordre du jour",
        "items": [
            {"key": PERM_AGENDA_VIEW, "label": "Voir l’ordre du jour"},
        ],
    },
    {
        "id": "formulaires",
        "label": "Bibliothèque documentaire",
        "items": [
            {"key": PERM_FORMULAIRES_VIEW, "label": "Voir la bibliothèque documentaire"},
        ],
    },
    {
        "id": "analyses",
        "label": "Effectuer une analyse",
        "items": [
            {"key": PERM_ANALYSES_VIEW, "label": "Voir les analyses de prévoyance"},
            {"key": PERM_ANALYSES_EDIT, "label": "Créer et modifier les analyses de prévoyance"},
        ],
    },
    {
        "id": "users",
        "label": "Utilisateurs",
        "items": [
            {"key": PERM_USERS_MANAGE, "label": "Gérer les utilisateurs (CRUD / import)"},
        ],
    },
    {
        "id": "messagerie",
        "label": "Messagerie",
        "items": [
            {"key": PERM_MESSAGERIE_VIEW, "label": "Consulter la messagerie (journal e-mails)"},
        ],
    },
    {
        "id": "entreprises",
        "label": "Entreprises",
        "items": [
            {"key": PERM_ENTREPRISES_VIEW, "label": "Voir les entreprises"},
            {"key": PERM_ENTREPRISES_CREATE, "label": "Créer une entreprise"},
            {"key": PERM_ENTREPRISES_UPDATE, "label": "Modifier une entreprise"},
        ],
    },
    {
        "id": "suivi_technique",
        "label": "Suivi technique",
        "items": [
            {"key": PERM_SUIVI_TECHNIQUE_VIEW, "label": "Consulter le suivi technique"},
        ],
    },
    {
        "id": "roles",
        "label": "Rôles et permissions",
        "items": [
            {
                "key": PERM_ROLES_MANAGE,
                "label": "Gérer les rôles et permissions",
            },
        ],
    },
    {
        "id": "conges",
        "label": "Congés & absences (@agencemendes.ch)",
        "items": [
            {
                "key": PERM_LEAVES_MANAGE,
                "label": "Gérer les demandes (RH : valider, refuser) — domaine @agencemendes.ch requis",
            },
        ],
    },
    {
        "id": "lamal",
        "label": "Comparateur LAMal",
        "items": [
            {
                "key": PERM_LAMAL_MODULE_ACCESS,
                "label": "Accès au comparateur LAMal (réservé au compte Cemile Demirtas, non transférable)",
            },
        ],
    },
]

# Métadonnées module×action sur chaque item (sans changer labels / clés).
for _group in PERMISSION_CATALOG:
    for _item in _group.get("items") or []:
        _meta = split_permission_key(_item.get("key") or "")
        _item.setdefault("module", _meta["module"])
        _item.setdefault("action", _meta["action"])


class User(BaseModel):
    """Authenticated principal. user_id is always the CRM tenant (data owner)."""
    user_id: str = TENANT_USER_ID
    account_id: str
    email: str
    name: str
    prenom: str = ""
    nom: str = ""
    telephone: Optional[str] = None
    picture: Optional[str] = None
    role: str = ROLE_CONSEILLER
    conseiller: Optional[str] = None
    finma_number: Optional[str] = None
    active: bool = True
    can_manage_users: bool = False
    can_manage_settings: bool = False
    see_all_dossiers: bool = False
    # Nouveaux conseillers : jamais de fallback nom, même en mode dual.
    access_by_account_id_only: bool = False
    permissions: Dict[str, bool] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    prenom: str
    nom: str
    email: EmailStr
    telephone: Optional[str] = None
    # Optionnel si send_activation=True (invitation sans MDP initial).
    password: Optional[str] = None
    role: str = ROLE_CONSEILLER
    conseiller: Optional[str] = None
    finma_number: Optional[str] = None
    entreprise_id: Optional[str] = None
    send_activation: Optional[bool] = False
    receive_conseiller_rappel_copies: Optional[bool] = False
    see_all_dossiers: Optional[bool] = None
    permissions: Optional[Dict[str, bool]] = None
    # Ignoré pour les conseillers : toujours True côté serveur.
    access_by_account_id_only: Optional[bool] = None


class UserUpdate(BaseModel):
    prenom: Optional[str] = None
    nom: Optional[str] = None
    email: Optional[EmailStr] = None
    telephone: Optional[str] = None
    role: Optional[str] = None
    conseiller: Optional[str] = None
    finma_number: Optional[str] = None
    entreprise_id: Optional[str] = None
    active: Optional[bool] = None
    receive_conseiller_rappel_copies: Optional[bool] = None
    see_all_dossiers: Optional[bool] = None
    permissions: Optional[Dict[str, bool]] = None
    # Phase 4 : exceptions individuelles (overlay sur le template rôle).
    # PUT /users/{id} — seuls users.manage peuvent les modifier (require_admin).
    permission_overrides: Optional[Dict[str, bool]] = None
    # True → vide permission_overrides et réaligne le snapshot permissions sur le template rôle.
    reset_permission_overrides: Optional[bool] = None
    # Seul un admin peut poser True ; False refusé si déjà True (nouveaux conseillers).
    access_by_account_id_only: Optional[bool] = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=6)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def display_name(prenom: str, nom: str) -> str:
    return f"{(prenom or '').strip()} {(nom or '').strip()}".strip()


def default_permissions(role: str) -> Dict[str, bool]:
    """Droits par défaut selon le rôle (conseiller ≠ gestionnaire d'offres)."""
    if role not in ROLES:
        role = ROLE_CONSEILLER
    perms = {key: True for key in PERMISSION_KEYS}
    if role != ROLE_ADMIN:
        perms[PERM_USERS_MANAGE] = False
        for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
            perms[key] = False
    # Traitement interne des offres : réservé admin / CEO / gestionnaire
    if role == ROLE_CONSEILLER:
        perms[PERM_DEMANDES_OFFRES_PROCESS] = False
    else:
        perms[PERM_DEMANDES_OFFRES_PROCESS] = True
    perms[PERM_LEAVES_MANAGE] = role == ROLE_ADMIN
    perms[PERM_LAMAL_MODULE_ACCESS] = False
    # Phase 3 : roles.manage uniquement pour le template Administrateur (pas d'héritage users.manage).
    perms[PERM_ROLES_MANAGE] = role == ROLE_ADMIN
    return perms


def apply_phase2_users_manage_inheritance(
    perms: Dict[str, bool],
    *,
    stored: Optional[dict] = None,
    overrides: Optional[dict] = None,
) -> Dict[str, bool]:
    """Si une clé Phase 2 admin est absente du snapshot/overrides, calquer users.manage.

    users.manage true → flags hérités true ; false → false.
    Une valeur explicite dans snapshot ou overrides est conservée (indépendance Phase 2).
    ``roles.manage`` n'est jamais hérité.
    """
    manage = bool(perms.get(PERM_USERS_MANAGE))
    explicit: set = set()
    if isinstance(stored, dict):
        explicit.update(k for k in PHASE2_USERS_MANAGE_INHERITED_KEYS if k in stored)
    if isinstance(overrides, dict):
        explicit.update(k for k in PHASE2_USERS_MANAGE_INHERITED_KEYS if k in overrides)
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        if key not in explicit:
            perms[key] = manage
    if not (isinstance(stored, dict) and PERM_ROLES_MANAGE in stored) and not (
        isinstance(overrides, dict) and PERM_ROLES_MANAGE in overrides
    ):
        perms[PERM_ROLES_MANAGE] = False
    return perms


def default_see_all_dossiers(role: str) -> bool:
    return role in (ROLE_ADMIN, ROLE_CEO, ROLE_GESTIONNAIRE_OFFRES)


def sanitize_permissions(raw: Optional[dict], role: str) -> Dict[str, bool]:
    base = default_permissions(role)
    stored = raw if isinstance(raw, dict) else None
    if stored:
        for key in PERMISSION_KEYS:
            if key in stored:
                base[key] = bool(stored[key])
    base[PERM_LAMAL_MODULE_ACCESS] = False
    apply_phase2_users_manage_inheritance(base, stored=stored)
    return base


def role_template_permissions(
    role: str,
    *,
    role_doc: Optional[dict] = None,
) -> Dict[str, bool]:
    """Template de permissions pour un rôle (code ou document Mongo ``roles``)."""
    if isinstance(role_doc, dict):
        stored = role_doc.get("permissions")
        if isinstance(stored, dict) and stored:
            return sanitize_permissions(stored, role_doc.get("id") or role)
    return default_permissions(role)


def role_seed_document(role_id: str, *, updated_at: Optional[str] = None) -> dict:
    """Document seed collection ``roles`` (ids / labels / défauts actuels)."""
    if role_id not in ROLES:
        role_id = ROLE_CONSEILLER
    return {
        "id": role_id,
        "label": ROLE_LABELS.get(role_id, role_id),
        "active": True,
        "system": True,
        "permissions": default_permissions(role_id),
        "see_all_dossiers_default": default_see_all_dossiers(role_id),
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
    }


async def ensure_roles_seeded(db) -> dict:
    """Insère les 4 rôles s'ils manquent. Ne réécrit pas un rôle déjà présent.

    Pose ``system: true`` sur les 4 ids seedés s'il manque (idempotent).
    Retourne ``{created, skipped, role_ids, system_flags_set}``. Journal optionnel si au moins un insert.
    """
    created = 0
    skipped = 0
    system_flags_set = 0
    now = datetime.now(timezone.utc).isoformat()
    for role_id in ROLES:
        existing = await db[ROLES_COLLECTION].find_one({"id": role_id}, {"_id": 1, "system": 1, "label": 1})
        if existing:
            skipped += 1
            patch: Dict[str, Any] = {}
            if not existing.get("system"):
                patch["system"] = True
            # Aligner les libellés Phase 3 sans toucher aux permissions.
            wanted_label = ROLE_LABELS.get(role_id)
            if wanted_label and existing.get("label") != wanted_label:
                patch["label"] = wanted_label
            if patch:
                patch["updated_at"] = now
                await db[ROLES_COLLECTION].update_one({"id": role_id}, {"$set": patch})
                system_flags_set += 1
            continue
        await db[ROLES_COLLECTION].insert_one(role_seed_document(role_id, updated_at=now))
        created += 1
    if created:
        try:
            from access_policy_journal import log_access_event

            await log_access_event(
                db,
                event_type="roles_seed",
                detail={"created": created, "skipped": skipped, "role_ids": list(ROLES)},
            )
        except Exception:
            logging.getLogger("access_control").warning(
                "Journal roles_seed indisponible (seed OK : created=%s)", created
            )
    return {
        "created": created,
        "skipped": skipped,
        "role_ids": list(ROLES),
        "system_flags_set": system_flags_set,
    }


def merge_phase2_permission_keys(
    stored: Optional[dict],
    *,
    manage: bool,
) -> Tuple[Dict[str, bool], bool]:
    """Ajoute les clés Phase 2 manquantes (héritage users.manage). Retourne (perms, changed)."""
    perms = dict(stored) if isinstance(stored, dict) else {}
    changed = False
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        if key not in perms:
            perms[key] = bool(manage)
            changed = True
    if PERM_ROLES_MANAGE not in perms:
        perms[PERM_ROLES_MANAGE] = False
        changed = True
    return perms, changed


async def backfill_phase2_admin_module_permissions(db) -> dict:
    """Backfill snapshots users + templates roles : users.manage → flags Phase 2.

    Idempotent : n'écrit que les clés absentes. ``roles.manage`` seeded false.
    Retourne ``{users_updated, roles_updated}``.
    """
    users_updated = 0
    roles_updated = 0
    now = datetime.now(timezone.utc).isoformat()

    users_coll = db.users
    cursor = users_coll.find({}, {"_id": 1, "user_id": 1, "permissions": 1, "role": 1, "can_manage_users": 1})
    async for doc in cursor:
        stored = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
        if PERM_USERS_MANAGE in stored:
            manage = bool(stored[PERM_USERS_MANAGE])
        else:
            manage = bool(doc.get("can_manage_users")) or doc.get("role") == ROLE_ADMIN
        merged, changed = merge_phase2_permission_keys(stored, manage=manage)
        if not changed:
            continue
        if PERM_USERS_MANAGE not in merged and manage:
            merged[PERM_USERS_MANAGE] = True
        filter_q = {"_id": doc["_id"]} if doc.get("_id") is not None else {"user_id": doc.get("user_id")}
        await users_coll.update_one(
            filter_q,
            {"$set": {"permissions": merged, "permissions_phase2_backfill_at": now}},
        )
        users_updated += 1

    roles_coll = db[ROLES_COLLECTION]
    role_cursor = roles_coll.find({}, {"_id": 1, "id": 1, "permissions": 1})
    async for doc in role_cursor:
        stored = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
        if PERM_USERS_MANAGE in stored:
            manage = bool(stored[PERM_USERS_MANAGE])
        else:
            manage = doc.get("id") == ROLE_ADMIN
        merged, changed = merge_phase2_permission_keys(stored, manage=manage)
        if not changed:
            continue
        filter_q = {"_id": doc["_id"]} if doc.get("_id") is not None else {"id": doc.get("id")}
        await roles_coll.update_one(
            filter_q,
            {"$set": {"permissions": merged, "updated_at": now}},
        )
        roles_updated += 1

    if users_updated or roles_updated:
        try:
            from access_policy_journal import log_access_event

            await log_access_event(
                db,
                event_type="permissions_phase2_backfill",
                detail={"users_updated": users_updated, "roles_updated": roles_updated},
            )
        except Exception:
            logging.getLogger("access_control").warning(
                "Journal phase2 backfill indisponible (backfill OK : users=%s roles=%s)",
                users_updated,
                roles_updated,
            )
    return {"users_updated": users_updated, "roles_updated": roles_updated}


def merge_phase3_roles_manage_key(
    stored: Optional[dict],
    *,
    users_manage: bool,
) -> Tuple[Dict[str, bool], bool]:
    """Backfill ``roles.manage`` : true seulement si ``users.manage`` déjà true.

    Idempotent. N'accorde pas d'autres flags sensibles. Si ``users.manage`` false,
    pose ``roles.manage=false`` uniquement lorsque la clé est absente.
    """
    perms = dict(stored) if isinstance(stored, dict) else {}
    changed = False
    if users_manage:
        if perms.get(PERM_ROLES_MANAGE) is not True:
            perms[PERM_ROLES_MANAGE] = True
            changed = True
    elif PERM_ROLES_MANAGE not in perms:
        perms[PERM_ROLES_MANAGE] = False
        changed = True
    return perms, changed


async def backfill_phase3_roles_manage(db) -> dict:
    """Backfill ``roles.manage=true`` pour users/rôles ayant déjà ``users.manage=true``.

    Ne touche pas les non-admins (users.manage false). Idempotent.
    Retourne ``{users_updated, roles_updated}``.
    """
    users_updated = 0
    roles_updated = 0
    now = datetime.now(timezone.utc).isoformat()

    users_coll = db.users
    cursor = users_coll.find({}, {"_id": 1, "user_id": 1, "permissions": 1, "role": 1, "can_manage_users": 1})
    async for doc in cursor:
        stored = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
        if PERM_USERS_MANAGE in stored:
            manage = bool(stored[PERM_USERS_MANAGE])
        else:
            manage = bool(doc.get("can_manage_users")) or doc.get("role") == ROLE_ADMIN
        merged, changed = merge_phase3_roles_manage_key(stored, users_manage=manage)
        if not changed:
            continue
        filter_q = {"_id": doc["_id"]} if doc.get("_id") is not None else {"user_id": doc.get("user_id")}
        await users_coll.update_one(
            filter_q,
            {"$set": {"permissions": merged, "permissions_phase3_backfill_at": now}},
        )
        users_updated += 1

    roles_coll = db[ROLES_COLLECTION]
    role_cursor = roles_coll.find({}, {"_id": 1, "id": 1, "permissions": 1})
    async for doc in role_cursor:
        stored = doc.get("permissions") if isinstance(doc.get("permissions"), dict) else {}
        if PERM_USERS_MANAGE in stored:
            manage = bool(stored[PERM_USERS_MANAGE])
        else:
            manage = doc.get("id") == ROLE_ADMIN
        merged, changed = merge_phase3_roles_manage_key(stored, users_manage=manage)
        if not changed:
            continue
        filter_q = {"_id": doc["_id"]} if doc.get("_id") is not None else {"id": doc.get("id")}
        await roles_coll.update_one(
            filter_q,
            {"$set": {"permissions": merged, "updated_at": now}},
        )
        roles_updated += 1

    if users_updated or roles_updated:
        try:
            from access_policy_journal import log_access_event

            await log_access_event(
                db,
                event_type="permissions_phase3_backfill",
                detail={"users_updated": users_updated, "roles_updated": roles_updated},
            )
        except Exception:
            logging.getLogger("access_control").warning(
                "Journal phase3 backfill indisponible (backfill OK : users=%s roles=%s)",
                users_updated,
                roles_updated,
            )
    return {"users_updated": users_updated, "roles_updated": roles_updated}


def resolve_effective_permissions(
    doc: dict,
    *,
    role_template: Optional[Dict[str, bool]] = None,
) -> Dict[str, bool]:
    """Résolution effective RBAC — accès effectif inchangé vs Phase 1 pour les 4 modules admin.

    Ordre :
    1. Template rôle (``default_permissions`` / seed ``roles`` / ``role_template``)
    2. Snapshot ``user.permissions`` s'il est présent (compat UI actuelle)
    3. Overlay ``permission_overrides`` (champ préparé Phase 4 ; vide = no-op)
    4. Héritage Phase 2 : clés admin absentes du snapshot → calquer ``users.manage``
    5. Règles système non contournables (LAMal owner / Alberto)

    Les clés hors ``LEGACY_PERMISSION_KEYS`` ne sont pas injectées ici :
    ``has_perm`` les refuse (deny-by-default nouvelles clés).
    """
    role = doc.get("role") or ROLE_CONSEILLER
    template_role = role if role in ROLES else ROLE_CONSEILLER
    if role_template is not None:
        perms = sanitize_permissions(role_template, template_role)
    else:
        perms = default_permissions(template_role)

    stored = doc.get("permissions")
    if isinstance(stored, dict) and stored:
        for key in PERMISSION_KEYS:
            if key in stored:
                perms[key] = bool(stored[key])
        perms[PERM_LAMAL_MODULE_ACCESS] = False
    elif doc.get("can_manage_users"):
        perms[PERM_USERS_MANAGE] = True

    overrides = doc.get("permission_overrides")
    if isinstance(overrides, dict) and overrides:
        for key in PERMISSION_KEYS:
            if key in overrides:
                perms[key] = bool(overrides[key])
        # LAMal reste non assignable via override utilisateur.
        perms[PERM_LAMAL_MODULE_ACCESS] = False

    apply_phase2_users_manage_inheritance(
        perms,
        stored=stored if isinstance(stored, dict) else None,
        overrides=overrides if isinstance(overrides, dict) else None,
    )

    email = (doc.get("email") or "").strip().lower()
    perms[PERM_LAMAL_MODULE_ACCESS] = email == LAMAL_OWNER_EMAIL or is_named_alberto_mendes(doc)
    return perms


def resolve_permissions(doc: dict) -> Dict[str, bool]:
    """Compat historique : délègue à ``resolve_effective_permissions``."""
    return resolve_effective_permissions(doc)


# Phase 4 — origines UI (fiche utilisateur).
PERM_ORIGIN_INHERITED = "inherited"  # Hérité du rôle
PERM_ORIGIN_GRANTED = "granted"  # Accès supplémentaire (override true)
PERM_ORIGIN_REVOKED = "revoked"  # Accès retiré (override false)


def sanitize_permission_overrides(raw: Optional[dict]) -> Dict[str, bool]:
    """Ne conserve que les clés catalogue ; LAMal non assignable via override."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, bool] = {}
    for key in PERMISSION_KEYS:
        if key == PERM_LAMAL_MODULE_ACCESS:
            continue
        if key in raw:
            out[key] = bool(raw[key])
    return out


def prune_redundant_overrides(
    overrides: Optional[dict],
    role_permissions: Dict[str, bool],
) -> Dict[str, bool]:
    """Conserve les overrides qui diffèrent encore du template rôle (changement de rôle)."""
    cleaned = sanitize_permission_overrides(overrides)
    out: Dict[str, bool] = {}
    for key, value in cleaned.items():
        if bool(value) != bool(role_permissions.get(key)):
            out[key] = bool(value)
    return out


def permission_origin_for_key(
    *,
    inherited: bool,
    override: Optional[bool],
) -> str:
    if override is None:
        return PERM_ORIGIN_INHERITED
    if bool(override) == bool(inherited):
        return PERM_ORIGIN_INHERITED
    if bool(override):
        return PERM_ORIGIN_GRANTED
    return PERM_ORIGIN_REVOKED


def build_permissions_rbac_view(
    doc: dict,
    *,
    role_template: Optional[Dict[str, bool]] = None,
) -> dict:
    """Vue héritage / override / effectif pour l'UI (source de vérité backend)."""
    role = doc.get("role") or ROLE_CONSEILLER
    template_role = role if role in ROLES else ROLE_CONSEILLER
    if role_template is not None:
        inherited = sanitize_permissions(role_template, template_role)
    else:
        inherited = default_permissions(template_role)

    overrides = sanitize_permission_overrides(doc.get("permission_overrides"))
    # Doc simulé avec template explicite pour l'effectif (rôles custom Mongo).
    effective = resolve_effective_permissions(
        {**doc, "permission_overrides": overrides},
        role_template=inherited,
    )
    origins: Dict[str, str] = {}
    for key in PERMISSION_KEYS:
        ov: Optional[bool] = overrides[key] if key in overrides else None
        origins[key] = permission_origin_for_key(
            inherited=bool(inherited.get(key)),
            override=ov,
        )
    return {
        "role_permissions": inherited,
        "permission_overrides": overrides,
        "permission_origins": origins,
        "permissions_effective": effective,
    }


def resolve_see_all_dossiers(doc: dict) -> bool:
    if "see_all_dossiers" in doc and doc.get("see_all_dossiers") is not None:
        return bool(doc.get("see_all_dossiers"))
    return default_see_all_dossiers(doc.get("role") or ROLE_CONSEILLER)


def clamp_see_all_dossiers_for_access_policy(
    *,
    role: str,
    see_all_dossiers: bool,
    access_by_account_id_only: bool,
) -> bool:
    """Compte account_id-only : jamais see_all (sinon is_global_viewer court-circuite le strict).

    Les conseillers legacy sans le flag conservent un éventuel see_all explicite.
    """
    if access_by_account_id_only:
        return False
    if role == ROLE_CONSEILLER and force_access_by_account_id_only_on_create(role):
        # Défense en profondeur à la création : nouveau conseiller = pas de vue globale.
        # Ne s'applique ici que si le flag est déjà True (voir appelants).
        pass
    return bool(see_all_dossiers)


def permission_storage_fields(
    role: str,
    permissions: Optional[dict] = None,
    see_all_dossiers: Optional[bool] = None,
    *,
    access_by_account_id_only: bool = False,
) -> dict:
    perms = sanitize_permissions(permissions, role) if permissions is not None else default_permissions(role)
    see_all = default_see_all_dossiers(role) if see_all_dossiers is None else bool(see_all_dossiers)
    see_all = clamp_see_all_dossiers_for_access_policy(
        role=role,
        see_all_dossiers=see_all,
        access_by_account_id_only=access_by_account_id_only,
    )
    return {
        "permissions": perms,
        "see_all_dossiers": see_all,
        "can_manage_users": bool(perms.get(PERM_USERS_MANAGE)),
        "can_manage_settings": bool(perms.get(PERM_USERS_MANAGE)),
    }


def permissions_for_role(role: str) -> dict:
    return permission_storage_fields(role)


def user_from_doc(doc: dict) -> User:
    role = doc.get("role") or ROLE_CONSEILLER
    # Conserver les rôles custom Phase 3 ; Alberto reste forcé admin.
    named_admin = is_named_alberto_mendes(doc)
    if named_admin:
        role = ROLE_ADMIN
    perms = resolve_permissions({**doc, "role": role})
    if named_admin:
        perms[PERM_USERS_MANAGE] = True
        for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
            perms[key] = True
        # Bootstrap Alberto : même capacité rôles que users.manage.
        perms[PERM_ROLES_MANAGE] = True
        perms[PERM_LAMAL_MODULE_ACCESS] = True
    prenom = doc.get("prenom") or ""
    nom = doc.get("nom") or ""
    name = doc.get("name") or display_name(prenom, nom) or doc.get("email", "")
    conseiller = doc.get("conseiller")
    if role == ROLE_CONSEILLER and not conseiller:
        conseiller = name
    see_source = {**doc, "role": role}
    if named_admin:
        see_source["see_all_dossiers"] = True
    return User(
        user_id=TENANT_USER_ID,
        account_id=doc["user_id"],
        email=doc["email"],
        name=name,
        prenom=prenom,
        nom=nom,
        telephone=doc.get("telephone"),
        picture=doc.get("picture"),
        role=role,
        conseiller=conseiller,
        finma_number=(doc.get("finma_number") or "").strip() or None,
        active=doc.get("active", True) is not False,
        can_manage_users=bool(perms.get(PERM_USERS_MANAGE)),
        can_manage_settings=bool(perms.get(PERM_USERS_MANAGE)),
        see_all_dossiers=resolve_see_all_dossiers(see_source),
        access_by_account_id_only=bool(doc.get("access_by_account_id_only")),
        permissions=perms,
    )


def public_user(doc: dict, *, role_doc: Optional[dict] = None) -> dict:
    u = user_from_doc(doc)
    role_template = None
    role_label = ROLE_LABELS.get(u.role, u.role)
    if isinstance(role_doc, dict):
        if role_doc.get("label"):
            role_label = str(role_doc.get("label"))
        if isinstance(role_doc.get("permissions"), dict) and role_doc.get("permissions"):
            role_template = role_doc.get("permissions")
    view = build_permissions_rbac_view(doc, role_template=role_template)
    # Effectif : préféer la vue (template Mongo) si fournie ; sinon user_from_doc.
    effective = view["permissions_effective"] if role_template is not None else u.permissions
    return {
        "user_id": u.account_id,
        "account_id": u.account_id,
        "email": u.email,
        "name": u.name,
        "prenom": u.prenom,
        "nom": u.nom,
        "telephone": u.telephone,
        "picture": u.picture,
        "role": u.role,
        "role_label": role_label,
        "conseiller": u.conseiller,
        "finma_number": (doc.get("finma_number") or "").strip() or None,
        "entreprise_id": (doc.get("entreprise_id") or "").strip() or None,
        "entreprise_nom": doc.get("entreprise_nom"),
        "entreprise_finma": doc.get("entreprise_finma"),
        "must_set_password": bool(doc.get("must_set_password")),
        "activation_pending": bool(
            doc.get("activation_pending") or doc.get("must_set_password")
        ),
        "active": u.active,
        "can_manage_users": bool(effective.get(PERM_USERS_MANAGE)),
        "can_manage_settings": bool(effective.get(PERM_USERS_MANAGE)),
        "see_all_dossiers": u.see_all_dossiers,
        "access_by_account_id_only": u.access_by_account_id_only,
        "permissions": effective,
        # Phase 4 — héritage vs exceptions (indépendant de see_all_dossiers / dual-strict).
        "role_permissions": view["role_permissions"],
        "permission_overrides": view["permission_overrides"],
        "permission_origins": view["permission_origins"],
        "receive_conseiller_rappel_copies": bool(doc.get("receive_conseiller_rappel_copies")),
        "created_at": doc.get("created_at"),
    }


def is_global_viewer(user: User) -> bool:
    return bool(getattr(user, "see_all_dossiers", False))


def force_access_by_account_id_only_on_create(role: str) -> bool:
    """Nouveaux conseillers : uniquement dossiers expressément attribués (account_id)."""
    return role == ROLE_CONSEILLER


def resolve_access_by_account_id_only_update(
    *,
    current: bool,
    incoming: Optional[bool],
    role: str,
    previous_role: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Retourne (valeur, erreur). False impossible si current=True (verrou nouveaux comptes).

    Un passage de rôle vers conseiller (admin→conseiller, etc.) force le flag comme à la création.
    Les conseillers legacy déjà en place restent à False tant qu'on ne l'active pas.
    """
    if role != ROLE_CONSEILLER:
        # Ne pas effacer un verrou existant lors d'un round-trip de rôle
        # (ex. conseiller→admin→conseiller) si le champ n'est pas explicitement fourni.
        if incoming is None:
            return bool(current), None
        return bool(incoming), None
    became_conseiller = (
        previous_role is not None
        and previous_role != ROLE_CONSEILLER
    )
    # Conseiller
    if current:
        if incoming is False:
            return True, "access_by_account_id_only ne peut pas être désactivé pour ce compte"
        return True, None
    if became_conseiller:
        # Même politique que POST /users : tout nouveau conseiller = account_id only.
        if incoming is False:
            return True, "access_by_account_id_only est obligatoire pour un nouveau conseiller"
        return True, None
    if incoming is True:
        return True, None
    if incoming is False:
        return False, None
    return False, None


def match_account_id_among_users(
    conseiller_label: Optional[str],
    user_docs: Iterable[dict],
) -> Optional[str]:
    """Retourne l'account_id si un seul compte conseiller correspond au libellé ; sinon None."""
    label = (conseiller_label or "").strip()
    if not label:
        return None
    matches: List[str] = []
    for doc in user_docs or []:
        if not isinstance(doc, dict):
            continue
        if doc.get("active") is False:
            continue
        role = (doc.get("role") or "").strip() or ROLE_CONSEILLER
        # Comptes avec libellé conseiller (y compris admin qui a un nom d'agent)
        candidate_labels = [
            doc.get("conseiller"),
            doc.get("name"),
            display_name(doc.get("prenom") or "", doc.get("nom") or ""),
        ]
        if not any(conseiller_labels_match(label, cand) for cand in candidate_labels if cand):
            continue
        # Préférer les vrais rôles conseiller ; un admin homonyme ne doit pas voler l'attribution
        if role != ROLE_CONSEILLER and role not in (ROLE_ADMIN, ROLE_CEO, ROLE_GESTIONNAIRE_OFFRES):
            continue
        if role != ROLE_CONSEILLER:
            continue
        aid = str(doc.get("user_id") or doc.get("account_id") or "").strip()
        if aid and aid not in matches:
            matches.append(aid)
    if len(matches) == 1:
        return matches[0]
    return None


def resolve_conseiller_account_id_for_write(
    user: "User",
    conseiller_label: Optional[str],
    *,
    matched_account_id: Optional[str] = None,
) -> Optional[str]:
    """Account_id à persister avec le libellé conseiller lors d'une écriture dossier.

    - Conseiller (sans see_all) : toujours son propre account_id.
    - Superviseur : account_id du conseiller désigné s'il est résolu de façon unique.
    - Libellé vide / pas de match : None (conserve le mode legacy au nom seul).
    """
    if not is_global_viewer(user):
        aid = str(getattr(user, "account_id", "") or "").strip()
        return aid or None
    if not (conseiller_label or "").strip():
        return None
    matched = str(matched_account_id or "").strip()
    return matched or None


def should_stamp_conseiller_account_id_on_update(
    *,
    user: "User",
    old_conseiller: Optional[str],
    new_conseiller: Optional[str],
    old_account_id: Optional[str],
) -> bool:
    """True s'il faut écrire conseiller_account_id sur cette mise à jour.

    - Conseiller : toujours (réaffirme son account_id).
    - Superviseur : uniquement si le libellé conseiller change (réattribution explicite).
      Un edit sans changement de libellé ne doit jamais toucher un stamp existant.
    """
    if not is_global_viewer(user):
        return True
    old_c = (old_conseiller or "").strip()
    new_c = (new_conseiller or "").strip()
    return old_c != new_c


def decide_conseiller_account_id_on_update(
    *,
    user: "User",
    old_conseiller: Optional[str],
    new_conseiller: Optional[str],
    old_account_id: Optional[str],
    matched_account_id: Optional[str] = None,
) -> tuple[bool, Optional[str], bool]:
    """Décide l'écriture de conseiller_account_id.

    Retourne ``(should_write, new_account_id, is_reattribution)``.

    - Conseiller : write=True, account=soi.
    - Admin, libellé inchangé : write=False (conserve l'existant, même si lookup échouerait).
    - Admin, libellé changé : write=True, account=match unique ou None (réattribution explicite).
    """
    old_aid = str(old_account_id or "").strip() or None
    if not is_global_viewer(user):
        own = str(getattr(user, "account_id", "") or "").strip() or None
        return True, own, False
    old_c = (old_conseiller or "").strip()
    new_c = (new_conseiller or "").strip()
    if old_c == new_c:
        return False, old_aid, False
    matched = str(matched_account_id or "").strip() or None
    if not new_c:
        return True, None, True
    return True, matched, True


def set_runtime_access_mode_override(mode: Optional[str]) -> None:
    """Cache processus pour éviter un round-trip Mongo à chaque requête."""
    global _runtime_access_mode_override
    if mode is None:
        _runtime_access_mode_override = None
        return
    m = str(mode).strip().lower()
    _runtime_access_mode_override = m if m in ("legacy", "dual", "strict") else None


def get_runtime_access_mode() -> str:
    if _runtime_access_mode_override in ("legacy", "dual", "strict"):
        return _runtime_access_mode_override
    return ACCESS_MODE


def effective_access_mode(user: User) -> str:
    """Mode effectif pour ce compte (strict forcé si access_by_account_id_only)."""
    if bool(getattr(user, "access_by_account_id_only", False)):
        return "strict"
    return get_runtime_access_mode()


def client_account_id_matches(user: User, client: dict) -> bool:
    wanted = str(getattr(user, "account_id", "") or "").strip()
    if not wanted:
        return False
    for key in ("conseiller_account_id", "agent_account_id"):
        if str(client.get(key) or "").strip() == wanted:
            return True
    return False


def _missing_field_clause(field: str) -> dict:
    return {
        "$or": [
            {field: {"$exists": False}},
            {field: None},
            {field: ""},
        ]
    }


def _missing_conseiller_account_id_clause() -> dict:
    """Compat : absence de conseiller_account_id seule (tests / scripts)."""
    return _missing_field_clause("conseiller_account_id")


def _missing_account_attribution_clause() -> dict:
    """Pas d'attribution account_id (ni conseiller_account_id ni agent_account_id)."""
    return {
        "$and": [
            _missing_field_clause("conseiller_account_id"),
            _missing_field_clause("agent_account_id"),
        ]
    }


def conseiller_access_mongo_filter(user: User) -> dict:
    """Filtre Mongo dossiers selon ACCESS_MODE / flag compte.

    Aligné sur can_access_client : strict/dual reconnaissent conseiller_account_id
    et agent_account_id. En dual, le fallback nom ne s'applique que si les deux
    champs account_id sont absents.
    """
    mode = effective_access_mode(user)
    account_id = str(getattr(user, "account_id", "") or "").strip()
    if mode == "strict":
        if not account_id:
            return {"conseiller_account_id": "__aucun__"}
        return {
            "$or": [
                {"conseiller_account_id": account_id},
                {"agent_account_id": account_id},
            ]
        }
    if mode == "dual":
        name_scope = conseiller_scope_mongo_filter(user)
        ors: List[dict] = []
        if account_id:
            ors.append({"conseiller_account_id": account_id})
            ors.append({"agent_account_id": account_id})
        ors.append({"$and": [_missing_account_attribution_clause(), name_scope]})
        return {"$or": ors}
    return conseiller_scope_mongo_filter(user)


def _norm_label(value: Optional[str]) -> str:
    from conseiller_identity import normalize_conseiller_key

    return normalize_conseiller_key(value)


# Variantes orthographiques d'une même personne (Excel vs fiche utilisateur).
_CONSEILLER_ALIAS_GROUPS = (
    frozenset({"emric", "emeric"}),
    frozenset({"laugerette", "lauguerette"}),
)

_ACCENT_CLASS = {
    "a": "aAàÀâÂäÄáÁ",
    "c": "cCçÇ",
    "e": "eEéÉèÈêÊëË",
    "i": "iIîÎïÏíÍ",
    "n": "nNñÑ",
    "o": "oOôÔöÖóÓ",
    "u": "uUùÙûÛüÜúÚ",
    "y": "yYÿŸ",
}


def _fold_conseiller_tokens(value: Optional[str]) -> List[str]:
    """Tokens comparables : accents retirés, apostrophes ignorées, ordre conservé."""
    raw = str(value or "")
    for apo in ("'", "’", "`", "´"):
        raw = raw.replace(apo, "")
    key = _norm_label(raw)
    return [t for t in key.split(" ") if t]


def _canonical_token(token: str) -> str:
    for group in _CONSEILLER_ALIAS_GROUPS:
        if token in group:
            return min(group)
    return token


def _token_spellings(token: str) -> List[str]:
    for group in _CONSEILLER_ALIAS_GROUPS:
        if token in group:
            return sorted(group)
    return [token]


def _canonical_token_set(value: Optional[str]) -> frozenset:
    return frozenset(_canonical_token(t) for t in _fold_conseiller_tokens(value))


def conseiller_labels_match(left: Optional[str], right: Optional[str]) -> bool:
    """
    True si deux libellés désignent le même conseiller.
    Accepte la casse, les accents, l'ordre prénom/nom, un nom seul,
    et les graphies connues (Emric / Emeric, Laugerette / Lauguerette).
    """
    a = _canonical_token_set(left)
    b = _canonical_token_set(right)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if not shorter <= longer:
        return False
    if len(shorter) == 1:
        return len(next(iter(shorter))) >= 4
    return True


def _accent_token_regex(token: str) -> str:
    parts: List[str] = []
    for i, ch in enumerate(token):
        if i:
            parts.append(r"['’`´-]?")
        alts = _ACCENT_CLASS.get(ch)
        parts.append(f"[{alts}]" if alts else re.escape(ch))
    return "".join(parts)


def conseiller_names_mongo_regex(labels: List[str]) -> Optional[str]:
    """Regex ancrée : mêmes règles que conseiller_labels_match, côté Mongo."""
    phrases: List[str] = []
    seen = set()

    def add(phrase: str) -> None:
        if phrase and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)

    for label in labels:
        tokens = _fold_conseiller_tokens(label)
        if not tokens:
            continue
        spellings = [_token_spellings(t) for t in tokens]
        for combo in product(*spellings):
            if len(combo) <= 3:
                sequences = permutations(combo)
            else:
                sequences = (combo, tuple(reversed(combo)))
            for seq in sequences:
                add(r"\s+".join(_accent_token_regex(t) for t in seq))
            if len(combo) == 1 and len(combo[0]) >= 4:
                # Compte « Valentin » → fiches « Valentin Lugnier »
                add(_accent_token_regex(combo[0]) + r"(?:\s+\S+)+")
            elif len(combo) >= 2:
                # Compte « Valentin Lugnier » → fiche au prénom ou au nom seul
                for token in combo:
                    if len(token) >= 4:
                        add(_accent_token_regex(token))
    if not phrases:
        return None
    return r"^\s*(?:" + "|".join(phrases) + r")\s*$"


def conseiller_identity_labels(user: User) -> List[str]:
    """Libellés sous lesquels ce compte peut être attribué sur un dossier / offre."""
    labels: List[str] = []
    seen = set()
    for raw in (
        getattr(user, "conseiller", None),
        getattr(user, "name", None),
        display_name(getattr(user, "prenom", None) or "", getattr(user, "nom", None) or ""),
    ):
        label = re.sub(r"\s+", " ", (raw or "").strip())
        key = label.casefold()
        if label and key not in seen:
            seen.add(key)
            labels.append(label)
    return labels


def conseiller_emails(user: User) -> List[str]:
    email = (getattr(user, "email", None) or "").strip()
    return [email] if email and "@" in email else []


def labels_match_conseiller(assigned: Optional[str], user: User) -> bool:
    return any(
        conseiller_labels_match(assigned, label)
        for label in conseiller_identity_labels(user)
    )


def email_matches_conseiller(doc: dict, user: User) -> bool:
    emails = {e.casefold() for e in conseiller_emails(user)}
    if not emails:
        return False
    for key in ("agent_email", "conseiller_email"):
        val = (doc.get(key) or "").strip().casefold()
        if val and val in emails:
            return True
    return False


def conseiller_scope_mongo_filter(user: User) -> dict:
    """
    Filtre Mongo : dossiers / fiches attribués à ce conseiller.
    - conseiller / agent_label : même personne (ordre, accents, graphies connues)
    - agent_email / conseiller_email : e-mail du compte
    Admin/CEO (see_all) ne doivent pas appeler cette fonction.
    """
    ors: List[dict] = []
    name_re = conseiller_names_mongo_regex(conseiller_identity_labels(user))
    if name_re:
        ors.append({"conseiller": {"$regex": name_re, "$options": "i"}})
        ors.append({"agent_label": {"$regex": name_re, "$options": "i"}})
    for email in conseiller_emails(user):
        pattern = f"^{re.escape(email)}$"
        email_re = {"$regex": pattern, "$options": "i"}
        ors.append({"agent_email": email_re})
        ors.append({"conseiller_email": email_re})
    if not ors:
        return {"conseiller": "__aucun__"}
    return {"$or": ors}


def is_named_alberto_mendes(source) -> bool:
    """Reconnaît Alberto Mendes par son nom, sans inventer d'adresse e-mail."""
    from conseiller_identity import normalize_conseiller_key

    if source is None:
        return False
    if isinstance(source, dict):
        prenom = source.get("prenom") or ""
        nom = source.get("nom") or ""
        candidates = (source.get("name"), source.get("conseiller"), f"{prenom} {nom}", f"{nom} {prenom}")
    else:
        prenom = getattr(source, "prenom", "") or ""
        nom = getattr(source, "nom", "") or ""
        candidates = (getattr(source, "name", ""), getattr(source, "conseiller", ""), f"{prenom} {nom}", f"{nom} {prenom}")
    expected = {"alberto", "mendes"}
    for raw in candidates:
        tokens = set(normalize_conseiller_key(raw).split())
        if tokens == expected:
            return True
    return False


def is_lamal_owner(user) -> bool:
    email = ""
    if isinstance(user, dict):
        email = user.get("email") or ""
    else:
        email = getattr(user, "email", "") or ""
    return email.strip().lower() == LAMAL_OWNER_EMAIL or is_named_alberto_mendes(user)


def has_perm(user: User, key: str) -> bool:
    """Vérifie une permission effective.

    Deny-by-default **uniquement** pour les clés hors ``LEGACY_PERMISSION_KEYS``
    (catalogue historique Phase 1). Les clés du catalogue absentes du snapshot
    restent default-allow, comme avant (pas de perte involontaire).
    ``leaves.access`` reste special-case (domaine e-mail).
    """
    from email_domain_access import can_access_leaves_module

    if key == PERM_LAMAL_MODULE_ACCESS:
        return is_lamal_owner(user)
    if key == PERM_LEAVES_ACCESS:
        return can_access_leaves_module(user)
    # Congés : le domaine est exigé même pour un admin hors @agencemendes.ch.
    if key == PERM_LEAVES_MANAGE and not can_access_leaves_module(user):
        return False
    perms = getattr(user, "permissions", None) or {}
    if key in perms:
        return bool(perms[key])
    if key == PERM_USERS_MANAGE:
        return bool(getattr(user, "can_manage_users", False)) or getattr(user, "role", None) == ROLE_ADMIN
    if key == PERM_LEAVES_MANAGE:
        return getattr(user, "role", None) == ROLE_ADMIN
    # Catalogue historique : clé absente du snapshot → allow (legacy).
    if key in LEGACY_PERMISSION_KEYS:
        return True
    # Nouvelle clé / hors catalogue → deny.
    return False


def can_process_offres(user: User) -> bool:
    """Droit de traiter les réponses d'offres (gestionnaire / CEO / admin)."""
    perms = getattr(user, "permissions", None) or {}
    if PERM_DEMANDES_OFFRES_PROCESS in perms:
        return bool(perms[PERM_DEMANDES_OFFRES_PROCESS])
    return getattr(user, "role", None) in (ROLE_ADMIN, ROLE_CEO, ROLE_GESTIONNAIRE_OFFRES)


def can_view_all_offres(user: User) -> bool:
    """Voir toutes les demandes d'offres (pas seulement les siennes)."""
    return can_process_offres(user) or is_global_viewer(user)


def has_any_perm(user: User, keys: Union[str, Tuple[str, ...], List[str]]) -> bool:
    if isinstance(keys, str):
        return has_perm(user, keys)
    return any(has_perm(user, k) for k in keys)


def require_perm(user: User, key: Union[str, Tuple[str, ...], List[str]], detail: str = "Accès non autorisé"):
    if not has_any_perm(user, key):
        raise HTTPException(status_code=403, detail=detail)


def can_access_client(user: User, client: dict) -> bool:
    if is_global_viewer(user):
        return True
    mode = effective_access_mode(user)
    if mode == "strict":
        return client_account_id_matches(user, client)
    if mode == "dual":
        aid = str(client.get("conseiller_account_id") or client.get("agent_account_id") or "").strip()
        if aid:
            return aid == str(getattr(user, "account_id", "") or "").strip()
        # Pas d'account_id : fallback nom (Pascal, BONVESTING, non migrés)
    if labels_match_conseiller(client.get("conseiller"), user):
        return True
    if labels_match_conseiller(client.get("agent_label"), user):
        return True
    if email_matches_conseiller(client, user):
        return True
    return False


def require_admin(user: User):
    if not has_perm(user, PERM_USERS_MANAGE):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")


def require_settings(user: User):
    if not user.can_manage_settings:
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")


def clients_base_query(
    user: User,
    conseiller: Optional[str] = None,
    *,
    for_dossiers: bool = False,
) -> dict:
    """Mongo filter for clients visible to this user.

    Exclut les imports Suivi 3P Excel.
    Si for_dossiers=True : uniquement les dossiers de prévoyance
    (exclut les fiches hub créées depuis Offres / Fiscalité, in_dossiers=False).

    Conseiller (sans see_all) : dossiers selon ACCESS_MODE
    (legacy = nom/e-mail ; dual = account_id ou nom si absent ; strict = account_id).
    """
    q: dict = {
        "user_id": TENANT_USER_ID,
        "source_import": {"$ne": "suivi_3p_excel"},
    }
    if for_dossiers:
        # Legacy (champ absent) + True → visibles ; False → stubs hub hors Kanban
        q["in_dossiers"] = {"$ne": False}
    if not is_global_viewer(user):
        q.update(conseiller_access_mongo_filter(user))
    elif conseiller and conseiller != "all":
        if conseiller == "Non attribué":
            q["$and"] = [{
                "$or": [
                    {"conseiller": {"$exists": False}},
                    {"conseiller": None},
                    {"conseiller": ""},
                    {"conseiller": "Non attribué"},
                ]
            }]
        else:
            # Filtre admin : insensible à la casse pour coller aux libellés stockés
            q["conseiller"] = {"$regex": f"^{re.escape(conseiller.strip())}$", "$options": "i"}
    return q


def force_conseiller_on_write(user: User, conseiller: Optional[str]) -> Optional[str]:
    """Sans vue globale, un utilisateur ne peut attribuer un dossier qu'à lui-même."""
    if not is_global_viewer(user):
        return (user.conseiller or user.name or "").strip()
    return (conseiller or "").strip() or None


def _normalize_api_path(path: str) -> str:
    p = path or "/"
    if p.startswith("/api"):
        p = p[4:] or "/"
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1:
        p = p.rstrip("/")
    return p


# (HTTP methods or None=all, regex on /api-stripped path, required perm or tuple of OR perms or None)
_ROUTE_PERMISSIONS: List[Tuple[Optional[Tuple[str, ...]], str, Optional[Union[str, Tuple[str, ...]]]]] = [
    (None, r"^/auth(/|$)", None),
    (None, r"^/lamal(/|$)", PERM_LAMAL_MODULE_ACCESS),
    (("GET",), r"^/$", None),
    (("GET",), r"^/dashboard(/|$)", None),
    (("GET",), r"^/analyses-prevoyance(/|$)", PERM_ANALYSES_VIEW),
    (("GET",), r"^/analyses-prevoyance/[^/]+/report$", PERM_ANALYSES_VIEW),
    (("GET",), r"^/analyses-prevoyance/[^/]+/pdf$", PERM_ANALYSES_VIEW),
    (("GET",), r"^/analyses-prevoyance/[^/]+/versions$", PERM_ANALYSES_VIEW),
    (("POST",), r"^/analyses-prevoyance(/|$)", PERM_ANALYSES_EDIT),
    (("PUT",), r"^/analyses-prevoyance/", PERM_ANALYSES_EDIT),
    (("POST",), r"^/analyses-prevoyance/[^/]+/", PERM_ANALYSES_EDIT),
    (("DELETE",), r"^/analyses-prevoyance/", PERM_ANALYSES_EDIT),
    (("GET",), r"^/comparatifs-rentes(/|$)", PERM_ANALYSES_VIEW),
    (("POST",), r"^/comparatifs-rentes(/|$)", PERM_ANALYSES_EDIT),
    (("PUT",), r"^/comparatifs-rentes/", PERM_ANALYSES_EDIT),
    (("POST",), r"^/comparatifs-rentes/[^/]+/", PERM_ANALYSES_EDIT),
    (("DELETE",), r"^/comparatifs-rentes/", PERM_ANALYSES_EDIT),
    (None, r"^/users/conseillers$", None),
    (None, r"^/users", PERM_USERS_MANAGE),
    (None, r"^/users-import(/|$)", PERM_USERS_MANAGE),
    # Phase 3 — admin Rôles et permissions (toutes méthodes).
    (None, r"^/roles(/|$)", PERM_ROLES_MANAGE),
    # Entreprises : droits fins Phase 2 (avant le catch-all admin).
    (("POST",), r"^/entreprises/ensure-agence-mendes$", PERM_ENTREPRISES_CREATE),
    (("GET",), r"^/entreprises", PERM_ENTREPRISES_VIEW),
    (("POST",), r"^/entreprises$", PERM_ENTREPRISES_CREATE),
    (("POST",), r"^/entreprises/", PERM_ENTREPRISES_UPDATE),
    (("PUT",), r"^/entreprises/", PERM_ENTREPRISES_UPDATE),
    (None, r"^/access-policy", PERM_USERS_MANAGE),
    # Tech status / messagerie admin : avant le catch-all /admin → users.manage.
    (None, r"^/admin/tech-status", PERM_SUIVI_TECHNIQUE_VIEW),
    (("GET",), r"^/admin/email-logs$", PERM_MESSAGERIE_VIEW),
    (None, r"^/admin(/|$)", PERM_USERS_MANAGE),
    (("GET",), r"^/rappel-email-logs$", PERM_MESSAGERIE_VIEW),
    (("GET",), r"^/clients/[^/]+/documents", PERM_DOCUMENTS_VIEW),
    (("POST",), r"^/clients/[^/]+/documents", PERM_DOCUMENTS_ADD),
    (("POST",), r"^/clients/[^/]+/offres/", PERM_DOCUMENTS_VIEW),
    (("GET",), r"^/clients/[^/]+/avs-caisse$", (PERM_CLIENTS_VIEW, PERM_DOSSIERS_VIEW, PERM_DOCUMENTS_VIEW)),
    (("PUT",), r"^/clients/[^/]+/avs-caisse$", (PERM_CLIENTS_EDIT, PERM_DOSSIERS_EDIT, PERM_DOCUMENTS_ADD)),
    (("POST",), r"^/clients/[^/]+/generate-", PERM_DOCUMENTS_ADD),
    (("POST",), r"^/clients/[^/]+/parse-", PERM_DOCUMENTS_ADD),
    (("POST",), r"^/clients/[^/]+/reparse-", PERM_DOCUMENTS_ADD),
    (("GET",), r"^/documents/", PERM_DOCUMENTS_VIEW),
    (("DELETE",), r"^/documents/", PERM_DOCUMENTS_DELETE),
    (("GET",), r"^/document-templates$", PERM_DOCUMENTS_VIEW),
    (("GET",), r"^/demand-packs$", (PERM_DOSSIERS_VIEW, PERM_DOCUMENTS_VIEW)),
    # Congés : domaine @agencemendes.ch pour tout le module ; leaves.manage pour les décisions RH.
    (None, r"^/leaves/admin(/|$)", PERM_LEAVES_MANAGE),
    (("GET",), r"^/leaves/employees$", PERM_LEAVES_MANAGE),
    (("POST",), r"^/leaves/[^/]+/(approve|reject|resolve-cancellation)$", PERM_LEAVES_MANAGE),
    (None, r"^/leaves(/|$)", PERM_LEAVES_ACCESS),
    (None, r"^/notifications/conges(/|$)", PERM_LEAVES_ACCESS),
    # Éligibilité : création de liste vérifiée dans le handler (ELIGIBILITY_MANAGER_USER_ID).
    (("GET",), r"^/eligibility(/|$)", (PERM_CLIENTS_VIEW, PERM_DOSSIERS_VIEW)),
    (("GET",), r"^/clients/[^/]+/eligibility$", (PERM_CLIENTS_VIEW, PERM_DOSSIERS_VIEW)),
    (("PUT", "DELETE"), r"^/clients/[^/]+/eligibility/[^/]+$", (PERM_CLIENTS_EDIT, PERM_DOSSIERS_EDIT)),
    (("GET",), r"^/clients/[^/]+/notes$", PERM_CLIENTS_VIEW),
    (("POST",), r"^/clients/[^/]+/notes$", PERM_CLIENTS_EDIT),
    (("PATCH",), r"^/clients/[^/]+/notes/", PERM_CLIENTS_EDIT),
    (("GET",), r"^/clients/[^/]+/journal$", (PERM_CLIENTS_VIEW, PERM_DOSSIERS_VIEW)),
    (("POST",), r"^/clients/[^/]+/journal$", PERM_CLIENTS_EDIT),
    (("PATCH",), r"^/clients/[^/]+/journal/", PERM_CLIENTS_EDIT),
    (("DELETE",), r"^/clients/[^/]+/journal/", PERM_CLIENTS_EDIT),
    (("GET",), r"^/clients/[^/]+/actions$", (PERM_CLIENTS_VIEW, PERM_DOSSIERS_VIEW)),
    (("GET",), r"^/clients/[^/]+/demandes$", PERM_RAPPELS_VIEW),
    (("GET",), r"^/clients/[^/]+/rappels$", PERM_RAPPELS_VIEW),
    (("POST",), r"^/clients/[^/]+/demandes$", PERM_RAPPELS_EDIT),
    (("POST",), r"^/clients/[^/]+/rappels$", PERM_RAPPELS_EDIT),
    (("GET",), r"^/demandes$", PERM_RAPPELS_VIEW),
    (("GET",), r"^/rappels/email-status$", PERM_RAPPELS_VIEW),
    (("GET",), r"^/rappels/mine$", PERM_RAPPELS_VIEW),
    (("GET",), r"^/rappels$", PERM_RAPPELS_VIEW),
    (("POST",), r"^/rappels$", PERM_RAPPELS_EDIT),
    (("PATCH",), r"^/demandes/", PERM_RAPPELS_EDIT),
    (("PATCH",), r"^/rappels/", PERM_RAPPELS_EDIT),
    (("POST",), r"^/rappels/", PERM_RAPPELS_EDIT),
    (("DELETE",), r"^/demandes/", PERM_RAPPELS_EDIT),
    (("DELETE",), r"^/rappels/", PERM_RAPPELS_EDIT),
    (("GET",), r"^/notifications/rappels$", PERM_RAPPELS_VIEW),
    (("GET",), r"^/notifications/offres$", PERM_DEMANDES_OFFRES_VIEW),
    (("POST",), r"^/notifications/offres/", PERM_DEMANDES_OFFRES_VIEW),
    (("POST",), r"^/clients/[^/]+/create-spouse$", (PERM_CLIENTS_CREATE, PERM_DOSSIERS_EDIT)),
    (("POST",), r"^/clients/[^/]+/echeances-3p", (PERM_CLIENTS_EDIT, PERM_SUIVI_3P_EDIT)),
    (("PATCH",), r"^/clients/[^/]+/echeance", (PERM_CLIENTS_EDIT, PERM_SUIVI_3P_EDIT)),
    (("DELETE",), r"^/clients/[^/]+/echeances-3p", (PERM_CLIENTS_EDIT, PERM_SUIVI_3P_EDIT)),
    (("GET",), r"^/echeances-3p$", (PERM_AGENDA_VIEW, PERM_SUIVI_3P_VIEW, PERM_DOSSIERS_VIEW)),
    (("PATCH",), r"^/clients/[^/]+/statut$", PERM_DOSSIERS_EDIT),
    (("PATCH",), r"^/clients/[^/]+/document-checklist$", PERM_DOSSIERS_EDIT),
    (("GET",), r"^/clients/[^/]+/rapport-imprimer$", (PERM_DOCUMENTS_VIEW, PERM_ANALYSES_VIEW)),
    (("PATCH",), r"^/clients/[^/]+/rapport-imprimer$", (PERM_DOSSIERS_EDIT, PERM_ANALYSES_EDIT)),
    (("POST",), r"^/clients/[^/]+/rapport-imprimer/pdf$", (PERM_DOCUMENTS_VIEW, PERM_ANALYSES_VIEW)),
    (("PATCH",), r"^/clients/[^/]+/lpp-caisse-tracking$", PERM_DOSSIERS_EDIT),
    (("PATCH",), r"^/clients/[^/]+/lpp-funds/person$", PERM_DOSSIERS_EDIT),
    (("DELETE",), r"^/clients/[^/]+$", (PERM_CLIENTS_DELETE, PERM_DOSSIERS_DELETE)),
    (("PUT",), r"^/clients/[^/]+$", PERM_CLIENTS_EDIT),
    (("GET",), r"^/dossiers/", PERM_DOSSIERS_VIEW),
    (("POST",), r"^/clients$", (PERM_CLIENTS_CREATE, PERM_DOSSIERS_CREATE)),
    (("GET",), r"^/clients(/|$)", (PERM_CLIENTS_VIEW, PERM_DOSSIERS_VIEW, PERM_AGENDA_VIEW, PERM_RAPPELS_VIEW, PERM_DEMANDES_OFFRES_VIEW, PERM_SUIVI_3P_VIEW)),
    (("GET",), r"^/suivi-3p/pending-documents", PERM_USERS_MANAGE),
    (("POST",), r"^/suivi-3p/pending-documents", PERM_USERS_MANAGE),
    (("DELETE",), r"^/suivi-3p/pending-documents", PERM_USERS_MANAGE),
    (("GET",), r"^/suivi-3p/documents/", PERM_SUIVI_3P_VIEW),
    (("DELETE",), r"^/suivi-3p/documents/", PERM_SUIVI_3P_EDIT),
    (("POST",), r"^/suivi-3p/courriers", PERM_SUIVI_3P_EDIT),
    (("GET",), r"^/suivi-3p/courriers", PERM_SUIVI_3P_VIEW),
    (("POST",), r"^/suivi-3p/import-addresses$", PERM_USERS_MANAGE),
    (("GET",), r"^/suivi-3p", PERM_SUIVI_3P_VIEW),
    (("POST",), r"^/suivi-3p", PERM_SUIVI_3P_EDIT),
    (("PUT",), r"^/suivi-3p", PERM_SUIVI_3P_EDIT),
    (("PATCH",), r"^/suivi-3p", PERM_SUIVI_3P_EDIT),
    (("DELETE",), r"^/suivi-3p", PERM_SUIVI_3P_EDIT),
    (("GET",), r"^/emails", PERM_MESSAGERIE_VIEW),
    # Quotas d'urgence : administrateur uniquement, avant le GET/PUT générique.
    (("GET",), r"^/demandes-offres/parametres-urgence$", PERM_USERS_MANAGE),
    (("PUT",), r"^/demandes-offres/parametres-urgence$", PERM_USERS_MANAGE),
    (("POST",), r"^/demandes-offres/parametres-urgence/exception$", PERM_USERS_MANAGE),
    (("POST",), r"^/demandes-offres/[^/]+/documents/[^/]+/confirmer-retour$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/suivi$", PERM_DEMANDES_OFFRES_PROCESS),
    # Checklist erreurs : avant le GET générique demandes-offres (sinon view gagne)
    (("GET",), r"^/demandes-offres/[^/]+/erreurs-checklist$", PERM_DEMANDES_OFFRES_PROCESS),
    (("GET",), r"^/demandes-offres/stats/erreurs-agent$", PERM_DEMANDES_OFFRES_VIEW),
    (("GET",), r"^/demandes-offres", PERM_DEMANDES_OFFRES_VIEW),
    # Traitement réservé gestionnaire / CEO / admin (avant le POST générique edit)
    (("POST",), r"^/demandes-offres/[^/]+/incomplete$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/compagnie-incomplete-annuler$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/compagnie-incomplete$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/complete$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/offres-completes$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/offre$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/notes-internes$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/notes-externes$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/complements/[^/]+/reponse$", (PERM_DEMANDES_OFFRES_EDIT, PERM_DEMANDES_OFFRES_PROCESS)),
    (("POST",), r"^/demandes-offres/[^/]+/complements/[^/]+/cloturer$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/erreurs$", PERM_DEMANDES_OFFRES_PROCESS),
    # Retrait d'une erreur : gestionnaire (process) ou admin (users.manage). Avant le DELETE générique.
    (("DELETE",), r"^/demandes-offres/[^/]+/erreurs/[^/]+$", (PERM_DEMANDES_OFFRES_PROCESS, PERM_USERS_MANAGE)),
    (("POST",), r"^/demandes-offres/[^/]+/soumis-compagnie$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/demande-annulee$", PERM_DEMANDES_OFFRES_PROCESS),
    # Créateur (edit) ou gestionnaire (process). Le handler refuse un conseiller tiers.
    (("POST",), r"^/demandes-offres/[^/]+/urgence$", (PERM_DEMANDES_OFFRES_EDIT, PERM_DEMANDES_OFFRES_PROCESS)),
    # Fil de discussion : agent (edit) ou gestionnaire (process). Le handler vérifie l'accès à la demande.
    (("POST",), r"^/demandes-offres/[^/]+/messages$", (PERM_DEMANDES_OFFRES_EDIT, PERM_DEMANDES_OFFRES_PROCESS)),
    (("POST",), r"^/demandes-offres/[^/]+/offre-non-signee$", (PERM_DEMANDES_OFFRES_EDIT, PERM_DEMANDES_OFFRES_PROCESS)),
    (("POST",), r"^/demandes-offres/[^/]+/annuler$", (PERM_DEMANDES_OFFRES_EDIT, PERM_DEMANDES_OFFRES_PROCESS)),
    (("POST",), r"^/demandes-offres/[^/]+/conclusion$", PERM_DEMANDES_OFFRES_PROCESS),
    # Renvoi admin d'une offre déjà envoyée (même id) — réservé administrateur
    (("POST",), r"^/demandes-offres/[^/]+/renvoyer$", PERM_USERS_MANAGE),
    # Attribution : « M'attribuer » gestionnaire ; réattribution admin / responsable (vérifié dans le handler).
    (("POST",), r"^/demandes-offres/[^/]+/attribuer$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/reattribuer$", (PERM_DEMANDES_OFFRES_PROCESS, PERM_USERS_MANAGE)),
    (("POST",), r"^/demandes-offres", PERM_DEMANDES_OFFRES_EDIT),
    (("PUT",), r"^/demandes-offres", PERM_DEMANDES_OFFRES_EDIT),
    (("PATCH",), r"^/demandes-offres", PERM_DEMANDES_OFFRES_EDIT),
    (("DELETE",), r"^/demandes-offres", PERM_DEMANDES_OFFRES_EDIT),
    (("GET",), r"^/form-library", PERM_FORMULAIRES_VIEW),
    (("POST",), r"^/form-library", PERM_FORMULAIRES_VIEW),
    (("PATCH",), r"^/form-library", PERM_FORMULAIRES_VIEW),
    (("DELETE",), r"^/form-library", PERM_FORMULAIRES_VIEW),
    (("GET",), r"^/appointments$", PERM_AGENDA_VIEW),
    (("POST",), r"^/appointments$", PERM_AGENDA_VIEW),
    (("PATCH",), r"^/appointments/", PERM_AGENDA_VIEW),
    (("DELETE",), r"^/appointments/", PERM_AGENDA_VIEW),
    (("GET",), r"^/tasks$", PERM_AGENDA_VIEW),
    (("POST",), r"^/tasks$", PERM_AGENDA_VIEW),
    (("PATCH",), r"^/tasks/", PERM_AGENDA_VIEW),
    (("DELETE",), r"^/tasks/", PERM_AGENDA_VIEW),
]


def permission_for_request(method: str, path: str) -> Optional[Union[str, Tuple[str, ...]]]:
    """Permission required for this API call, or None if auth alone is enough."""
    method = (method or "GET").upper()
    normalized = _normalize_api_path(path)
    for methods, pattern, perm in _ROUTE_PERMISSIONS:
        if methods and method not in methods:
            continue
        if re.search(pattern, normalized):
            return perm
    return None


def enforce_route_permission(user: User, method: str, path: str):
    required = permission_for_request(method, path)
    if required:
        require_perm(user, required)


async def create_session(db, account_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": account_id,
        "session_token": token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return token


async def resolve_session_user(db, request: Request, authorization: Optional[str]) -> User:
    token = request.cookies.get("session_token")
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")

    cached = _session_cache_get(token)
    if cached is not None:
        return cached

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Session invalide")

    expires = session.get("expires_at")
    if expires:
        try:
            exp = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < datetime.now(timezone.utc):
                await db.user_sessions.delete_one({"session_token": token})
                invalidate_session_user_cache(token)
                raise HTTPException(status_code=401, detail="Session expirée")
        except HTTPException:
            raise
        except Exception:
            pass

    doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    if doc.get("active") is False:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    user = user_from_doc(doc)
    _session_cache_put(token, user)
    return user


async def ensure_bootstrap_admin(db):
    """Ensure the configured admin account exists and can log in."""
    email = (os.environ.get("ADMIN_EMAIL") or "cdemirtas@agencemendes.ch").strip().lower()
    default_password = "Mendes2026!"
    password = os.environ.get("ADMIN_PASSWORD") or default_password
    on_railway = bool(
        (os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_ID") or "").strip()
    )
    if password == default_password:
        msg = (
            "ADMIN_PASSWORD utilise la valeur par defaut du code — "
            "definir ADMIN_PASSWORD dans les variables d'environnement (obligatoire en production)."
        )
        log = logging.getLogger("access_control")
        if on_railway:
            log.critical(msg)
        else:
            log.warning(msg)
    prenom = os.environ.get("ADMIN_PRENOM") or "Cemile"
    nom = os.environ.get("ADMIN_NOM") or "Demirtas"
    bootstrap_version = "admin-v2-cdemirtas"

    await db.users.update_many(
        {"role": {"$exists": False}},
        {"$set": {"role": ROLE_CONSEILLER}},
    )

    doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not doc:
        legacy = await db.users.find_one({"email": "admin@prevoyancecrm.local"}, {"_id": 0})
        if legacy:
            await db.users.update_one(
                {"user_id": legacy["user_id"]},
                {"$set": {"email": email}},
            )
            doc = await db.users.find_one({"email": email}, {"_id": 0})

    fields = {
        "email": email,
        "role": ROLE_ADMIN,
        "active": True,
        "prenom": prenom,
        "nom": nom,
        "name": display_name(prenom, nom),
        "bootstrap_version": bootstrap_version,
        **permissions_for_role(ROLE_ADMIN),
    }

    if doc:
        updates = dict(fields)
        # Reset password once for this bootstrap version (or if missing)
        if doc.get("bootstrap_version") != bootstrap_version or not doc.get("password_hash"):
            updates["password_hash"] = hash_password(password)
        await db.users.update_one({"user_id": doc["user_id"]}, {"$set": updates})
        return True

    account_id = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": account_id,
        "telephone": None,
        "picture": None,
        "conseiller": None,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **fields,
    })
    return True


async def accessible_client_ids(db, user: User, conseiller: Optional[str] = None) -> List[str]:
    q = clients_base_query(user, conseiller=conseiller)
    rows = await db.clients.find(q, {"id": 1}).to_list(20000)
    return [r["id"] for r in rows]
