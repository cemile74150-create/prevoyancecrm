"""
Feature flag — import PDF structuré (pré-production).

Activation progressive :
  OFFRE_PDF_STRUCTURED_EXTRACT=admin   (défaut) → admins / ceo / users.manage seulement
  OFFRE_PDF_STRUCTURED_EXTRACT=on      → tous les utilisateurs avec permission édition offres
  OFFRE_PDF_STRUCTURED_EXTRACT=off     → kill-switch immédiat → chemin legacy analyse-pdf

Surcharge runtime optionnelle via Mongo `app_settings` clé `offre_pdf_structured_extract`
(valeur: admin|on|off). Si absente, l'env gouverne.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("server")

SETTINGS_KEY = "offre_pdf_structured_extract"
ENV_KEY = "OFFRE_PDF_STRUCTURED_EXTRACT"
DEFAULT_MODE = "admin"

_VALID = frozenset({"admin", "on", "off", "1", "0", "true", "false", "all"})


def _normalize_mode(raw: Optional[str]) -> str:
    val = (raw or DEFAULT_MODE).strip().lower()
    if val in {"1", "true", "all", "yes"}:
        return "on"
    if val in {"0", "false", "no"}:
        return "off"
    if val in {"admin", "on", "off"}:
        return val
    return DEFAULT_MODE


def env_mode() -> str:
    return _normalize_mode(os.environ.get(ENV_KEY))


async def resolve_mode(db: Any = None) -> str:
    """Lit app_settings puis env. Kill-switch `off` prioritaire si posé en settings."""
    if db is not None:
        try:
            row = await db.app_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0, "value": 1})
            if row and row.get("value") is not None:
                return _normalize_mode(str(row.get("value")))
        except Exception:
            logger.exception("Lecture feature flag PDF structurée impossible — repli env")
    return env_mode()


def mode_sync(db_value: Optional[str] = None) -> str:
    """Version sync (tests / scripts) : db_value optionnel sinon env."""
    if db_value is not None:
        return _normalize_mode(db_value)
    return env_mode()


def user_can_use_structured_extract(user: Any, mode: Optional[str] = None) -> bool:
    """True si le nouvel extract+mapping est actif pour cet utilisateur."""
    m = _normalize_mode(mode) if mode is not None else env_mode()
    if m == "off":
        return False
    if m == "on":
        return True
    # admin
    role = (getattr(user, "role", None) or (user.get("role") if isinstance(user, dict) else None) or "").strip().lower()
    if role in {"admin", "ceo"}:
        return True
    try:
        from access_control import PERM_USERS_MANAGE, has_perm

        return bool(has_perm(user, PERM_USERS_MANAGE))
    except Exception:
        return False


def public_flag_payload(enabled: bool, mode: str) -> dict:
    return {
        "pdf_extract_structured_enabled": bool(enabled),
        "pdf_extract_structured_mode": mode,
        "pdf_extract_structured_env": ENV_KEY,
    }
