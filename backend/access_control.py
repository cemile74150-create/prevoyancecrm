"""Auth helpers: roles, passwords, conseiller scoping."""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import bcrypt
from fastapi import HTTPException, Request, Header
from pydantic import BaseModel, Field, EmailStr

TENANT_USER_ID = os.environ.get("TENANT_USER_ID", "local-dev")

ROLE_ADMIN = "admin"
ROLE_CEO = "ceo"
ROLE_CONSEILLER = "conseiller"
ROLES = [ROLE_ADMIN, ROLE_CEO, ROLE_CONSEILLER]

ROLE_LABELS = {
    ROLE_ADMIN: "Administrateur",
    ROLE_CEO: "CEO / Direction",
    ROLE_CONSEILLER: "Conseiller",
}

DEFAULT_CONSEILLERS = [
    "Alberto Mendes",
    "Valentin Lugnier",
    "Emric Laugerette",
    "Tony D'Andrea",
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
    active: bool = True
    can_manage_users: bool = False
    can_manage_settings: bool = False


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


class UserUpdate(BaseModel):
    prenom: Optional[str] = None
    nom: Optional[str] = None
    email: Optional[EmailStr] = None
    telephone: Optional[str] = None
    role: Optional[str] = None
    conseiller: Optional[str] = None
    active: Optional[bool] = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=6)


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


def permissions_for_role(role: str) -> dict:
    return {
        "can_manage_users": role == ROLE_ADMIN,
        "can_manage_settings": role == ROLE_ADMIN,
    }


def user_from_doc(doc: dict) -> User:
    role = doc.get("role") or ROLE_CONSEILLER
    if role not in ROLES:
        role = ROLE_CONSEILLER
    perms = permissions_for_role(role)
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
        active=doc.get("active", True) is not False,
        **perms,
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
        "active": u.active,
        "can_manage_users": u.can_manage_users,
        "can_manage_settings": u.can_manage_settings,
        "created_at": doc.get("created_at"),
    }


def is_global_viewer(user: User) -> bool:
    return user.role in (ROLE_ADMIN, ROLE_CEO)


def can_access_client(user: User, client: dict) -> bool:
    if is_global_viewer(user):
        return True
    if user.role != ROLE_CONSEILLER:
        return False
    assigned = (client.get("conseiller") or "").strip()
    mine = (user.conseiller or "").strip()
    return bool(mine) and assigned == mine


def require_admin(user: User):
    if not user.can_manage_users:
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")


def require_settings(user: User):
    if not user.can_manage_settings:
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")


def clients_base_query(user: User, conseiller: Optional[str] = None) -> dict:
    """Mongo filter for clients visible to this user."""
    q: dict = {"user_id": TENANT_USER_ID}
    if user.role == ROLE_CONSEILLER:
        q["conseiller"] = (user.conseiller or "").strip() or "__aucun__"
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
            q["conseiller"] = conseiller
    return q


def force_conseiller_on_write(user: User, conseiller: Optional[str]) -> Optional[str]:
    """Conseillers cannot assign dossiers to someone else."""
    if user.role == ROLE_CONSEILLER:
        return (user.conseiller or user.name or "").strip()
    return (conseiller or "").strip() or None


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
    """Create default admin if no admin exists."""
    existing = await db.users.find_one({"role": ROLE_ADMIN}, {"_id": 0})
    email = (os.environ.get("ADMIN_EMAIL") or "admin@prevoyancecrm.local").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or "Admin123!"
    prenom = os.environ.get("ADMIN_PRENOM") or "Admin"
    nom = os.environ.get("ADMIN_NOM") or "CRM"

    if existing:
        # Ensure admin has a password if somehow missing
        if not existing.get("password_hash"):
            await db.users.update_one(
                {"user_id": existing["user_id"]},
                {"$set": {"password_hash": hash_password(password), "active": True}},
            )
            return True
        return False

    # Do not mass-disable legacy users — only tag missing role
    await db.users.update_many(
        {"role": {"$exists": False}},
        {"$set": {"role": ROLE_CONSEILLER}},
    )

    still = await db.users.find_one({"email": email}, {"_id": 0})
    if still:
        await db.users.update_one(
            {"email": email},
            {"$set": {
                "role": ROLE_ADMIN,
                "active": True,
                "password_hash": hash_password(password),
                "prenom": still.get("prenom") or prenom,
                "nom": still.get("nom") or nom,
                "name": display_name(still.get("prenom") or prenom, still.get("nom") or nom),
                **permissions_for_role(ROLE_ADMIN),
            }},
        )
        return True

    account_id = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": account_id,
        "email": email,
        "prenom": prenom,
        "nom": nom,
        "name": display_name(prenom, nom),
        "telephone": None,
        "picture": None,
        "role": ROLE_ADMIN,
        "conseiller": None,
        "active": True,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        **permissions_for_role(ROLE_ADMIN),
    })
    return True


async def accessible_client_ids(db, user: User, conseiller: Optional[str] = None) -> List[str]:
    q = clients_base_query(user, conseiller=conseiller)
    rows = await db.clients.find(q, {"id": 1}).to_list(20000)
    return [r["id"] for r in rows]
