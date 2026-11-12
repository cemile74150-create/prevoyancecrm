"""Tests de la politique dual-read / stricte (non branchée en production)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import ROLE_ADMIN, ROLE_CONSEILLER, default_see_all_dossiers, user_from_doc
from access_dual_read import can_access_client_dual_read, can_access_client_strict


def _u(role, account_id, name, **extra):
    prenom, _, nom = name.partition(" ")
    doc = {
        "user_id": account_id,
        "email": f"{account_id}@test.ch",
        "prenom": prenom or name,
        "nom": nom or name,
        "name": name,
        "role": role,
        "conseiller": name if role == ROLE_CONSEILLER else None,
        "active": True,
        "see_all_dossiers": default_see_all_dossiers(role),
        **extra,
    }
    return user_from_doc(doc)


def test_dual_read_uses_account_id_when_present():
    alice = _u(ROLE_CONSEILLER, "u_a", "Alice Conseil")
    bob = _u(ROLE_CONSEILLER, "u_b", "Bob Collègue")
    doc = {"conseiller": "Bob Collègue", "conseiller_account_id": "u_b"}
    assert can_access_client_dual_read(bob, doc) is True
    assert can_access_client_dual_read(alice, doc) is False


def test_dual_read_fallback_name_preserves_pascal_couple_without_id():
    pascal = _u(ROLE_CONSEILLER, "u_p", "Pascal Maret")
    doc = {"conseiller": "Pascal Maret"}  # pas d'account_id (couple ambigu)
    assert can_access_client_dual_read(pascal, doc) is True
    assert can_access_client_strict(pascal, doc) is False


def test_dual_read_service_fiscal_supervisors_only():
    admin = _u(ROLE_ADMIN, "u_adm", "Admin Mendes")
    alice = _u(ROLE_CONSEILLER, "u_a", "Alice Conseil")
    doc = {"conseiller": "Service Fiscal (Impot)"}
    assert can_access_client_dual_read(admin, doc) is True
    assert can_access_client_dual_read(alice, doc) is False
    assert can_access_client_strict(admin, doc) is True
    assert can_access_client_strict(alice, doc) is False


def test_dual_read_bonvesting_keeps_name_until_validated():
    bonv = _u(ROLE_CONSEILLER, "u_bonv", "BONVESTING SNC", conseiller="Jordy Bonvin")
    doc = {"conseiller": "Jordy Bonvin"}  # exclu de la migration
    assert can_access_client_dual_read(bonv, doc) is True
    assert can_access_client_strict(bonv, doc) is False


def test_new_conseiller_account_id_only_never_name_fallback(monkeypatch):
    import access_control as ac

    monkeypatch.setattr(ac, "ACCESS_MODE", "dual")
    new = _u(
        ROLE_CONSEILLER,
        "u_new",
        "Valentin Lugnier",
        access_by_account_id_only=True,
    )
    orphan = {"conseiller": "Valentin Lugnier"}  # même nom, sans account_id
    owned = {"conseiller": "Valentin Lugnier", "conseiller_account_id": "u_new"}
    foreign = {"conseiller": "Valentin Lugnier", "conseiller_account_id": "u_old"}
    assert ac.can_access_client(new, orphan) is False
    assert ac.can_access_client(new, owned) is True
    assert ac.can_access_client(new, foreign) is False
    assert ac.effective_access_mode(new) == "strict"
