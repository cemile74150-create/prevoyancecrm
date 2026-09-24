"""Séparation Gestionnaire vs Agent — droits Traitement demandes d'offres."""
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
    ERREURS_CHAMPS_CATALOG,
    build_erreur_agent_records,
    build_erreurs_checklist,
    can_follow_signature,
    compute_erreurs_agent_stats,
    normalize_erreurs_agent_fields,
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


def test_erreurs_and_checklist_routes_require_process():
    assert permission_for_request("POST", "/api/demandes-offres/abc/erreurs") == PERM_DEMANDES_OFFRES_PROCESS
    assert (
        permission_for_request("GET", "/api/demandes-offres/abc/erreurs-checklist")
        == PERM_DEMANDES_OFFRES_PROCESS
    )
    assert permission_for_request("POST", "/api/demandes-offres/abc/offre") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/offres-completes") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/notes-internes") == PERM_DEMANDES_OFFRES_PROCESS


def test_erreurs_champs_catalog_covers_required_fields():
    codes = {e["code"] for e in ERREURS_CHAMPS_CATALOG}
    for needed in (
        "nom_prenom",
        "date_naissance",
        "adresse",
        "salaire",
        "taux_activite",
        "vehicule",
        "date_effet",
        "type_assurance",
        "informations_client",
    ):
        assert needed in codes


def test_normalize_and_build_erreur_records():
    fields = normalize_erreurs_agent_fields(["salaire", {"code": "date_effet"}, "salaire"])
    assert [f["code"] for f in fields] == ["salaire", "date_effet"]
    agent = _user(ROLE_CONSEILLER, account_id="agent1", name="Jean Dupont", conseiller="Jean Dupont")
    mgr = _user(ROLE_GESTIONNAIRE_OFFRES, account_id="mgr1", name="Mgr Offres")
    doc = {
        "id": "d1",
        "numero": "OFF-1",
        "prenom": "Client",
        "nom": "X",
        "agent_label": "Jean Dupont",
        "created_by_account_id": "agent1",
    }
    records = build_erreur_agent_records(doc, fields, by_user=mgr)
    assert len(records) == 2
    assert records[0]["agent_id"] == "agent1"
    assert records[0]["demande_id"] == "d1"
    assert records[0]["field"] == "salaire"
    assert records[0]["client"] == "Client X"
    assert records[0]["error_type"] == "Erreur"
    assert can_follow_signature(agent, doc) is True
    assert can_follow_signature(mgr, doc) is False


def test_compute_erreurs_agent_stats_breakdown():
    records = [
        {"agent_label": "Jean Dupont", "agent_id": "a1", "field": "salaire", "field_label": "Salaire"},
        {"agent_label": "Jean Dupont", "agent_id": "a1", "field": "salaire", "field_label": "Salaire"},
        {"agent_label": "Jean Dupont", "agent_id": "a1", "field": "vehicule", "field_label": "Véhicule"},
        {"agent_label": "Autre", "agent_id": "a2", "field": "adresse", "field_label": "Adresse"},
    ]
    stats = compute_erreurs_agent_stats(records)
    assert stats["total"] == 4
    jean = next(a for a in stats["by_agent"] if a["agent_id"] == "a1")
    assert jean["total"] == 3
    by_code = {f["code"]: f["count"] for f in jean["by_field"]}
    assert by_code["salaire"] == 2
    assert by_code["vehicule"] == 1


def test_serialize_hides_notes_keeps_erreurs_for_agent():
    doc = {
        "id": "d1",
        "statut": "Offres complètes",
        "notes_internes": [{"note": "secret", "id": "n1"}],
        "erreurs_agent": [{"field": "salaire", "field_label": "Salaire", "id": "e1"}],
        "historique": [
            {"action": "Note interne", "detail": "secret"},
            {"action": "Erreurs signalées", "detail": "Salaire"},
            {"action": "Offres complètes"},
        ],
        "created_by_account_id": "agent1",
        "agent_label": "Jean Dupont",
    }
    agent = _user(ROLE_CONSEILLER, account_id="agent1", name="Jean Dupont", conseiller="Jean Dupont")
    out = serialize_demande(doc, viewer=agent)
    assert out["notes_internes"] == []
    assert out["erreurs_agent"]
    assert out["can_process"] is False
    assert out["can_follow_signature"] is True
    actions = [e["action"] for e in out["historique"]]
    assert "Note interne" not in actions
    assert "Erreurs signalées" in actions

    mgr = _user(ROLE_GESTIONNAIRE_OFFRES, account_id="mgr1", see_all_dossiers=True)
    out2 = serialize_demande(doc, viewer=mgr)
    assert out2["notes_internes"]
    assert out2["can_process"] is True
    assert out2["can_follow_signature"] is False


def test_checklist_includes_catalog():
    items = build_erreurs_checklist({"form_type": "pilier3_legacy"})
    codes = {i["code"] for i in items}
    assert "salaire" in codes
    assert "date_effet" in codes
