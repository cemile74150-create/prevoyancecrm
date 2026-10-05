"""Tests génération lettre AVS depuis le modèle Word exact (+ PDF preview)."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from lettre_avs_word import ORIGINAL_DOCX, fill_lettre_avs_docx  # noqa: E402
from pdf_generator import client_field_values, generate_document_pdf  # noqa: E402

SAMPLE = {
    "nom": "Dupont",
    "prenom": "Jean",
    "date_naissance": "1980-01-15",
    "sexe": "Homme",
    "avs_number": "756.1234.5678.90",
    "adresse": "Rue du Lac 12",
    "npa": "1200",
    "ville": "Genève",
}

FAKE_PDF = b"%PDF-1.4 fake-avs-preview"


@pytest.mark.skipif(not ORIGINAL_DOCX.exists(), reason="Modèle Word AVS absent")
def test_lettre_avs_docx_replaces_name_and_date_keeps_layout():
    import hashlib
    from datetime import datetime

    before = hashlib.sha256(ORIGINAL_DOCX.read_bytes()).hexdigest()
    values = client_field_values(SAMPLE)
    data = fill_lettre_avs_docx(values)
    assert hashlib.sha256(ORIGINAL_DOCX.read_bytes()).hexdigest() == before

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
        names = zf.namelist()

    assert "word/media/image1.jpg" in names
    assert "word/media/image2.png" in names
    assert "NOM Prénom" not in xml
    assert "Jean DUPONT" in xml
    assert "Caisse suisse de compensation CSC" in xml
    assert "Avenue Edmond Vaucher 18" in xml
    assert "Transmission de la procuration" in xml
    assert "Agence Mendes" in xml
    assert "Sàrl" in xml
    assert "TIME" not in xml
    i = xml.find("Perly, le ")
    assert i >= 0
    assert "fldChar" not in xml[i : i + 200]
    months = [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ]
    today = datetime.now()
    assert f"Perly, le {today.day} {months[today.month - 1]} {today.year}" in xml


@pytest.mark.skipif(not ORIGINAL_DOCX.exists(), reason="Modèle Word AVS absent")
def test_generate_document_pdf_lettre_avs_returns_pdf_with_docx_companion():
    with patch("lettre_lpp_word.convert_docx_to_pdf", return_value=FAKE_PDF):
        file_bytes, meta = generate_document_pdf("lettre_avs", SAMPLE)
    assert meta["template_id"] == "lettre_avs"
    assert meta["original_filename"] == "Lettre_Demande_AVS_Jean_Dupont.pdf"
    assert meta["content_type"] == "application/pdf"
    assert meta["has_word_download"] is True
    assert meta["docx_filename"] == "Lettre_Demande_AVS_Jean_Dupont.docx"
    assert file_bytes == FAKE_PDF
    assert meta["docx_bytes"][:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(meta["docx_bytes"])) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "Jean DUPONT" in xml
    assert "complété par" in xml or "complete par" in xml


@pytest.mark.skipif(not ORIGINAL_DOCX.exists(), reason="Modèle Word AVS absent")
def test_lettre_avs_filename_uses_prenom_nom():
    with patch("lettre_lpp_word.convert_docx_to_pdf", return_value=FAKE_PDF):
        file_bytes, meta = generate_document_pdf(
            "lettre_avs",
            {
                "nom": "Bauer",
                "prenom": "Thierry",
                "date_naissance": "1980-01-15",
                "sexe": "Homme",
                "avs_number": "756.1234.5678.90",
                "adresse": "Rue du Lac 12",
                "npa": "1200",
                "ville": "Genève",
            },
        )
    assert meta["original_filename"] == "Lettre_Demande_AVS_Thierry_Bauer.pdf"
    assert meta["docx_filename"] == "Lettre_Demande_AVS_Thierry_Bauer.docx"
    assert file_bytes == FAKE_PDF
