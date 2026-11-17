"""Phase 5 — OCR scannés, auto form_type, types document, contrôle qualité."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import extract_offre_fields, map_extract_to_form  # noqa: E402
from offre_extract_company_adapters import score_extraction_coverage  # noqa: E402
from offre_extract_structured import (  # noqa: E402
    detect_document_type,
    extract_structured_offre,
    suggest_form_type_with_candidates,
)
from offre_pdf_form_map import merge_payload_preserve_existing  # noqa: E402

FIXTURES = BACKEND / "tests" / "fixtures"
ZURICH_FP = FIXTURES / "zurich_feuille_prestations_synth.txt"
ELVIA = FIXTURES / "elvia_porsche_toyota_2026.txt"


def _extract_from_fixture(path: Path, filename: str, monkeypatch):
    text = path.read_text(encoding="utf-8")
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: text)
    return extract_offre_fields(b"%PDF-1.4", filename=filename)


def test_phase5_document_type_valeurs_rachat():
    text = ZURICH_FP.read_text(encoding="utf-8")
    doc = detect_document_type(text, "Jean-Yves May Zurich.pdf")
    assert doc["value"] == "valeurs_rachat"
    assert doc["status"] == "found"


def test_phase5_zurich_feuille_no_invented_prime(monkeypatch):
    extracted = _extract_from_fixture(ZURICH_FP, "Jean-Yves May Zurich.pdf", monkeypatch)
    assert extracted["compagnie"] == "Zurich"
    assert extracted["prenom"] == "Jean-Yves"
    assert extracted["nom"] == "May"
    assert extracted["date_naissance"] == "1962-01-19"
    assert extracted["reference_police"] == "9.363.640"
    assert extracted["date_debut"] == "1998-12-30"
    assert extracted["date_fin"] == "2026-12-29"
    assert extracted["montant_investi"] == 74931.0
    assert extracted["montant_prime"] is None  # jamais inventer
    assert extracted["document_type"] == "valeurs_rachat"
    assert extracted["form_type_suggere"] == "pilier3"
    assert extracted["page_refs"] == [1]
    mapped = map_extract_to_form(extracted, form_type="pilier3")
    assert mapped["fields"].get("montant_prime") in (None, "")
    assert "montant_prime" not in (mapped.get("filled_keys") or []) or mapped["fields"].get("montant_prime") in (
        None,
        "",
    )


def test_phase5_form_type_candidates_elvia(monkeypatch):
    extracted = _extract_from_fixture(ELVIA, "Insurance Porsche & Toyota 2026.pdf", monkeypatch)
    assert extracted["form_type_suggere"] == "voyage"
    cands = extracted.get("form_type_candidates") or []
    assert any(c.get("form_type") == "voyage" for c in cands)


def test_phase5_form_type_needs_confirm_ambiguous():
    structured = extract_structured_offre(
        b"%PDF",
        filename="mixte.pdf",
        text=(
            "Assurance véhicules à moteur\nVéhicule assuré TOYOTA\n"
            "Plaque VS 123456\n"
            "Prévoyance liée 3a / pilier 3\nPolice de prévoyance n° L50 1\n"
        ),
    )
    info = suggest_form_type_with_candidates(structured, text=structured.get("meta", {}).get("filename", ""))
    # Branche véhicule prioritaire ici ; candidats peuvent inclure pilier3 selon signaux
    assert info.get("form_type_suggere") in {"vehicule", "pilier3", "voyage"}


def test_phase5_ocr_embedded_image_roundtrip(tmp_path):
    """PDF image-only synthétique : OCR images embarquées doit lire le texte."""
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    fitz = pytest.importorskip("fitz")
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 1200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
    lines = [
        "ZURICH",
        "FEUILLE DES PRESTATIONS (FP)",
        "PERSONNE ASSUREE: POLICE NO 1.234.567",
        "DUPONT MARIE FP NO. 1",
        "DATE DE NAISSANCE: 01.02.1980 VALABLE DES LE 01.01.2010",
        "SOMME D ASSURANCE DE FR. 10 000.-",
    ]
    y = 40
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0), font=font)
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    jpeg = buf.getvalue()

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=jpeg)
    pdf_bytes = doc.tobytes()
    doc.close()

    from pdf_generator import _ocr_pdf_text, _extract_pdf_text

    ocr = _ocr_pdf_text(pdf_bytes)
    assert "Page 1 sur 1" in ocr
    compact = "".join(ocr.split()).upper()
    assert "ZURICH" in compact or "FEUILLE" in compact or "POLICE" in compact

    text = _extract_pdf_text(pdf_bytes)
    assert len("".join(text.split())) >= 20

    extracted = extract_offre_fields(pdf_bytes, filename="synth_zurich_scan.pdf")
    # Tolérant OCR : au minimum compagnie ou type document / police
    assert (
        extracted.get("compagnie") == "Zurich"
        or extracted.get("document_type") == "valeurs_rachat"
        or extracted.get("reference_police")
        or extracted.get("_raw_text_len", 0) >= 40
    )


def test_phase5_quality_statuses_and_non_overwrite(monkeypatch):
    extracted = _extract_from_fixture(ELVIA, "elvia.pdf", monkeypatch)
    mapped = map_extract_to_form(extracted, form_type="voyage")
    statuses = mapped.get("field_statuses") or {}
    assert statuses  # found / to_verify / not_found exposés
    existing = {"input_48": "KEEP"}
    merged, skipped = merge_payload_preserve_existing(
        existing, mapped["form_payload"], overwrite=False
    )
    assert merged["input_48"] == "KEEP"
    assert "input_48" in skipped


def test_phase5_score_zurich_fixture(monkeypatch):
    extracted = _extract_from_fixture(ZURICH_FP, "Jean-Yves May Zurich.pdf", monkeypatch)
    score = score_extraction_coverage(
        extracted,
        expected={
            "prenom": "Jean-Yves",
            "nom": "May",
            "compagnie": "Zurich",
            "reference_police": "9.363.640",
            "montant_investi": 74931.0,
        },
    )
    assert score["counts"]["incorrect"] == 0
    assert score["counts"]["ok"] >= 4
