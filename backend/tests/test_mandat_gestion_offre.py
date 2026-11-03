"""Mandat de gestion obligatoire — pro + Allianz/Vaudoise uniquement."""
from __future__ import annotations

from datetime import date

from mandat_gestion_offre import (
    DOC_CATEGORY_MANDAT,
    demande_requires_mandat_gestion,
    has_mandat_document,
    is_mandat_required_company,
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
    assert "entreprise_46" in ids
    assert "pilier3" not in ids
    assert "menage_rc" not in ids


def test_is_professionnelle_form_menu_and_category():
    assert is_professionnelle_form("entreprise")
    assert not is_professionnelle_form("pilier3_legacy")
    assert is_professionnelle_form(None, form_category="Entreprise")


def test_allianz_vaudoise_detection():
    assert is_mandat_required_company("Allianz")
    assert is_mandat_required_company("Allianz (Romandie Courtage uniquement)")
    assert is_mandat_required_company("Vaudoise")
    assert is_mandat_required_company("La Vaudoise")
    assert not is_mandat_required_company("Mobilière")
    assert not is_mandat_required_company("AXA")
    assert not is_mandat_required_company("Helsana")


def test_parse_and_duration():
    assert parse_mandat_date("2025-01-15") == date(2025, 1, 15)
    assert mandat_covers_at_least_one_year(date(2025, 1, 15), date(2026, 1, 15))
    assert not mandat_covers_at_least_one_year(date(2025, 1, 15), date(2026, 1, 14))


def test_normalize_upload_category():
    assert normalize_mandat_upload_category("Mandat") == DOC_CATEGORY_MANDAT
    assert normalize_mandat_upload_category("Pièce jointe") is None


def test_pro_without_allianz_vaudoise_no_mandat():
    doc = {
        "form_type": "entreprise",
        "form_category": "Entreprise",
        "compagnies": ["Mobilière", "AXA"],
        "form_payload": {},
        "agent_finma": "12345",
    }
    assert not demande_requires_mandat_gestion(doc)
    assert mandat_gestion_missing(doc, docs=[]) == []
    miss = missing_required(doc, docs=[])
    assert not any("mandat" in m.lower() for m in miss)


def test_pro_with_allianz_requires_mandat():
    doc = {
        "form_type": "entreprise",
        "form_category": "Entreprise",
        "compagnies": ["Allianz", "Mobilière"],
        "form_payload": {},
        "agent_finma": "12345",
    }
    assert demande_requires_mandat_gestion(doc)
    errors = mandat_gestion_missing(doc, docs=[], today=date(2026, 3, 1))
    assert "Mandat de gestion (document manquant)" in errors
    assert "Dates du mandat de gestion (début et fin)" in errors


def test_pro_with_vaudoise_variant_requires_mandat():
    doc = {
        "form_type": "rc_entreprise",
        "form_category": "Entreprise",
        "compagnies": ["Allianz (Romandie Courtage uniquement)"],
        "form_payload": {},
        "agent_finma": "12345",
        "mandat_debut": "2026-01-01",
        "mandat_fin": "2026-06-01",
    }
    docs = [{"id": "1", "category": DOC_CATEGORY_MANDAT}]
    errors = mandat_gestion_missing(doc, docs=docs, today=date(2026, 3, 1))
    assert "Durée du mandat inférieure à 1 an" in errors


def test_particulier_no_mandat_even_with_vaudoise():
    doc = {
        "form_type": "pilier3",
        "form_category": "3ème pilier",
        "compagnies": ["Vaudoise", "Allianz"],
        "form_payload": {},
        "agent_finma": "12345",
    }
    assert not demande_requires_mandat_gestion(doc)
    assert mandat_gestion_missing(doc, docs=[]) == []


def test_pro_ok_with_vaudoise():
    today = date(2026, 3, 1)
    doc = {
        "form_type": "entreprise_46",
        "form_category": "Entreprise",
        "compagnies": ["Vaudoise"],
        "mandat_debut": today.isoformat(),
        "mandat_fin": date(2027, 3, 1).isoformat(),
        "agent_finma": "12345",
        "form_payload": {},
    }
    docs = [{"id": "1", "category": DOC_CATEGORY_MANDAT}]
    assert mandat_gestion_missing(doc, docs=docs, today=today) == []


def test_missing_required_includes_mandat_for_allianz_pro():
    doc = {
        "form_type": "formulaire_complet",
        "form_category": "Autre",
        "compagnies": ["Allianz"],
        "form_payload": {},
        "agent_finma": "999",
    }
    miss = missing_required(doc, docs=[])
    assert any(m == "Mandat de gestion (document manquant)" for m in miss)


def test_legacy_category_still_counts():
    assert has_mandat_document([{"category": "Mandat"}])
    assert not has_mandat_document([{"category": "Pièce jointe"}])
