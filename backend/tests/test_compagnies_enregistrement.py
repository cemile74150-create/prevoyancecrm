"""Cohérence compagnies demande d'offre → enregistrement des réponses.

Ces tests n'ouvrent aucune base et ne modifient aucun dossier client.
"""
import copy

import pytest

from demandes_offres_3p import (
    COMPAGNIES_DEFAUT,
    STATUT_ENVOYEE,
    STATUT_OFFRE_RECUE,
    apply_form_fields,
    build_reponses_compagnies,
    compagnies_enregistrement,
    effective_compagnies,
    resolve_compagnie_saisie,
    resolve_statut_apres_reception_offre,
    serialize_demande,
    upsert_company_offre,
)
from offre_form_types import (
    champs_compagnies_sollicitees,
    compagnies_selectionnees,
    options_compagnies_formulaire,
    referentiel_compagnies,
)


def _champ(form_type: str) -> str:
    fields = champs_compagnies_sollicitees(form_type)
    assert fields, form_type
    return fields[0]["name"]


def _demande_batiment(selection):
    return {
        "id": "demande-test",
        "form_type": "assurances_particulier",
        "statut": STATUT_ENVOYEE,
        "date_envoi": "2026-10-01T00:00:00+00:00",
        "compagnies": [],
        "offres": [],
        "form_payload": {_champ("assurances_particulier"): list(selection)},
    }


def test_referentiel_reconnait_gvb_sans_mode_envoi_ni_liste_legacy():
    assert "GVB" not in COMPAGNIES_DEFAUT
    options = options_compagnies_formulaire("assurances_particulier")
    assert options[:3] == ["Axa", "Generali", "La Mobilière"]
    assert "GVB" in options
    assert "Rouky" in options
    assert "Envoi du formulaire" not in options
    assert "PAX" not in options
    ref = referentiel_compagnies(COMPAGNIES_DEFAUT)
    assert "GVB" in ref
    assert "Envoi du formulaire" not in ref
    assert ref[:1] == ["PAX"]


def test_batiment_gvb_disponible_et_rattache_sans_modifier_les_offres():
    doc = _demande_batiment(["GVB", "Envoi du formulaire"])
    offre_existante = {
        "id": "o-helvetia",
        "compagnie": "Helvetia",
        "statut": "Offre reçue",
        "date_reception": "2026-01-01",
        "documents": [{"id": "pdf-1"}],
    }
    doc["offres"] = [offre_existante]
    avant = copy.deepcopy(doc)

    assert effective_compagnies(doc) == ["GVB"]
    menu = compagnies_enregistrement(doc)
    assert menu[0] == "GVB"
    assert "Envoi du formulaire" not in menu
    assert "Axa" in menu

    cards = build_reponses_compagnies(doc)
    assert cards[0]["compagnie"] == "GVB"
    assert cards[0]["has_offre"] is False
    assert any(c["compagnie"] == "Helvetia" and c["has_offre"] for c in cards)
    assert doc["offres"] == avant["offres"]
    assert doc["compagnies"] == avant["compagnies"]

    nom = resolve_compagnie_saisie(doc, "gvb", doc["offres"])
    assert nom == "GVB"
    offres = upsert_company_offre(
        doc["offres"],
        {
            "id": "o-gvb",
            "compagnie": nom,
            "statut": "Offre reçue",
            "date_reception": "2026-10-14",
            "documents": [{"id": "pdf-gvb"}],
        },
    )
    assert doc["offres"][0]["compagnie"] == "Helvetia"
    assert doc["offres"][0]["documents"] == [{"id": "pdf-1"}]
    gvb = next(o for o in offres if o["compagnie"] == "GVB")
    assert gvb["id"] == "o-gvb"
    assert resolve_statut_apres_reception_offre(doc, offres) == STATUT_OFFRE_RECUE


def test_trois_compagnies_restent_rattachees_a_la_demande():
    doc = _demande_batiment(["GVB", "Helvetia", "Axa"])
    assert effective_compagnies(doc) == ["GVB", "Helvetia", "Axa"]
    assert compagnies_enregistrement(doc)[:3] == ["GVB", "Helvetia", "Axa"]

    offres = []
    for nom in ("GVB", "Helvetia", "Axa"):
        assert resolve_statut_apres_reception_offre(doc, offres) == STATUT_ENVOYEE
        offres = upsert_company_offre(
            offres,
            {
                "id": f"o-{nom}",
                "compagnie": resolve_compagnie_saisie(doc, nom, offres),
                "statut": "Offre reçue",
                "date_reception": "2026-10-14",
            },
        )
    assert [o["compagnie"] for o in offres] == ["GVB", "Helvetia", "Axa"]
    assert resolve_statut_apres_reception_offre(doc, offres) == STATUT_OFFRE_RECUE
    cards = build_reponses_compagnies({**doc, "offres": offres})
    assert [(c["compagnie"], c["has_offre"]) for c in cards] == [
        ("GVB", True),
        ("Helvetia", True),
        ("Axa", True),
    ]


def test_autres_produits_utilisent_leur_propre_liste():
    for form_type in (
        "menage_rc",
        "vehicule",
        "pilier3",
        "animaux",
        "protection_juridique_particulier",
        "rc_entreprise",
    ):
        options = options_compagnies_formulaire(form_type)
        assert options, form_type
        assert "Envoi du formulaire" not in options
        assert "GVB" not in options
        chosen = options[0]
        payload = {_champ(form_type): [chosen, "Envoi du formulaire"]}
        assert compagnies_selectionnees(form_type, payload) == [chosen]
        doc = {
            "form_type": form_type,
            "form_payload": payload,
            "compagnies": [],
            "offres": [],
        }
        assert compagnies_enregistrement(doc)[0] == chosen


def test_demande_historique_et_offre_deja_attribuee_restees_intactes():
    offre = {
        "id": "o1",
        "compagnie": "AXA",
        "statut": "Offre reçue",
        "date_reception": "2026-01-05",
        "documents": [{"id": "doc-axa", "original_filename": "axa.pdf"}],
    }
    doc = {
        "id": "hist",
        "form_type": "pilier3_legacy",
        "statut": STATUT_ENVOYEE,
        "compagnies": ["AXA", "Helvetia"],
        "offres": [offre],
        "form_payload": {},
    }
    avant = copy.deepcopy(doc)
    assert effective_compagnies(doc) == ["AXA", "Helvetia"]
    menu = compagnies_enregistrement(doc)
    assert menu[:2] == ["AXA", "Helvetia"]
    assert "GVB" not in menu
    assert "PAX" in menu
    out = serialize_demande(doc)
    assert out["compagnies"] == ["AXA", "Helvetia"]
    assert out["compagnies_sollicitees"] == ["AXA", "Helvetia"]
    assert out["offres"][0]["compagnie"] == "AXA"
    assert out["offres"][0]["documents"][0]["id"] == "doc-axa"
    assert doc == avant
    assert resolve_compagnie_saisie(doc, "axa", doc["offres"]) == "AXA"
    with pytest.raises(ValueError):
        resolve_compagnie_saisie(doc, "Envoi du formulaire", doc["offres"])


def test_enregistrement_formulaire_copie_les_compagnies_sans_toucher_aux_offres():
    name = _champ("assurances_particulier")
    target = {
        "form_type": "assurances_particulier",
        "compagnies": ["AXA"],
        "offres": [{"id": "o1", "compagnie": "AXA", "documents": [{"id": "d1"}]}],
    }
    avant_offres = copy.deepcopy(target["offres"])
    apply_form_fields(
        target,
        {
            "form_type": "assurances_particulier",
            "form_payload": {name: ["GVB", "Vaudoise"]},
        },
    )
    assert target["compagnies"] == ["GVB", "Vaudoise"]
    assert target["offres"] == avant_offres
