"""Activation / réinitialisation MDP — jetons hachés, jamais loggés en clair."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from access_control import hash_password

logger = logging.getLogger(__name__)

COLLECTION = "user_activation_tokens"
DEFAULT_TTL_HOURS = 72
MIN_PASSWORD_LEN = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def generate_provisional_password() -> str:
    """Mot de passe provisoire unique (jamais commun)."""
    # 4 blocs alphanumériques — lisible pour transmission admin unique.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    parts = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return "-".join(parts)


def validate_new_password(password: str) -> Optional[str]:
    p = password or ""
    if len(p) < MIN_PASSWORD_LEN:
        return f"Mot de passe trop court (min. {MIN_PASSWORD_LEN})"
    if p.strip() != p:
        return "Le mot de passe ne doit pas commencer ou finir par un espace"
    return None


async def create_activation_token(
    db,
    *,
    user_id: str,
    purpose: str = "activate",
    ttl_hours: int = DEFAULT_TTL_HOURS,
    created_by: Optional[str] = None,
) -> Tuple[str, dict]:
    """
    Crée un jeton. Retourne (raw_token, meta_sans_secret).
    Invalide les jetons actifs précédents du même purpose pour cet utilisateur.
    """
    purpose = purpose if purpose in ("activate", "reset") else "activate"
    raw = generate_raw_token()
    token_hash = hash_token(raw)
    expires = _now() + timedelta(hours=max(1, int(ttl_hours or DEFAULT_TTL_HOURS)))
    await db[COLLECTION].update_many(
        {"user_id": user_id, "purpose": purpose, "used_at": None},
        {"$set": {"revoked_at": _now_iso()}},
    )
    doc = {
        "id": f"uat_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "purpose": purpose,
        "token_hash": token_hash,
        "expires_at": expires.isoformat(),
        "created_at": _now_iso(),
        "created_by": created_by,
        "used_at": None,
        "revoked_at": None,
    }
    await db[COLLECTION].insert_one(doc)
    meta = {
        "id": doc["id"],
        "user_id": user_id,
        "purpose": purpose,
        "expires_at": doc["expires_at"],
        # Jamais le raw ni le hash dans les réponses journalisées côté appelant
    }
    return raw, meta


async def lookup_valid_token(db, raw_token: str) -> Optional[dict]:
    th = hash_token(raw_token)
    if not th or th == hash_token(""):
        return None
    doc = await db[COLLECTION].find_one(
        {"token_hash": th, "used_at": None, "revoked_at": None},
        {"_id": 0},
    )
    if not doc:
        return None
    try:
        exp = datetime.fromisoformat(str(doc.get("expires_at") or "").replace("Z", "+00:00"))
    except Exception:
        return None
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < _now():
        return None
    return doc


async def consume_token_and_set_password(
    db,
    *,
    raw_token: str,
    new_password: str,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Valide le jeton, pose le MDP, lève must_set_password.
    Retourne (user_public_fields, error_code).
    """
    err = validate_new_password(new_password)
    if err:
        return None, "weak_password"
    tok = await lookup_valid_token(db, raw_token)
    if not tok:
        return None, "invalid_or_expired"
    user_id = tok.get("user_id")
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user or user.get("active") is False:
        return None, "user_inactive"
    await db.users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "password_hash": hash_password(new_password),
                "must_set_password": False,
                "activation_pending": False,
                "password_set_at": _now_iso(),
            }
        },
    )
    await db[COLLECTION].update_one(
        {"id": tok["id"]},
        {"$set": {"used_at": _now_iso()}},
    )
    await db.user_sessions.delete_many({"user_id": user_id})
    fresh = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return fresh, None


def build_activation_link(public_app_url: str, raw_token: str) -> str:
    base = (public_app_url or "").rstrip("/")
    return f"{base}/activer-compte?token={raw_token}"


def activation_email_bodies(*, prenom: str, link: str, expires_hours: int) -> Tuple[str, str, str]:
    name = (prenom or "").strip() or "Bonjour"
    subject = "Activez votre compte LeoSoft"
    text = (
        f"{name},\n\n"
        f"Votre compte LeoSoft est prêt. Définissez votre mot de passe personnel via ce lien "
        f"(valable {expires_hours} h) :\n\n{link}\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n"
    )
    html = (
        f"<p>{name},</p>"
        f"<p>Votre compte LeoSoft est prêt. Cliquez pour définir votre mot de passe personnel "
        f"(lien valable {expires_hours}&nbsp;h)&nbsp;:</p>"
        f'<p><a href="{link}">Activer mon compte</a></p>'
        "<p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.</p>"
    )
    return subject, text, html


async def send_activation_email(
    db,
    *,
    user: dict,
    raw_token: str,
    public_app_url: str,
    expires_hours: int = DEFAULT_TTL_HOURS,
) -> Tuple[bool, Optional[str], str]:
    """
    Envoie l'e-mail d'activation.
    Retourne (ok, error, link) — le link est pour l'admin si SMTP down, jamais journalisé ici.
    """
    from email_service import smtp_configured, send_email

    link = build_activation_link(public_app_url, raw_token)
    subject, text, html = activation_email_bodies(
        prenom=user.get("prenom") or "",
        link=link,
        expires_hours=expires_hours,
    )
    if not smtp_configured():
        logger.info(
            "Activation e-mail non envoyé (SMTP absent) user_id=%s — lien remis à l'admin uniquement",
            user.get("user_id"),
        )
        return False, "smtp_not_configured", link
    # Ne jamais logger le lien ni le jeton
    ok, err = send_email(
        user.get("email") or "",
        subject,
        text,
        body_html=html,
        mail_type="user_activation",
        log_meta={"user_id": user.get("user_id"), "purpose": "activate"},
        persist_log=True,
    )
    # Redacte le corps (contient le lien) dans le journal e-mail si présent.
    if ok:
        try:
            await db.email_logs.update_many(
                {"mail_type": "user_activation", "log_meta.user_id": user.get("user_id")},
                {"$unset": {"body_text": "", "body_html": ""}, "$set": {"body_redacted": True}},
            )
        except Exception:
            pass
    return ok, err, link


def user_needs_activation(doc: Optional[dict]) -> bool:
    if not isinstance(doc, dict):
        return False
    if doc.get("must_set_password") or doc.get("activation_pending"):
        return True
    # Compte créé sans hash (invite)
    if not (doc.get("password_hash") or "").strip():
        return True
    return False
