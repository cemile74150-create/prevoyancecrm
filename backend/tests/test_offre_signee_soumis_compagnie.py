"""Offre signée (proposition PDF) + Soumis à la compagnie (gestionnaire only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    PERM_DEMANDES_OFFRES_PROCESS,
    permission_for_request,
    user_from_doc,
)
from demandes_offres_3p import (  # noqa: E402
    ACTION_SOUMIS_COMPAGNIE,
    DOC_CATEGORY_PROPOSITION_SIGNEE,
    FIELD_SOUMIS_COMPAGNIE,
    STATUT_OFFRE_SIGNEE,
    build_soumis_compagnie_payload,
    can_follow_signature,
    normalize_soumis_compagnie,
    serialize_demande,
)


def _user(role, **kwargs):
    doc = {
        "user_id": kwargs.pop("account_id", "acc1"),
        "email": kwargs.pop("email", "x@test.ch"),
        "prenom": "Test",
        "nom": "User",
        "name": kwargs.pop("name", "Test User"),
        "role": role,
        "conseiller": kwargs.pop("conseiller", "Test User"),
        "active": True,
        **kwargs,
    }
    return user_from_doc(doc)


def test_soumis_compagnie_route_requires_process_perm():
    assert (
        permission_for_request("POST", "/api/demandes-offres/abc/soumis-compagnie")
        == PERM_DEMANDES_OFFRES_PROCESS
    )


def test_doc_category_proposition_signee_label():
    assert DOC_CATEGORY_PROPOSITION_SIGNEE == "Proposition signée"
    assert ACTION_SOUMIS_COMPAGNIE == "Soumis à la compagnie"


def test_normalize_soumis_default_false_not_auto():
    """Signature seule ne doit pas impliquer soumis_compagnie."""
    doc = {
        "statut": STATUT_OFFRE_SIGNEE,
        "signature": {
            "signee": True,
            "signed_by": "Agent",
            "signed_by_id": "a1",
        },
    }
    sc = normalize_soumis_compagnie(doc)
    assert sc["soumis"] is False
    assert sc["at"] is None


def test_normalize_soumis_nested_and_legacy():
    nested = normalize_soumis_compagnie({
        FIELD_SOUMIS_COMPAGNIE: {
            "soumis": True,
            "at": "2026-03-01T10:00:00+00:00",
            "by": "Mgr",
            "by_id": "m1",
        }
    })
    assert nested["soumis"] is True
    assert nested["by"] == "Mgr"
    assert nested["by_id"] == "m1"

    legacy = normalize_soumis_compagnie({
        FIELD_SOUMIS_COMPAGNIE: True,
        "soumis_compagnie_at": "2026-03-02T10:00:00+00:00",
        "soumis_compagnie_by": "Mgr2",
        "soumis_compagnie_by_id": "m2",
    })
    assert legacy["soumis"] is True
    assert legacy["by"] == "Mgr2"


def test_build_soumis_payload_persists_user_and_date():
    on = build_soumis_compagnie_payload(
        soumis=True,
        by_name="Gestionnaire Test",
        by_id="mgr-1",
        at="2026-03-10T12:00:00+00:00",
    )
    assert on[FIELD_SOUMIS_COMPAGNIE]["soumis"] is True
    assert on[FIELD_SOUMIS_COMPAGNIE]["by"] == "Gestionnaire Test"
    assert on[FIELD_SOUMIS_COMPAGNIE]["by_id"] == "mgr-1"
    assert on["soumis_compagnie_at"] == "2026-03-10T12:00:00+00:00"

    off = build_soumis_compagnie_payload(soumis=False, by_name="X", by_id="y")
    assert off[FIELD_SOUMIS_COMPAGNIE]["soumis"] is False
    assert off["soumis_compagnie_at"] is None


def test_serialize_exposes_soumis_and_signature_followup():
    agent = _user(ROLE_CONSEILLER, account_id="agent-1", name="Alice Agent", conseiller="Alice Agent")
    mgr = _user(ROLE_GESTIONNAIRE_OFFRES, account_id="mgr-1", see_all_dossiers=True)
    doc = {
        "id": "d1",
        "statut": STATUT_OFFRE_SIGNEE,
        "created_by_account_id": "agent-1",
        "agent_label": "Alice Agent",
        "signature": {
            "signee": True,
            "recorded_by": "Alice Agent",
            "recorded_by_id": "agent-1",
            "signed_at": "2026-03-01T09:00:00+00:00",
            "document_category": DOC_CATEGORY_PROPOSITION_SIGNEE,
        },
        FIELD_SOUMIS_COMPAGNIE: {
            "soumis": True,
            "at": "2026-03-02T11:00:00+00:00",
            "by": "Mgr",
            "by_id": "mgr-1",
        },
        "historique": [
            {"action": "Offre signée", "at": "2026-03-01T09:00:00+00:00"},
            {"action": ACTION_SOUMIS_COMPAGNIE, "at": "2026-03-02T11:00:00+00:00"},
        ],
    }
    out_agent = serialize_demande(doc, viewer=agent)
    assert out_agent["soumis_compagnie"]["soumis"] is True
    assert out_agent["can_follow_signature"] is True
    assert out_agent["can_process"] is False
    assert any(e.get("action") == ACTION_SOUMIS_COMPAGNIE for e in out_agent["historique"])

    out_mgr = serialize_demande(doc, viewer=mgr)
    assert out_mgr["can_process"] is True
    # Gestionnaire pur (pas créateur) : pas le suivi signature
    assert can_follow_signature(mgr, doc) is False
    assert out_mgr["can_follow_signature"] is False


def test_signing_does_not_imply_soumis_in_serialize():
    doc = {
        "id": "d2",
        "statut": STATUT_OFFRE_SIGNEE,
        "signature": {"signee": True, "recorded_by_id": "a1"},
    }
    out = serialize_demande(doc)
    assert out["client_signe"] is True
    assert out["soumis_compagnie"]["soumis"] is False
