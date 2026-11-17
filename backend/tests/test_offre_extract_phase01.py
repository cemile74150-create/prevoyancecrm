"""Phase 0 (sûreté) + Phase 1 (extraction structurée) — non-régression + golden ELVIA."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import (  # noqa: E402
    _compact_money_token,
    _find_adresse_block,
    _find_prime_annuelle,
    _find_telephone,
    extract_offre_fields,
    map_extract_to_form,
)
from offre_extract_structured import (  # noqa: E402
    extract_structured_offre,
    suggest_form_type,
    structured_to_flat_extracted,
)
from offre_pdf_form_fill import _match_choice  # noqa: E402

FIXTURE_TEXT = BACKEND / "tests" / "fixtures" / "elvia_porsche_toyota_2026.txt"
ELVIA_PDF = Path(r"C:\Users\offic\Desktop\Insurance Porsche & Toyota 2026.pdf")


def _elvia_text() -> str:
    assert FIXTURE_TEXT.exists(), f"Fixture manquante: {FIXTURE_TEXT}"
    return FIXTURE_TEXT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 0 — correctifs sûreté
# ---------------------------------------------------------------------------


def test_phase0_chf_parser_no_truncation():
    assert _compact_money_token("1178.50") == 1178.5
    assert _compact_money_token("1'243.90") == 1243.9
    assert _compact_money_token("1 243.90") == 1243.9
    assert _compact_money_token("CHF 1\u202f243.90") == 1243.9
    assert _compact_money_token("1.243,90") == 1243.9


def test_phase0_prime_annuelle_prefers_ttc_not_truncated():
    text = (
        "PRIME ANNUELLE 1178.50\n"
        "PRIME ANNUELLE AVEC REDEVANCES LÉGALES ET SUPPLÉMENTS 1243.90\n"
    )
    assert _find_prime_annuelle(text) == 1243.9


def test_phase0_address_prefers_preneur_not_zurich_header():
    text = _elvia_text()
    addr = _find_adresse_block(text)
    assert addr["npa"] == "7134"
    assert "obersaxen" in (addr["ville"] or "").casefold()
    assert addr["npa"] != "8010"
    assert "zurich" not in (addr["ville"] or "").casefold() and "zürich" not in (addr["ville"] or "").casefold()


def test_phase0_telephone_ignores_insurer_service():
    text = _elvia_text()
    assert _find_telephone(text) is None  # seuls tél. sinistre / service ELVIA


def test_phase0_match_choice_no_single_letter_substring():
    opts = ["Aucun permis", "Permis B", "Permis C"]
    assert _match_choice("C", opts) == "Permis C"
    assert _match_choice("a", opts) is None
    assert _match_choice("Aucun permis", opts) == "Aucun permis"
    assert _match_choice("Permis B", opts) == "Permis B"


def test_phase0_pilier_sample_still_works(monkeypatch):
    sample = """
Vaudoise Assurances
Montant investi : CHF 385'000.–
Rente mensuelle garantie : CHF 1'250.–
Durée du contrat : 20 ans
Prénom : Marie
Nom : Dupont
Date de naissance : 15.03.1985
Adresse : Rue du Lac 12
NPA : 1000
Ville : Lausanne
Prime annuelle : CHF 4'800.–
"""
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: sample)
    result = extract_offre_fields(b"%PDF-1.4", filename="Offre 20 ans VD.pdf")
    assert result["compagnie"] == "Vaudoise"
    assert result["rente_mensuelle_garantie"] == 1250.0
    assert result["montant_investi"] == 385000.0
    assert result["duree"] == 20
    assert result["prenom"] == "Marie"
    assert result["npa"] == "1000"
    assert result["montant_prime"] == 4800.0


# ---------------------------------------------------------------------------
# Phase 1 — modèle structuré + golden ELVIA
# ---------------------------------------------------------------------------


def test_phase1_structured_elvia_two_vehicles_one_prime():
    text = _elvia_text()
    structured = extract_structured_offre(b"%PDF", filename="elvia.pdf", text=text)
    flat = structured_to_flat_extracted(structured)

    assert structured["marque"]["value"] == "ELVIA"
    assert structured["marque"]["status"] == "found"
    assert structured["assureur"]["value"] in {"Allianz", "ELVIA"}
    assert structured["police"]["numero"]["value"] == "T309497274"
    assert structured["preneur"]["npa"]["value"] == "7134"
    assert "obersaxen" in (structured["preneur"]["ville"]["value"] or "").casefold()
    assert structured["preneur"]["date_naissance"]["value"] == "1967-07-04"
    assert structured["preneur"]["telephone"]["status"] == "not_found"
    assert structured["preneur"]["email"]["status"] == "not_found"

    objets = structured["objets"]
    assert len(objets) == 2
    marques = {(o["marque"]["value"] or "").lower() for o in objets}
    assert "toyota" in marques
    assert "porsche" in marques
    plaques = [o["plaque"]["value"] for o in objets]
    assert all(p and "96299" in p.replace(" ", "") for p in plaques)

    # Prime globale unique ~1243.90 — pas 117, pas double
    assert structured["primes"]["globale"]["value"] == 1243.9
    assert flat["montant_prime"] == 1243.9
    assert flat["npa"] == "7134"
    assert flat["telephone"] is None
    assert flat["email"] is None

    assert suggest_form_type(structured) == "voyage"
    assert structured["meta"]["form_type_suggere"] == "voyage"


def test_phase1_extract_offre_fields_elvia_golden(monkeypatch):
    text = _elvia_text()
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: text)
    result = extract_offre_fields(b"%PDF-1.4", filename="Insurance Porsche & Toyota 2026.pdf")

    assert result["montant_prime"] == 1243.9
    assert result["npa"] == "7134"
    assert "obersaxen" in (result["ville"] or "").casefold()
    assert result["npa"] != "8010"
    assert result["telephone"] is None
    assert result["email"] is None
    assert result["date_naissance"] == "1967-07-04"
    assert result["reference_police"] == "T309497274"
    assert result["form_type_suggere"] == "voyage"
    assert len(result["objets"] or []) == 2

    mapped = map_extract_to_form(result, form_type="voyage")
    assert mapped["fields"]["montant_prime"] == 1243.9
    assert mapped["fields"]["npa"] == "7134"
    assert "telephone" not in mapped["fields"] or mapped["fields"].get("telephone") in (None, "")
    assert mapped["form_type_suggere"] == "voyage"
    assert len(mapped["objets"]) == 2
    # Mapping hints sans modifier les JSON
    hints = mapped["objet_hints"]
    assert hints.get("vehicule_1_marque")
    assert hints.get("vehicule_2_marque")
    assert hints["vehicule_1_marque"].lower() != hints["vehicule_2_marque"].lower()


def test_phase1_real_pdf_if_present():
    if not ELVIA_PDF.exists():
        return
    result = extract_offre_fields(
        ELVIA_PDF.read_bytes(),
        filename=ELVIA_PDF.name,
    )
    assert result["montant_prime"] == 1243.9
    assert result["npa"] == "7134"
    assert len(result["objets"] or []) == 2
    assert result["form_type_suggere"] == "voyage"
