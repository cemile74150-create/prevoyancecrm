"""Verrou du conseiller sur une planification.

Un conseiller non administrateur ne peut pas substituer une autre identité,
y compris en réécrivant le JSON envoyé à l'API.
"""

from __future__ import annotations

from typing import Optional

from access_control import ROLE_ADMIN, User


def is_planification_admin(user: User) -> bool:
    return bool(getattr(user, "can_manage_users", False)) or getattr(user, "role", None) == ROLE_ADMIN


def lock_conseiller_nom(incoming, previous: Optional[dict], user: User):
    """Retourne l'input avec conseillerNom autorisé."""
    if not isinstance(incoming, dict):
        return incoming
    data = dict(incoming)
    stored = ""
    if isinstance(previous, dict):
        stored = str(previous.get("conseillerNom") or "").strip()
    own = str(getattr(user, "name", "") or "").strip()
    if is_planification_admin(user):
        chosen = str(data.get("conseillerNom") or "").strip()
        data["conseillerNom"] = chosen or stored or own
        return data
    data["conseillerNom"] = stored or own
    return data
