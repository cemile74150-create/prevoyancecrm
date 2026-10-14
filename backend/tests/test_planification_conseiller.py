"""Le conseiller standard ne peut pas changer l'identité enregistrée."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyse_conseiller import is_planification_admin, lock_conseiller_nom


def _user(name, role="conseiller", can_manage_users=False):
    return SimpleNamespace(name=name, role=role, can_manage_users=can_manage_users)


def test_conseiller_cannot_replace_identity():
    user = _user("Ada Martin")
    saved = lock_conseiller_nom(
        {"conseillerNom": "Quelqu'un d'autre", "villeRecherche": "Lausanne"},
        {"conseillerNom": "Ada Martin"},
        user,
    )
    assert saved["conseillerNom"] == "Ada Martin"
    assert saved["villeRecherche"] == "Lausanne"
    assert is_planification_admin(user) is False


def test_new_plan_uses_authenticated_name():
    saved = lock_conseiller_nom(
        {"conseillerNom": "Intrus"},
        None,
        _user("Ada Martin"),
    )
    assert saved["conseillerNom"] == "Ada Martin"


def test_existing_conseiller_is_kept_for_another_standard_user():
    saved = lock_conseiller_nom(
        {"conseillerNom": "Ada Martin"},
        {"conseillerNom": "Paul Conseiller"},
        _user("Ada Martin"),
    )
    assert saved["conseillerNom"] == "Paul Conseiller"


def test_admin_can_select_another_conseiller():
    admin = _user("Admin Leo", role="admin", can_manage_users=True)
    saved = lock_conseiller_nom(
        {"conseillerNom": "Paul Conseiller"},
        {"conseillerNom": "Admin Leo"},
        admin,
    )
    assert saved["conseillerNom"] == "Paul Conseiller"
    assert is_planification_admin(admin) is True
