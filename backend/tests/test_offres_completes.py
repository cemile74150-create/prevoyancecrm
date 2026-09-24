"""Tests — statut / e-mail « Offres complètes »."""
from __future__ import annotations

import email_service as es
from access_control import PERM_DEMANDES_OFFRES_PROCESS, permission_for_request
from demandes_offres_3p import (
    STATUT_OFFRE_COMPLETE,
    STATUT_OFFRE_COMPLETE_LEGACY,
    normalize_statut,
)


def test_statut_constant_is_plural():
    assert STATUT_OFFRE_COMPLETE == "Offres complètes"


def test_normalize_statut_maps_legacy_singulier():
    assert normalize_statut(STATUT_OFFRE_COMPLETE_LEGACY) == STATUT_OFFRE_COMPLETE
    assert normalize_statut("Offres complètes") == STATUT_OFFRE_COMPLETE
    assert normalize_statut("Offre reçue") == "Offre reçue"


def test_offres_completes_route_requires_process_perm():
    assert (
        permission_for_request("POST", "/api/demandes-offres/abc/offres-completes")
        == PERM_DEMANDES_OFFRES_PROCESS
    )


def test_format_offres_completes_email(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.leosoft.ch")
    subject, text, html = es.format_offres_completes_email(
        {
            "id": "d-complete",
            "numero": "OFF-2026-0099",
            "prenom": "Jean",
            "nom": "Dupont",
            "statut": "Offres complètes",
            "agent_prenom": "Cemile",
            "agent_nom": "Demirtas",
            "agent_email": "cemile@cabinet.ch",
            "montant_prime": 1200,
            "commentaires": "ne doit pas apparaître",
        }
    )
    assert subject == "Offres complètes – Jean Dupont – OFF-2026-0099"
    assert "Bonjour Cemile," in text
    assert "complètes et disponibles" in text
    assert "https://app.leosoft.ch/demandes-offres/d-complete" in text
    assert "Voir les offres dans Leosoft" in text
    assert "Bonne journée," in text
    assert "Leosoft" in text
    assert "1200" not in text
    assert "ne doit pas apparaître" not in text
    assert 'href="https://app.leosoft.ch/demandes-offres/d-complete"' in html
    assert es.MAIL_TYPE_OFFRES_COMPLETES == "offres_completes"


def test_offre_notify_role_offres_completes():
    assert es.offre_notify_role("offres_completes") == "createur"
    assert es.offre_notify_role("complete") == "createur"
