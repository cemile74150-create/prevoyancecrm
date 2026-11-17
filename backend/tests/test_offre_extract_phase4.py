"""Phase 4 — généralisation multi-compagnies + couverture comparative."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import extract_offre_fields, map_extract_to_form  # noqa: E402
from offre_extract_company_adapters import (  # noqa: E402
    detect_company_adapter,
    prepare_text_for_extraction,
    score_extraction_coverage,
)
from offre_pdf_form_map import merge_payload_preserve_existing  # noqa: E402

FIXTURES = BACKEND / "tests" / "fixtures"
ELVIA = FIXTURES / "elvia_porsche_toyota_2026.txt"
MOBILIERE = FIXTURES / "mobiliere_vehicule_synth.txt"
VAUDOISE = FIXTURES / "vaudoise_vehicule_synth.txt"
AXA = FIXTURES / "axa_vehicule_synth.txt"
ZURICH = FIXTURES / "zurich_vehicule_synth.txt"


def _extract_from_fixture(path: Path, filename: str, monkeypatch):
    text = path.read_text(encoding="utf-8")
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: text)
    return extract_offre_fields(b"%PDF-1.4", filename=filename)


def test_phase4_detect_adapters():
    assert detect_company_adapter(ELVIA.read_text(encoding="utf-8"), "elvia.pdf").company_id == "ELVIA"
    assert detect_company_adapter(MOBILIERE.read_text(encoding="utf-8")).company_id == "Mobilière"
    assert detect_company_adapter(VAUDOISE.read_text(encoding="utf-8")).company_id == "Vaudoise"
    assert detect_company_adapter(AXA.read_text(encoding="utf-8")).company_id == "AXA"
    assert detect_company_adapter(ZURICH.read_text(encoding="utf-8")).company_id == "Zurich"


def test_phase4_prepare_rewrites_garage_synonyms():
    raw = MOBILIERE.read_text(encoding="utf-8")
    normalized, company_id, notes = prepare_text_for_extraction(raw, "mobiliere.pdf")
    assert company_id == "Mobilière"
    assert "Place de garage à disposition: Oui" in normalized
    assert any("Mobilière" in n for n in notes)


def test_phase4_elvia_golden_still_strong(monkeypatch):
    extracted = _extract_from_fixture(ELVIA, "Insurance Porsche & Toyota 2026.pdf", monkeypatch)
    mapped = map_extract_to_form(extracted, form_type="voyage")
    expected = {
        "prenom": "Fernando",
        "nom": "Gasca",
        "npa": "7134",
        "montant_prime": 1243.9,
        "reference_police": "T309497274",
        "compagnie": "ELVIA",
    }
    score = score_extraction_coverage(extracted, expected=expected)
    assert score["counts"]["incorrect"] == 0
    assert score["counts"]["ok"] >= 5
    assert len(mapped["filled_keys"]) >= 50
    assert mapped["fields"]["montant_prime"] == 1243.9
    # Non-écrasement
    existing = {"input_48": "Honda"}
    merged, skipped = merge_payload_preserve_existing(
        existing, mapped["form_payload"], overwrite=False
    )
    assert merged["input_48"] == "Honda"
    assert "input_48" in skipped


def test_phase4_comparative_table_multi_companies(monkeypatch):
    """Tableau comparatif : champs OK / manquants / incorrects par compagnie."""
    cases = [
        (
            "ELVIA",
            ELVIA,
            "elvia.pdf",
            "voyage",
            {
                "prenom": "Fernando",
                "nom": "Gasca",
                "npa": "7134",
                "montant_prime": 1243.9,
                "compagnie": "ELVIA",
            },
        ),
        (
            "Mobilière",
            MOBILIERE,
            "mobiliere.pdf",
            "vehicule",
            {
                "prenom": "Sophie",
                "nom": "Martin",
                "npa": "1003",
                "montant_prime": 890.5,
                "compagnie": "Mobilière",
            },
        ),
        (
            "Vaudoise",
            VAUDOISE,
            "vaudoise.pdf",
            "vehicule",
            {
                "prenom": "Lucas",
                "nom": "Favre",
                "npa": "1800",
                "montant_prime": 720.0,
                "compagnie": "Vaudoise",
            },
        ),
        (
            "AXA",
            AXA,
            "axa.pdf",
            "vehicule",
            {
                "prenom": "Marc",
                "nom": "Dubois",
                "npa": "8001",
                "montant_prime": 1150.0,
                "compagnie": "AXA",
            },
        ),
        (
            "Zurich",
            ZURICH,
            "zurich.pdf",
            "vehicule",
            {
                "prenom": "Elena",
                "nom": "Rossi",
                "npa": "1205",
                "montant_prime": 980.4,
                "compagnie": "Zurich",
            },
        ),
    ]

    rows = []
    for company, path, fname, form_type, expected in cases:
        extracted = _extract_from_fixture(path, fname, monkeypatch)
        mapped = map_extract_to_form(extracted, form_type=form_type)
        # Enrichir pour scoring véhicule (marque + garage mappé)
        flat_for_score = dict(extracted)
        payload = mapped.get("form_payload") or {}
        if form_type == "vehicule":
            flat_for_score["marque_vehicule"] = payload.get("input_48")
            flat_for_score["garage"] = payload.get("input_58")
        elif form_type == "voyage":
            flat_for_score["marque_v1"] = payload.get("input_48")
            flat_for_score["marque_v2"] = payload.get("input_90")
            flat_for_score["garage"] = payload.get("input_58")

        expected_ext = dict(expected)
        if company == "ELVIA":
            expected_ext.update({"marque_v1": "Toyota", "marque_v2": "Porsche", "garage": "Garage au domicile"})
        elif company == "Mobilière":
            expected_ext.update({"marque_vehicule": "Volkswagen", "garage": "Garage au domicile"})
        elif company == "Vaudoise":
            expected_ext.update({"marque_vehicule": "Renault", "garage": "Garage au domicile"})
        elif company == "AXA":
            expected_ext.update({"marque_vehicule": "Bmw", "garage": "Garage au domicile"})
        elif company == "Zurich":
            expected_ext.update({"marque_vehicule": "Audi", "garage": "Garage au domicile"})

        score = score_extraction_coverage(flat_for_score, expected=expected_ext)
        rows.append({"company": company, **score["counts"], "filled_keys": len(mapped.get("filled_keys") or [])})

        # Au moins identité + prime reconnues (pipeline générique + synonymes)
        assert extracted.get("npa") == expected["npa"] or score["counts"]["ok"] >= 3
        assert extracted.get("montant_prime") == expected["montant_prime"]

    # Rapport minimal : chaque compagnie a au moins 3 champs OK
    assert all(r["ok"] >= 3 for r in rows)
    assert next(r for r in rows if r["company"] == "ELVIA")["filled_keys"] >= 50
    # Pas de deploy / prod ici — pure mesure offline
    print("PHASE4_COMPARATIVE", rows)


def test_phase4_prime_synonym_jahrespraemie():
    from offre_extract_structured import _extract_primes

    primes = _extract_primes("Fahrzeugversicherung\nJahresprämie inkl. Steuern CHF 980.40\n")
    assert primes["globale"]["status"] == "found"
    assert primes["globale"]["value"] == 980.4


def test_phase4_overwrite_requires_flag_end_to_end(monkeypatch):
    """A5 : parcours extract → map → merge sans écrasement sauf flag."""
    extracted = _extract_from_fixture(ELVIA, "elvia.pdf", monkeypatch)
    mapped = map_extract_to_form(extracted, form_type="voyage")
    existing = {
        "input_48": "KEEP_ME",
        "input_130": "Alice",
        "input_2.5": "9999",
    }
    merged, skipped = merge_payload_preserve_existing(
        existing, mapped["form_payload"], overwrite=False
    )
    assert merged["input_48"] == "KEEP_ME"
    assert merged["input_130"] == "Alice"
    assert merged["input_2.5"] == "9999"
    assert "input_48" in skipped
    # Nouveaux champs PDF toujours injectés
    assert merged.get("input_90") == "Porsche"
    overwritten, skipped2 = merge_payload_preserve_existing(
        existing, mapped["form_payload"], overwrite=True
    )
    assert overwritten["input_48"] == "Toyota"
    assert skipped2 == []
