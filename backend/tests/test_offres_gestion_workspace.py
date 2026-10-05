"""Tests priorite / categories gestionnaire demandes d'offres."""
from datetime import datetime, timedelta, timezone

from demandes_offres_3p import (
    OFFRES_DELAI_SURVEILLER_JOURS,
    OFFRES_DELAI_URGENT_JOURS,
    STATUT_ENVOYEE,
    STATUT_INCOMPLETE,
    STATUT_OFFRE_COMPLETE,
    STATUT_OFFRE_RECUE,
    STATUT_OFFRE_SIGNEE,
    build_variantes,
    compute_gestion_kpis,
    compute_priorite,
    enrich_gestion_fields,
    gestion_categorie_ids,
    serialize_demande,
)


def _doc(**kwargs):
    now = datetime.now(timezone.utc)
    base = {
        "id": "d1",
        "numero": "2026-0001",
        "statut": STATUT_ENVOYEE,
        "compagnies": ["AXA", "Swiss Life"],
        "created_at": (now - timedelta(days=2)).isoformat(),
        "date_envoi": (now - timedelta(days=2)).isoformat(),
        "updated_at": now.isoformat(),
        "historique": [{"id": "h1", "at": now.isoformat(), "action": "Demande envoyée", "by_name": "Cemile"}],
        "offres": [],
        "notes_internes": [{"id": "n1", "note": "secret", "at": now.isoformat(), "by_name": "Mgr"}],
    }
    base.update(kwargs)
    return base


def test_priorite_normal_under_5_days():
    doc = _doc(date_envoi=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat())
    p = compute_priorite(doc)
    assert p["niveau"] == "normal"
    assert p["en_retard"] is False
    assert p["jours"] == 2


def test_priorite_surveiller_at_5_days():
    doc = _doc(
        date_envoi=(datetime.now(timezone.utc) - timedelta(days=OFFRES_DELAI_SURVEILLER_JOURS)).isoformat()
    )
    p = compute_priorite(doc)
    assert p["niveau"] == "surveiller"
    assert p["en_retard"] is False


def test_priorite_urgent_at_10_days():
    doc = _doc(
        date_envoi=(datetime.now(timezone.utc) - timedelta(days=OFFRES_DELAI_URGENT_JOURS)).isoformat()
    )
    p = compute_priorite(doc)
    assert p["niveau"] == "urgent"
    assert p["en_retard"] is True


def test_priorite_closed_status_not_urgent():
    doc = _doc(
        statut=STATUT_OFFRE_SIGNEE,
        date_envoi=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
    )
    p = compute_priorite(doc)
    assert p["niveau"] == "normal"
    assert p["en_retard"] is False


def test_gestion_categories_and_kpis():
    rows = [
        _doc(statut=STATUT_ENVOYEE),
        _doc(id="d2", statut=STATUT_INCOMPLETE),
        _doc(id="d3", statut=STATUT_OFFRE_RECUE),
        _doc(id="d4", statut=STATUT_OFFRE_COMPLETE),
        _doc(
            id="d5",
            statut=STATUT_ENVOYEE,
            date_envoi=(datetime.now(timezone.utc) - timedelta(days=12)).isoformat(),
        ),
    ]
    assert "a_traiter" in gestion_categorie_ids(rows[0])
    assert "incompletes" in gestion_categorie_ids(rows[1])
    assert "en_retard" in gestion_categorie_ids(rows[4])
    kpis = compute_gestion_kpis(rows)
    assert kpis["incompletes"] >= 1
    assert kpis["offres_recues"] >= 1
    assert kpis["completes"] >= 1
    assert kpis["en_retard"] >= 1


def test_variantes_count_companies_not_demandes():
    doc = _doc(
        compagnies=["AXA", "Swiss Life", "Helvetia"],
        offres=[{"id": "o1", "compagnie": "AXA", "statut": "Reçue"}],
    )
    variantes = build_variantes(doc)
    assert len(variantes) == 3
    assert variantes[0]["compagnie"] == "AXA"
    assert variantes[0]["statut"] in {"Reçue", "Offre reçue"}
    assert variantes[0]["has_offre"] is True
    assert variantes[1]["statut"] == "En attente"


def test_serialize_hides_notes_for_conseiller():
    class U:
        role = "conseiller"
        account_id = "a1"
        permissions = {"demandes_offres.process": False}

    out = serialize_demande(_doc(), viewer=U())
    assert out["notes_internes"] == []
    assert out["nb_variantes_sollicitees"] == 2
    assert "priorite" in out
    assert "variantes" in out


def test_serialize_shows_notes_for_gestionnaire():
    class U:
        role = "gestionnaire_offres"
        account_id = "g1"
        permissions = {"demandes_offres.process": True}

    out = serialize_demande(_doc(), viewer=U())
    assert len(out["notes_internes"]) == 1
    assert out["can_process"] is True


def test_enrich_fields():
    out = {}
    enrich_gestion_fields(_doc(), out)
    assert "jours_depuis" in out
    assert out["priorite"] in {"normal", "surveiller", "urgent"}
    assert isinstance(out["gestion_categories"], list)
