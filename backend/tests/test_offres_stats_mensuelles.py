"""Suivi des offres : statistiques mensuelles (reçues / signées / non signées).

Chaque série lit sa propre date. Les filtres sont ceux du pilotage.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demandes_offres_pilotage import (  # noqa: E402
    compute_stats_mensuelles,
    date_decision_commerciale,
    date_reception_demande,
    mois_glissants,
)
from demandes_offres_routes import OffreNonSigneeRequest  # noqa: E402
from test_offres_pilotage_attribution import ADMIN, AGENT, AUTRE_AGENT, G1, Harness, _demande  # noqa: E402

NOW = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)


def _mois(result):
    return {m["mois"]: (m["recues"], m["signees"], m["non_signees"]) for m in result["mois"]}


def _signee(did, envoi, signee_at, **extra):
    return _demande(
        did,
        statut="Offre signée",
        date_envoi=envoi,
        signature={"signee": True, "recorded_at": signee_at, "signed_at": signee_at},
        **extra,
    )


def _non_signee(did, envoi, at, **extra):
    return _demande(
        did,
        statut="offre_non_signee",
        date_envoi=envoi,
        offre_non_signee={"status": "offre_non_signee", "at": at, "reason": "Trop cher"},
        **extra,
    )


# --------------------------------------------------------------------------- calcul

def test_six_derniers_mois_mois_courant_inclus():
    assert mois_glissants(6, NOW) == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    assert mois_glissants(12, NOW)[0] == "2025-12"
    assert mois_glissants(6, datetime(2027, 2, 3, tzinfo=timezone.utc)) == [
        "2026-09", "2026-10", "2026-11", "2026-12", "2027-01", "2027-02",
    ]


def test_recue_en_septembre_signee_en_octobre_compte_dans_les_deux_mois():
    out = compute_stats_mensuelles(
        [_signee("s1", "2026-09-10T08:00:00+00:00", "2026-10-02T09:00:00+00:00")], now=NOW,
    )
    mois = _mois(out)
    assert mois["2026-09"] == (1, 0, 0)
    assert mois["2026-10"] == (0, 1, 0)
    assert out["totaux"] == {"recues": 1, "signees": 1, "non_signees": 0}
    assert [s["label"] for s in out["series"]] == ["Offres reçues", "Offres signées", "Offres non signées"]
    assert out["mois"][-1]["label"] == "nov. 2026"


def test_non_signee_et_refusee_comptent_comme_non_signees():
    rows = [
        _non_signee("n1", "2026-08-01T08:00:00+00:00", "2026-11-03T10:00:00+00:00"),
        _demande(
            "r1",
            statut="Offre refusée",
            date_envoi="2026-08-02T08:00:00+00:00",
            signature={"signee": False, "recorded_at": "2026-11-04T10:00:00+00:00"},
        ),
    ]
    mois = _mois(compute_stats_mensuelles(rows, now=NOW))
    assert mois["2026-08"] == (2, 0, 0)
    assert mois["2026-11"] == (0, 0, 2)


def test_brouillons_annulees_et_supprimees_exclues():
    rows = [
        _demande("b1", statut="Brouillon", date_envoi="2026-11-01T08:00:00+00:00"),
        _demande("a1", statut="demande_annulee", date_envoi="2026-11-01T08:00:00+00:00"),
        _demande("x1", is_deleted=True, date_envoi="2026-11-01T08:00:00+00:00"),
        _demande("ok", date_envoi="2026-11-01T08:00:00+00:00"),
    ]
    assert _mois(compute_stats_mensuelles(rows, now=NOW))["2026-11"] == (1, 0, 0)


def test_une_demande_compte_une_seule_fois_par_serie():
    doc = _signee("s2", "2026-10-01T08:00:00+00:00", "2026-10-20T08:00:00+00:00")
    doc["historique"] = [
        {"at": "2026-10-01T08:00:00+00:00", "action": "Demande envoyée", "statut": "Demande envoyée"},
        {"at": "2026-10-05T08:00:00+00:00", "action": "Demande envoyée", "statut": "Demande envoyée"},
        {"at": "2026-10-20T08:00:00+00:00", "action": "Offre signée", "statut": "Offre signée"},
    ]
    assert _mois(compute_stats_mensuelles([doc, doc], now=NOW))["2026-10"] == (2, 2, 0)
    assert _mois(compute_stats_mensuelles([doc], now=NOW))["2026-10"] == (1, 1, 0)


def test_mois_lu_en_heure_de_zurich():
    doc = _signee("z1", "2026-10-31T23:30:00+00:00", "2026-11-30T23:30:00+00:00")
    mois = _mois(compute_stats_mensuelles([doc], now=datetime(2026, 12, 5, tzinfo=timezone.utc)))
    assert mois["2026-11"] == (1, 0, 0)
    assert mois["2026-12"] == (0, 1, 0)


def test_decision_sans_date_lue_dans_historique_sinon_non_placee():
    avec_hist = _demande(
        "h1",
        statut="Offre signée",
        date_envoi="2026-09-01T08:00:00+00:00",
        historique=[{"at": "2026-09-15T08:00:00+00:00", "action": "Offre signée", "statut": "Offre signée"}],
    )
    sans_rien = _demande("h2", statut="Offre signée", date_envoi="2026-09-01T08:00:00+00:00")
    assert date_decision_commerciale(avec_hist) == "2026-09-15T08:00:00+00:00"
    assert date_decision_commerciale(sans_rien) is None
    out = compute_stats_mensuelles([avec_hist, sans_rien], now=NOW)
    assert _mois(out)["2026-09"] == (2, 1, 0)
    assert out["sans_date"] == {"recues": 0, "signees": 1, "non_signees": 0}


def test_reception_sans_date_envoi_lit_le_premier_envoi_de_l_historique():
    doc = _demande(
        "e1",
        date_envoi=None,
        historique=[
            {"at": "2026-07-03T08:00:00+00:00", "action": "Demande envoyée"},
            {"at": "2026-08-03T08:00:00+00:00", "action": "Demande envoyée"},
        ],
    )
    assert date_reception_demande(doc) == "2026-07-03T08:00:00+00:00"


def test_hors_fenetre_ignore_et_douze_mois():
    doc = _signee("o1", "2026-03-01T08:00:00+00:00", "2026-04-01T08:00:00+00:00")
    six = compute_stats_mensuelles([doc], now=NOW)
    assert six["totaux"] == {"recues": 0, "signees": 0, "non_signees": 0}
    douze = compute_stats_mensuelles([doc], nb_mois=12, now=NOW)
    assert len(douze["mois"]) == 12
    assert _mois(douze)["2026-03"] == (1, 0, 0)
    assert _mois(douze)["2026-04"] == (0, 1, 0)
    assert compute_stats_mensuelles([doc], nb_mois=7, now=NOW)["nb_mois"] == 6


def test_periode_borne_la_date_de_chaque_evenement():
    doc = _signee("p1", "2026-09-10T08:00:00+00:00", "2026-11-02T08:00:00+00:00")
    out = compute_stats_mensuelles(
        [doc], debut="2026-11-01T00:00:00+00:00", fin="2026-12-01T00:00:00+00:00", now=NOW,
    )
    assert _mois(out)["2026-09"] == (0, 0, 0)
    assert _mois(out)["2026-11"] == (0, 1, 0)


# --------------------------------------------------------------------------- route et filtres

def _stats(h, user, **kw):
    return h.call("GET", "/demandes-offres/pilotage/mensuel", user=user, **kw)


def _courant():
    return mois_glissants(1)[0]


def _rows_courants():
    courant = _courant()
    stamp = f"{courant}-02T09:00:00+00:00"
    return [
        _signee("d-1001", stamp, stamp),
        _non_signee(
            "d-1002", stamp, stamp,
            created_by_account_id=AUTRE_AGENT.account_id, agent_label="Alex Martin",
            agent_email="agent-2@test.ch", gestionnaire_id=G1.account_id, gestionnaire_nom="Lea Gestion",
        ),
        _demande("d-1003", statut="Brouillon", date_envoi=stamp),
    ]


def test_route_global_filtres_agent_et_gestionnaire(monkeypatch):
    h = Harness(_rows_courants(), monkeypatch)
    courant = _courant()
    tout = _mois(_stats(h, ADMIN))
    assert tout[courant] == (2, 1, 1)
    assert _mois(_stats(h, ADMIN, conseiller="Alex Martin"))[courant] == (1, 0, 1)
    assert _mois(_stats(h, ADMIN, gestionnaire=G1.account_id))[courant] == (1, 0, 1)
    assert _mois(_stats(h, ADMIN, gestionnaire="non_attribue"))[courant] == (1, 1, 0)
    douze = _stats(h, ADMIN, mois=12)
    assert douze["nb_mois"] == 12 and len(douze["mois"]) == 12
    assert _stats(h, ADMIN)["perimetre"] == "global"


def test_route_agent_ne_voit_que_ses_demandes(monkeypatch):
    h = Harness(_rows_courants(), monkeypatch)
    out = _stats(h, AGENT)
    assert out["perimetre"] == "agent"
    assert _mois(out)[_courant()] == (1, 1, 0)


def test_route_periode_du_tableau_de_bord(monkeypatch):
    h = Harness(_rows_courants(), monkeypatch)
    out = _stats(h, ADMIN, periode="custom", date_de="2000-01-01", date_a="2000-01-31")
    assert out["totaux"] == {"recues": 0, "signees": 0, "non_signees": 0}
    assert out["periode"]["periode"] == "custom"


def test_marquage_non_signee_enregistre_la_date_et_compte_ce_mois(monkeypatch):
    h = Harness([_demande("d-1004", statut="Offre envoyée au client", date_envoi="2026-01-05T08:00:00+00:00")], monkeypatch)
    h.call(
        "POST", "/demandes-offres/{demande_id}/offre-non-signee",
        demande_id="d-1004", payload=OffreNonSigneeRequest(commentaire="Client renonce"), user=G1,
    )
    assert h.doc("d-1004")["offre_non_signee"]["at"]
    assert _mois(_stats(h, ADMIN))[_courant()] == (0, 0, 1)
