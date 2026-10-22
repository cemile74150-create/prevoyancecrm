"""Tests rappels auto Envoyé → Reçu (1,5 mois)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from demande_envoi_relances import (
    AVS_FOLLOWUP_MONTHS,
    FOLLOWUP_DAYS,
    LPP_VERIFY_MONTHS,
    build_rappel_payload,
    due_date_after_months,
    enrich_checklist_entry,
    enrich_checklist_map,
    is_followup_due,
    source_key_checklist,
    source_key_lpp,
)


def test_followup_delay_is_45_days():
    assert FOLLOWUP_DAYS == 45
    sent = (date.today() - timedelta(days=45)).isoformat()
    assert is_followup_due(sent) is True
    almost = (date.today() - timedelta(days=44)).isoformat()
    assert is_followup_due(almost) is False


def test_enrich_checklist_stamps_sent_at_and_keeps_sent_when_received():
    now = datetime.now(timezone.utc).isoformat()
    after_sent = enrich_checklist_entry(
        {"sent": False, "received": False},
        {"sent": True, "received": False},
        now_iso=now,
    )
    assert after_sent["sent"] is True
    assert after_sent["sent_at"] == now

    after_received = enrich_checklist_entry(
        after_sent,
        {"sent": True, "received": True, "sent_at": after_sent["sent_at"]},
        now_iso=now,
    )
    assert after_received["sent"] is True
    assert after_received["received"] is True
    assert after_received["sent_at"] == now
    assert after_received["received_at"] == now


def test_enrich_checklist_map_preserves_other_items():
    prev = {"Formulaire AVS": {"sent": True, "received": False, "sent_at": "2025-01-01T00:00:00+00:00"}}
    incoming = {
        "Formulaire AVS": {"sent": True, "received": True},
        "Demande LPP": {"sent": True, "received": False},
    }
    out = enrich_checklist_map(prev, incoming)
    assert out["Formulaire AVS"]["received"] is True
    assert out["Formulaire AVS"]["sent_at"] == "2025-01-01T00:00:00+00:00"
    assert out["Demande LPP"]["sent"] is True
    assert out["Demande LPP"]["sent_at"]


def test_build_rappel_payload_is_urgent_and_crm_only():
    client = {"id": "c1", "prenom": "Karine", "nom": "Ambrosetti", "conseiller": "Jean"}
    sent = (date.today() - timedelta(days=50)).isoformat()
    doc = build_rappel_payload(
        user_id="tenant",
        client=client,
        source_key=source_key_checklist("c1", "Formulaire AVS"),
        demande_label="Formulaire AVS",
        caisse_label="Formulaire AVS",
        sent_at=sent,
    )
    assert doc["priorite"] == "haute"
    assert doc["notify_crm"] is True
    assert doc["send_email"] is False
    assert doc["done"] is False
    assert "Réponse toujours pas reçue — relancer" in doc["titre"]
    assert "Formulaire AVS" in doc["description"]
    assert doc["source_key"] == source_key_checklist("c1", "Formulaire AVS")


def test_no_invented_sent_at_without_date():
    """Ancien dossier Envoyé sans date → pas de délai inventé."""
    after = enrich_checklist_entry(
        {"sent": True, "received": False},
        {"sent": True, "received": False},
        now_iso="2026-01-01T00:00:00+00:00",
    )
    # enrich ne crée une date que sur transition False→True
    assert after["sent"] is True
    assert after.get("sent_at") is None
    assert is_followup_due(None) is False


def test_source_keys_distinct_for_checklist_and_lpp():
    assert source_key_checklist("c1", "AVS") != source_key_lpp("c1", "trk1")


def test_avs_reminder_is_two_months_and_lpp_is_one():
    sent = "2026-09-17"
    assert LPP_VERIFY_MONTHS == 1
    assert AVS_FOLLOWUP_MONTHS == 2
    assert due_date_after_months(sent, LPP_VERIFY_MONTHS) == date(2026, 10, 17)
    assert due_date_after_months(sent, AVS_FOLLOWUP_MONTHS) == date(2026, 11, 17)
    client = {"id": "c1", "prenom": "José", "nom": "Da Rocha"}
    lpp = build_rappel_payload(
        user_id="u",
        client=client,
        source_key=source_key_checklist("c1", "Demande LPP"),
        demande_label="Demande LPP",
        caisse_label="Demande LPP",
        sent_at=sent,
        followup_months=LPP_VERIFY_MONTHS,
    )
    avs = build_rappel_payload(
        user_id="u",
        client=client,
        source_key=source_key_checklist("c1", "Formulaire AVS"),
        demande_label="Formulaire AVS",
        caisse_label="Formulaire AVS",
        sent_at=sent,
        followup_months=AVS_FOLLOWUP_MONTHS,
    )
    assert lpp["date"] == "2026-10-17"
    assert avs["date"] == "2026-11-17"
    assert lpp["titre"].startswith("Réponse non reçue — contacter la caisse")
    assert avs["titre"].startswith("Réponse non reçue — contacter la caisse")
    assert "Contacter la caisse" in lpp["description"]
    assert "Contacter la caisse" in avs["description"]
