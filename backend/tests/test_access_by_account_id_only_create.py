"""Nouveaux conseillers : access_by_account_id_only forcé et verrouillé."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (
    ROLE_ADMIN,
    ROLE_CONSEILLER,
    force_access_by_account_id_only_on_create,
    resolve_access_by_account_id_only_update,
)


def test_create_conseiller_forces_flag():
    assert force_access_by_account_id_only_on_create(ROLE_CONSEILLER) is True
    assert force_access_by_account_id_only_on_create(ROLE_ADMIN) is False


def test_cannot_disable_once_true():
    val, err = resolve_access_by_account_id_only_update(
        current=True, incoming=False, role=ROLE_CONSEILLER
    )
    assert val is True
    assert err


def test_legacy_pascal_can_stay_false_if_not_touched():
    val, err = resolve_access_by_account_id_only_update(
        current=False, incoming=None, role=ROLE_CONSEILLER
    )
    assert val is False
    assert err is None


def test_admin_can_enable_on_legacy_conseiller():
    val, err = resolve_access_by_account_id_only_update(
        current=False, incoming=True, role=ROLE_CONSEILLER
    )
    assert val is True
    assert err is None


def test_promotion_to_conseiller_forces_flag():
    from access_control import ROLE_ADMIN

    val, err = resolve_access_by_account_id_only_update(
        current=False,
        incoming=None,
        role=ROLE_CONSEILLER,
        previous_role=ROLE_ADMIN,
    )
    assert val is True
    assert err is None
