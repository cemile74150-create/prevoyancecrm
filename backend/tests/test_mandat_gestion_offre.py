"""Mandat de gestion obligatoire — Assurances professionnelles."""
from __future__ import annotations

from datetime import date, timedelta

from mandat_gestion_offre import (
    DOC_CATEGORY_MANDAT,
    has_mandat_document,
    mandat_covers_at_least_one_year,
    mandat_gestion_missing,
    normalize_mandat_upload_category,
    parse_mandat_date,
)
from offre_form_types import is_professionnelle_form, professional_form_type_ids
from demandes_offres_3p import missing_required


def test_professional_form_types_from_menu():
    ids = professional_form_type_ids()
    assert "entreprise" in ids
    assert "formulaire_complet" in ids
    assert "entreprise_46" in ids  # LPP
    assert "rc_entreprise" in ids
    assert "entreprise_offres" in ids  # véhicule entreprise
    assert "pilier3" not in ids
    assert "pilier3_legacy" not in ids
    assert "menage_rc" not in ids


def test_is_professionnelle_form_menu_and_category():
    assert is_professionnelle_form("entreprise")
    assert is_professionnelle_form("formulaire_complet")
    assert is_professionnelle_form("protection_juridique_entreprise")
    assert not is_professionnelle_form("pilier3")
    assert not is_professionnelle_form("pilier3_legacy")
    assert not is_professionnelle_form("menage_rc")
    assert is_professionnelle_form(None, form_category="Entreprise")
    assert is_professionnelle_form(None, form_category="Assurances professionnelles")
    assert not is_professionnelle_form(None, form_category="Particulier")


def test_parse_and_duration():
    assert parse_mandat_date("2025-01-15") == date(2025, 1, 15)
    assert parse_mandat_date("15.01.2025") == date(2025, 1, 15)
    assert mandat_covers_at_least_one_year(date(2025, 1, 15), date(2026, 1, 15))
    assert mandat_covers_at_least_one_year(date(2025, 1, 15), date(2026, 1, 16))
    assert not mandat_covers_at_least_one_year(date(2025, 1, 15), date(2026, 1, 14))
    assert not mandat_covers_at_least_one_year(date(2025, 1, 15), date(2025, 7, 15))
    # Année bissextile
    assert mandat_covers_at_least_one_year(date(2024, 2, 29), date(2025, 2, 28))


def test_normalize_upload_category():
    assert normalize_mandat_upload_category("Mandat") == DOC_CATEGORY_MANDAT
    assert normalize_mandat_upload_category("Mandat de gestion") == DOC_CATEGORY_MANDAT
    assert normalize_mandat_upload_category("Pièce jointe") is None


def test_particulier_no_mandat_required():
    doc = {
        "form_type": "pilier3",
        "form_category": "3ème pilier",
        "form_payload": {},
        "agent_finma": "12345",
    }
    assert mandat_gestion_missing(doc, docs=[]) == []
    # missing_required may still flag schema fields / FINMA — mandat absent
    miss = missing_required(doc, docs=[])
    assert not any("mandat" in m.lower() for m in miss)


def test_pro_missing_document_and_dates():
    doc = {
        "form_type": "entreprise",
        "form_category": "Entreprise",
        "form_payload": {},
        "agent_finma": "12345",
    }
    errors = mandat_gestion_missing(doc, docs=[], today=date(2026, 3, 1))
    assert "Mandat de gestion (document manquant)" in errors
    assert "Dates du mandat de gestion (début et fin)" in errors


def test_pro_duration_too_short():
    doc = {
        "form_type": "rc_entreprise",
        "form_category": "Entreprise",
        "mandat_debut": "2026-01-01",
        "mandat_fin": "2026-06-01",
        "agent_finma": "12345",
    }
    docs = [{"id": "1", "category": DOC_CATEGORY_MANDAT, "original_filename": "m.pdf"}]
    errors = mandat_gestion_missing(doc, docs=docs, today=date(2026, 3, 1))
    assert "Durée du mandat inférieure à 1 an" in errors
    assert has_mandat_document(docs)


def test_pro_expired():
    doc = {
        "form_type": "entreprise_46",
        "form_category": "Entreprise",
        "mandat_debut": "2023-01-01",
        "mandat_fin": "2024-01-01",
        "agent_finma": "12345",
    }
    docs = [{"id": "1", "category": "Mandat"}]  # legacy category accepted
    errors = mandat_gestion_missing(doc, docs=docs, today=date(2026, 3, 1))
    assert "Mandat de gestion expiré" in errors


def test_pro_ok_blocks_nothing():
    today = date(2026, 3, 1)
    doc = {
        "form_type": "entreprise",
        "form_category": "Entreprise",
        "mandat_debut": today.isoformat(),
        "mandat_fin": (today.replace(year=today.year + 1)).isoformat(),
        "agent_finma": "12345",
        "form_payload": {},
    }
    docs = [{"id": "1", "category": DOC_CATEGORY_MANDAT}]
    assert mandat_gestion_missing(doc, docs=docs, today=today) == []


def test_missing_required_includes_mandat_for_pro():
    doc = {
        "form_type": "formulaire_complet",
        "form_category": "Autre",
        "form_payload": {},
        "agent_finma": "999",
    }
    miss = missing_required(doc, docs=[])
    assert any("Mandat de gestion (document manquant)" == m for m in miss)
    assert any("Dates du mandat" in m for m in miss)


def test_legacy_category_still_counts():
    assert has_mandat_document([{"category": "Mandat"}])
    assert has_mandat_document([{"category": "Mandat de gestion"}])
    assert not has_mandat_document([{"category": "Pièce jointe"}])
