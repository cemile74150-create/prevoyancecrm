"""Nouveau conseiller (access_by_account_id_only=true) : cycle dossier + isolation.

Couvre la création stampée, l'accès après « reconnexion », notes/docs/demande,
et le refus des dossiers collègues — sans désactiver le flag.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_CONSEILLER,
    can_access_client,
    clients_base_query,
    force_conseiller_on_write,
    match_account_id_among_users,
    resolve_access_by_account_id_only_update,
    resolve_conseiller_account_id_for_write,
    should_stamp_conseiller_account_id_on_update,
    user_from_doc,
)
from demandes_offres_3p import can_access_demande  # noqa: E402
from suivi_3p import suivi_3p_base_query  # noqa: E402


def _conseiller(account_id: str, prenom: str, nom: str, *, access_only: bool = True, **extra):
    doc = {
        "user_id": account_id,
        "email": f"{prenom.lower()}@test.ch",
        "prenom": prenom,
        "nom": nom,
        "name": f"{prenom} {nom}",
        "role": ROLE_CONSEILLER,
        "conseiller": f"{prenom} {nom}",
        "active": True,
        "access_by_account_id_only": access_only,
        "see_all_dossiers": False,
        **extra,
    }
    return user_from_doc(doc)


def _admin(account_id: str = "admin1"):
    return user_from_doc(
        {
            "user_id": account_id,
            "email": "admin@test.ch",
            "prenom": "Admin",
            "nom": "Mendes",
            "name": "Admin Mendes",
            "role": ROLE_ADMIN,
            "active": True,
            "see_all_dossiers": True,
        }
    )


def _stamp_create(user, conseiller_label=None, matched=None):
    label = force_conseiller_on_write(user, conseiller_label)
    aid = resolve_conseiller_account_id_for_write(
        user, label, matched_account_id=matched
    )
    return label, aid


def test_new_conseiller_create_stamps_own_account_id():
    new = _conseiller("u_new", "Nora", "Nouveau")
    label, aid = _stamp_create(new, "Quelqu'un D'autre")
    assert label == "Nora Nouveau"
    assert aid == "u_new"
    dossier = {
        "id": "d1",
        "conseiller": label,
        "conseiller_account_id": aid,
        "prenom": "Client",
        "nom": "A",
    }
    assert can_access_client(new, dossier) is True


def test_new_conseiller_without_stamp_blocked_regression():
    """Comportement Bugbot : sans stamp, accès refusé malgré le bon nom."""
    new = _conseiller("u_new", "Nora", "Nouveau")
    assert can_access_client(
        new, {"conseiller": "Nora Nouveau", "conseiller_account_id": None}
    ) is False


def test_admin_create_for_designated_conseiller_uses_matched_id():
    admin = _admin()
    users = [
        {
            "user_id": "u_val",
            "role": ROLE_CONSEILLER,
            "conseiller": "Valentin Lugnier",
            "name": "Valentin Lugnier",
            "prenom": "Valentin",
            "nom": "Lugnier",
            "active": True,
        },
        {
            "user_id": "u_eme",
            "role": ROLE_CONSEILLER,
            "conseiller": "Emeric Laugerette",
            "name": "Emeric Laugerette",
            "prenom": "Emeric",
            "nom": "Laugerette",
            "active": True,
        },
    ]
    matched = match_account_id_among_users("Valentin Lugnier", users)
    assert matched == "u_val"
    label, aid = _stamp_create(admin, "Valentin Lugnier", matched=matched)
    assert label == "Valentin Lugnier"
    assert aid == "u_val"


def test_admin_edit_without_reattribution_does_not_force_stamp():
    admin = _admin()
    assert (
        should_stamp_conseiller_account_id_on_update(
            user=admin,
            old_conseiller="Valentin Lugnier",
            new_conseiller="Valentin Lugnier",
            old_account_id=None,
        )
        is False
    )


def test_admin_reattribution_updates_stamp():
    admin = _admin()
    assert (
        should_stamp_conseiller_account_id_on_update(
            user=admin,
            old_conseiller="Valentin Lugnier",
            new_conseiller="Emeric Laugerette",
            old_account_id="u_val",
        )
        is True
    )
    matched = match_account_id_among_users(
        "Emeric Laugerette",
        [
            {
                "user_id": "u_eme",
                "role": ROLE_CONSEILLER,
                "conseiller": "Emeric Laugerette",
                "name": "Emeric Laugerette",
                "active": True,
            }
        ],
    )
    aid = resolve_conseiller_account_id_for_write(
        admin, "Emeric Laugerette", matched_account_id=matched
    )
    assert aid == "u_eme"


def test_full_lifecycle_create_list_reopen_modify_notes_docs_demande_relogin():
    new = _conseiller("u_new", "Nora", "Nouveau")
    colleague = _conseiller("u_col", "Colin", "Collègue")

    # 1. Créer un dossier (stamp serveur)
    label, aid = _stamp_create(new)
    dossier = {
        "id": str(uuid.uuid4()),
        "user_id": "local-dev",
        "prenom": "Alice",
        "nom": "Client",
        "conseiller": label,
        "conseiller_account_id": aid,
        "in_dossiers": True,
        "statut": "Nouveau",
    }
    assert aid == "u_new"
    assert can_access_client(new, dossier) is True

    # 2. Tableau de bord / liste
    q = clients_base_query(new, for_dossiers=True)
    assert {"conseiller_account_id": "u_new"} in q.get("$or", [])
    assert {"agent_account_id": "u_new"} in q.get("$or", [])

    # 3. Rouvrir + modifier (même accès)
    dossier["statut"] = "Documents en attente"
    dossier["notes_internes"] = "relance"
    assert can_access_client(new, dossier) is True

    # 4. Documents + notes liés au client_id
    note = {"id": "n1", "client_id": dossier["id"], "created_by": "u_new", "texte": "note"}
    document = {"id": "doc1", "client_id": dossier["id"], "filename": "caisse.pdf"}
    # Accès via le dossier parent
    assert can_access_client(new, dossier) is True
    assert note["client_id"] == dossier["id"]
    assert document["client_id"] == dossier["id"]

    # 5. Demande d'offre liée
    demande = {
        "id": "dem1",
        "client_id": dossier["id"],
        "agent_label": label,
        "agent_account_id": "u_new",
        "created_by_account_id": "u_new",
        "is_deleted": False,
    }
    assert can_access_demande(new, demande) is True
    assert can_access_demande(colleague, demande) is False

    # 6. Déconnexion / reconnexion = recharger le user depuis le doc
    reloaded = _conseiller("u_new", "Nora", "Nouveau", access_only=True)
    assert reloaded.access_by_account_id_only is True
    assert can_access_client(reloaded, dossier) is True
    assert can_access_demande(reloaded, demande) is True

    # 7. Isolation collègue (même si libellé homonyme)
    foreign = {
        "id": "d-col",
        "conseiller": "Nora Nouveau",  # homonyme volontaire
        "conseiller_account_id": "u_col",
    }
    assert can_access_client(new, foreign) is False
    assert can_access_client(colleague, foreign) is True
    assert can_access_client(colleague, dossier) is False


def test_legacy_mendes_still_name_based_without_stamp():
    valentin = _conseiller(
        "u_val", "Valentin", "Lugnier", access_only=False
    )
    old_dossier = {"conseiller": "Valentin Lugnier"}  # pas d'account_id
    assert valentin.access_by_account_id_only is False
    assert can_access_client(valentin, old_dossier) is True


def test_role_change_to_conseiller_forces_flag():
    val, err = resolve_access_by_account_id_only_update(
        current=False,
        incoming=None,
        role=ROLE_CONSEILLER,
        previous_role=ROLE_ADMIN,
    )
    assert val is True
    assert err is None


def test_role_change_cannot_bypass_flag():
    val, err = resolve_access_by_account_id_only_update(
        current=False,
        incoming=False,
        role=ROLE_CONSEILLER,
        previous_role=ROLE_ADMIN,
    )
    assert val is True
    assert err


def test_suivi_list_uses_account_filter_for_new_conseiller():
    new = _conseiller("u_new", "Nora", "Nouveau")
    q = suivi_3p_base_query(new)
    assert {"conseiller_account_id": "u_new"} in q.get("$or", [])
    assert {"agent_account_id": "u_new"} in q.get("$or", [])


def test_flag_stays_true_never_disabled():
    new = _conseiller("u_new", "Nora", "Nouveau", access_only=True)
    assert new.access_by_account_id_only is True
    val, err = resolve_access_by_account_id_only_update(
        current=True, incoming=False, role=ROLE_CONSEILLER
    )
    assert val is True
    assert err


def test_role_roundtrip_preserves_locked_flag():
    # conseiller → admin sans toucher au flag : conserve True
    val, err = resolve_access_by_account_id_only_update(
        current=True, incoming=None, role=ROLE_ADMIN, previous_role=ROLE_CONSEILLER
    )
    assert val is True
    assert err is None


def test_spouse_inherits_parent_account_stamp():
    new = _conseiller("u_new", "Nora", "Nouveau")
    primary = {
        "conseiller": "Nora Nouveau",
        "conseiller_account_id": "u_new",
    }
    spouse = {
        "conseiller": primary["conseiller"],
        "conseiller_account_id": primary.get("conseiller_account_id"),
    }
    assert can_access_client(new, primary) is True
    assert can_access_client(new, spouse) is True


def test_strict_list_filter_accepts_agent_account_id():
    new = _conseiller("u_new", "Nora", "Nouveau")
    q = clients_base_query(new, for_dossiers=True)
    assert "$or" in q
    assert {"conseiller_account_id": "u_new"} in q["$or"]
    assert {"agent_account_id": "u_new"} in q["$or"]
    # Dossier stampé via agent_account_id seulement → accessible en GET
    assert can_access_client(
        new, {"agent_account_id": "u_new", "conseiller": "Autre"}
    ) is True
