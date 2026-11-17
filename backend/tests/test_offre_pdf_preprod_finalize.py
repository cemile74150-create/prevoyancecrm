"""Finalisation pré-prod import PDF intelligent — identité AXA, flag, incertitude, mapping."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import (  # noqa: E402
    _find_person_name,
    _is_plausible_person_name,
    extract_offre_fields,
    map_extract_to_form,
    offre_fields_for_storage,
)
from offre_pdf_feature_flag import (  # noqa: E402
    mode_sync,
    user_can_use_structured_extract,
)
from pdf_generator import _ocr_table_line_heuristics  # noqa: E402


AXA_MAY_LETTER = """
Page 1 sur 2
Preneur d'assurance
Personne assurée
Broker Service Center
Suisse Romande
Chemin de Primerose 11
CH-1002 Lausanne
Monsieur
Jean-Yves May
Route de la Croix 10
1948 Sarreyer

Page 2 sur 2
Preneur d'assurance
May Jean-Yves
né(e) le 19.01.1962
Personne assurée
May Jean-Yves (A)
né(e) le 19.01.1962
Prime annuelle à partir du 01.11.2020
CHF 3'865
"""

AXA_VANESSA = """
Page 1 sur 1
Police d'assurance vie individuelle n° 147288
Preneur d'assurance VANESSA CHABLOZ (28.11.1967)
Personne assurée VANESSA CHABLOZ (28.11.1967)
Prime payable annuellement dès le 01.12.2006 CHF 6'192.--
AXA COMPAGNIE D'ASSURANCES SUR LA VIE
"""

AXA_CORINNE = """
Page 1 sur 1
Preneur d'assurance Corinne Perritaz Wahlen, né(e) le 15.03.1978
Votre police de prévoyance n° G 3.370.269
Prime annuelle CHF 2'005.00
"""


def test_axa_may_never_suisse_romande(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: AXA_MAY_LETTER)
    raw = extract_offre_fields(b"%PDF", filename="Jean-Yves May Axa.pdf")
    assert raw["prenom"] == "Jean-Yves"
    assert raw["nom"] == "May"
    assert raw["prenom"] != "Romande"
    assert raw["nom"] != "Suisse"
    assert raw["montant_prime"] == 3865.0
    assert raw["date_naissance"] == "1962-01-19"


def test_axa_vanessa_identity_and_prime(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: AXA_VANESSA)
    raw = extract_offre_fields(b"%PDF", filename="3p axa vanessa.pdf")
    assert raw["prenom"] == "Vanessa"
    assert raw["nom"] == "Chabloz"
    assert raw["date_naissance"] == "1967-11-28"
    assert raw["montant_prime"] == 6192.0


def test_axa_corinne_strips_dob_from_nom(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: AXA_CORINNE)
    raw = extract_offre_fields(b"%PDF", filename="AXA Corinne.pdf")
    assert raw["prenom"] == "Corinne"
    assert "Perritaz" in (raw["nom"] or "")
    assert "né" not in (raw["nom"] or "").casefold()
    assert "1978" not in (raw["nom"] or "")
    assert raw["date_naissance"] == "1978-03-15"


def test_uncertainty_rejects_org_tokens():
    assert not _is_plausible_person_name("Romande", "Suisse")
    assert not _is_plausible_person_name("(28.11.1967)", "VANESSA")
    assert not _is_plausible_person_name("Nos", "prestations")
    assert _is_plausible_person_name("Jean-Yves", "May")
    prenom, nom = _find_person_name(
        "Personne assurée\nBroker Service Center\nSuisse Romande\n"
    )
    assert prenom is None and nom is None


def test_feature_flag_admin_default_and_kill_switch():
    assert mode_sync(None) in {"admin", "on", "off"}
    admin = SimpleNamespace(role="admin", permissions={})
    conseiller = SimpleNamespace(role="conseiller", permissions={})
    assert user_can_use_structured_extract(admin, "admin") is True
    assert user_can_use_structured_extract(conseiller, "admin") is False
    assert user_can_use_structured_extract(conseiller, "on") is True
    assert user_can_use_structured_extract(admin, "off") is False


def test_kill_switch_uses_legacy_mapping(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: AXA_MAY_LETTER)
    raw = extract_offre_fields(b"%PDF", filename="may.pdf", use_structured=False)
    assert raw.get("structured") is None
    mapped = map_extract_to_form(raw, form_type="pilier3", use_structured=False)
    assert mapped["fields"].get("prenom") == "Jean-Yves"
    assert mapped.get("field_statuses") in ({}, None) or mapped["field_statuses"] == {}


def test_modifier_mapping_includes_visible_crm_and_prime(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: AXA_MAY_LETTER)
    raw = extract_offre_fields(b"%PDF", filename="may.pdf")
    mapped = map_extract_to_form(raw, form_type="pilier3", use_structured=True)
    fields = mapped["fields"]
    assert fields.get("prenom") == "Jean-Yves"
    assert fields.get("nom") == "May"
    assert fields.get("montant_prime") == 3865.0
    assert fields.get("date_naissance") == "1962-01-19"
    storage = offre_fields_for_storage(raw)
    assert storage["offre_extract"]["montant_prime"] == 3865.0
    assert storage["offre_extract"]["prenom"] == "Jean-Yves"


def test_ocr_table_heuristics_multi_money_lines():
    sample = """
Garantie collision   CHF 1'000   CHF 2'500
RC privée            CHF  500    CHF  750
texte sans tableau
"""
    hint = _ocr_table_line_heuristics(sample)
    assert "[ocr-table-heuristics]" in hint
    assert "1'000" in hint or "1000" in hint.replace("'", "")


def test_persist_roundtrip_montant_prime_shape():
    """Simule enregistrement → réouverture (champs plats + snapshot)."""
    extracted = {
        "prenom": "Jean-Yves",
        "nom": "May",
        "montant_prime": 3865.0,
        "compagnie": "AXA",
        "structured": {"audit": {"fields": []}},
    }
    stored = offre_fields_for_storage(extracted)
    # Comme un GET demande : les champs CRM restent corrects
    assert stored["offre_extract"]["montant_prime"] == 3865.0
    reopened_prime = stored["offre_extract"]["montant_prime"]
    assert reopened_prime == 3865.0
