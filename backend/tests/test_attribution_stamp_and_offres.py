"""Corrections Bugbot High : conservation stamp admin + attribution offres."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    can_access_client,
    decide_conseiller_account_id_on_update,
    default_see_all_dossiers,
    set_runtime_access_mode_override,
    should_stamp_conseiller_account_id_on_update,
    user_from_doc,
)
from demandes_offres_3p import can_access_demande  # noqa: E402
from offre_agent_identity import resolve_offre_agent_account_id  # noqa: E402


def _u(role, account_id, prenom, nom, **extra):
    doc = {
        "user_id": account_id,
        "email": f"{account_id}@test.ch",
        "prenom": prenom,
        "nom": nom,
        "name": f"{prenom} {nom}",
        "role": role,
        "conseiller": f"{prenom} {nom}" if role == ROLE_CONSEILLER else None,
        "active": True,
        "see_all_dossiers": default_see_all_dossiers(role),
        **extra,
    }
    return user_from_doc(doc)


def test_admin_edit_same_conseiller_does_not_write_stamp():
    admin = _u(ROLE_ADMIN, "admin1", "Admin", "Mendes")
    assert (
        should_stamp_conseiller_account_id_on_update(
            user=admin,
            old_conseiller="Nora Nouveau",
            new_conseiller="Nora Nouveau",
            old_account_id="u_new",
        )
        is False
    )
    write, val, reattrib = decide_conseiller_account_id_on_update(
        user=admin,
        old_conseiller="Nora Nouveau",
        new_conseiller="Nora Nouveau",
        old_account_id="u_new",
        matched_account_id=None,  # lookup would fail
    )
    assert write is False
    assert val == "u_new"
    assert reattrib is False


def test_admin_lookup_failure_never_wipes_existing_stamp():
    admin = _u(ROLE_ADMIN, "admin1", "Admin", "Mendes")
    write, val, reattrib = decide_conseiller_account_id_on_update(
        user=admin,
        old_conseiller="Nora Nouveau",
        new_conseiller="Nora Nouveau",
        old_account_id="u_new",
        matched_account_id=None,
    )
    assert write is False
    assert val == "u_new"
    # Champ non écrit → Mongo conserve conseiller_account_id
    doc = {"conseiller": "Nora Nouveau", "conseiller_account_id": "u_new"}
    new_user = _u(
        ROLE_CONSEILLER, "u_new", "Nora", "Nouveau", access_by_account_id_only=True
    )
    assert can_access_client(new_user, doc) is True


def test_admin_explicit_reattribution_updates_stamp_and_flags_history():
    admin = _u(ROLE_ADMIN, "admin1", "Admin", "Mendes")
    assert (
        should_stamp_conseiller_account_id_on_update(
            user=admin,
            old_conseiller="Nora Nouveau",
            new_conseiller="Colin Collegue",
            old_account_id="u_new",
        )
        is True
    )
    write, val, reattrib = decide_conseiller_account_id_on_update(
        user=admin,
        old_conseiller="Nora Nouveau",
        new_conseiller="Colin Collegue",
        old_account_id="u_new",
        matched_account_id="u_col",
    )
    assert write is True
    assert val == "u_col"
    assert reattrib is True


def test_admin_explicit_reattribution_without_match_clears_stamp():
    admin = _u(ROLE_ADMIN, "admin1", "Admin", "Mendes")
    write, val, reattrib = decide_conseiller_account_id_on_update(
        user=admin,
        old_conseiller="Nora Nouveau",
        new_conseiller="Service Fiscal",
        old_account_id="u_new",
        matched_account_id=None,
    )
    assert write is True
    assert val is None
    assert reattrib is True


def test_conseiller_create_offre_for_self():
    agent = resolve_offre_agent_account_id(
        creator_account_id="u_new",
        assigned_to_account_id=None,
    )
    assert agent == "u_new"
    demande = {
        "created_by_account_id": "u_new",
        "agent_account_id": agent,
        "agent_label": "Nora Nouveau",
    }
    assert demande["created_by_account_id"] == demande["agent_account_id"]


def test_admin_create_offre_for_conseiller_keeps_creator_and_agent_distinct():
    agent = resolve_offre_agent_account_id(
        creator_account_id="admin1",
        assigned_to_account_id="u_new",
    )
    assert agent == "u_new"
    demande = {
        "created_by_account_id": "admin1",
        "created_by_name": "Admin Mendes",
        "agent_account_id": agent,
        "assigned_to_account_id": "u_new",
    }
    assert demande["created_by_account_id"] == "admin1"
    assert demande["agent_account_id"] == "u_new"


def test_hub_stamp_uses_agent_not_creator():
    """Création hub depuis offre : conseiller_account_id = agent, pas le gestionnaire."""
    creator = "gest1"
    agent = resolve_offre_agent_account_id(
        creator_account_id=creator,
        assigned_to_account_id="u_new",
    )
    hub_stamp = agent  # comme demandes_offres_routes (agent_account_id)
    assert hub_stamp == "u_new"
    assert hub_stamp != creator


def test_offre_visibility_legacy_dual_strict_and_isolation():
    nora = _u(
        ROLE_CONSEILLER, "u_new", "Nora", "Nouveau", access_by_account_id_only=True
    )
    colin = _u(
        ROLE_CONSEILLER, "u_col", "Colin", "Collegue", access_by_account_id_only=True
    )
    demande_nora = {
        "agent_account_id": "u_new",
        "created_by_account_id": "admin1",
        "agent_label": "Nora Nouveau",
    }
    demande_colin = {
        "agent_account_id": "u_col",
        "created_by_account_id": "admin1",
        "agent_label": "Colin Collegue",
    }

    try:
        for mode in ("legacy", "dual", "strict"):
            set_runtime_access_mode_override(mode)
            # Nora account-only → strict effectif même en legacy instance
            assert can_access_demande(nora, demande_nora) is True
            assert can_access_demande(nora, demande_colin) is False
            assert can_access_demande(colin, demande_colin) is True
            assert can_access_demande(colin, demande_nora) is False
    finally:
        set_runtime_access_mode_override(None)


def test_dossier_isolation_between_conseillers():
    nora = _u(
        ROLE_CONSEILLER, "u_new", "Nora", "Nouveau", access_by_account_id_only=True
    )
    colin = _u(
        ROLE_CONSEILLER, "u_col", "Colin", "Collegue", access_by_account_id_only=True
    )
    d_nora = {"conseiller": "Nora Nouveau", "conseiller_account_id": "u_new"}
    d_colin = {"conseiller": "Colin Collegue", "conseiller_account_id": "u_col"}
    assert can_access_client(nora, d_nora) is True
    assert can_access_client(nora, d_colin) is False
    assert can_access_client(colin, d_colin) is True
    assert can_access_client(colin, d_nora) is False


def test_legacy_mendes_untouched_by_stamp_helpers():
    valentin = _u(ROLE_CONSEILLER, "u_val", "Valentin", "Lugnier")
    assert valentin.access_by_account_id_only is False
    old = {"conseiller": "Valentin Lugnier"}
    assert can_access_client(valentin, old) is True
    admin = _u(ROLE_ADMIN, "admin1", "Admin", "Mendes")
    write, _, _ = decide_conseiller_account_id_on_update(
        user=admin,
        old_conseiller="Valentin Lugnier",
        new_conseiller="Valentin Lugnier",
        old_account_id=None,
        matched_account_id="u_val",
    )
    # Pas de migration silencieuse des dossiers sans stamp
    assert write is False


def test_creator_save_does_not_overwrite_assigned_agent_identity():
    from offre_agent_identity import resolve_agent_identity_for_write

    admin = _u(ROLE_ADMIN, "admin1", "Admin", "Mendes")
    doc = {
        "created_by_account_id": "admin1",
        "agent_account_id": "u_new",
        "agent_prenom": "Nora",
        "agent_nom": "Nouveau",
        "agent_email": "nora@test.ch",
        "agent_label": "Nora Nouveau",
        "agent_finma": "F-1",
    }
    agent_identity = {
        "prenom": "Nora",
        "nom": "Nouveau",
        "email": "nora@test.ch",
        "finma": "F-1",
        "label": "Nora Nouveau",
        "account_id": "u_new",
    }
    resolved = resolve_agent_identity_for_write(
        doc, admin, creator_identity=agent_identity
    )
    assert resolved["prenom"] == "Nora"
    assert resolved["email"] == "nora@test.ch"
    assert resolved["label"] == "Nora Nouveau"


def test_signature_follow_uses_agent_not_operator_creator():
    nora = _u(ROLE_CONSEILLER, "u_new", "Nora", "Nouveau")
    admin = _u(ROLE_ADMIN, "admin1", "Admin", "Mendes")
    doc = {
        "created_by_account_id": "admin1",
        "agent_account_id": "u_new",
        "agent_label": "Nora Nouveau",
    }
    from demandes_offres_3p import can_follow_signature

    assert can_follow_signature(nora, doc) is True
    assert can_follow_signature(admin, doc) is False
