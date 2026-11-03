"""Tests LPP : personne M./Mme, fusion caisses, dates, rappel +1 mois."""
from __future__ import annotations

from datetime import date, datetime, timezone

from demande_envoi_relances import (
    add_calendar_months,
    build_lpp_verify_rappel_payload,
    due_date_lpp_verify,
    enrich_lpp_tracking_list,
    source_key_lpp,
)
import pytest

from pdf_generator import (
    assign_unknown_lpp_person,
    infer_lpp_person_from_filename,
    merge_lpp_detected_funds,
    resolve_lpp_person,
    tag_lpp_funds_with_person,
)


def test_infer_person_from_filename_mme_mr():
    assert infer_lpp_person_from_filename("Recherche LPP Mme.pdf") == "Madame"
    assert infer_lpp_person_from_filename("Recherche_LPP_Mr.pdf") == "Monsieur"
    assert infer_lpp_person_from_filename("Recherche LPP Madame.pdf") == "Madame"
    assert infer_lpp_person_from_filename("reponse.pdf") == ""


def test_merge_funds_keeps_monsieur_and_madame():
    existing = [
        {"name": "Caisse A", "person": "Madame", "source_doc_id": "d1"},
        {"name": "Caisse B", "person": "Madame", "source_doc_id": "d1"},
    ]
    incoming = [
        {"name": "Caisse C", "person": "Monsieur", "source_doc_id": "d2"},
        {"name": "Caisse A", "person": "Monsieur", "source_doc_id": "d2"},
    ]
    merged = merge_lpp_detected_funds(existing, incoming)
    assert len(merged) == 4
    keys = {(f["person"], f["name"]) for f in merged}
    assert ("Madame", "Caisse A") in keys
    assert ("Monsieur", "Caisse A") in keys
    assert ("Madame", "Caisse B") in keys
    assert ("Monsieur", "Caisse C") in keys


def test_assign_unknown_person_covers_the_whole_response():
    funds = [
        {"name": "Groupe Mutuel", "person": "", "source_doc_id": "doc-a"},
        {"name": "AXA", "person": "", "source_doc_id": "doc-a"},
        {"name": "UBS", "person": "Monsieur", "source_doc_id": "doc-b"},
    ]
    tracking = [
        {"id": "t1", "name": "Groupe Mutuel", "person": "", "source_doc_id": "doc-a", "sent": True, "received": False},
        {"id": "t2", "name": "AXA", "person": "", "source_doc_id": "doc-a", "sent": False, "received": False},
        {"id": "t3", "name": "UBS", "person": "Monsieur", "source_doc_id": "doc-b", "sent": False, "received": False},
    ]
    new_funds, new_tracking, source_ids = assign_unknown_lpp_person(
        funds, tracking, person="Madame", name="Groupe Mutuel", source_doc_id="doc-a",
    )
    by_name = {f["name"]: f["person"] for f in new_funds}
    assert by_name == {"Groupe Mutuel": "Madame", "AXA": "Madame", "UBS": "Monsieur"}
    assert source_ids == ["doc-a"]
    groupe = next(t for t in new_tracking if t["id"] == "t1")
    assert groupe["person"] == "Madame"
    assert groupe["sent"] is True
    assert next(t for t in new_tracking if t["id"] == "t3")["person"] == "Monsieur"


def test_assign_does_not_touch_another_unknown_response():
    funds = [
        {"name": "Caisse A", "person": "", "source_doc_id": "doc-a"},
        {"name": "Caisse B", "person": "", "source_doc_id": "doc-b"},
    ]
    new_funds, _, source_ids = assign_unknown_lpp_person(
        funds, [], person="Monsieur", name="Caisse B", source_doc_id="doc-b",
    )
    by_name = {f["name"]: f["person"] for f in new_funds}
    assert by_name["Caisse A"] == ""
    assert by_name["Caisse B"] == "Monsieur"
    assert source_ids == ["doc-b"]


def test_assign_refuses_caisse_that_already_has_a_person():
    with pytest.raises(ValueError, match="déjà"):
        assign_unknown_lpp_person(
            [{"name": "AXA", "person": "Madame", "source_doc_id": "doc-a"}],
            [],
            person="Monsieur",
            name="AXA",
            source_doc_id="doc-a",
        )


def test_tag_and_resolve_person():
    funds = tag_lpp_funds_with_person(
        [{"name": "UBS"}],
        resolve_lpp_person(filename="Recherche LPP Mme.pdf"),
        source_doc_id="doc1",
    )
    assert funds[0]["person"] == "Madame"
    assert funds[0]["source_doc_id"] == "doc1"


def test_lpp_sent_at_and_clear_on_uncheck():
    now = datetime.now(timezone.utc).isoformat()
    after = enrich_lpp_tracking_list(
        [{"id": "t1", "name": "AXA", "person": "Monsieur", "sent": False, "received": False}],
        [{"id": "t1", "name": "AXA", "person": "Monsieur", "sent": True, "received": False}],
    )
    assert after[0]["sent"] is True
    assert after[0]["sent_at"]
    cleared = enrich_lpp_tracking_list(
        after,
        [{"id": "t1", "name": "AXA", "person": "Monsieur", "sent": False, "received": False}],
    )
    assert cleared[0]["sent"] is False
    assert cleared[0]["sent_at"] is None


def test_lpp_received_keeps_sent_and_stamps_received_at():
    sent_at = "2026-09-17T10:00:00+00:00"
    after = enrich_lpp_tracking_list(
        [{"id": "t1", "name": "UBS", "person": "Madame", "sent": True, "received": False, "sent_at": sent_at}],
        [{"id": "t1", "name": "UBS", "person": "Madame", "sent": True, "received": True}],
    )
    assert after[0]["sent"] is True
    assert after[0]["sent_at"] == sent_at
    assert after[0]["received"] is True
    assert after[0]["received_at"]


def test_calendar_month_and_rappel_text():
    assert add_calendar_months(date(2026, 9, 17), 1) == date(2026, 10, 17)
    assert due_date_lpp_verify("2026-09-17") == date(2026, 10, 17)
    payload = build_lpp_verify_rappel_payload(
        user_id="u1",
        client={"id": "c1", "prenom": "Jean", "nom": "Dupont"},
        source_key=source_key_lpp("c1", "trk1", "Madame"),
        caisse_label="Freizügigkeitsstiftung der UBS AG",
        person="Madame",
        sent_at="2026-09-17T12:00:00+00:00",
    )
    assert payload["date"] == "2026-10-17"
    assert "Freizügigkeitsstiftung der UBS AG" in payload["titre"]
    assert "Madame" in payload["titre"]
    assert payload["type"] == "lpp_caisse_verify"
    assert "verify" in payload["source_key"]


def test_source_key_includes_person():
    a = source_key_lpp("c1", "t1", "Madame")
    b = source_key_lpp("c1", "t1", "Monsieur")
    assert a != b
