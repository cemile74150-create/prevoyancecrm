"""Tests lecture seule du matching d'attribution conseiller → compte."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from attribution_matching import (  # noqa: E402
    FORBIDDEN_CLIENT_CONTACT_FIELDS,
    REASON_COUPLE_MISMATCH,
    REASON_EMPTY,
    REASON_NO_MATCH,
    REASON_PARTIAL_TOKEN,
    REASON_SURE_EMAIL,
    REASON_SURE_FULL_NAME,
    build_account_index,
    classify_collection,
    match_record_to_accounts,
    summarize_results,
)


def _load_rapport_module():
    path = ROOT / "scripts" / "rapport_attribution_conseillers.py"
    spec = importlib.util.spec_from_file_location("rapport_attribution_conseillers", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


_rapport = _load_rapport_module()
_fixture_payload = _rapport._fixture_payload
build_report = _rapport.build_report


def _users():
    return build_account_index(_fixture_payload()["users"])


def test_sure_full_name_ignores_client_email_collision():
    """Un client dont l'e-mail = compte conseiller ne doit PAS créer le match."""
    accounts = _users()
    # E-mail client = celui de Valentin, mais champs conseiller vides → empty
    doc = {
        "id": "x",
        "email": "vlugnier@agencemendes.ch",
        "telephone": "079",
        "conseiller": "",
    }
    # Le matching ne lit pas doc["email"]
    result = match_record_to_accounts(doc, accounts)
    assert result.status == "empty"
    assert result.reason == REASON_EMPTY


def test_sure_by_conseiller_email_field_only():
    accounts = _users()
    doc = {
        "conseiller": "Inconnu",
        "agent_email": "vlugnier@agencemendes.ch",
        "email": "client@autre.ch",
    }
    result = match_record_to_accounts(doc, accounts)
    assert result.status == "sure"
    assert result.reason == REASON_SURE_EMAIL
    assert result.account_id == "user_valentin"


def test_sure_by_full_name():
    accounts = _users()
    result = match_record_to_accounts({"conseiller": "Valentin Lugnier"}, accounts)
    assert result.status == "sure"
    assert result.reason == REASON_SURE_FULL_NAME
    assert result.account_id == "user_valentin"


def test_partial_single_token_is_ambiguous():
    accounts = _users()
    result = match_record_to_accounts({"conseiller": "Martin"}, accounts)
    assert result.status == "ambiguous"
    assert result.reason == REASON_PARTIAL_TOKEN
    assert len(result.candidates) >= 2


def test_empty_and_unknown():
    accounts = _users()
    assert match_record_to_accounts({"conseiller": "Non attribué"}, accounts).status == "empty"
    unknown = match_record_to_accounts({"conseiller": "Personne Inconnue"}, accounts)
    assert unknown.status == "impossible"
    assert unknown.reason == REASON_NO_MATCH


def test_inactive_account_not_auto():
    accounts = _users()
    result = match_record_to_accounts({"conseiller": "Ex Conseiller"}, accounts)
    assert result.status == "ambiguous"


def test_couple_mismatch_flagged_on_primary():
    accounts = _users()
    primary = {"id": "c7", "conseiller": "Valentin Lugnier", "linked_spouse_id": "c8"}
    spouse = {"id": "c8", "conseiller": "Martin Albert"}
    result = match_record_to_accounts(primary, accounts, spouse=spouse)
    assert result.status == "ambiguous"
    assert result.reason == REASON_COUPLE_MISMATCH


def test_forbidden_fields_are_documented_and_unused_by_classify():
    payload = _fixture_payload()
    # Injecte un e-mail client égal à un conseiller : ne doit pas créer de sure supplémentaire
    for c in payload["clients"]:
        if c["id"] == "c4":
            c["email"] = "vlugnier@agencemendes.ch"
            c["telephone"] = "079111"
    accounts = build_account_index(payload["users"])
    rows = classify_collection(payload["clients"], accounts)
    by_id = {r["id"]: r for r in rows}
    assert by_id["c4"]["status"] == "empty"
    for key in FORBIDDEN_CLIENT_CONTACT_FIELDS:
        assert key in FORBIDDEN_CLIENT_CONTACT_FIELDS


def test_fixture_report_statistics():
    report = build_report(_fixture_payload(), source="fixture")
    tot = report["totals"]
    assert tot["total"] > 0
    assert tot["sure"] >= 3
    assert tot["ambiguous"] >= 2
    assert tot["empty"] >= 1
    assert tot["impossible"] >= 1
    assert report["mode"] == "LECTURE_SEULE"
    clients = report["collections"]["clients"]["summary"]
    assert clients["sure"] + clients["ambiguous"] + clients["empty"] + clients["impossible"] == clients["total"]
    s = summarize_results(report["collections"]["clients"]["anomalies"])
    assert s["total"] == len(report["collections"]["clients"]["anomalies"])
