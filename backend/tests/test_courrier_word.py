"""Tests génération courrier Word Suivi 3P."""
import io
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from courrier_word import (  # noqa: E402
    TEMPLATE_PATH,
    courrier_filename,
    generate_courrier_docx,
    greeting_for_client,
    closing_civility_for_client,
    format_gain_chf,
    infer_country,
    is_eligible_for_courrier,
    optimisation_fiscale_gain,
    recipient_lines,
    format_perly_date,
)


def test_homme_seul_lines_and_greeting():
    client = {
        "sexe": "Homme",
        "prenom": "Antonio",
        "nom": "AFONSO",
        "adresse": "Rue de Lausanne, 63",
        "npa": "1202",
        "ville": "Genève",
        "pays": "Suisse",
    }
    assert recipient_lines(client) == [
        "M. Antonio AFONSO",
        "Rue de Lausanne, 63",
        "1202 Genève",
        "Suisse",
    ]
    assert greeting_for_client(client) == "Monsieur,"
    assert closing_civility_for_client(client) == "Monsieur"


def test_femme_seule():
    client = {
        "sexe": "Femme",
        "prenom": "Olga",
        "nom": "PEREIRA DA SILVA",
        "adresse": "Rue de Lausanne, 63",
        "npa": "1202",
        "ville": "Genève",
    }
    lines = recipient_lines(client)
    assert lines[0] == "Mme Olga PEREIRA DA SILVA"
    assert lines[-1] == "Suisse"
    assert greeting_for_client(client) == "Madame,"
    assert closing_civility_for_client(client) == "Madame"


def test_couple_mr_puis_mme():
    client = {
        "sexe": "Homme",
        "prenom": "Antonio",
        "nom": "AFONSO",
        "conjoint_prenom": "Olga",
        "conjoint_nom": "PEREIRA DA SILVA AFONSO",
        "adresse": "Rue de Lausanne, 63",
        "npa": "1202",
        "ville": "Genève",
    }
    lines = recipient_lines(client)
    assert lines[0] == "M. Antonio AFONSO"
    assert lines[1] == "Mme Olga PEREIRA DA SILVA AFONSO"
    assert lines[2] == "Rue de Lausanne, 63"
    assert lines[3] == "1202 Genève"
    assert lines[4] == "Suisse"
    assert greeting_for_client(client) == "Madame, Monsieur,"
    assert closing_civility_for_client(client) == "Madame, Monsieur"


def test_no_empty_spouse_or_placeholders():
    client = {"prenom": "Xqzt", "nom": "Rossi", "conjoint": "  ", "adresse_complement": None, "pays": None}
    lines = recipient_lines(client)
    assert lines == ["Xqzt Rossi"]
    joined = " | ".join(lines)
    assert "undefined" not in joined
    assert "null" not in joined
    assert "[" not in joined
    assert "M. " not in joined
    assert "Mme " not in joined


def test_couple_civilite_depuis_prenom_sans_sexe():
    """Si le sexe n'est pas renseigné, M./Mme viennent des prénoms CRM."""
    client = {
        "prenom": "Antonio",
        "nom": "AFONSO",
        "conjoint_prenom": "Olga",
        "conjoint_nom": "PEREIRA DA SILVA AFONSO",
        "adresse": "Rue de Lausanne, 63",
        "npa": "1202",
        "ville": "Genève",
    }
    lines = recipient_lines(client)
    assert lines[0] == "M. Antonio AFONSO"
    assert lines[1] == "Mme Olga PEREIRA DA SILVA AFONSO"
    assert lines[2] == "Rue de Lausanne, 63"
    assert lines[3] == "1202 Genève"
    assert lines[4] == "Suisse"
    assert greeting_for_client(client) == "Madame, Monsieur,"
    alone = {"prenom": "Léa", "nom": "Rossi"}
    assert recipient_lines(alone)[0] == "Mme Léa Rossi"
    assert greeting_for_client(alone) == "Madame,"


def test_civility_from_prenom_compose_et_ambigu():
    from courrier_word import CIV_F, CIV_M, civility_from_prenom

    assert civility_from_prenom("Anne-Lise") == CIV_F
    assert civility_from_prenom("Lamri Nathalie-Yasmina") == CIV_F
    assert civility_from_prenom("Joo Ann Natalia") == CIV_F
    assert civility_from_prenom("Quy Dat") == CIV_M
    assert civility_from_prenom("Camille") is None
    assert civility_from_prenom("Maxime") is None
    assert civility_from_prenom("Karell") is None
    assert civility_from_prenom("Marta") == CIV_F
    assert civility_from_prenom("Perrine") == CIV_F
    assert civility_from_prenom("Sabine") == CIV_F


def test_infer_country_npa_and_city():
    assert infer_country({"npa": "1202", "ville": "Genève"}) == "Suisse"
    assert infer_country({"npa": "74000", "ville": "Annecy"}) == "France"
    assert infer_country({"ville": "Paris"}) == "France"
    assert infer_country({"adresse": "20 Place des Aviateurs - F 74580 VIRY"}) == "France"
    assert infer_country({"pays": "CH"}) == "Suisse"
    assert infer_country({"ville": "Atlantis"}) == ""


def test_filename_couple():
    name = courrier_filename({
        "nom": "AFONSO",
        "prenom": "Antonio",
        "conjoint_nom": "PEREIRA DA SILVA AFONSO",
        "conjoint_prenom": "Olga",
    })
    assert name.startswith("Courrier_Optimisation_Fiscale_AFONSO_Antonio")
    assert "Olga" in name
    assert name.endswith(".docx")


def test_gain_matches_table_and_threshold():
    fortune = {
        "display_label": "Analyse optimisation fiscale",
        "source_folder": "PDF - Analyse Fortune",
        "extracted_gain_fiscal": 119,
        "is_deleted": False,
    }
    pilier = {
        "display_label": "Analyse 3e Pilier",
        "extracted_gain_fiscal": 2000,
        "is_deleted": False,
    }
    # Même champ que la colonne « GAIN FISCAL » du tableau (ex. Afonso 3 504 CHF)
    client = {"gain_fiscal_estime": 3504}
    assert optimisation_fiscale_gain(client, [fortune, pilier]) == 3504
    assert is_eligible_for_courrier(client, [fortune, pilier]) is True
    assert is_eligible_for_courrier({"gain_fiscal_estime": 250}, []) is False
    assert is_eligible_for_courrier({"gain_fiscal_estime": 251}, []) is True
    assert is_eligible_for_courrier({}, []) is False
    assert is_eligible_for_courrier({}, [fortune]) is False
    fortune2 = {**fortune, "extracted_gain_fiscal": 251}
    assert is_eligible_for_courrier({}, [fortune2]) is True


def test_date_fr():
    assert format_perly_date(date(2026, 8, 14)) == "Perly, le 14 août 2026"
    assert format_perly_date(date(2026, 8, 1)) == "Perly, le 1 août 2026"


def test_format_gain_chf():
    assert format_gain_chf(3504) == "3 504 CHF"
    assert format_gain_chf(119) == "119 CHF"
    assert format_gain_chf(None) == ""


def test_real_docx_keeps_template_and_replaces_fields():
    assert TEMPLATE_PATH.is_file()
    client = {
        "sexe": "Femme",
        "prenom": "Cemile",
        "nom": "Demirtas",
        "conjoint_prenom": "Paulo",
        "conjoint_nom": "Mendes",
        "adresse": "Route de Genève 10",
        "npa": "1200",
        "ville": "Genève",
        "gain_fiscal_estime": 3504,
    }
    data, filename = generate_courrier_docx(client, when=date(2026, 8, 14))
    assert filename.endswith(".docx")
    assert data[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "word/document.xml" in names
        assert "word/header1.xml" in names
        assert "word/footer1.xml" in names
        assert "word/media/image1.jpg" in names
        xml = zf.read("word/document.xml").decode("utf-8")
        header = zf.read("word/header1.xml").decode("utf-8")
        footer = zf.read("word/footer1.xml").decode("utf-8")
    assert "[Prénom]" not in xml
    assert "M. Paulo Mendes" in xml
    assert "Mme Cemile Demirtas" in xml
    assert "Route de Genève 10" in xml
    assert "1200 Genève" in xml
    assert "Suisse" in xml
    assert "Perly, le 14 août 2026" in xml
    assert "<w:rPr><w:r " not in xml
    plain = _plain_text(xml)
    assert plain.count("Madame, Monsieur") >= 2
    assert "3 504 CHF" in xml
    assert "0 000 CHF" not in xml
    assert "[Madame]" not in xml
    assert "[Monsieur]" not in xml
    assert "Nous vous remercions de votre confiance" in xml
    assert "Agence Mendes" in xml
    assert "Alberto Mendes" in xml
    assert "18 août 2026" not in xml
    orig = zipfile.ZipFile(TEMPLATE_PATH)
    assert orig.read("word/header1.xml") == zipfile.ZipFile(io.BytesIO(data)).read("word/header1.xml")
    orig.close()
    assert footer
    assert header


def _plain_text(xml: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml))


def test_real_docx_personne_seule_madame_only():
    client = {
        "sexe": "Femme",
        "prenom": "Olga",
        "nom": "PEREIRA",
        "adresse": "Rue de Lausanne, 63",
        "npa": "1202",
        "ville": "Genève",
        "gain_fiscal_estime": 1190,
    }
    data, _ = generate_courrier_docx(client, when=date(2026, 8, 17))
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    plain = _plain_text(xml)
    assert "Madame," in xml
    assert "Monsieur" not in xml
    assert "1 190 CHF" in xml
    assert "Madame, Monsieur" not in plain
    assert "M. " not in xml
    assert "Mme Olga PEREIRA" in xml
    assert "<w:rPr><w:r " not in xml


def test_real_docx_personne_seule_monsieur_only():
    client = {
        "sexe": "Homme",
        "prenom": "Antonio",
        "nom": "AFONSO",
        "adresse": "Rue de Lausanne, 63",
        "npa": "1202",
        "ville": "Genève",
        "gain_fiscal_estime": 3504,
    }
    data, _ = generate_courrier_docx(client, when=date(2026, 8, 17))
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    plain = _plain_text(xml)
    assert "Monsieur," in xml
    assert "Madame" not in xml
    assert "Madame, Monsieur" not in plain
    assert "M. Antonio AFONSO" in xml
    assert "Mme " not in xml
    assert "<w:rPr><w:r " not in xml
