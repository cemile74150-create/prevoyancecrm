"""Fil du mail « offre signée » et note externe au conseiller créateur."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import email_service as es  # noqa: E402
from access_control import (  # noqa: E402
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    user_from_doc,
)
from demandes_offres_3p import serialize_demande  # noqa: E402


def _user(role, **kwargs):
    doc = {
        "user_id": "acc1",
        "email": "gestionnaire@test.ch",
        "prenom": "Lea",
        "nom": "Gestion",
        "name": "Lea Gestion",
        "role": role,
        "conseiller": "Lea Gestion",
        "active": True,
        **kwargs,
    }
    return user_from_doc(doc)


def test_normalize_message_id_wraps_and_rejects_blank():
    assert es.normalize_message_id("  abc@leosoft.ch ") == "<abc@leosoft.ch>"
    assert es.normalize_message_id("<abc@leosoft.ch>") == "<abc@leosoft.ch>"
    assert es.normalize_message_id("") is None
    assert es.normalize_message_id("pas un id") is None


def test_pick_initial_message_id_is_the_first_successful_offres_mail():
    logs = [
        {
            "type": es.MAIL_TYPE_DEMANDE_OFFRE_RECAP,
            "event": "envoyee_recap",
            "status": "sent",
            "message_id": "<recap@leosoft.ch>",
            "sent_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "type": es.MAIL_TYPE_DEMANDE_OFFRE,
            "event": "envoyee",
            "status": "error",
            "message_id": "<failed@leosoft.ch>",
            "sent_at": "2026-01-02T00:00:00+00:00",
        },
        {
            "type": es.MAIL_TYPE_DEMANDE_OFFRE,
            "event": "envoyee",
            "status": "sent",
            "message_id": "second@leosoft.ch",
            "sent_at": "2026-03-01T00:00:00+00:00",
        },
        {
            "type": es.MAIL_TYPE_DEMANDE_OFFRE,
            "event": "envoyee",
            "status": "sent",
            "message_id": "<first@leosoft.ch>",
            "sent_at": "2026-02-01T00:00:00+00:00",
        },
        {
            "type": es.MAIL_TYPE_OFFRE_RECUE,
            "event": "recue",
            "status": "sent",
            "message_id": "<recue@leosoft.ch>",
            "sent_at": "2026-01-15T00:00:00+00:00",
        },
    ]
    assert es.pick_initial_offres_message_id(logs) == "<first@leosoft.ch>"
    assert es.pick_initial_offres_message_id([]) is None


def test_remember_thread_id_only_on_first_successful_envoyee():
    doc = {"id": "d1"}
    assert es.should_remember_offres_thread_message_id(
        doc, event="envoyee", sent=True, message_id="<a@leosoft.ch>"
    ) is True
    assert es.should_remember_offres_thread_message_id(
        doc, event="signee", sent=True, message_id="<a@leosoft.ch>"
    ) is False
    assert es.should_remember_offres_thread_message_id(
        doc, event="envoyee", sent=False, message_id="<a@leosoft.ch>"
    ) is False
    assert es.should_remember_offres_thread_message_id(
        doc, event="note_externe", sent=True, message_id="<a@leosoft.ch>"
    ) is False
    already = {"offres_thread_message_id": "<first@leosoft.ch>"}
    assert es.should_remember_offres_thread_message_id(
        already, event="envoyee", sent=True, message_id="<second@leosoft.ch>"
    ) is False


def test_build_message_sets_reply_headers_only_when_asked(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "noreply@leosoft.ch")
    monkeypatch.setenv("SMTP_FROM_NAME", "LeoSoft")
    msg, _, _ = es._build_message(
        to_email="office@agencemendes.ch",
        subject="OFF-2026-1-Dupont Jean -3e pilier",
        body_text="Signée",
        cc=["offres@agencemendes.ch"],
        in_reply_to="first@leosoft.ch",
        references="first@leosoft.ch",
    )
    assert msg["In-Reply-To"] == "<first@leosoft.ch>"
    assert msg["References"] == "<first@leosoft.ch>"
    assert msg["Subject"] == "OFF-2026-1-Dupont Jean -3e pilier"
    assert msg["To"] == "office@agencemendes.ch"
    assert "offres@agencemendes.ch" in msg["Cc"]


def test_send_email_async_keeps_two_tuple_and_forwards_reply_headers(monkeypatch):
    captured = {}

    def fake_deliver(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return True, None, "<new@leosoft.ch>"

    monkeypatch.setattr(es, "_smtp_deliver", fake_deliver)
    out = {}

    async def _run():
        return await es.send_email_async(
            "office@agencemendes.ch",
            "OFF-1",
            "Corps",
            cc=["offres@agencemendes.ch"],
            persist_log=False,
            in_reply_to="<first@leosoft.ch>",
            references="<first@leosoft.ch>",
            result_out=out,
        )

    result = asyncio.run(_run())
    assert result == (True, None)
    assert len(result) == 2
    assert captured["kwargs"]["in_reply_to"] == "<first@leosoft.ch>"
    assert captured["kwargs"]["references"] == "<first@leosoft.ch>"
    assert captured["kwargs"]["cc"] == ["offres@agencemendes.ch"]
    assert out["message_id"] == "<new@leosoft.ch>"
    assert out["ok"] is True


def test_signature_subject_stays_permanent_and_note_externe_is_separate():
    doc = {
        "id": "d1",
        "numero": "OFF-2026-00452",
        "nom": "Dupont",
        "prenom": "Jean",
        "email_subject": "OFF-2026-00452-Dupont Jean -3e pilier",
        "agent_prenom": "Camille",
        "note_externe_author": "Lea Gestion",
    }
    subject, text, _html = es.format_offre_signee_email(doc, signature={"date_signature": "2026-09-17"})
    assert subject == doc["email_subject"]
    assert not subject.lower().startswith("re:")

    note_subject, note_text, note_html = es.format_note_externe_email(
        doc, note="Merci de rappeler le client."
    )
    assert note_subject.startswith("Note sur votre demande d’offre")
    assert "Jean" in note_subject or "Dupont" in note_subject
    assert "OFF-2026-00452" in note_subject
    assert "Merci de rappeler le client." in note_text
    assert "Lea Gestion" in note_text
    assert "Bonjour Camille" in note_text
    assert "offres@" not in note_text
    assert "office@" not in note_text
    assert "Merci de rappeler le client." in note_html
    assert es.offre_notify_role("signee") == "offres_mailbox"
    assert es.offre_notify_role("note_externe") == "createur"


def test_serialize_external_note_visible_internal_hidden():
    doc = {
        "id": "d1",
        "statut": "Demande envoyée",
        "created_by_account_id": "owner",
        "notes_internes": [{"note": "secret gestionnaire"}],
        "notes_externes": [{"id": "e1", "note": "à transmettre", "email_to": "camille@test.ch"}],
        "historique": [
            {"action": "Note interne", "detail": "secret gestionnaire"},
            {"action": "Note externe", "detail": "à transmettre"},
        ],
    }
    conseiller = _user(
        ROLE_CONSEILLER,
        user_id="owner",
        email="camille@test.ch",
        prenom="Camille",
        nom="Durand",
        conseiller="Camille Durand",
    )
    out = serialize_demande(doc, viewer=conseiller)
    assert out["notes_internes"] == []
    assert out["notes_externes"][0]["note"] == "à transmettre"
    assert out["notes_externes"][0]["email_to"] == "camille@test.ch"
    actions = [e.get("action") for e in out["historique"]]
    assert "Note interne" not in actions
    assert "Note externe" in actions

    gestionnaire = _user(ROLE_GESTIONNAIRE_OFFRES, see_all_dossiers=True)
    out_mgr = serialize_demande(doc, viewer=gestionnaire)
    assert out_mgr["notes_internes"]
    assert out_mgr["notes_externes"][0]["note"] == "à transmettre"


def test_signature_and_external_note_routes_keep_their_recipients():
    routes = (ROOT / "demandes_offres_routes.py").read_text(encoding="utf-8")
    start = routes.index("async def try_send_email")
    end = routes.index("async def write_offre_notification", start)
    body = routes[start:end]

    signee = body.split('event_key in {"signee"', 1)[1].split("elif event_key", 1)[0]
    assert "office_email_to()" in signee
    assert "offres_email_to()" in signee
    assert "resolve_demande_creator_email" not in signee

    note = body.split('event_key in {"note_externe"', 1)[1].split("else:", 1)[0]
    assert "format_note_externe_email" in note
    assert "resolve_demande_creator_email" in note
    assert "office_email_to" not in note
    assert "offres_email_to" not in note

    assert 'if event_key in {"signee", "signée", "signed"}:' in body
    assert "in_reply_to=thread_message_id" in body
    assert "references=thread_message_id" in body

    handler = routes.split("async def add_external_note", 1)[1].split("@api_router.", 1)[0]
    assert "resolve_demande_creator_email(doc)" in handler
    assert 'event="note_externe"' in handler
    assert "to_override=to_addr" in handler
    assert "user.email" not in handler
    assert '"Note externe"' in handler
    assert "notes_externes" in handler


def test_external_note_requires_text():
    from demandes_offres_routes import ExternalNoteRequest

    with pytest.raises(Exception):
        ExternalNoteRequest(note="")
    assert ExternalNoteRequest(note="Bonjour").note == "Bonjour"
