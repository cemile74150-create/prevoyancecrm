"""Permissions Demandes d'offres : créer vs traiter."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    PERM_DEMANDES_OFFRES_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
    PERM_DEMANDES_OFFRES_VIEW,
    PERM_USERS_MANAGE,
    User,
    can_process_offres,
    can_view_all_offres,
    default_permissions,
    permission_for_request,
    user_from_doc,
)
from demandes_offres_3p import (  # noqa: E402
    can_access_demande,
    demandes_offres_base_query,
    serialize_demande,
)


def _user(role, **kwargs):
    doc = {
        "user_id": "acc1",
        "email": "x@test.ch",
        "prenom": "Test",
        "nom": "User",
        "name": "Test User",
        "role": role,
        "conseiller": "Test User",
        "active": True,
        **kwargs,
    }
    return user_from_doc(doc)


def test_conseiller_cannot_process_by_default():
    perms = default_permissions(ROLE_CONSEILLER)
    assert perms[PERM_DEMANDES_OFFRES_VIEW] is True
    assert perms[PERM_DEMANDES_OFFRES_EDIT] is True
    assert perms[PERM_DEMANDES_OFFRES_PROCESS] is False
    u = _user(ROLE_CONSEILLER)
    assert can_process_offres(u) is False
    assert can_view_all_offres(u) is False


def test_gestionnaire_and_ceo_can_process():
    assert default_permissions(ROLE_GESTIONNAIRE_OFFRES)[PERM_DEMANDES_OFFRES_PROCESS] is True
    assert default_permissions(ROLE_CEO)[PERM_DEMANDES_OFFRES_PROCESS] is True
    assert default_permissions(ROLE_ADMIN)[PERM_DEMANDES_OFFRES_PROCESS] is True
    assert can_process_offres(_user(ROLE_GESTIONNAIRE_OFFRES)) is True
    assert can_view_all_offres(_user(ROLE_CEO, see_all_dossiers=True)) is True


def test_process_routes_require_process_perm():
    assert permission_for_request("POST", "/api/demandes-offres/abc/incomplete") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/complete") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/offres-completes") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/offre") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/notes-internes") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/erreurs") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/soumis-compagnie") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/envoyer") == PERM_DEMANDES_OFFRES_EDIT
    assert permission_for_request("POST", "/api/demandes-offres/abc/annuler") == PERM_DEMANDES_OFFRES_EDIT
    assert permission_for_request("POST", "/api/demandes-offres/abc/restaurer") == PERM_DEMANDES_OFFRES_EDIT
    assert permission_for_request("POST", "/api/demandes-offres/abc/renvoyer") == PERM_USERS_MANAGE
    assert permission_for_request("GET", "/api/demandes-offres") == PERM_DEMANDES_OFFRES_VIEW


def test_serialize_hides_internal_notes_for_conseiller():
    doc = {
        "id": "d1",
        "statut": "Demande envoyée",
        "notes_internes": [{"note": "secret"}],
        "historique": [
            {"action": "Demande envoyée", "at": "2026-01-01"},
            {"action": "Note interne", "detail": "secret", "at": "2026-01-02"},
        ],
    }
    conseiller = _user(ROLE_CONSEILLER)
    out = serialize_demande(doc, viewer=conseiller)
    assert out["notes_internes"] == []
    assert out["can_process"] is False
    assert all(not str(e.get("action") or "").lower().startswith("note interne") for e in out["historique"])

    gestionnaire = _user(ROLE_GESTIONNAIRE_OFFRES, see_all_dossiers=True)
    out2 = serialize_demande(doc, viewer=gestionnaire)
    assert out2["notes_internes"]
    assert out2["can_process"] is True


def test_conseiller_query_scoped_gestionnaire_sees_all():
    c = _user(ROLE_CONSEILLER)
    q = demandes_offres_base_query(c)
    assert "$or" in q or "created_by_account_id" in q

    g = _user(ROLE_GESTIONNAIRE_OFFRES, see_all_dossiers=True)
    q2 = demandes_offres_base_query(g)
    assert "$or" not in q2
