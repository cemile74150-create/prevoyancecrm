"""Régression urgente : lettres de décompte = 1 identité par caisse (M./Mme)."""
from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from pdf_generator import (
    _map_lettre_decompte,
    client_field_values,
    generate_decompte_letters,
    lpp_profiles_by_person,
    resolve_lpp_assure_for_letter,
)


MADAME = {
    "prenom": "Agnès",
    "nom": "Dupont",
    "sexe": "Femme",
    "avs_number": "756.1111.2222.33",
    "date_naissance": "1985-03-10",
    "adresse": "Route de Test 1",
    "npa": "1200",
    "ville": "Genève",
}

MONSIEUR = {
    "prenom": "Lionel",
    "nom": "Dupont",
    "sexe": "Homme",
    "avs_number": "756.9999.8888.77",
    "date_naissance": "1982-07-22",
}

FUNDS_MIXED = [
    {
        "name": "Swiss Life Team Freizügigkeitspolicen",
        "person": "Madame",
        "address": "General-Guisan-Quai 40\n8022 Zürich",
    },
    {
        "name": "Fondation Institution supplétive LPP",
        "person": "Madame",
        "address": "Weststrasse 50\n8003 Zürich",
    },
    {
        "name": "BVG-Sammelstiftung Swiss Life",
        "person": "Madame",
        "address": "General-Guisan-Quai 40\n8022 Zürich",
    },
    {
        "name": "GastroSocial Pensionskasse",
        "person": "Monsieur",
        "address": "Mühlemattstrasse 23\n5001 Aarau",
    },
]


def _dossier_madame_titulaire():
    """Cas réel : titulaire dossier = Madame, conjoint = Monsieur."""
    return {
        **MADAME,
        "conjoint_prenom": MONSIEUR["prenom"],
        "conjoint_nom": MONSIEUR["nom"],
        "conjoint_avs": MONSIEUR["avs_number"],
        "conjoint_sexe": MONSIEUR["sexe"],
        "conjoint_date_naissance": MONSIEUR["date_naissance"],
        "linked_spouse_id": "spouse-1",
    }, dict(MONSIEUR)


def _dossier_monsieur_titulaire():
    """Titulaire dossier = Monsieur, conjoint = Madame."""
    return {
        **MONSIEUR,
        "conjoint_prenom": MADAME["prenom"],
        "conjoint_nom": MADAME["nom"],
        "conjoint_avs": MADAME["avs_number"],
        "conjoint_sexe": MADAME["sexe"],
        "conjoint_date_naissance": MADAME["date_naissance"],
    }, dict(MADAME)


def test_profiles_map_madame_and_monsieur():
    client, spouse = _dossier_madame_titulaire()
    profiles = lpp_profiles_by_person(client, spouse)
    assert profiles["Madame"]["prenom"] == "Agnès"
    assert profiles["Madame"]["avs_number"] == MADAME["avs_number"]
    assert profiles["Monsieur"]["prenom"] == "Lionel"
    assert profiles["Monsieur"]["avs_number"] == MONSIEUR["avs_number"]


def test_resolve_assure_never_reuses_titulaire_for_spouse_caisse():
    client, spouse = _dossier_madame_titulaire()
    letter_mme = resolve_lpp_assure_for_letter(client, "Madame", spouse=spouse)
    letter_mr = resolve_lpp_assure_for_letter(client, "Monsieur", spouse=spouse)
    assert letter_mme["prenom"] == "Agnès"
    assert letter_mme["avs_number"] == MADAME["avs_number"]
    assert letter_mr["prenom"] == "Lionel"
    assert letter_mr["avs_number"] == MONSIEUR["avs_number"]
    assert letter_mr["prenom"] != letter_mme["prenom"]
    assert letter_mr["avs_number"] != letter_mme["avs_number"]


def test_resolve_assure_when_titulaire_is_monsieur():
    client, spouse = _dossier_monsieur_titulaire()
    letter_mme = resolve_lpp_assure_for_letter(client, "Madame", spouse=spouse)
    letter_mr = resolve_lpp_assure_for_letter(client, "Monsieur", spouse=spouse)
    assert letter_mme["prenom"] == "Agnès"
    assert letter_mr["prenom"] == "Lionel"


def test_map_decompte_uses_assure_identity_only():
    client, spouse = _dossier_madame_titulaire()
    letter_mr = resolve_lpp_assure_for_letter(client, "Monsieur", spouse=spouse)
    values = client_field_values(letter_mr)
    mapping = _map_lettre_decompte(
        values,
        {"fund": FUNDS_MIXED[-1], "lpp_person": "Monsieur"},
    )
    assert mapping["Nom"] == "DUPONT"
    assert mapping["Prenom"] == "Lionel"
    assert mapping["AVS"] == MONSIEUR["avs_number"]
    assert "Lionel" in mapping["Objet"]
    assert "Agnès" not in mapping["Objet"]
    assert "GastroSocial" in (mapping["Adresse"] or mapping["Adresse caisse"])


def test_generate_mixed_caisses_letters_person_isolation():
    client, spouse = _dossier_madame_titulaire()
    results = generate_decompte_letters(client, FUNDS_MIXED, agent_name="Agent", spouse=spouse)
    assert len(results) == 4

    by_caisse = {meta["caisse_name"]: meta for _, meta in results}
    for name in (
        "Swiss Life Team Freizügigkeitspolicen",
        "Fondation Institution supplétive LPP",
        "BVG-Sammelstiftung Swiss Life",
    ):
        meta = by_caisse[name]
        assert meta["lpp_person"] == "Madame"
        assert meta["assure_prenom"] == "Agnès"
        assert meta["assure_avs"] == MADAME["avs_number"]
        assert "Mme" in meta["original_filename"]

    gastro = by_caisse["GastroSocial Pensionskasse"]
    assert gastro["lpp_person"] == "Monsieur"
    assert gastro["assure_prenom"] == "Lionel"
    assert gastro["assure_avs"] == MONSIEUR["avs_number"]
    assert "Mr" in gastro["original_filename"]
    assert gastro["assure_prenom"] != by_caisse["Swiss Life Team Freizügigkeitspolicen"]["assure_prenom"]


def test_generate_letters_pdf_contains_correct_names():
    client, spouse = _dossier_madame_titulaire()
    results = generate_decompte_letters(
        client,
        [FUNDS_MIXED[0], FUNDS_MIXED[-1]],
        agent_name="Agent",
        spouse=spouse,
    )
    assert len(results) == 2
    mme_pdf, mme_meta = results[0]
    mr_pdf, mr_meta = results[1]
    assert mme_meta["lpp_person"] == "Madame"
    assert mr_meta["lpp_person"] == "Monsieur"

    try:
        import fitz

        mme_text = fitz.open(stream=mme_pdf, filetype="pdf")[0].get_text()
        mr_text = fitz.open(stream=mr_pdf, filetype="pdf")[0].get_text()
        assert "Agnès" in mme_text or "Agnes" in mme_text or MADAME["avs_number"] in mme_text
        assert "Lionel" in mr_text or MONSIEUR["avs_number"] in mr_text
        assert MADAME["avs_number"] not in mr_text
        assert MONSIEUR["avs_number"] not in mme_text
    except ImportError:
        assert PdfReader(io.BytesIO(mme_pdf)).pages
        assert PdfReader(io.BytesIO(mr_pdf)).pages


def test_missing_person_rejected():
    client, spouse = _dossier_madame_titulaire()
    with pytest.raises(ValueError, match="personne"):
        generate_decompte_letters(
            client,
            [{"name": "Caisse X", "address": "1 rue", "person": ""}],
            spouse=spouse,
        )


def test_missing_spouse_identity_rejected_for_monsieur_caisse():
    """Dossier Madame seule : caisse Monsieur ne doit pas retomber sur Agnès."""
    client = dict(MADAME)
    with pytest.raises(ValueError, match="Monsieur"):
        resolve_lpp_assure_for_letter(client, "Monsieur", spouse=None)


def test_assert_person_pdf_equals_letter():
    client, spouse = _dossier_madame_titulaire()
    letter = resolve_lpp_assure_for_letter(client, "Madame", spouse=spouse)
    assert letter["civilite"] == "Madame"
    letter2 = resolve_lpp_assure_for_letter(client, "Monsieur", spouse=spouse)
    assert letter2["civilite"] == "Monsieur"
    assert letter["avs_number"] != letter2["avs_number"]
