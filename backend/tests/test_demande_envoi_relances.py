"""Tests rappels auto Envoyé → Reçu (1,5 mois)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from demande_envoi_relances import (
    FOLLOWUP_DAYS,
    build_rappel_payload,
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
