"""Auth helpers: roles, passwords, conseiller scoping."""
from __future__ import annotations

import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple, Union

import bcrypt
from fastapi import HTTPException, Request, Header
from pydantic import BaseModel, Field, EmailStr

TENANT_USER_ID = os.environ.get("TENANT_USER_ID", "local-dev")

ROLE_ADMIN = "admin"
ROLE_CEO = "ceo"
ROLE_GESTIONNAIRE_OFFRES = "gestionnaire_offres"
ROLE_CONSEILLER = "conseiller"
ROLES = [ROLE_ADMIN, ROLE_CEO, ROLE_GESTIONNAIRE_OFFRES, ROLE_CONSEILLER]

ROLE_LABELS = {
    ROLE_ADMIN: "Administrateur",
    ROLE_CEO: "CEO / Direction",
    ROLE_GESTIONNAIRE_OFFRES: "Gestionnaire d'offres",
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
PERM_USERS_MANAGE = "users.manage"

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
    PERM_USERS_MANAGE,
]

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
        "label": "Formulaires",
        "items": [
            {"key": PERM_FORMULAIRES_VIEW, "label": "Voir les formulaires"},
        ],
    },
    {
        "id": "users",
        "label": "Administration",
        "items": [
            {"key": PERM_USERS_MANAGE, "label": "Gérer les utilisateurs"},
        ],
    },
]


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
    permissions: Dict[str, bool] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    prenom: str
    nom: str
    email: EmailStr
    telephone: Optional[str] = None
    password: str
    role: str = ROLE_CONSEILLER
    conseiller: Optional[str] = None
    finma_number: Optional[str] = None
    receive_conseiller_rappel_copies: Optional[bool] = False
    see_all_dossiers: Optional[bool] = None
    permissions: Optional[Dict[str, bool]] = None


class UserUpdate(BaseModel):
    prenom: Optional[str] = None
    nom: Optional[str] = None
    email: Optional[EmailStr] = None
    telephone: Optional[str] = None
    role: Optional[str] = None
    conseiller: Optional[str] = None
    finma_number: Optional[str] = None
    active: Optional[bool] = None
    receive_conseiller_rappel_copies: Optional[bool] = None
    see_all_dossiers: Optional[bool] = None
    permissions: Optional[Dict[str, bool]] = None


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
    # Traitement interne des offres : réservé admin / CEO / gestionnaire
    if role == ROLE_CONSEILLER:
        perms[PERM_DEMANDES_OFFRES_PROCESS] = False
    else:
        perms[PERM_DEMANDES_OFFRES_PROCESS] = True
    return perms


def default_see_all_dossiers(role: str) -> bool:
    return role in (ROLE_ADMIN, ROLE_CEO, ROLE_GESTIONNAIRE_OFFRES)


def sanitize_permissions(raw: Optional[dict], role: str) -> Dict[str, bool]:
    base = default_permissions(role)
    if not isinstance(raw, dict):
        return base
    for key in PERMISSION_KEYS:
        if key in raw:
            base[key] = bool(raw[key])
    return base


def resolve_permissions(doc: dict) -> Dict[str, bool]:
    role = doc.get("role") or ROLE_CONSEILLER
    stored = doc.get("permissions")
    if isinstance(stored, dict) and stored:
        perms = sanitize_permissions(stored, role)
    else:
        perms = default_permissions(role)
        if doc.get("can_manage_users"):
            perms[PERM_USERS_MANAGE] = True
    return perms


def resolve_see_all_dossiers(doc: dict) -> bool:
    if "see_all_dossiers" in doc and doc.get("see_all_dossiers") is not None:
        return bool(doc.get("see_all_dossiers"))
    return default_see_all_dossiers(doc.get("role") or ROLE_CONSEILLER)


def permission_storage_fields(
    role: str,
    permissions: Optional[dict] = None,
    see_all_dossiers: Optional[bool] = None,
) -> dict:
    perms = sanitize_permissions(permissions, role) if permissions is not None else default_permissions(role)
    see_all = default_see_all_dossiers(role) if see_all_dossiers is None else bool(see_all_dossiers)
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
    if role not in ROLES:
        role = ROLE_CONSEILLER
    perms = resolve_permissions({**doc, "role": role})
    prenom = doc.get("prenom") or ""
    nom = doc.get("nom") or ""
    name = doc.get("name") or display_name(prenom, nom) or doc.get("email", "")
    conseiller = doc.get("conseiller")
    if role == ROLE_CONSEILLER and not conseiller:
        conseiller = name
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
        see_all_dossiers=resolve_see_all_dossiers({**doc, "role": role}),
        permissions=perms,
    )


def public_user(doc: dict) -> dict:
    u = user_from_doc(doc)
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
        "role_label": ROLE_LABELS.get(u.role, u.role),
        "conseiller": u.conseiller,
        "finma_number": (doc.get("finma_number") or "").strip() or None,
        "active": u.active,
        "can_manage_users": u.can_manage_users,
        "can_manage_settings": u.can_manage_settings,
        "see_all_dossiers": u.see_all_dossiers,
        "permissions": u.permissions,
        "receive_conseiller_rappel_copies": bool(doc.get("receive_conseiller_rappel_copies")),
        "created_at": doc.get("created_at"),
    }


def is_global_viewer(user: User) -> bool:
    return bool(getattr(user, "see_all_dossiers", False))


def _norm_label(value: Optional[str]) -> str:
    from conseiller_identity import normalize_conseiller_key

    return normalize_conseiller_key(value)


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
    target = _norm_label(assigned)
    if not target:
        return False
    return any(_norm_label(label) == target for label in conseiller_identity_labels(user))


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
    - conseiller / agent_label : correspondance insensible à la casse
    - agent_email / conseiller_email : e-mail du compte
    Admin/CEO (see_all) ne doivent pas appeler cette fonction.
    """
    ors: List[dict] = []
    for label in conseiller_identity_labels(user):
        pattern = f"^{re.escape(label)}$"
        ors.append({"conseiller": {"$regex": pattern, "$options": "i"}})
        ors.append({"agent_label": {"$regex": pattern, "$options": "i"}})
    for email in conseiller_emails(user):
        pattern = f"^{re.escape(email)}$"
        email_re = {"$regex": pattern, "$options": "i"}
        ors.append({"agent_email": email_re})
        ors.append({"conseiller_email": email_re})
    if not ors:
        return {"conseiller": "__aucun__"}
    return {"$or": ors}


def has_perm(user: User, key: str) -> bool:
    perms = getattr(user, "permissions", None) or {}
    if key in perms:
        return bool(perms[key])
    if key == PERM_USERS_MANAGE:
        return bool(getattr(user, "can_manage_users", False)) or getattr(user, "role", None) == ROLE_ADMIN
    # Clés absentes (ex. nouveaux modules) : autorisées par défaut, comme le front.
    return True


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

    Conseiller (sans see_all) : tous les dossiers qui lui sont attribués
    (libellé conseiller, casse ignorée, ou e-mail agent), y compris créés par un tiers.
    """
    q: dict = {
        "user_id": TENANT_USER_ID,
        "source_import": {"$ne": "suivi_3p_excel"},
    }
    if for_dossiers:
        # Legacy (champ absent) + True → visibles ; False → stubs hub hors Kanban
        q["in_dossiers"] = {"$ne": False}
    if not is_global_viewer(user):
        q.update(conseiller_scope_mongo_filter(user))
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
    (("GET",), r"^/$", None),
    (("GET",), r"^/dashboard(/|$)", None),
    (None, r"^/users/conseillers$", None),
    (None, r"^/users", PERM_USERS_MANAGE),
    (None, r"^/admin(/|$)", PERM_USERS_MANAGE),
    (("GET",), r"^/rappel-email-logs$", PERM_USERS_MANAGE),
    (("GET",), r"^/clients/[^/]+/documents", PERM_DOCUMENTS_VIEW),
    (("POST",), r"^/clients/[^/]+/documents", PERM_DOCUMENTS_ADD),
    (("POST",), r"^/clients/[^/]+/offres/", PERM_DOCUMENTS_VIEW),
    (("POST",), r"^/clients/[^/]+/generate-", PERM_DOCUMENTS_ADD),
    (("POST",), r"^/clients/[^/]+/parse-", PERM_DOCUMENTS_ADD),
    (("POST",), r"^/clients/[^/]+/reparse-", PERM_DOCUMENTS_ADD),
    (("GET",), r"^/documents/", PERM_DOCUMENTS_VIEW),
    (("DELETE",), r"^/documents/", PERM_DOCUMENTS_DELETE),
    (("GET",), r"^/document-templates$", PERM_DOCUMENTS_VIEW),
    (("GET",), r"^/demand-packs$", (PERM_DOSSIERS_VIEW, PERM_DOCUMENTS_VIEW)),
    (("GET",), r"^/clients/[^/]+/notes$", PERM_CLIENTS_VIEW),
    (("POST",), r"^/clients/[^/]+/notes$", PERM_CLIENTS_EDIT),
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
    (("POST",), r"^/clients/[^/]+/create-spouse$", (PERM_CLIENTS_CREATE, PERM_DOSSIERS_EDIT)),
    (("POST",), r"^/clients/[^/]+/echeances-3p", (PERM_CLIENTS_EDIT, PERM_SUIVI_3P_EDIT)),
    (("PATCH",), r"^/clients/[^/]+/echeance", (PERM_CLIENTS_EDIT, PERM_SUIVI_3P_EDIT)),
    (("DELETE",), r"^/clients/[^/]+/echeances-3p", (PERM_CLIENTS_EDIT, PERM_SUIVI_3P_EDIT)),
    (("GET",), r"^/echeances-3p$", (PERM_AGENDA_VIEW, PERM_SUIVI_3P_VIEW, PERM_DOSSIERS_VIEW)),
    (("PATCH",), r"^/clients/[^/]+/statut$", PERM_DOSSIERS_EDIT),
    (("PATCH",), r"^/clients/[^/]+/document-checklist$", PERM_DOSSIERS_EDIT),
    (("PATCH",), r"^/clients/[^/]+/lpp-caisse-tracking$", PERM_DOSSIERS_EDIT),
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
    (("GET",), r"^/emails", PERM_USERS_MANAGE),
    # Checklist erreurs : avant le GET générique demandes-offres (sinon view gagne)
    (("GET",), r"^/demandes-offres/[^/]+/erreurs-checklist$", PERM_DEMANDES_OFFRES_PROCESS),
    (("GET",), r"^/demandes-offres/stats/erreurs-agent$", PERM_DEMANDES_OFFRES_VIEW),
    (("GET",), r"^/demandes-offres", PERM_DEMANDES_OFFRES_VIEW),
    # Traitement réservé gestionnaire / CEO / admin (avant le POST générique edit)
    (("POST",), r"^/demandes-offres/[^/]+/incomplete$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/complete$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/offres-completes$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/offre$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/notes-internes$", PERM_DEMANDES_OFFRES_PROCESS),
    (("POST",), r"^/demandes-offres/[^/]+/erreurs$", PERM_DEMANDES_OFFRES_PROCESS),
    # Renvoi admin d'une offre déjà envoyée (même id) — réservé administrateur
    (("POST",), r"^/demandes-offres/[^/]+/renvoyer$", PERM_USERS_MANAGE),
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
    return user_from_doc(doc)


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
