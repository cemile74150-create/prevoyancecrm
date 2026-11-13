"""Vérifications pré-déploiement : show_when, validation, persistance, isolation."""
from __future__ import annotations

import json
from pathlib import Path

from offre_form_types import (
    _field_visible,
    blank_hidden_fields_when_invisible,
    filter_form_payload_to_schema,
    load_form_schema,
    missing_schema_required,
    schema_field_names,
)

SCHEMAS = Path(__file__).resolve().parents[1] / "offre_form_schemas"
SOURCES = Path(__file__).resolve().parents[1] / "offre_form_sources"


def _all_populated_schemas():
    for path in sorted(SCHEMAS.glob("*.json")):
        if path.name in {"index.json", "menu.json"}:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = data.get("fields") or []
        if fields:
            yield data


def test_all_show_when_parents_exist_in_same_schema():
    broken = []
    for data in _all_populated_schemas():
        names = {f.get("name") for f in data["fields"] if f.get("name")}
        for f in data["fields"]:
            for rule in (f.get("show_when") or {}).get("rules") or []:
                parent = rule.get("field")
                if parent not in names:
                    broken.append((data.get("id"), f.get("name"), parent))
    assert broken == []


def test_show_when_count_stable_and_documented_gaps():
    total = 0
    zero = []
    for data in _all_populated_schemas():
        n = sum(1 for f in data["fields"] if f.get("show_when"))
        total += n
        if n == 0:
            zero.append(data.get("id"))
    # After stripping broken var rules, count is around 690
    assert total >= 680
    for sid in [
        "laa_employee_maison",
        "pilier3_autre",
        "pilier3_standard",
        "protection_juridique_entreprise",
    ]:
        assert sid in zero
    # pilier3 keeps pre-existing rules (no fresh JS blob)
    pilier3 = load_form_schema("pilier3") or {}
    assert sum(1 for f in pilier3.get("fields") or [] if f.get("show_when")) >= 50


def test_oui_non_toggle_vehicule_immediate_visibility_and_validation():
    schema = load_form_schema("vehicule") or {}
    by = {f["name"]: f for f in schema.get("fields") or []}
    # Pick a Oui/Non-gated field if present
    gated = None
    for f in schema.get("fields") or []:
        rules = (f.get("show_when") or {}).get("rules") or []
        if len(rules) == 1 and rules[0].get("value") == "Oui" and (rules[0].get("op") or "is") == "is":
            parent = by.get(rules[0]["field"])
            if parent and parent.get("options") == ["Oui", "Non"]:
                gated = f
                break
    assert gated is not None
    parent = gated["show_when"]["rules"][0]["field"]
    name = gated["name"]

    assert _field_visible(gated, {parent: "Oui"}) is True
    assert _field_visible(gated, {parent: "Non"}) is False

    # Hidden required field must not block validation
    if gated.get("required"):
        missing_non = missing_schema_required("vehicule", {parent: "Non"})
        assert (gated.get("label") or name) not in missing_non
        missing_oui = missing_schema_required("vehicule", {parent: "Oui"})
        assert (gated.get("label") or name) in missing_oui


def test_toggle_clear_then_reopen_preserves_until_parent_answered():
    schema = load_form_schema("entreprise_46") or {}
    by = {f["name"]: f for f in schema.get("fields") or []}
    detail = by["input_83"]
    # Cycle: Non + saisie → Oui (clear) → save simulation
    filled = {"input_62": "Non", "input_83": "fracture 2024"}
    assert _field_visible(detail, filled) is True
    after_oui = blank_hidden_fields_when_invisible(
        "entreprise_46", {"input_62": "Oui", "input_83": "fracture 2024"}
    )
    assert after_oui["input_83"] == ""

    # Réouverture d'un ancien payload sans parent : ne pas détruire
    reopened = blank_hidden_fields_when_invisible(
        "entreprise_46", {"input_83": "ancienne valeur dossier"}
    )
    assert reopened["input_83"] == "ancienne valeur dossier"

    # Plusieurs bascules
    p1 = blank_hidden_fields_when_invisible(
        "entreprise_46", {"input_62": "Non", "input_83": "A"}
    )
    assert p1["input_83"] == "A"
    p2 = blank_hidden_fields_when_invisible(
        "entreprise_46", {"input_62": "Oui", "input_83": "A"}
    )
    assert p2["input_83"] == ""
    p3 = blank_hidden_fields_when_invisible(
        "entreprise_46", {"input_62": "Non", "input_83": "B"}
    )
    assert p3["input_83"] == "B"


def test_numeric_comparison_ops_for_compagnie_blocks():
    schema = load_form_schema("formulaire_complet") or {}
    candidates = [
        f
        for f in schema.get("fields") or []
        if any((r.get("op") in {">", "<"}) for r in (f.get("show_when") or {}).get("rules") or [])
    ]
    assert candidates, "expected >/< rules on formulaire_complet"
    field = candidates[0]
    rule = next(r for r in field["show_when"]["rules"] if r.get("op") in {">", "<"})
    parent = rule["field"]
    if rule["op"] == ">":
        assert _field_visible(field, {parent: "600000"}) is True
        assert _field_visible(field, {parent: "100000"}) is False
    else:
        assert _field_visible(field, {parent: "100000"}) is True
        assert _field_visible(field, {parent: "600000"}) is False


def test_filter_payload_does_not_touch_unrelated_module_keys_outside_schema():
    cleaned = filter_form_payload_to_schema(
        "vehicule",
        {"input_1": "x", "lamal_secret": "nope", "analyse_prevoyance": 1},
    )
    allowed = schema_field_names("vehicule")
    assert "lamal_secret" not in cleaned
    assert "analyse_prevoyance" not in cleaned
    assert set(cleaned).issubset(allowed | {k for k in cleaned if k.endswith("__comment")})


def test_gaps_file_lists_five_incomplete_forms():
    gaps = (SOURCES / "GAPS.md").read_text(encoding="utf-8")
    for sid in [
        "laa_employee_maison",
        "pilier3",
        "pilier3_autre",
        "pilier3_standard",
        "protection_juridique_entreprise",
    ]:
        assert sid in gaps
