"""Journalisation des changements de mode d'accès et des attributions account_id."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from access_control import (
    ACCESS_POLICY_JOURNAL,
    ACCESS_POLICY_SETTINGS_KEY,
    get_runtime_access_mode,
    set_runtime_access_mode_override,
)

# Recharge périodique depuis Mongo pour les workers qui n'ont pas reçu le PUT local.
_ACCESS_MODE_RELOAD_SECONDS = 5.0
_last_access_mode_reload_at = 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_access_mode_fresh(db, *, max_age_seconds: float = _ACCESS_MODE_RELOAD_SECONDS) -> str:
    """Recharge app_settings si le cache processus est trop vieux (multi-worker)."""
    global _last_access_mode_reload_at
    now = time.monotonic()
    if (now - _last_access_mode_reload_at) < max_age_seconds and _last_access_mode_reload_at > 0:
        return get_runtime_access_mode()
    mode = await load_access_mode_from_db(db)
    _last_access_mode_reload_at = now
    return mode


async def log_access_event(
    db,
    *,
    event_type: str,
    actor_account_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    detail: Optional[dict] = None,
) -> dict:
    doc = {
        "id": f"ape_{uuid.uuid4().hex[:16]}",
        "event_type": event_type,
        "actor_account_id": actor_account_id,
        "actor_email": actor_email,
        "detail": detail or {},
        "created_at": _now(),
    }
    await db[ACCESS_POLICY_JOURNAL].insert_one(doc)
    return doc


async def load_access_mode_from_db(db) -> str:
    """Charge la surcharge Mongo (sinon env ACCESS_MODE / legacy)."""
    global _last_access_mode_reload_at
    row = await db.app_settings.find_one({"key": ACCESS_POLICY_SETTINGS_KEY}, {"_id": 0})
    mode = (row or {}).get("access_mode")
    if mode in ("legacy", "dual", "strict"):
        set_runtime_access_mode_override(mode)
        _last_access_mode_reload_at = time.monotonic()
        return mode
    set_runtime_access_mode_override(None)
    _last_access_mode_reload_at = time.monotonic()
    return get_runtime_access_mode()


async def set_access_mode(
    db,
    *,
    mode: str,
    actor_account_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    reason: str = "",
) -> dict:
    global _last_access_mode_reload_at
    mode = (mode or "").strip().lower()
    if mode not in ("legacy", "dual", "strict"):
        raise ValueError("mode invalide (legacy|dual|strict)")
    previous = await load_access_mode_from_db(db)
    await db.app_settings.update_one(
        {"key": ACCESS_POLICY_SETTINGS_KEY},
        {
            "$set": {
                "key": ACCESS_POLICY_SETTINGS_KEY,
                "access_mode": mode,
                "updated_at": _now(),
                "updated_by": actor_account_id,
            }
        },
        upsert=True,
    )
    set_runtime_access_mode_override(mode)
    _last_access_mode_reload_at = time.monotonic()
    event = await log_access_event(
        db,
        event_type="access_mode_change",
        actor_account_id=actor_account_id,
        actor_email=actor_email,
        detail={"from": previous, "to": mode, "reason": reason},
    )
    return {"previous": previous, "mode": mode, "event": event}


async def log_attribution_batch(
    db,
    *,
    actor_account_id: Optional[str],
    actor_email: Optional[str],
    summary: dict[str, Any],
) -> dict:
    return await log_access_event(
        db,
        event_type="attribution_migration",
        actor_account_id=actor_account_id,
        actor_email=actor_email,
        detail=summary,
    )


async def log_user_access_flag(
    db,
    *,
    actor_account_id: Optional[str],
    actor_email: Optional[str],
    target_account_id: str,
    access_by_account_id_only: bool,
) -> dict:
    return await log_access_event(
        db,
        event_type="user_access_flag",
        actor_account_id=actor_account_id,
        actor_email=actor_email,
        detail={
            "target_account_id": target_account_id,
            "access_by_account_id_only": access_by_account_id_only,
        },
    )
