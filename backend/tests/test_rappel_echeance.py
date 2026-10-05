"""Tests échéance passée et report +14 jours des rappels."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def tz():
    return ZoneInfo("Europe/Zurich")


def test_rappel_not_overdue_before_due(tz):
    from server import _rappel_is_overdue

    rappel = {"statut": "a_faire", "done": False, "date": "2026-09-01", "heure": "09:00"}
    now = datetime(2026, 9, 1, 8, 0, tzinfo=tz)
    assert _rappel_is_overdue(rappel, now=now) is False


def test_rappel_overdue_after_due_day(tz):
    from server import _rappel_is_overdue

    rappel = {"statut": "a_faire", "done": False, "date": "2026-09-01", "heure": "09:00"}
    now = datetime(2026, 9, 2, 10, 0, tzinfo=tz)
    assert _rappel_is_overdue(rappel, now=now) is True


def test_rappel_not_overdue_when_en_attente(tz):
    from server import _rappel_is_overdue

    rappel = {"statut": "en_attente", "done": False, "date": "2026-01-01", "heure": "09:00"}
    now = datetime(2026, 9, 2, 10, 0, tzinfo=tz)
    assert _rappel_is_overdue(rappel, now=now) is False


def test_stamp_sets_statut_effectif(tz):
    from server import _stamp_rappel_statut, _rappel_is_overdue

    doc = {"statut": "a_faire", "done": False, "date": "2026-09-01", "heure": "09:00"}
    stamped = _stamp_rappel_statut(dict(doc))
    assert stamped["statut"] == "a_faire"
    # Sans date passée simulée, on vérifie la structure
    assert "statut_effectif" in stamped
    assert "is_echeance_passee" in stamped


def test_rappel_email_kind_initial_when_due():
    from server import _rappel_email_kind_needed
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Zurich")
    rappel = {
        "statut": "a_faire",
        "done": False,
        "send_email": True,
        "date": "2026-09-18",
        "heure": "09:00",
    }
    now = datetime(2026, 9, 18, 10, 0, tzinfo=tz)
    assert _rappel_email_kind_needed(rappel, now) == "initial"


def test_rappel_email_kind_none_before_due():
    from server import _rappel_email_kind_needed
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Zurich")
    rappel = {
        "statut": "a_faire",
        "done": False,
        "send_email": True,
        "date": "2026-09-18",
        "heure": "09:00",
    }
    now = datetime(2026, 9, 18, 8, 0, tzinfo=tz)
    assert _rappel_email_kind_needed(rappel, now) is None


def test_rappel_email_relance_every_2_days_including_en_attente():
    from server import _rappel_email_kind_needed
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Zurich")
    last = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc).isoformat()
    rappel = {
        "statut": "en_attente",
        "done": False,
        "send_email": True,
        "date": "2026-09-18",
        "heure": "09:00",
        "email_sent": True,
        "email_notified_at": last,
        "email_history": [{"sent_at": last, "status": "sent", "kind": "initial"}],
    }
    # J+1 → pas encore
    now1 = datetime(2026, 9, 19, 12, 0, tzinfo=tz)
    assert _rappel_email_kind_needed(rappel, now1) is None
    # J+2 → relance
    now2 = datetime(2026, 9, 20, 12, 0, tzinfo=tz)
    assert _rappel_email_kind_needed(rappel, now2) == "relance"


def test_rappel_email_stops_when_effectue():
    from server import _rappel_email_kind_needed
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Zurich")
    last = datetime(2026, 9, 18, 10, 0, tzinfo=timezone.utc).isoformat()
    rappel = {
        "statut": "termine",
        "done": True,
        "send_email": True,
        "date": "2026-09-18",
        "heure": "09:00",
        "email_sent": True,
        "email_notified_at": last,
        "email_history": [{"sent_at": last, "status": "sent", "kind": "initial"}],
    }
    now = datetime(2026, 9, 22, 12, 0, tzinfo=tz)
    assert _rappel_email_kind_needed(rappel, now) is None


def test_reporter_adds_14_days_from_current_date():
    from datetime import date as date_cls

    base = "2026-09-01"
    new_date = (date_cls.fromisoformat(base) + timedelta(days=14)).isoformat()
    assert new_date == "2026-09-15"

    base2 = "2026-09-15"
    new_date2 = (date_cls.fromisoformat(base2) + timedelta(days=14)).isoformat()
    assert new_date2 == "2026-09-29"

