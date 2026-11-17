"""Phases 2–3 : mapping structuré → input_* voyage + non-écrasement + golden ELVIA."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import extract_offre_fields, map_extract_to_form  # noqa: E402
from offre_pdf_form_map import (  # noqa: E402
    map_structured_to_form_payload,
    merge_payload_preserve_existing,
)

FIXTURE_TEXT = BACKEND / "tests" / "fixtures" / "elvia_porsche_toyota_2026.txt"
ELVIA_PDF = Path(r"C:\Users\offic\Desktop\Insurance Porsche & Toyota 2026.pdf")


def _elvia_text() -> str:
    assert FIXTURE_TEXT.exists(), f"Fixture manquante: {FIXTURE_TEXT}"
    return FIXTURE_TEXT.read_text(encoding="utf-8")


def test_phase23_voyage_mapping_two_blocks_no_mix(monkeypatch):
    text = _elvia_text()
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: text)
    extracted = extract_offre_fields(b"%PDF-1.4", filename="Insurance Porsche & Toyota 2026.pdf")
    mapped = map_extract_to_form(extracted, form_type="voyage")
    payload = mapped["form_payload"]
    statuses = mapped["field_statuses"]

    assert extracted["montant_prime"] == 1243.9
    assert mapped["fields"]["montant_prime"] == 1243.9

    # Bloc 1 = Toyota, bloc 2 = Porsche — pas de mélange
    assert payload["input_48"] == "Toyota"
    assert "Yaris" in str(payload["input_49"])
    assert payload["input_51"] == "687.456.245"
    assert "96299" in str(payload["input_52"]).replace(" ", "")
    assert payload["input_53"] == "28.10.2024"

    assert payload["input_90"] == "Porsche"
    assert "911" in str(payload["input_91"])
    assert payload["input_93"] == "137.526.840"
    assert "96299" in str(payload["input_95"]).replace(" ", "")
    assert payload["input_96"] == "01.08.2005"

    assert payload["input_48"].lower() != payload["input_90"].lower()
    assert payload["input_51"] != payload["input_93"]

    # Garanties / franchises + prime unique (pas de double saisie schéma)
    assert payload["input_66"] == "Oui"
    assert payload["input_69"] == "Oui"
    assert payload["input_71"] == "Oui"
    assert str(payload["input_70"]) == "500"
    assert payload["input_107"] == "Oui"
    assert payload["input_110"] == "Oui"
    assert str(payload["input_111"]) == "500"

    assert payload.get("input_136") == "Monsieur"
    assert payload.get("input_37") == "15.08.1985"
    assert payload.get("input_131") == "Annuel"
    assert payload.get("input_39") == "Oui"
    assert payload.get("input_40") == "ELVIA"

    assert statuses["input_48"]["status"] == "found"
    assert statuses["input_90"]["status"] == "found"
    assert statuses["input_58"]["status"] == "to_verify"  # garage heuristique
    # Champs typiquement absents du PDF
    assert statuses.get("input_60", {}).get("status") == "not_found" or payload.get("input_60") in (None, "")


def test_phase23_merge_does_not_overwrite_without_flag():
    existing = {"input_48": "Honda", "input_130": "Alice"}
    incoming = {"input_48": "Toyota", "input_130": "Fernando", "input_90": "Porsche"}
    merged, skipped = merge_payload_preserve_existing(existing, incoming, overwrite=False)
    assert merged["input_48"] == "Honda"
    assert merged["input_130"] == "Alice"
    assert merged["input_90"] == "Porsche"
    assert "input_48" in skipped and "input_130" in skipped

    overwritten, skipped2 = merge_payload_preserve_existing(existing, incoming, overwrite=True)
    assert overwritten["input_48"] == "Toyota"
    assert overwritten["input_130"] == "Fernando"
    assert skipped2 == []


def test_phase23_pilier_non_regression(monkeypatch):
    sample = """
Vaudoise Assurances
Prénom : Marie
Nom : Dupont
Date de naissance : 15.03.1985
Adresse : Rue du Lac 12
NPA : 1000
Ville : Lausanne
Prime annuelle : CHF 4'800.–
"""
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: sample)
    extracted = extract_offre_fields(b"%PDF-1.4", filename="Offre 20 ans VD.pdf")
    mapped = map_extract_to_form(extracted, form_type="pilier3")
    assert mapped["fields"]["prenom"] == "Marie"
    assert mapped["fields"]["npa"] == "1000"
    assert any(v == "Marie" for v in (mapped["form_payload"] or {}).values())


def test_phase23_real_pdf_if_present():
    if not ELVIA_PDF.exists():
        return
    extracted = extract_offre_fields(ELVIA_PDF.read_bytes(), filename=ELVIA_PDF.name)
    mapped = map_extract_to_form(extracted, form_type="voyage")
    payload = mapped["form_payload"]
    assert extracted["montant_prime"] == 1243.9
    assert payload["input_48"] == "Toyota"
    assert payload["input_90"] == "Porsche"
    assert payload["input_66"] == "Oui"
    assert payload["input_107"] == "Oui"
    assert str(payload["input_70"]) == "500"
    filled = map_structured_to_form_payload("voyage", extracted, text=extracted.get("_text") or "")
    assert len(filled["filled_keys"]) >= 40
