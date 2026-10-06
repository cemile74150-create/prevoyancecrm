"""Préremplissage PDF → champs réels des formulaires d'offre."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import extract_offre_fields, map_extract_to_form  # noqa: E402
from offre_form_types import empty_form_payload, list_form_types, load_form_schema, schema_field_names  # noqa: E402
from offre_pdf_form_fill import fill_form_payload_from_pdf  # noqa: E402


PILIER_TEXT = """
Offre de prévoyance 3a
OFF-2026-0042
Civilité : Madame
Prénom : Marie
Nom : Dupont
Date de naissance : 15.03.1985
Adresse : Rue du Lac 12
NPA : 1000
Ville : Lausanne
Pays : Suisse
Nationalité : Suisse
Profession : Enseignante
Email : marie.dupont@example.ch
Téléphone : 021 555 12 12
N° de police : POL-998877
Compagnie : Helvetia
Prime annuelle : CHF 4'800.–
Date de début : 01.01.2026
Durée du contrat : 20 ans
"""

VEHICULE_TEXT = """
Prénom : Paul
Nom : Martin
Date de naissance : 02.02.1980
Adresse : Avenue de la Gare 4
NPA : 1003
Ville : Lausanne
Marque du véhicule : Volkswagen
Immatriculation : VD 123456
"""


def _first_field(form_type: str, label: str) -> dict:
    schema = load_form_schema(form_type) or {}
    for field in schema.get("fields") or []:
        if field.get("label") == label and field.get("type") not in {"section", "html"}:
            return field
    raise AssertionError(f"{form_type} n'a pas de champ {label!r}")


def test_pilier3_fills_real_schema_fields_not_generic_keys():
    extracted = {
        "prenom": "Marie",
        "nom": "Dupont",
        "civilite": "Madame",
        "date_naissance": "1985-03-15",
        "adresse": "Rue du Lac 12",
        "npa": "1000",
        "ville": "Lausanne",
        "pays": "Suisse",
        "profession": "Enseignante",
        "email": "marie.dupont@example.ch",
        "montant_prime": 4800,
        "duree": 20,
        "date_debut": "2026-01-01",
        "compagnie": "Helvetia",
        "type_pilier": "3a",
        "periodicite": "Annuel",
        "reference_police": "POL-998877",
        "_text": PILIER_TEXT,
    }
    filled = fill_form_payload_from_pdf("pilier3", extracted, text=PILIER_TEXT)
    payload = filled["form_payload"]
    names = schema_field_names("pilier3")
    assert set(payload) <= names
    assert "prenom" not in payload
    assert "nom" not in payload

    assert payload[_first_field("pilier3", "Prénom")["name"]] == "Marie"
    assert payload[_first_field("pilier3", "Nom")["name"]] == "Dupont"
    assert payload[_first_field("pilier3", "Civilité")["name"]] == "Madame"
    assert payload[_first_field("pilier3", "Sexe")["name"]] == "Féminin"
    assert payload[_first_field("pilier3", "Date de naissance")["name"]] == "15.03.1985"
    assert payload[_first_field("pilier3", "Adresse postale")["name"]] == "Rue du Lac 12"
    assert payload[_first_field("pilier3", "Code postal")["name"]] == "1000"
    assert payload[_first_field("pilier3", "Ville")["name"]] == "Lausanne"
    assert payload[_first_field("pilier3", "Pays")["name"]] == "Suisse"
    assert payload[_first_field("pilier3", "Profession")["name"]] == "Enseignante"
    assert payload[_first_field("pilier3", "Montant de la prime")["name"]] == "4800"
    assert payload[_first_field("pilier3", "Durée du contrat")["name"]] == "20"
    assert payload[_first_field("pilier3", "Date de début")["name"]] == "01.01.2026"
    assert payload[_first_field("pilier3", "Type de pilier")["name"]] == "Pilier lié 3a"
    assert payload[_first_field("pilier3", "Périodicité de la prime")["name"]] == "Annuel"
    companies = payload[_first_field("pilier3", "La demande doit être faite aux compagnies suivantes :")["name"]]
    assert companies == ["Helvetia"]

    # Champ du médecin (2e adresse) et champs absents du PDF : pas inventés.
    doctor = "input_72.1"
    empty = empty_form_payload("pilier3")
    assert payload[doctor] == empty[doctor]
    taille = _first_field("pilier3", "Taille")["name"]
    assert payload[taille] == empty[taille]
    assert taille not in filled["filled_keys"]
    agent = _first_field("pilier3", "Prénom de l'agent")["name"]
    assert payload[agent] == empty[agent]
    assert agent not in filled["filled_keys"]


def test_vehicule_uses_its_own_fields():
    extracted = {
        "prenom": "Paul",
        "nom": "Martin",
        "date_naissance": "1980-02-02",
        "adresse": "Avenue de la Gare 4",
        "npa": "1003",
        "ville": "Lausanne",
        "_text": VEHICULE_TEXT,
    }
    filled = fill_form_payload_from_pdf("vehicule", extracted, text=VEHICULE_TEXT)
    payload = filled["form_payload"]
    assert set(payload) <= schema_field_names("vehicule")
    assert payload[_first_field("vehicule", "Prénom")["name"]] == "Paul"
    assert payload[_first_field("vehicule", "Nom")["name"]] == "Martin"
    assert payload[_first_field("vehicule", "Marque du véhicule")["name"]] == "Volkswagen"
    # Clé 3e pilier absente du schéma véhicule.
    assert "input_31" not in payload or "input_31" in schema_field_names("vehicule")
    assert _first_field("pilier3", "Montant de la prime")["name"] not in payload or (
        _first_field("pilier3", "Montant de la prime")["name"] in schema_field_names("vehicule")
    )


def test_map_extract_pilier3_and_legacy_shapes(monkeypatch):
    monkeypatch.setattr("pdf_generator._extract_pdf_text", lambda _b: PILIER_TEXT)
    extracted = extract_offre_fields(b"%PDF-1.4", filename="offre.pdf")
    legacy = map_extract_to_form(extracted, form_type="pilier3_legacy")
    assert legacy["fields"]["prenom"] == "Marie"
    assert legacy["fields"]["nom"] == "Dupont"
    assert "prenom" in legacy["form_payload"]
    assert legacy["filled_keys"] == []

    schema = map_extract_to_form(extracted, form_type="pilier3")
    assert schema["fields"]["prenom"] == "Marie"
    payload = schema["form_payload"]
    assert payload[_first_field("pilier3", "Prénom")["name"]] == "Marie"
    assert "prenom" not in payload
    assert schema["filled_keys"]
    assert _first_field("pilier3", "Prénom")["name"] in schema["filled_keys"]


def test_every_active_form_type_stays_inside_its_schema():
    extracted = {
        "prenom": "Marie",
        "nom": "Dupont",
        "date_naissance": "1985-03-15",
        "adresse": "Rue du Lac 12",
        "npa": "1000",
        "ville": "Lausanne",
        "compagnie": "Helvetia",
        "montant_prime": 1200,
        "_text": "Prénom : Marie\nNom : Dupont\nMarque du véhicule : Volkswagen\n",
    }
    for meta in list_form_types(active_only=True):
        fid = meta["id"]
        if fid == "pilier3_legacy":
            continue
        filled = fill_form_payload_from_pdf(fid, extracted, text=extracted["_text"])
        allowed = schema_field_names(fid)
        assert set(filled["form_payload"]) <= allowed, fid
        assert set(filled["filled_keys"]) <= allowed, fid


def test_absent_values_are_not_invented():
    extracted = {"_text": "Document sans identité ni montant."}
    filled = fill_form_payload_from_pdf("pilier3", extracted, text=extracted["_text"])
    empty = empty_form_payload("pilier3")
    assert filled["form_payload"][_first_field("pilier3", "Prénom")["name"]] == empty[
        _first_field("pilier3", "Prénom")["name"]
    ]
    assert filled["form_payload"][_first_field("pilier3", "Montant de la prime")["name"]] == empty[
        _first_field("pilier3", "Montant de la prime")["name"]
    ]
    assert filled["filled_keys"] == []
