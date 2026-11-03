"""Journal d'action : champs, ordre, rattachement au dossier."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from journal_actions import (  # noqa: E402
    journal_belongs_to_scope,
    normalize_journal_fields,
    sort_journal_actions,
)


def test_normalize_keeps_free_label_and_optional_note():
    fields = normalize_journal_fields(
        "  mail envoyé au client avec l'offre  ",
        "2026-10-20",
        "  relance prévue  ",
    )
    assert fields == {
        "libelle": "mail envoyé au client avec l'offre",
        "date": "2026-10-20",
        "note": "relance prévue",
    }


def test_note_can_be_empty():
    fields = normalize_journal_fields("j'ai contacté le client", "2026-10-20", "  ")
    assert fields["note"] is None


def test_label_and_date_are_required():
    with pytest.raises(ValueError):
        normalize_journal_fields("  ", "2026-10-20")
    with pytest.raises(ValueError):
        normalize_journal_fields("Appel", "20.10.2026")
    with pytest.raises(ValueError):
        normalize_journal_fields("Appel", "2026-02-31")


def test_newest_action_date_first():
    rows = sort_journal_actions([
        {"id": "old", "date": "2026-01-02", "created_at": "2026-01-02T10:00:00"},
        {"id": "late", "date": "2026-10-20", "created_at": "2026-10-20T08:00:00"},
        {"id": "same-day-later", "date": "2026-10-20", "created_at": "2026-10-20T18:00:00"},
    ])
    assert [row["id"] for row in rows] == ["same-day-later", "late", "old"]


def test_assigned_query_targets_only_that_account():
    from journal_actions import assigned_journal_query

    scope = {"member_ids": ["c1"], "dossier_id": "dos-1"}
    query = assigned_journal_query("tenant", "user_sophie", scope)
    assert query["assignee_account_id"] == "user_sophie"
    assert query["user_id"] == "tenant"
    assert {"client_id": {"$in": ["c1"]}} in query["$or"]
    assert assigned_journal_query("tenant", "  ", scope) is None


def test_action_stays_on_its_client_or_shared_dossier():
    scope = {"member_ids": ["c1", "c2"], "dossier_id": "dos-1"}
    assert journal_belongs_to_scope({"client_id": "c1", "dossier_id": "dos-1"}, scope)
    assert journal_belongs_to_scope({"client_id": "other", "dossier_id": "dos-1"}, scope)
    assert journal_belongs_to_scope({"client_id": "other", "dossier_id": "dos-9"}, scope) is False


def test_assigned_action_sends_one_mail_and_plain_action_sends_none(monkeypatch):
    """Transport simulé : un seul message si attribué, zéro sinon. Aucun SMTP réel."""
    import asyncio

    from journal_actions import plan_journal_assignment_mail, send_planned_journal_mail

    sent = []

    async def fake_send(to_email, subject, body_text, **kwargs):
        sent.append({
            "to": to_email,
            "subject": subject,
            "body": body_text,
            "from_name": kwargs.get("from_name"),
            "attachments": kwargs.get("attachments"),
        })
        return True, None

    monkeypatch.setattr("email_service.send_email_async", fake_send)

    author = "Nadia Rossi"
    client = "Claire Martin"

    async def _run():
        assigned = plan_journal_assignment_mail(
            assigned=True,
            author_name=author,
            client_name=client,
            action_date="2026-10-29",
            libelle="Fini de faire la planification",
            note="Suite à donner",
            assignee_email="paul.berger@example.test",
        )
        plain = plan_journal_assignment_mail(assigned=False)
        missing_email = plan_journal_assignment_mail(
            assigned=True,
            author_name=author,
            client_name=client,
            action_date="2026-10-29",
            libelle="Appel",
            note=None,
            assignee_email="  ",
        )
        sent_notice = await send_planned_journal_mail(assigned)
        plain_notice = await send_planned_journal_mail(plain)
        missing_notice = await send_planned_journal_mail(missing_email)
        return sent_notice, plain_notice, missing_notice

    sent_notice, plain_notice, missing_notice = asyncio.run(_run())

    assert len(sent) == 1
    assert sent_notice == {"sent": True, "reason": None}
    assert plain_notice == {"sent": False, "reason": None}
    assert missing_notice == {"sent": False, "reason": "no_email"}
    assert missing_notice.get("to") in (None, "")
    message = sent[0]
    assert message["to"] == "paul.berger@example.test"
    assert client in message["subject"]
    assert author in message["subject"]
    assert message["subject"] == (
        "Vous avez une notification de Nadia Rossi sur le dossier Claire Martin"
    )
    assert message["from_name"] == author
    assert message["attachments"] is None
    assert "Date : 29/10/2026" in message["body"]
    assert "Ce qui a été fait : Fini de faire la planification" in message["body"]
    assert "Note : Suite à donner" in message["body"]
    assert "Dossier : Claire Martin" in message["body"]
    assert "cochez « Action traitée »" in message["body"]
    assert "https://" not in message["body"]
    assert "AVS" not in message["body"]
    assert "Henri Favre" not in message["body"]

    without_note = plan_journal_assignment_mail(
        assigned=True,
        author_name=author,
        client_name=client,
        action_date="2026-10-29",
        libelle="Appel",
        note="   ",
        assignee_email="paul.berger@example.test",
    )
    assert "Note :" not in without_note["body_text"]
    assert without_note["send"] is True

    with_link = plan_journal_assignment_mail(
        assigned=True,
        author_name=author,
        client_name=client,
        action_date="2026-10-29",
        libelle="Appel",
        assignee_email="paul.berger@example.test",
        dossier_url="https://crm.example.com/clients/c1?tab=journal",
    )
    assert "https://crm.example.com/clients/c1?tab=journal" in with_link["body_text"]


def test_only_the_assignee_can_mark_the_action_treated():
    from journal_actions import blank_treated_fields, mark_journal_treated

    row = {
        "assignee_account_id": "user_sophie",
        "assignee_name": "Sophie Martin",
        **blank_treated_fields(),
    }
    marked = mark_journal_treated(
        row,
        treated=True,
        actor_account_id="user_sophie",
        actor_name="Sophie Martin",
        now="2026-10-30T09:00:00+00:00",
    )
    assert marked["treated"] is True
    assert marked["treated_by_name"] == "Sophie Martin"
    assert marked["treated_by_account_id"] == "user_sophie"

    cleared = mark_journal_treated(
        {**row, **marked},
        treated=False,
        actor_account_id="user_sophie",
        actor_name="Sophie Martin",
        now="2026-10-30T10:00:00+00:00",
    )
    assert cleared == blank_treated_fields()

    with pytest.raises(PermissionError):
        mark_journal_treated(
            row,
            treated=True,
            actor_account_id="user_cemile",
            actor_name="Cemile Demirtas",
            now="2026-10-30T09:00:00+00:00",
        )
    with pytest.raises(ValueError):
        mark_journal_treated(
            {"assignee_account_id": None},
            treated=True,
            actor_account_id="user_sophie",
            actor_name="Sophie Martin",
            now="2026-10-30T09:00:00+00:00",
        )


def test_assignee_without_email_keeps_the_name_and_invents_no_address():
    from journal_actions import assignee_identity

    identity = assignee_identity({
        "account_id": "user_paul",
        "prenom": "Paul",
        "nom": "Berger",
        "email": "",
    })
    assert identity["name"] == "Paul Berger"
    assert identity["email"] == ""
    assert identity["account_id"] == "user_paul"
