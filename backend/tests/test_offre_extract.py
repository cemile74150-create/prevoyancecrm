"""Tests d'extraction des métadonnées d'offres PDF."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import (  # noqa: E402
    _compact_money_token,
    _find_compagnie,
    _find_duree_ans,
    _find_montant_investi,
    _find_rente_mensuelle,
    extract_offre_fields,
    format_chf,
    format_duree,
    map_extract_to_form,
    offre_fields_for_storage,
)


SAMPLE_TEXT = """
Vaudoise Assurances
Offre de prévoyance 3a

Durée du contrat : 20 ans

Montant investi : CHF 385'000.–
Rente mensuelle garantie : CHF 1'250.–

Conditions générales...
"""


def test_parse_swiss_money():
    assert _compact_money_token("385'000") == 385000.0
    assert _compact_money_token("1'250.–") == 1250.0
    assert _compact_money_token("1.250,50") == 1250.5
    assert _compact_money_token("1178.50") == 1178.5
    assert _compact_money_token("1'243.90") == 1243.9
    assert _compact_money_token("CHF 1\u202f243.90") == 1243.9


def test_format_chf_and_duree():
    assert format_chf(1250) == "CHF 1'250.–"
    assert format_chf(385000) == "CHF 385'000.–"
    assert format_chf(None) == "Non indiqué"
    assert format_duree(20) == "20 ans"
    assert format_duree(None) == "Non indiqué"


def test_find_fields_in_sample_text():
    assert _find_compagnie(SAMPLE_TEXT, "Offre 20 ans VD.pdf") == "Vaudoise"
    assert _find_rente_mensuelle(SAMPLE_TEXT) == 1250.0
    assert _find_montant_investi(SAMPLE_TEXT) == 385000.0
    assert _find_duree_ans(SAMPLE_TEXT, "Offre 20 ans VD.pdf") == 20


def test_filename_hints_when_text_sparse():
    assert _find_compagnie("", "Offre Helvetia 15 ans.pdf") == "Helvetia"
    assert _find_duree_ans("", "Offre Helvetia 15 ans.pdf") == 15


def test_uncertain_values_stay_none():
    assert _find_rente_mensuelle("Bonjour, voici une offre générique sans chiffres utiles.") is None
    assert _find_montant_investi("Document sans montant clair.") is None


def test_storage_payload_shape(monkeypatch):
    def fake_extract(_bytes):
        return SAMPLE_TEXT

    monkeypatch.setattr("pdf_generator._extract_pdf_text", fake_extract)
    # Bypass PDF reader by calling helpers directly via extract with monkeypatch
    monkeypatch.setattr(
        "offre_extract._extract_pdf_text" if False else "pdf_generator._extract_pdf_text",
        fake_extract,
        raising=False,
    )

    # Unit test without real PDF: build storage from known extraction
    extracted = {
        "compagnie": "Vaudoise",
        "rente_mensuelle_garantie": 1250.0,
        "montant_investi": 385000.0,
        "duree": 20,
        "compagnie_label": "Vaudoise",
        "rente_mensuelle_garantie_label": format_chf(1250.0),
        "montant_investi_label": format_chf(385000.0),
        "duree_label": format_duree(20),
    }
    fields = offre_fields_for_storage(extracted)
    assert fields["compagnie"] == "Vaudoise"
    assert fields["rente_mensuelle_garantie"] == 1250.0
    assert fields["montant_investi"] == 385000.0
    assert fields["duree"] == 20
    assert fields["offre_extract"]["duree_label"] == "20 ans"


def test_extract_offre_fields_uses_filename_when_pdf_empty(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: "")
    result = extract_offre_fields(b"%PDF-1.4 empty", filename="Offre 20 ans VD (plus recent).pdf")
    assert result["compagnie"] == "Vaudoise"
    assert result["duree"] == 20
    assert result["rente_mensuelle_garantie"] is None
    assert result["rente_mensuelle_garantie_label"] == "Non indiqué"


def test_extract_person_and_map_to_form(monkeypatch):
    sample = """
Offre OFF-2026-0042
Prénom : Marie
Nom : Dupont
Date de naissance : 15.03.1985
Adresse : Rue du Lac 12
NPA : 1000
Ville : Lausanne
N° de police : POL-998877
Compagnie : Helvetia
Prime annuelle : CHF 4'800.–
Date de début : 01.01.2026
Durée du contrat : 20 ans
"""
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: sample)
    result = extract_offre_fields(b"%PDF-1.4", filename="offre.pdf")
    assert result["prenom"] == "Marie"
    assert result["nom"] == "Dupont"
    assert result["date_naissance"] == "1985-03-15"
    assert result["npa"] == "1000"
    assert result["ville"] == "Lausanne"
    assert result["numero_offre"] == "OFF-2026-0042"
    assert result["reference_police"] == "POL-998877"
    assert result["compagnie"] == "Helvetia"
    assert result["date_debut"] == "2026-01-01"
    assert result["duree"] == 20

    mapped = map_extract_to_form(result, form_type="pilier3_legacy")
    assert mapped["fields"]["prenom"] == "Marie"
    assert mapped["fields"]["nom"] == "Dupont"
    assert mapped["fields"]["duree_contrat"] == "20"
    assert "Helvetia" in (mapped["fields"].get("compagnies") or [])
    assert mapped["numero_offre"] == "OFF-2026-0042"


VAUDOISE_SERENITY_SAMPLE = """
VAUDOISE VIE, Compagnie d'Assurances SA, Place de Milan, C.P. 120, 1001 Lausanne www.vaudoise.ch
1/7 Offre Serenity Benefit Plan sans différé
Prévoyance individuelle libre (pilier 3b)
N° 86510062000281065
Cocontractant
Prénom, nom Monsieur Benoit Stempfel
Date de naissance 19.11.1956
Date d'effet - Echéance 01.11.2026 - 31.10.2041
Durée 15 ans
Contact
Votre conseiller AGENCE MENDES Sàrl
Adresse Bd du Théâtre 9
NPA - Localité 1204 Genève
Téléphone 022 317 72 72
E-mail geneve@vaudoise.ch
Versement annuel, payable par fraction mensuelle de
CHF 4'482.90, la première fois le 30.11.2026
Prime unique 935'000.00
Montant investi dans le fonds Vaudoise Umbrella Fund - Dynamic S 74'143.50
"""


def test_vaudoise_serenity_3p_generic_extract(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: VAUDOISE_SERENITY_SAMPLE)
    result = extract_offre_fields(b"%PDF-1.4", filename="Offre VAUDOISE 935K 15 ans.pdf")
    assert result["form_type_suggere"] == "pilier3"
    assert result["compagnie"] == "Vaudoise"
    assert result["type_pilier"] == "3b"
    assert result["prenom"] == "Benoit"
    assert result["nom"] == "Stempfel"
    assert result["civilite"] == "Monsieur"
    assert result["date_naissance"] == "1956-11-19"
    assert result["duree"] == 15
    assert result["montant_investi"] == 935000.0
    assert result["rente_mensuelle_garantie"] == 4482.9
    assert result["montant_prime"] == 935000.0
    assert result["reference_police"] == "86510062000281065"
    assert result["date_debut"] == "2026-11-01"
    assert result["date_fin"] == "2041-10-31"
    # Adresse agence non inventée comme adresse client
    assert result["email"] is None
    mapped = map_extract_to_form(result, form_type="pilier3")
    assert mapped["fields"]["prenom"] == "Benoit"
    assert mapped["fields"]["montant_investi"] == 935000.0
    assert mapped["fields"]["type_pilier"] == "3b"


def test_branche_rc_alone_does_not_override_pilier3():
    from offre_extract_structured import _detect_branche

    br = _detect_branche(
        "Prévoyance individuelle libre (pilier 3b) Offre Serenity "
        "responsabilité civile mention annexée sans véhicule",
        "Vaudoise RC 640k 15 ans.pdf",
    )
    assert br.get("value") == "pilier3"

