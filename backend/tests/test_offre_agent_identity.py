"""Tests identité AGENT DEMANDEUR (autofill session + anti-spoof + FINMA)."""
from __future__ import annotations

from types import SimpleNamespace

from demandes_offres_3p import empty_form_defaults, missing_required
from offre_agent_identity import (
    agent_identity_from_user,
    apply_agent_identity_to_doc,
    apply_agent_identity_to_payload,
    classify_agent_field,
    missing_agent_finma_message,
    resolve_agent_identity_for_write,
    schema_requires_finma,
    viewer_is_demande_creator,
)
from offre_form_types import empty_form_payload


def test_classify_agent_fields_menage_labels():
    assert classify_agent_field("Prénom de l'agent") == "prenom"
    assert classify_agent_field("Nom de l'agent") == "nom"
    assert classify_agent_field("Votre adresse email") == "email"
    assert classify_agent_field("Votre numéro FINMA") == "finma"
    assert classify_agent_field("Numéro FINMA") == "finma"
    assert classify_agent_field("Votre. numéro FINMA") == "finma"
    assert classify_agent_field("Agent demandeur") is None
    assert classify_agent_field(
        "Vous recevrez les offres à l'adresse email suivante :"
    ) is None
    assert classify_agent_field("Prénom") is None
    assert classify_agent_field("Email de l'agent (Nécessaire)") == "email"
    assert classify_agent_field("Nom de l'agent (Nécessaire)") == "nom"


def test_agent_identity_from_user_and_defaults():
    user = SimpleNamespace(
        prenom="Cemile",
        nom="Agent",
        email="cemile@example.ch",
        finma_number="FINMA-42",
        name="Cemile Agent",
    )
    ident = agent_identity_from_user(user)
    assert ident["prenom"] == "Cemile"
    assert ident["nom"] == "Agent"
    assert ident["email"] == "cemile@example.ch"
    assert ident["finma"] == "FINMA-42"

    doc = empty_form_defaults(user, form_type="menage_rc")
    assert doc["agent_prenom"] == "Cemile"
    assert doc["agent_finma"] == "FINMA-42"


def test_inject_agent_into_menage_rc_payload_overwrites_spoof():
    user = SimpleNamespace(
        prenom="Alice",
        nom="Martin",
        email="alice@leosoft.ch",
        finma_number="F-100",
        name="Alice Martin",
    )
    identity = agent_identity_from_user(user)
    payload = empty_form_payload("menage_rc")
    # Spoofed values
    payload["input_120.3"] = "Hacker"
    payload["input_120.6"] = "Fake"
    payload["input_121"] = "spoof@evil.test"
    payload["input_122"] = "SPOOF-FINMA"

    cleaned = apply_agent_identity_to_payload(
        "menage_rc", payload, identity, overwrite=True
    )
    assert cleaned["input_120.3"] == "Alice"
    assert cleaned["input_120.6"] == "Martin"
    assert cleaned["input_121"] == "alice@leosoft.ch"
    assert cleaned["input_122"] == "F-100"
    # E-mail de réception aussi
    assert cleaned.get("input_26") == "alice@leosoft.ch"


def test_apply_agent_identity_to_doc_crm_and_payload():
    identity = {
        "prenom": "Bob",
        "nom": "Dupont",
        "email": "bob@example.ch",
        "finma": "F-9",
        "label": "Bob Dupont",
    }
    doc = {
        "form_type": "vehicule",
        "form_payload": empty_form_payload("vehicule"),
        "agent_prenom": "Spoof",
        "agent_nom": "X",
        "agent_email": "x@y.z",
        "agent_finma": "NOPE",
    }
    apply_agent_identity_to_doc(doc, identity, overwrite_payload=True)
    assert doc["agent_prenom"] == "Bob"
    assert doc["agent_nom"] == "Dupont"
    assert doc["agent_email"] == "bob@example.ch"
    assert doc["agent_finma"] == "F-9"
    assert doc["agent_label"] == "Bob Dupont"
    fp = doc["form_payload"]
    assert fp["input_136.3"] == "Bob"
    assert fp["input_136.6"] == "Dupont"
    assert fp["input_137"] == "bob@example.ch"
    assert fp["input_138"] == "F-9"


def test_missing_finma_blocks_validate():
    assert schema_requires_finma("menage_rc") is True
    assert schema_requires_finma("pilier3_legacy") is True

    doc = {
        "form_type": "menage_rc",
        "form_payload": empty_form_payload("menage_rc"),
        "agent_finma": "",
    }
    msg = missing_agent_finma_message(doc, {"finma": ""})
    assert msg and "FINMA" in msg

    missing = missing_required(doc)
    assert any("FINMA" in str(m) for m in missing)

    doc2 = {**doc, "agent_finma": "F-1"}
    assert missing_agent_finma_message(doc2) is None


def test_entreprise_offres_agent_keys():
    identity = {
        "prenom": "Cemile",
        "nom": "Leo",
        "email": "c@leo.ch",
        "finma": "F-7",
        "label": "Cemile Leo",
    }
    payload = apply_agent_identity_to_payload(
        "entreprise_offres", empty_form_payload("entreprise_offres"), identity
    )
    assert payload["input_127.3"] == "Cemile"
    assert payload["input_127.6"] == "Leo"
    assert payload["input_128"] == "c@leo.ch"
    assert payload["input_129"] == "F-7"


def test_admin_viewing_other_agent_draft_does_not_take_identity():
    sophie = SimpleNamespace(
        account_id="sophie-id",
        prenom="Sophie",
        nom="Masi",
        email="sophie@agencemendes.ch",
        finma_number="F-SOPHIE",
        name="Sophie Masi",
    )
    admin = SimpleNamespace(
        account_id="admin-id",
        prenom="Cemile",
        nom="Admin",
        email="cemile@agencemendes.ch",
        finma_number="F-ADMIN",
        name="Cemile Admin",
    )
    doc = {
        "created_by_account_id": "sophie-id",
        "agent_prenom": "Sophie",
        "agent_nom": "Masi",
        "agent_email": "sophie@agencemendes.ch",
        "agent_finma": "F-SOPHIE",
        "agent_label": "Sophie Masi",
        "form_type": "menage_rc",
        "form_payload": empty_form_payload("menage_rc"),
    }
    assert viewer_is_demande_creator(doc, sophie) is True
    assert viewer_is_demande_creator(doc, admin) is False

    stolen = apply_agent_identity_to_doc(dict(doc), agent_identity_from_user(admin))
    assert stolen["agent_prenom"] == "Cemile"

    restored = resolve_agent_identity_for_write(
        stolen, admin, creator_identity=agent_identity_from_user(sophie)
    )
    assert restored["prenom"] == "Sophie"
    assert restored["nom"] == "Masi"
    assert restored["email"] == "sophie@agencemendes.ch"
    assert restored["finma"] == "F-SOPHIE"

    own = resolve_agent_identity_for_write(doc, sophie)
    assert own["prenom"] == "Sophie"
    assert own["email"] == "sophie@agencemendes.ch"

    kept = resolve_agent_identity_for_write(
        {
            **doc,
            "agent_prenom": "David",
            "agent_nom": "Martin",
            "agent_email": "david@agencemendes.ch",
            "agent_label": "David Martin",
            "agent_account_id": "david-id",
        },
        admin,
        creator_identity=agent_identity_from_user(sophie),
    )
    assert kept["prenom"] == "David"
    assert kept["email"] == "david@agencemendes.ch"

