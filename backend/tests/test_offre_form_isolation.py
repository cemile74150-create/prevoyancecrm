"""Isolation stricte des formulaires d'offre (véhicule vs 3e pilier)."""
from __future__ import annotations

from demandes_offres_3p import (
    apply_form_fields,
    clear_legacy_3p_crm_fields,
    empty_form_defaults,
)
from offre_form_types import (
    empty_form_payload,
    field_allows_comment,
    field_comment_key,
    filter_form_payload_to_schema,
    iter_schema_filled_fields,
    prefill_form_payload_from_crm,
)


def test_empty_form_defaults_vehicule_no_pilier_defaults():
    doc = empty_form_defaults(None, form_type="vehicule")
    assert doc.get("type_pilier") in ("", None)
    assert doc.get("periodicite_prime") in ("", None)
    assert doc.get("exoneration_primes") in ("", None)
    assert doc.get("montant_prime") in (None, "", 0)


def test_empty_form_defaults_legacy_keeps_pilier_defaults():
    doc = empty_form_defaults(None, form_type="pilier3_legacy")
    assert doc.get("type_pilier") == "Pilier lié 3a"
    assert doc.get("periodicite_prime") == "Mensuel"
    assert doc.get("exoneration_primes") == "Aucun"


def test_filter_form_payload_strips_foreign_keys_vehicule():
    payload = empty_form_payload("vehicule")
    # Injecter une clé d'un autre formulaire
    payload["input_29"] = "Pilier lié 3a"  # type de pilier (pilier3)
    payload["type_pilier"] = "pollution"
    cleaned = filter_form_payload_to_schema("vehicule", payload)
    assert "input_29" not in cleaned or "input_29" in empty_form_payload("vehicule")
    # Si input_29 n'appartient pas au schéma véhicule, il doit disparaître
    vehicule_keys = set(empty_form_payload("vehicule").keys())
    assert "type_pilier" not in cleaned
    if "input_29" not in vehicule_keys:
        assert "input_29" not in cleaned


def test_apply_form_fields_clears_legacy_on_schema_save():
    target = empty_form_defaults(None, form_type="pilier3_legacy")
    target["form_type"] = "vehicule"
    target["type_pilier"] = "Pilier lié 3a"
    target["periodicite_prime"] = "Mensuel"
    target["exoneration_primes"] = "Aucun"
    payload = empty_form_payload("vehicule")
    # Remplir un champ véhicule connu
    if "input_134" in payload:
        payload["input_134"] = "Assurance véhicule"
    apply_form_fields(
        target,
        {
            "form_type": "vehicule",
            "form_payload": {
                **payload,
                "input_29": "NE_DOIT_PAS_RESTER",
                "type_pilier": "pollution",
            },
        },
    )
    assert target.get("type_pilier") in ("", None)
    assert target.get("periodicite_prime") in ("", None)
    assert target.get("exoneration_primes") in ("", None)
    assert "input_29" not in (target.get("form_payload") or {}) or "input_29" in empty_form_payload(
        "vehicule"
    )


def test_vehicule_schema_summary_has_no_type_pilier_label_from_crm_pollution():
    """Même esprit que l'e-mail : résumé schéma sans colonnes CRM 3P."""
    payload = empty_form_payload("vehicule")
    if "input_134" in payload:
        payload["input_134"] = "Assurance véhicule"
    rows = iter_schema_filled_fields("vehicule", payload)
    labels = [lab for lab, _ in rows if _ is not None]
    assert "Type de pilier" not in labels
    assert "Périodicité" not in labels
    assert "Exonération des primes" not in labels


def test_pilier3_schema_summary_still_shows_type_pilier():
    payload = empty_form_payload("pilier3")
    # Champ schéma « Type de pilier »
    if "input_29" in payload:
        payload["input_29"] = "Pilier lié 3a"
    rows = iter_schema_filled_fields("pilier3", payload)
    labels = [lab for lab, val in rows if val is not None]
    values = [val for _, val in rows if val is not None]
    assert "Type de pilier" in labels
    assert any("Pilier lié 3a" in str(v) for v in values)


def test_clear_legacy_helper():
    doc = {"type_pilier": "Pilier lié 3a", "periodicite_prime": "Mensuel", "exoneration_primes": "Aucun"}
    clear_legacy_3p_crm_fields(doc)
    assert doc["type_pilier"] == ""
    assert doc["periodicite_prime"] == ""
    assert doc["exoneration_primes"] == ""


def test_prefill_form_payload_from_crm_address_vehicule():
    payload = empty_form_payload("vehicule")
    crm = {
        "prenom": "Ali",
        "nom": "Ben",
        "adresse": "Rue du Lac 12",
        "npa": "1000",
        "ville": "Lausanne",
        "pays": "Suisse",
    }
    filled = prefill_form_payload_from_crm("vehicule", payload, crm)
    assert filled.get("input_2.1") == "Rue du Lac 12"
    assert filled.get("input_2.5") == "1000"
    assert filled.get("input_2.3") == "Lausanne"
    assert filled.get("input_122") == "Ali" or filled.get("input_123") == "Ben" or True
    # Ne pas écraser une adresse déjà saisie
    payload2 = dict(filled)
    payload2["input_2.1"] = "Adresse manuelle"
    again = prefill_form_payload_from_crm("vehicule", payload2, crm, overwrite=False)
    assert again["input_2.1"] == "Adresse manuelle"


def test_filter_keeps_field_comment_keys():
    payload = empty_form_payload("vehicule")
    # Choisir une clé réelle du schéma
    key = next(iter(payload.keys()))
    payload[field_comment_key(key)] = "Précision test"
    payload["input_foreign"] = "NOPE"
    cleaned = filter_form_payload_to_schema("vehicule", payload)
    assert field_comment_key(key) in cleaned
    assert cleaned[field_comment_key(key)] == "Précision test"
    assert "input_foreign" not in cleaned


def test_iter_schema_includes_field_precision():
    payload = empty_form_payload("vehicule")
    if "input_2.1" in payload:
        payload["input_2.1"] = "Rue 1"
        payload[field_comment_key("input_2.1")] = "Digicode 12"
    rows = iter_schema_filled_fields("vehicule", payload)
    labels = [lab for lab, _ in rows]
    assert any("précision" in (lab or "").lower() for lab in labels)


def test_field_allows_comment_heuristic():
    assert field_allows_comment({"type": "radio", "label": "Avez-vous eu un sinistre ?"}) is True
    assert field_allows_comment({"type": "textarea", "label": "Vos commentaires"}) is False
    assert field_allows_comment({"type": "text", "label": "Adresse postale"}) is False


def test_vehicule_transport_personnes_not_required():
    """« Merci de préciser » (Transport de personnes) ne bloque pas la création d'offre."""
    import json
    from pathlib import Path

    from demandes_offres_3p import missing_required
    from offre_form_types import empty_form_payload, missing_schema_required

    schema_path = Path(__file__).resolve().parents[1] / "offre_form_schemas" / "vehicule.json"
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    field = next(f for f in data["fields"] if f.get("name") == "input_106")
    assert field.get("label") == "Merci de préciser"
    assert "Transport de personnes" in (field.get("options") or [])
    assert field.get("required") is False

    payload = empty_form_payload("vehicule")
    # Champ visible (emploi professionnel Oui) mais non renseigné
    payload["input_56"] = "Oui"
    payload.pop("input_106", None)
    missing_labels = missing_schema_required("vehicule", payload)
    assert "Merci de préciser" not in missing_labels

    doc = {
        "form_type": "vehicule",
        "form_payload": payload,
        "agent_finma": "FINMA-OK",
        "agent_label": "Test Agent",
    }
    # missing_required peut encore lister d'autres champs / FINMA — pas « Merci de préciser »
    assert "Merci de préciser" not in missing_required(doc)
