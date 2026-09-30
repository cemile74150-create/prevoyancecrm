"""Unit tests for CRM access permissions."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_CONSEILLER,
    PERM_USERS_MANAGE,
    PERM_CLIENTS_VIEW,
    PERM_CLIENTS_CREATE,
    PERM_DOSSIERS_VIEW,
    PERM_DOSSIERS_EDIT,
    PERM_DOCUMENTS_ADD,
    PERM_SUIVI_3P_VIEW,
    PERM_SUIVI_3P_EDIT,
    PERM_RAPPELS_VIEW,
    PERM_RAPPELS_EDIT,
    default_permissions,
    default_see_all_dossiers,
    resolve_permissions,
    resolve_see_all_dossiers,
    user_from_doc,
    is_global_viewer,
    can_access_client,
    clients_base_query,
    force_conseiller_on_write,
    permission_for_request,
    has_perm,
)


def _doc(**kwargs):
    base = {
        "user_id": "user_valentin",
        "email": "valentin@cabinet.ch",
        "prenom": "Valentin",
        "nom": "Lugnier",
        "name": "Valentin Lugnier",
        "role": ROLE_CONSEILLER,
        "conseiller": "Valentin Lugnier",
        "active": True,
    }
    base.update(kwargs)
    return base


def test_conseiller_defaults_hide_user_admin_and_other_dossiers():
    perms = default_permissions(ROLE_CONSEILLER)
    assert perms[PERM_CLIENTS_VIEW] is True
    assert perms[PERM_USERS_MANAGE] is False
    assert default_see_all_dossiers(ROLE_CONSEILLER) is False


def test_admin_defaults_see_all_and_manage_users():
    perms = default_permissions(ROLE_ADMIN)
    assert perms[PERM_USERS_MANAGE] is True
    assert default_see_all_dossiers(ROLE_ADMIN) is True
    assert default_see_all_dossiers(ROLE_CEO) is True
    assert default_permissions(ROLE_CEO)[PERM_USERS_MANAGE] is False


def test_stored_permission_override():
    doc = _doc(permissions={PERM_CLIENTS_VIEW: False, PERM_USERS_MANAGE: False})
    perms = resolve_permissions(doc)
    assert perms[PERM_CLIENTS_VIEW] is False
    assert perms[PERM_CLIENTS_CREATE] is True


def test_legacy_user_without_permissions_dict():
    admin = resolve_permissions({"role": ROLE_ADMIN, "can_manage_users": True})
    assert admin[PERM_USERS_MANAGE] is True
    conseiller = resolve_permissions({"role": ROLE_CONSEILLER})
    assert conseiller[PERM_USERS_MANAGE] is False
    assert resolve_see_all_dossiers({"role": ROLE_ADMIN}) is True
    assert resolve_see_all_dossiers({"role": ROLE_CONSEILLER}) is False
    assert resolve_see_all_dossiers({"role": ROLE_CONSEILLER, "see_all_dossiers": True}) is True


def test_conseiller_with_all_dossiers_flag():
    user = user_from_doc(_doc(see_all_dossiers=True))
    assert is_global_viewer(user) is True
    assert can_access_client(user, {"conseiller": "Alberto Mendes"}) is True
    q = clients_base_query(user)
    assert "conseiller" not in q


def test_conseiller_scoped_to_own_dossiers():
    user = user_from_doc(_doc())
    assert is_global_viewer(user) is False
    assert can_access_client(user, {"conseiller": "Valentin Lugnier"}) is True
    assert can_access_client(user, {"conseiller": "Alberto Mendes"}) is False
    q = clients_base_query(user)
    assert "$or" in q
    assert any(
        isinstance(clause.get("conseiller"), dict) and clause["conseiller"].get("$options") == "i"
        for clause in q["$or"]
    )
    assert force_conseiller_on_write(user, "Alberto Mendes") == "Valentin Lugnier"


def test_conseiller_sees_dossiers_case_insensitive_and_by_email():
    """Compte « Valentin LUGNIER » voit aussi les dossiers « Valentin Lugnier » / agent_email."""
    user = user_from_doc(_doc(conseiller="Valentin LUGNIER", email="vlugnier@agencemendes.ch"))
    assert can_access_client(user, {"conseiller": "Valentin Lugnier"}) is True
    assert can_access_client(user, {"conseiller": "valentin lugnier"}) is True
    assert can_access_client(user, {"agent_email": "vlugnier@agencemendes.ch"}) is True
    assert can_access_client(user, {"agent_email": "VLUGNIER@agencemendes.ch"}) is True
    assert can_access_client(user, {"conseiller": "Alberto Mendes"}) is False
    q = clients_base_query(user, for_dossiers=True)
    assert q["in_dossiers"] == {"$ne": False}
    assert any(
        (c.get("agent_email") or {}).get("$regex", "").lower().find("vlugnier") >= 0
        for c in q["$or"]
    )


def test_admin_still_sees_all_dossiers():
    user = user_from_doc(_doc(role=ROLE_ADMIN, see_all_dossiers=True, conseiller=None))
    assert is_global_viewer(user) is True
    q = clients_base_query(user, for_dossiers=True)
    assert "$or" not in q
    assert "conseiller" not in q


def test_dossiers_scope_excludes_hub_stubs():
    user = user_from_doc(_doc(see_all_dossiers=True))
    q_all = clients_base_query(user, for_dossiers=False)
    assert "in_dossiers" not in q_all
    q_dos = clients_base_query(user, for_dossiers=True)
    assert q_dos["in_dossiers"] == {"$ne": False}


def test_route_permissions():
    assert permission_for_request("GET", "/api/auth/me") is None
    assert permission_for_request("GET", "/api/users") == PERM_USERS_MANAGE
    assert permission_for_request("GET", "/api/clients") == (
        PERM_CLIENTS_VIEW,
        PERM_DOSSIERS_VIEW,
        "agenda.view",
        PERM_RAPPELS_VIEW,
        "demandes_offres.view",
        "suivi_3p.view",
    )
    assert permission_for_request("POST", "/api/clients") == (PERM_CLIENTS_CREATE, "dossiers.create")
    assert permission_for_request("PATCH", "/api/clients/abc/statut") == PERM_DOSSIERS_EDIT
    assert permission_for_request("POST", "/api/clients/abc/documents") == PERM_DOCUMENTS_ADD
    assert permission_for_request("GET", "/api/suivi-3p") == PERM_SUIVI_3P_VIEW
    assert permission_for_request("PUT", "/api/suivi-3p/abc") == PERM_SUIVI_3P_EDIT
    assert permission_for_request("GET", "/api/rappels") == PERM_RAPPELS_VIEW
    assert permission_for_request("GET", "/api/rappels/email-status") == PERM_RAPPELS_VIEW
    assert permission_for_request("POST", "/api/rappels") == PERM_RAPPELS_EDIT
    assert permission_for_request("GET", "/api/users/conseillers") is None


def test_has_perm_reads_user_permissions():
    user = user_from_doc(_doc(permissions={PERM_CLIENTS_VIEW: False}))
    assert has_perm(user, PERM_CLIENTS_VIEW) is False
    assert has_perm(user, PERM_CLIENTS_CREATE) is True
    assert has_perm(user, PERM_USERS_MANAGE) is False
