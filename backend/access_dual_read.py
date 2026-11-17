"""Helpers dual-read / strict (équivalents à ACCESS_MODE=dual|strict).

Le branchement runtime passe par access_control.can_access_client + ACCESS_MODE.
Ces fonctions restent pour les tests et simulations hors requête HTTP.
"""
from __future__ import annotations

from access_control import (
    can_access_client,
    client_account_id_matches,
    is_global_viewer,
    labels_match_conseiller,
    email_matches_conseiller,
)


def can_access_client_dual_read(user, client: dict) -> bool:
    if is_global_viewer(user):
        return True
    aid = str(client.get("conseiller_account_id") or client.get("agent_account_id") or "").strip()
    if aid:
        return aid == str(getattr(user, "account_id", "") or "").strip()
    if labels_match_conseiller(client.get("conseiller"), user):
        return True
    if labels_match_conseiller(client.get("agent_label"), user):
        return True
    if email_matches_conseiller(client, user):
        return True
    return False


def can_access_client_strict(user, client: dict) -> bool:
    if is_global_viewer(user):
        return True
    return client_account_id_matches(user, client)
