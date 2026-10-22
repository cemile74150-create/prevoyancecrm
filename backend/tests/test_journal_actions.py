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


def test_action_stays_on_its_client_or_shared_dossier():
    scope = {"member_ids": ["c1", "c2"], "dossier_id": "dos-1"}
    assert journal_belongs_to_scope({"client_id": "c1", "dossier_id": "dos-1"}, scope)
    assert journal_belongs_to_scope({"client_id": "other", "dossier_id": "dos-1"}, scope)
    assert journal_belongs_to_scope({"client_id": "other", "dossier_id": "dos-9"}, scope) is False
