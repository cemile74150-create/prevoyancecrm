"""Retrait d'une erreur agent : elle sort du scoring, les autres restent."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    PERM_DEMANDES_OFFRES_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
    PERM_USERS_MANAGE,
    permission_for_request,
)
from demandes_offres_3p import (  # noqa: E402
    STATUT_ENVOYEE,
    compute_erreur_stats,
    compute_erreurs_agent_stats,
    detail_erreur_retiree,
    history_entry,
    retirer_erreur_agent,
)


def _records():
    return [
        {
            "id": "e1",
            "demande_id": "d1",
            "demande_numero": "OFF-2026-0316",
            "field": "date_effet",
            "field_label": "Date d'effet",
            "comment": "tarifs Cies non disponibles, échéance du contrat AXA au 31.03.2028",
            "agent_label": "Cemile Demirtas",
            "agent_id": "a1",
            "at": "2026-03-01T10:00:00",
            "client": "Jean Martin",
        },
        {
            "id": "e1b",
            "demande_id": "d1",
            "demande_numero": "OFF-2026-0316",
            "field": "date_effet",
            "field_label": "Date d'effet",
            "comment": "doublon",
            "agent_label": "Cemile Demirtas",
            "agent_id": "a1",
            "at": "2026-03-01T11:00:00",
        },
        {
            "id": "e2",
            "demande_id": "d1",
            "demande_numero": "OFF-2026-0316",
            "field": "salaire",
            "field_label": "Salaire",
            "agent_label": "Cemile Demirtas",
            "agent_id": "a1",
            "at": "2026-03-02T10:00:00",
        },
        {
            "id": "e3",
            "demande_id": "d2",
            "demande_numero": "OFF-2026-0317",
            "field": "date_effet",
            "field_label": "Date d'effet",
            "agent_label": "Cemile Demirtas",
            "agent_id": "a1",
            "at": "2026-03-04T09:00:00",
            "client": "Paul Bernard",
        },
    ]


def _demandes():
    return [
        {
            "id": "d1",
            "numero": "OFF-2026-0316",
            "statut": STATUT_ENVOYEE,
            "agent_label": "Cemile Demirtas",
            "prenom": "Jean",
        },
        {
            "id": "d2",
            "numero": "OFF-2026-0317",
            "statut": STATUT_ENVOYEE,
            "agent_label": "Cemile Demirtas",
            "prenom": "Paul",
        },
    ]


def test_retrait_retire_le_champ_et_laisse_le_reste():
    demandes = _demandes()
    remaining, removed = retirer_erreur_agent(_records(), demande_id="d1", erreur_ref="e1")
    assert removed["id"] == "e1"
    assert {r["id"] for r in remaining} == {"e2", "e3"}
    assert demandes[0]["id"] == "d1"
    assert demandes[0]["statut"] == STATUT_ENVOYEE
    assert demandes[1]["id"] == "d2"

    par_champ, _ = retirer_erreur_agent(remaining, demande_id="d2", erreur_ref="date_effet")
    assert {r["id"] for r in par_champ} == {"e2"}

    inchange, absent = retirer_erreur_agent(par_champ, demande_id="d1", erreur_ref="introuvable")
    assert absent is None
    assert {r["id"] for r in inchange} == {"e2"}


def test_retrait_disparait_des_stats_les_autres_restent():
    demandes = _demandes()
    records = _records()
    before_agent = compute_erreurs_agent_stats(records)
    before_score = compute_erreur_stats(demandes, error_records=records)
    assert before_agent["total"] == 3
    assert before_score["by_agent"][0]["incompletes"] == 2
    assert before_score["by_agent"][0]["demandes"] == 2

    date_effet = next(f for f in before_agent["by_agent"][0]["by_field"] if f["code"] == "date_effet")
    assert date_effet["count"] == 2
    assert date_effet["dossiers"][0]["demande_id"] == "d2"
    assert {d["demande_id"] for d in date_effet["dossiers"]} == {"d1", "d2"}
    score_d1 = next(e for e in before_score["by_agent"][0]["erreurs"] if e["erreur_id"] == "e1")
    assert score_d1["demande_id"] == "d1"

    remaining, removed = retirer_erreur_agent(records, demande_id="d1", erreur_ref="e1")
    after_agent = compute_erreurs_agent_stats(remaining)
    after_score = compute_erreur_stats(demandes, error_records=remaining)
    assert after_agent["total"] == 2
    by_code = {f["code"]: f for f in after_agent["by_agent"][0]["by_field"]}
    assert by_code["salaire"]["count"] == 1
    assert by_code["salaire"]["dossiers"][0]["demande_id"] == "d1"
    assert by_code["date_effet"]["count"] == 1
    assert by_code["date_effet"]["dossiers"][0]["demande_id"] == "d2"
    assert after_score["by_agent"][0]["incompletes"] == 2
    assert after_score["by_agent"][0]["demandes"] == 2
    d1_codes = [e["code"] for e in after_score["by_agent"][0]["erreurs"] if e["demande_id"] == "d1"]
    assert d1_codes == ["salaire"]
    assert any(e["demande_id"] == "d2" and e["code"] == "date_effet" for e in after_score["by_agent"][0]["erreurs"])

    restants, removed_salaire = retirer_erreur_agent(remaining, demande_id="d1", erreur_ref="e2")
    assert removed_salaire["field"] == "salaire"
    final_score = compute_erreur_stats(demandes, error_records=restants)
    final_agent = compute_erreurs_agent_stats(restants)
    assert final_score["by_agent"][0]["incompletes"] == 1
    assert final_score["by_agent"][0]["demandes"] == 2
    assert {e["demande_id"] for e in final_score["by_agent"][0]["erreurs"]} == {"d2"}
    assert final_agent["total"] == 1
    assert demandes[0]["statut"] == STATUT_ENVOYEE
    assert removed["field"] == "date_effet"


def test_historique_retrait_nomme_lerreur_sans_statut():
    _remaining, removed = retirer_erreur_agent(_records(), demande_id="d1", erreur_ref="e1")
    detail = detail_erreur_retiree(removed)
    assert detail.startswith("Date d'effet — tarifs")
    entry = history_entry(
        "Erreur retirée",
        by_name="Cemile Admin",
        by_id="admin-1",
        detail=detail,
        meta={"erreur_id": removed["id"], "field": removed["field"], "demande_id": "d1"},
    )
    assert entry["action"] == "Erreur retirée"
    assert entry["by_name"] == "Cemile Admin"
    assert entry["at"]
    assert "statut" not in entry
    assert "Date d'effet" in entry["detail"]
    assert entry["meta"]["erreur_id"] == "e1"


def test_route_retrait_reservee_gestionnaire_ou_admin():
    assert permission_for_request("DELETE", "/api/demandes-offres/d1/erreurs/e1") == (
        PERM_DEMANDES_OFFRES_PROCESS,
        PERM_USERS_MANAGE,
    )
    assert permission_for_request("POST", "/api/demandes-offres/d1/erreurs") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("DELETE", "/api/demandes-offres/d1") == PERM_DEMANDES_OFFRES_EDIT
