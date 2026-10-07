"""Recherche par nom et payload d'envoi — modifier une offre, sans numéro OFF saisi."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from demandes_offres_3p import (  # noqa: E402
    client_identity_for_search,
    demande_matches_client_name,
    modifier_client_search_hit,
    payload_modification_leosoft,
    payload_nouvelle_demande_pdf,
)
from offre_form_types import load_form_schema  # noqa: E402


def _field_name(form_type: str, label: str) -> str:
    schema = load_form_schema(form_type) or {}
    for field in schema.get("fields") or []:
        if field.get("label") == label and field.get("type") not in {"section", "html"}:
            return field["name"]
    raise AssertionError(f"{form_type} n'a pas de champ {label!r}")


def test_recherche_par_nom_liste_plusieurs_clients_ignore_le_numero():
    marie = {
        "id": "1",
        "prenom": "Marie",
        "nom": "Dupont",
        "form_type": "pilier3",
        "form_type_label": "3e pilier",
        "created_at": "2026-03-12T10:00:00",
        "numero": "OFF-2026-0042",
        "statut": "Demande envoyée",
    }
    paul = {
        "id": "2",
        "prenom": "Paul",
        "nom": "Martin",
        "form_type": "vehicule",
        "form_type_label": "Véhicule",
        "date_envoi": "2026-01-02T08:00:00",
        "numero": "OFF-2026-0007",
        "statut": "Offre reçue",
    }
    autre = {
        "id": "3",
        "prenom": "Marie",
        "nom": "Durand",
        "form_type": "pilier3",
        "form_type_label": "3e pilier",
        "created_at": "2026-02-01T09:00:00",
        "numero": "OFF-2025-0099",
    }
    docs = [marie, paul, autre]

    dupont = [modifier_client_search_hit(d) for d in docs if demande_matches_client_name(d, "Dupont")]
    assert len(dupont) == 1
    assert dupont[0]["prenom"] == "Marie"
    assert dupont[0]["nom"] == "Dupont"
    assert dupont[0]["form_type"] == "pilier3"
    assert dupont[0]["form_type_label"] == "3e pilier"
    assert dupont[0]["date"] == "2026-03-12"
    assert dupont[0]["id"] == "1"

    maries = [d["id"] for d in docs if demande_matches_client_name(d, "marie")]
    assert maries == ["1", "3"]
    assert demande_matches_client_name(marie, "marie dupont") is True
    assert demande_matches_client_name(marie, "OFF-2026-0042") is False
    assert demande_matches_client_name(paul, "Martin") is True
    # Le nom de l'agent ne sert pas de clé de recherche.
    agent_only = {"id": "4", "prenom": "Luc", "nom": "Bernard", "agent_label": "Paul Martin"}
    assert demande_matches_client_name(agent_only, "Martin") is False
    assert demande_matches_client_name({"prenom": "Hans", "nom": "Müller"}, "muller") is True


def test_recherche_lit_le_nom_dans_form_payload_sans_reecrire():
    prenom = _field_name("pilier3", "Prénom")
    nom = _field_name("pilier3", "Nom")
    doc = {
        "id": "p",
        "prenom": "",
        "nom": "",
        "form_type": "pilier3",
        "form_type_label": "3e pilier",
        "form_payload": {prenom: "Alice", nom: "Bernard"},
        "numero": "OFF-2024-0001",
        "created_at": "2026-04-01",
    }
    original = dict(doc["form_payload"])
    assert demande_matches_client_name(doc, "Bernard") is True
    assert doc["form_payload"] == original
    assert doc["nom"] == ""
    assert doc["prenom"] == ""
    hit = modifier_client_search_hit(doc)
    ident = client_identity_for_search(doc)
    assert ident["prenom"] == "Alice"
    assert ident["nom"] == "Bernard"
    assert hit["prenom"] == "Alice"
    assert hit["nom"] == "Bernard"
    assert hit["date"] == "2026-04-01"
    assert "form_payload" not in hit


def test_payload_pdf_hors_leosoft_formulaire_complet_sans_numero():
    original = {"input_1": "Marie", "input_2": "Dupont", "input_9": "Lausanne"}
    edited = {**original, "input_9": "Genève"}
    changes = [{
        "field": "form_payload.input_9",
        "label": "Ville",
        "old": "Lausanne",
        "new": "Genève",
    }]
    body = payload_nouvelle_demande_pdf(
        form_type="pilier3",
        form_payload=edited,
        note="Merci de reprendre la ville",
        changes=changes,
    )
    assert "numero" not in body
    assert "id" not in body
    assert body["form_type"] == "pilier3"
    assert body["form_payload"] == edited
    assert body["form_payload"]["input_1"] == "Marie"
    assert body["form_payload"]["input_2"] == "Dupont"
    assert body["form_payload"]["input_9"] == "Genève"
    assert "Merci de reprendre la ville" in body["commentaires"]
    assert "Modifications :" in body["commentaires"]
    assert "Ville" in body["commentaires"]
    assert "Lausanne" in body["commentaires"]
    assert "Genève" in body["commentaires"]
    assert body["note_service_offre"] == body["commentaires"]


def test_payload_leosoft_garde_le_formulaire_complet_et_les_seuls_changements():
    stored = {"input_1": "Paul", "input_2": "Martin", "input_9": "Lausanne"}
    edited = {**stored, "input_9": "Morges"}
    changes = [{
        "field": "form_payload.input_9",
        "label": "Ville",
        "old": "Lausanne",
        "new": "Morges",
    }]
    body = payload_modification_leosoft(
        form_type="vehicule",
        form_type_label="Véhicule",
        form_payload=edited,
        note=None,
        changes=changes,
    )
    assert "numero" not in body
    assert body["form_payload"] == edited
    assert body["form_payload"]["input_1"] == "Paul"
    assert body["changes"] == changes
    assert body["form_type"] == "vehicule"
    assert body["note_service_offre"] is None


def test_recherche_par_numero_off_trouve_la_demande_existante():
    from demandes_offres_3p import find_demande_by_offre_numero, normalize_offre_numero

    docs = [
        {"id": "1", "numero": "OFF-2026-0042", "nom": "Dupont", "prenom": "Marie"},
        {"id": "2", "numero": "OFF-2026-0007", "nom": "Martin", "prenom": "Paul"},
    ]
    assert normalize_offre_numero("off-2026-042") == "OFF-2026-0042"
    assert normalize_offre_numero("OFF 2026 0042") == "OFF-2026-0042"
    found = find_demande_by_offre_numero(docs, "OFF-2026-0042")
    assert found["id"] == "1"
    assert found["numero"] == "OFF-2026-0042"
    assert find_demande_by_offre_numero(docs, "Marie") is None
    assert demande_matches_client_name(docs[0], "Dupont") is True
    assert demande_matches_client_name(docs[0], "OFF-2026-0042") is False


def test_pdf_avec_off_existant_rattache_sans_doublon():
    from demandes_offres_3p import resolve_pdf_offre_target

    existing = {
        "id": "demande-42",
        "numero": "OFF-2026-0042",
        "email_subject": "OFF-2026-0042-Dupont Jean -3e pilier",
        "statut": "Offre reçue",
        "prenom": "Marie",
        "nom": "Dupont",
    }
    autre = {
        "id": "demande-99",
        "numero": "OFF-2026-0099",
        "email_subject": "OFF-2026-0099-Martin Paul",
    }
    decision = resolve_pdf_offre_target([existing, autre], "OFF-2026-0042")
    assert decision["action"] == "rattacher"
    assert decision["demande"]["id"] == "demande-42"
    assert decision["demande"]["numero"] == "OFF-2026-0042"
    assert decision["numero"] == "OFF-2026-0042"
    assert decision["email_subject"] == "OFF-2026-0042-Dupont Jean -3e pilier"
    assert decision["action"] != "creer"
    ids = {existing["id"], autre["id"]}
    assert decision["demande"]["id"] in ids
    assert len([d for d in (existing, autre) if d["numero"] == "OFF-2026-0042"]) == 1


def test_pdf_sans_off_cree_et_off_inconnu_ne_cree_pas():
    from demandes_offres_3p import resolve_pdf_offre_target

    existing = {"id": "demande-42", "numero": "OFF-2026-0042", "email_subject": "fil"}
    sans = resolve_pdf_offre_target([existing], "")
    assert sans["action"] == "creer"
    assert sans["demande"] is None
    assert sans["numero"] is None
    inconnu = resolve_pdf_offre_target([existing], "OFF-2026-0001")
    assert inconnu["action"] == "refus"
    assert inconnu["demande"] is None
    assert inconnu["numero"] == "OFF-2026-0001"


def test_kanban_et_page_gardent_off_nom_et_colonnes():
    root = Path(__file__).resolve().parents[2]
    page = (root / "frontend" / "src" / "pages" / "ModifierOffre.js").read_text(encoding="utf-8")
    kanban = (root / "frontend" / "src" / "lib" / "demandesOffres.js").read_text(encoding="utf-8")
    dashboard = (root / "frontend" / "src" / "pages" / "DemandesOffres.js").read_text(encoding="utf-8")
    reponses = (root / "frontend" / "src" / "pages" / "GestionReponsesOffres.js").read_text(encoding="utf-8")
    schema = (root / "frontend" / "src" / "components" / "OffreSchemaForm.js").read_text(encoding="utf-8")
    assert "N° d'offre existant" in page
    assert "modifier-offre-numero" in page
    assert "/demandes-offres/modifier/recherche" in page
    assert "modifier/recherche-numero" in page
    assert 'setSource("off")' in page
    assert 'action === "rattacher"' in page
    assert "Aucune deuxième demande" in page or "deuxième demande" in page
    assert '{ id: "a_modifier", label: "À modifier", statuts: ["Offre à modifier"] }' in kanban
    assert '{ id: "modifiees", label: "Modifiées", statuts: ["Offre modifiée"] }' in kanban
    assert "Demandes d'offres modifiées" in dashboard
    assert "isOffreAModifier" in reponses
    assert "bg-amber-50/70" in reponses
    assert "border-rose-600" in schema
    assert "changedKeys" in schema
