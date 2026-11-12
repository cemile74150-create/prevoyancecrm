"""Fidélité show_when après import depuis dumps GF (conditionalLogic)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "offre_form_schemas"
CL_DIR = ROOT / "offre_form_sources" / "conditional_logic"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_attestation_vehicule_got_conditionals_from_gf110():
    data = _load("attestation_vehicule.json")
    by = {f["name"]: f for f in data["fields"]}
    # GF110: champ lié à la raison d'attestation (Nouvelle immatriculation / Changement de détenteur)
    conditioned = [f for f in data["fields"] if f.get("show_when")]
    assert len(conditioned) >= 2
    assert any(
        r.get("field") == "input_146"
        for f in conditioned
        for r in (f.get("show_when") or {}).get("rules") or []
    )
    assert data.get("show_when_import", {}).get("gravity_form_id") == 110


def test_extracted_cl_matches_schema_for_vehicule():
    cl_path = CL_DIR / "8.json"
    if not cl_path.exists():
        pytest.skip("GF8 conditional export missing")
    cl = json.loads(cl_path.read_text(encoding="utf-8"))
    data = _load("vehicule.json")
    by_gf = {f.get("gf_field_id"): f for f in data["fields"] if f.get("gf_field_id") is not None}
    for fid_s, sw in (cl.get("fields") or {}).items():
        fid = int(fid_s)
        field = by_gf.get(fid)
        if not field:
            continue
        assert field.get("show_when"), f"missing show_when on gf_field_id={fid}"
        assert field["show_when"]["rules"][0]["field"] == sw["rules"][0]["field"]
        assert field["show_when"]["rules"][0]["value"] == sw["rules"][0]["value"]


def test_blank_hidden_fields_clears_only_when_parent_answered():
    from offre_form_types import blank_hidden_fields_when_invisible, load_form_schema

    schema = load_form_schema("attestation_vehicule") or {}
    conditioned = next((f for f in schema.get("fields") or [] if f.get("show_when")), None)
    if not conditioned:
        pytest.skip("no show_when on attestation_vehicule")
    name = conditioned["name"]
    parent = conditioned["show_when"]["rules"][0]["field"]
    expected = conditioned["show_when"]["rules"][0]["value"]
    op = conditioned["show_when"]["rules"][0].get("op") or "is"

    # Build a payload that hides the field with an explicit parent answer
    if op == "is":
        hide_payload = {parent: "__other__", name: "valeur à effacer"}
    else:
        hide_payload = {parent: expected, name: "valeur à effacer"}

    cleaned = blank_hidden_fields_when_invisible("attestation_vehicule", hide_payload)
    assert cleaned[name] == ""

    # Réouverture : parent vide → conserver la valeur déjà enregistrée
    preserved = blank_hidden_fields_when_invisible(
        "attestation_vehicule", {name: "valeur à conserver"}
    )
    assert preserved[name] == "valeur à conserver"


def test_gaps_report_lists_forms_without_js_blob():
    report = json.loads(
        (ROOT / "offre_form_sources" / "import_show_when_report.json").read_text(encoding="utf-8")
    )
    gaps = set(report["gaps"].get("no_js_conditional_export") or []) | set(
        report["gaps"].get("export_with_zero_rules") or []
    )
    # Known forms without usable JS blob in current dumps
    assert "protection_juridique_entreprise" in gaps or "pilier3" in gaps
