"""Tests hub clients centralisé."""
from __future__ import annotations

from client_hub import (
    apply_hub_to_offre,
    apply_hub_to_suivi,
    person_dict_from_any,
    person_match_key,
)


def test_person_dict_and_apply_hub():
    hub = {
        "prenom": "Jean",
        "nom": "Dupont",
        "date_naissance": "1980-01-15",
        "adresse": "Rue du Lac 1",
        "npa": "1200",
        "ville": "Genève",
        "sexe": "Homme",
        "etat_civil": "Marié(e)",
        "profession": "Ingénieur",
        "pays_residence": "Suisse",
    }
    offre = apply_hub_to_offre(hub)
    assert offre["prenom"] == "Jean"
    assert offre["nom"] == "Dupont"
    assert offre["date_naissance"] == "1980-01-15"
    assert offre["ville"] == "Genève"
    assert offre["pays"] == "Suisse"
    assert offre["situation"] == "Marié(e)"

    suivi = apply_hub_to_suivi(hub)
    assert suivi["prenom"] == "Jean"
    assert suivi["nom"] == "Dupont"
    assert suivi["pays"] == "Suisse"


def test_person_dict_from_offre_fields():
    p = person_dict_from_any({
        "prenom": "Marie",
        "nom": "Martin",
        "date_naissance": "1990-05-01T00:00:00Z",
        "ville": "Lausanne",
    })
    assert p["prenom"] == "Marie"
    assert p["date_naissance"] == "1990-05-01"
    assert p["ville"] == "Lausanne"


def test_person_match_key_stable():
    assert person_match_key("Dupont", "Jean") == person_match_key(" dupont ", "JEAN")
