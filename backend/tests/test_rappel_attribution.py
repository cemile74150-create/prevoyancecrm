"""Attribution créateur des rappels : create, isolation Mes rappels, immutabilité, legacy."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import (  # noqa: E402
    _rappel_creator_id,
    _rappel_creator_snapshot,
    _stamp_rappel_creator,
    _stamp_rappel_statut,
    _strip_rappel_creator_from_updates,
)


def _user(**kwargs):
    base = {
        "account_id": "user_cemile01",
        "name": "Cemile Demirtas",
        "email": "cemile@cabinet.ch",
        "user_id": "tenant_crm",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_creator_snapshot_from_session_only():
    snap = _rappel_creator_snapshot(_user())
    assert snap["created_by_user_id"] == "user_cemile01"
    assert snap["created_by_name"] == "Cemile Demirtas"
    assert snap["created_by_email"] == "cemile@cabinet.ch"
    assert snap["created_by"] == "user_cemile01"
    assert snap["author"] == "Cemile Demirtas"


def test_strip_creator_from_updates_preserves_other_fields():
    updates = {
        "titre": "Nouveau titre",
        "created_by_user_id": "hacker",
        "created_by_name": "Fake",
        "created_by_email": "fake@x.ch",
        "created_by": "hacker",
        "author": "Fake",
        "date": "2026-09-20",
    }
    cleaned = _strip_rappel_creator_from_updates(updates)
    assert cleaned["titre"] == "Nouveau titre"
    assert cleaned["date"] == "2026-09-20"
    assert "created_by_user_id" not in cleaned
    assert "created_by_name" not in cleaned
    assert "created_by_email" not in cleaned
    assert "created_by" not in cleaned
    assert "author" not in cleaned


def test_stamp_legacy_uses_created_by_and_author():
    doc = {
        "statut": "a_faire",
        "done": False,
        "date": "2099-01-01",
        "heure": "09:00",
        "created_by": "user_legacy",
        "author": "Ancien User",
        "created_at": "2025-01-01T10:00:00+00:00",
    }
    stamped = _stamp_rappel_statut(dict(doc))
    assert stamped["created_by_user_id"] == "user_legacy"
    assert stamped["created_by_name"] == "Ancien User"


def test_stamp_legacy_without_creator_id():
    doc = {
        "statut": "a_faire",
        "done": False,
        "date": "2099-01-01",
        "heure": "09:00",
        "author": None,
        "created_at": "2025-01-01T10:00:00+00:00",
    }
    stamped = _stamp_rappel_creator(dict(doc))
    assert stamped["created_by_user_id"] is None
    assert stamped["created_by_name"] is None
    assert _rappel_creator_id(stamped) is None


def test_mine_isolation_logic_excludes_null_creator():
    """Mes rappels : uniquement si id créateur présent et égal à moi."""
    me = "user_cemile01"
    mine = {"created_by_user_id": me, "titre": "A"}
    legacy_ok = {"created_by": me, "titre": "B"}
    other = {"created_by_user_id": "user_other", "titre": "C"}
    orphan = {"author": "Quelqu'un", "titre": "D"}  # pas d'id → exclus

    def belongs(doc):
        cid = _rappel_creator_id(doc)
        return bool(cid) and cid == me

    assert belongs(mine) is True
    assert belongs(legacy_ok) is True
    assert belongs(other) is False
    assert belongs(orphan) is False


def test_update_does_not_change_creator_fields_in_payload_strip():
    """Simule un PATCH : les champs créateur sont retirés avant $set."""
    original = _rappel_creator_snapshot(_user())
    updates = {
        "titre": "Modifié",
        "statut": "en_attente",
        **{k: "SHOULD_NOT_APPLY" for k in original},
    }
    _strip_rappel_creator_from_updates(updates)
    for key in original:
        assert key not in updates
    assert updates["titre"] == "Modifié"
