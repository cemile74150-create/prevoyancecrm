"""Tests rétention Infomaniak (sélection 7 plus récentes) — sans S3 réel."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from scripts.backup_remote import select_crmbak_for_retention


def _item(name: str, days_ago: int) -> dict:
    return {
        "key": f"crm-backups/{name}",
        "size": 100,
        "last_modified": datetime.now(timezone.utc) - timedelta(days=days_ago),
    }


def test_keeps_seven_newest_only():
    items = [
        _item("prevoyancecrm_backup_20260801.tar.gz.crmbak", 26),
        _item("prevoyancecrm_backup_20260810.tar.gz.crmbak", 17),
        _item("prevoyancecrm_backup_20260820.tar.gz.crmbak", 7),
        _item("prevoyancecrm_backup_20260821.tar.gz.crmbak", 6),
        _item("prevoyancecrm_backup_20260822.tar.gz.crmbak", 5),
        _item("prevoyancecrm_backup_20260823.tar.gz.crmbak", 4),
        _item("prevoyancecrm_backup_20260824.tar.gz.crmbak", 3),
        _item("prevoyancecrm_backup_20260825.tar.gz.crmbak", 2),
        _item("prevoyancecrm_backup_20260826.tar.gz.crmbak", 1),
        _item("prevoyancecrm_backup_20260827.tar.gz.crmbak", 0),
        {"key": "crm-backups/", "size": 0, "last_modified": datetime.now(timezone.utc)},
    ]
    keep, delete = select_crmbak_for_retention(items, 7)
    assert len(keep) == 7
    assert len(delete) == 3
    assert all(k["key"].endswith(".crmbak") for k in keep + delete)
    assert keep[0]["key"].endswith("20260827.tar.gz.crmbak")
    assert delete[-1]["key"].endswith("20260801.tar.gz.crmbak")
    keep_keys = {k["key"] for k in keep}
    assert all(d["key"] not in keep_keys for d in delete)


def test_keep_seven_with_fewer_archives_deletes_nothing():
    items = [_item(f"prevoyancecrm_backup_{i}.tar.gz.crmbak", i) for i in range(6)]
    keep, delete = select_crmbak_for_retention(items, 7)
    assert len(keep) == 6
    assert delete == []


def test_keep_zero_skips():
    items = [_item("prevoyancecrm_backup_x.tar.gz.crmbak", 0)]
    keep, delete = select_crmbak_for_retention(items, 0)
    assert keep == [] and delete == []
