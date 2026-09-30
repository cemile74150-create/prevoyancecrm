"""Tests Suivi RDV (statut + compte rendu) et relance e-mail J+1."""
from datetime import date, timedelta

from suivi_3p import (
    RDV_STATUTS,
    is_rdv_suivi_complete,
    needs_rdv_suivi_relance,
    normalize_rdv_statut,
    serialize_suivi_client,
)


def test_normalize_rdv_statut():
    assert normalize_rdv_statut("En cours") == "En cours"
    assert normalize_rdv_statut("signé") == "Signé"
    assert normalize_rdv_statut("ANNULÉ") == "Annulé"
    assert normalize_rdv_statut("") is None
    assert normalize_rdv_statut(None) is None
    assert normalize_rdv_statut("Autre") is None
    assert set(RDV_STATUTS) == {"En cours", "Signé", "Annulé"}


def test_is_rdv_suivi_complete_requires_both():
    assert not is_rdv_suivi_complete({})
    assert not is_rdv_suivi_complete({"rdv_statut": "Signé"})
    assert not is_rdv_suivi_complete({"rdv_compte_rendu": "OK"})
    assert not is_rdv_suivi_complete({"rdv_statut": "Signé", "rdv_compte_rendu": "  "})
    assert is_rdv_suivi_complete({"rdv_statut": "Signé", "rdv_compte_rendu": "Client a signé"})


def test_needs_rdv_suivi_relance_j_plus_1():
    today = date(2026, 9, 25)
    base = {
        "rdv_pris": True,
        "date_rdv": "2026-09-24",  # J-1 → éligible
        "rdv_statut": None,
        "rdv_compte_rendu": None,
        "rdv_suivi_relance_sent_at": None,
    }
    assert needs_rdv_suivi_relance(base, today=today) is True

    # Même jour que le RDV → pas encore
    same_day = {**base, "date_rdv": "2026-09-25"}
    assert needs_rdv_suivi_relance(same_day, today=today) is False

    # RDV demain → non
    future = {**base, "date_rdv": "2026-09-26"}
    assert needs_rdv_suivi_relance(future, today=today) is False

    # Complet → non
    complete = {**base, "rdv_statut": "Signé", "rdv_compte_rendu": "Fait"}
    assert needs_rdv_suivi_relance(complete, today=today) is False

    # Partiel (statut seul) → oui
    partial = {**base, "rdv_statut": "En cours"}
    assert needs_rdv_suivi_relance(partial, today=today) is True

    # Déjà relancé → non
    sent = {**base, "rdv_suivi_relance_sent_at": "2026-09-25T10:00:00+00:00"}
    assert needs_rdv_suivi_relance(sent, today=today) is False

    # Pas de RDV → non
    assert needs_rdv_suivi_relance({**base, "rdv_pris": False}, today=today) is False


def test_serialize_includes_rdv_suivi_fields():
    row = serialize_suivi_client(
        {
            "id": "abc",
            "prenom": "Ada",
            "nom": "Lovelace",
            "statut": "Offre envoyée",
            "rdv_pris": True,
            "date_rdv": "2026-09-20",
            "rdv_statut": "En cours",
            "rdv_compte_rendu": "Discussion ouverte",
            "rdv_suivi_relance_sent_at": None,
        }
    )
    assert row["rdv_statut"] == "En cours"
    assert row["rdv_compte_rendu"] == "Discussion ouverte"
    assert row["rdv_suivi_complete"] is True
    assert row["date_rdv"] == "2026-09-20"


def test_format_rdv_suivi_relance_email():
    from email_service import format_rdv_suivi_relance_email

    subject, text, html = format_rdv_suivi_relance_email(
        {
            "id": "c1",
            "prenom": "Jean",
            "nom": "Dupont",
            "date_rdv": "2026-09-20",
        },
        conseiller_prenom="Marie",
    )
    assert subject == "Suivi du rendez-vous – Dupont Jean"
    assert "Bonjour Marie" in text
    assert "20/09/2026" in text
    assert "Statut du rendez-vous" in text
    assert "compte rendu" in text.lower()
    assert "Bonjour Marie" in html
    assert "Dupont Jean" in html
