"""Caisse AVS destinataire selon le canton de résidence."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from avs_caisse import (  # noqa: E402
    detect_residence_canton,
    get_caisse,
    list_caisses,
    resolve_avs_caisse,
)
from lettre_avs_word import ORIGINAL_DOCX, fill_lettre_avs_docx  # noqa: E402
from pdf_generator import client_field_values  # noqa: E402


def test_catalog_has_26_cantons_and_csc():
    options = list_caisses()
    cantons = [c["id"] for c in options if c["id"] != "CSC"]
    assert len(cantons) == 26
    assert "GE" in cantons and "VD" in cantons and "VS" in cantons
    assert get_caisse("CSC")["name"].startswith("Caisse suisse")
    assert "Rue des Gares 12" in " ".join(get_caisse("GE")["address_lines"])
    assert "Rue des Moulins 3" in " ".join(get_caisse("VD")["address_lines"])
    assert "Avenue Pratifori 22" in " ".join(get_caisse("VS")["address_lines"])


def test_detect_geneva_vaud_valais_from_official_npa():
    ge = detect_residence_canton({"npa": "1204", "ville": "Genève", "pays": "Suisse"})
    assert ge["canton"] == "GE"
    assert ge["needs_manual"] is False

    # NPA de case postale absent du répertoire : la localité Genève suffit
    ge_box = detect_residence_canton({"npa": "1211", "ville": "Genève 2", "pays": "CH"})
    assert ge_box["canton"] == "GE"

    vd = detect_residence_canton({"npa": "1003", "ville": "Lausanne", "pays": "Suisse"})
    assert vd["canton"] == "VD"

    vs = detect_residence_canton({"npa": "1950", "ville": "Sion", "pays": "Suisse"})
    assert vs["canton"] == "VS"


def test_foreign_residence_proposes_csc_without_fake_canton():
    fr = detect_residence_canton(
        {"npa": "74100", "ville": "Annemasse", "pays": "France"}
    )
    assert fr["canton"] is None
    assert fr["source"] == "foreign"
    resolved = resolve_avs_caisse(
        {"npa": "74100", "ville": "Annemasse", "pays": "France"}
    )
    assert resolved["caisse"]["id"] == "CSC"
    assert resolved["needs_selection"] is False


def test_unknown_address_requires_manual_selection():
    unknown = resolve_avs_caisse({"npa": "", "ville": "", "pays": "Suisse"})
    assert unknown["caisse"] is None
    assert unknown["needs_selection"] is True
    assert unknown["detection"]["needs_manual"] is True


def test_manual_override_is_kept():
    client = {"npa": "1204", "ville": "Genève", "pays": "Suisse", "avs_caisse_id": "VD"}
    resolved = resolve_avs_caisse(client, selected_id="VD")
    assert resolved["detection"]["canton"] == "GE"
    assert resolved["caisse"]["id"] == "VD"
    assert resolved["manual"] is True


@pytest.mark.skipif(not ORIGINAL_DOCX.exists(), reason="Modèle Word AVS absent")
def test_letter_uses_selected_cantonal_address_not_csc():
    values = client_field_values(
        {
            "nom": "Dupont",
            "prenom": "Jean",
            "npa": "1204",
            "ville": "Genève",
            "pays": "Suisse",
            "avs_caisse_id": "GE",
        }
    )
    data = fill_lettre_avs_docx(values)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "Caisse genevoise de compensation" in xml
    assert "Rue des Gares 12" in xml
    assert "Caisse suisse de compensation CSC" not in xml
    assert "Avenue Edmond Vaucher 18" not in xml
    assert "Jean DUPONT" in xml
    assert "Agence Mendes" in xml


@pytest.mark.skipif(not ORIGINAL_DOCX.exists(), reason="Modèle Word AVS absent")
def test_letter_keeps_csc_when_chosen_for_frontier():
    values = client_field_values(
        {
            "nom": "Martin",
            "prenom": "Claire",
            "npa": "74100",
            "ville": "Annemasse",
            "pays": "France",
        }
    )
    assert values["avs_caisse_id"] == "CSC"
    data = fill_lettre_avs_docx(values)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "Caisse suisse de compensation CSC" in xml
    assert "Claire MARTIN" in xml
