"""Étape 1 — isolation des accès (tests non destructifs, hors production).

Vérifie le comportement actuel + le comportement cible par account_id
(non branché sur les routes). Aucune écriture MongoDB.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    can_access_client,
    clients_base_query,
    default_see_all_dossiers,
    is_global_viewer,
    user_from_doc,
)
from attribution_matching import (  # noqa: E402
    planned_access_by_account_id,
    supervision_roles_keep_global,
)
from demandes_offres_3p import can_access_demande  # noqa: E402


def _user(role, account_id, prenom, nom, email, **extra):
    doc = {
        "user_id": account_id,
        "email": email,
        "prenom": prenom,
        "nom": nom,
        "name": f"{prenom} {nom}",
        "role": role,
        "conseiller": f"{prenom} {nom}" if role == ROLE_CONSEILLER else None,
        "active": True,
        **extra,
    }
    if "see_all_dossiers" not in doc:
        doc["see_all_dossiers"] = default_see_all_dossiers(role)
    return user_from_doc(doc)


def test_supervision_roles_documented():
    roles = supervision_roles_keep_global()
    assert roles[ROLE_ADMIN] is True
    assert roles[ROLE_CEO] is True
    assert roles[ROLE_GESTIONNAIRE_OFFRES] is True
    assert roles[ROLE_CONSEILLER] is False


def test_admin_ceo_gestionnaire_keep_global_view():
    admin = _user(ROLE_ADMIN, "a1", "Admin", "Mendes", "admin@test.ch")
    ceo = _user(ROLE_CEO, "c1", "Dir", "Mendes", "ceo@test.ch")
    gest = _user(ROLE_GESTIONNAIRE_OFFRES, "g1", "Gest", "Offres", "gest@test.ch")
    foreign = {"id": "d1", "conseiller": "Autre Personne", "conseiller_account_id": "other"}
    for u in (admin, ceo, gest):
        assert is_global_viewer(u) is True
        assert can_access_client(u, foreign) is True
        assert planned_access_by_account_id(u, foreign) is True
        q = clients_base_query(u)
        assert "$or" not in q


def test_conseiller_current_cannot_open_colleague_dossier_by_name():
    alice = _user(ROLE_CONSEILLER, "u_alice", "Alice", "Conseil", "alice@test.ch")
    bob_dossier = {"id": "d-bob", "conseiller": "Bob Collègue", "email": "client@x.ch"}
    assert can_access_client(alice, bob_dossier) is False


def test_conseiller_current_cannot_use_client_email_as_identity():
    """Même si l'e-mail client = e-mail du conseiller, pas d'accès sans champ conseiller."""
    alice = _user(ROLE_CONSEILLER, "u_alice", "Alice", "Conseil", "alice@test.ch")
    doc = {"id": "d1", "email": "alice@test.ch", "telephone": "079", "conseiller": "Bob Collègue"}
    assert can_access_client(alice, doc) is False


def test_planned_account_id_blocks_url_guessing():
    alice = _user(ROLE_CONSEILLER, "u_alice", "Alice", "Conseil", "alice@test.ch")
    bob = _user(ROLE_CONSEILLER, "u_bob", "Bob", "Collègue", "bob@test.ch")
    dossier_bob = {
        "id": "d-bob",
        "conseiller": "Bob Collègue",
        "conseiller_account_id": "u_bob",
    }
    doc_bob = {"id": "doc1", "conseiller_account_id": "u_bob", "client_id": "d-bob"}
    offre_bob = {
        "id": "o1",
        "agent_label": "Bob Collègue",
        "agent_account_id": "u_bob",
        "created_by_account_id": "u_bob",
    }
    assert planned_access_by_account_id(alice, dossier_bob) is False
    assert planned_access_by_account_id(bob, dossier_bob) is True
    assert planned_access_by_account_id(alice, doc_bob) is False
    assert planned_access_by_account_id(alice, offre_bob) is False
    assert planned_access_by_account_id(bob, offre_bob) is True


def test_planned_account_id_preserves_supervision():
    gest = _user(ROLE_GESTIONNAIRE_OFFRES, "g1", "Gest", "Offres", "gest@test.ch")
    dossier_bob = {"conseiller_account_id": "u_bob"}
    assert planned_access_by_account_id(gest, dossier_bob) is True


def test_current_offres_isolation_between_conseillers():
    alice = _user(ROLE_CONSEILLER, "u_alice", "Alice", "Conseil", "alice@test.ch")
    bob_offre = {
        "agent_label": "Bob Collègue",
        "agent_email": "bob@test.ch",
        "created_by_account_id": "u_bob",
    }
    assert can_access_demande(alice, bob_offre) is False
    alice_offre = {
        "agent_label": "Alice Conseil",
        "agent_email": "alice@test.ch",
        "created_by_account_id": "u_alice",
    }
    assert can_access_demande(alice, alice_offre) is True


def test_gestionnaire_sees_all_offres():
    gest = _user(ROLE_GESTIONNAIRE_OFFRES, "g1", "Gest", "Offres", "gest@test.ch")
    offre = {"agent_label": "Alice Conseil", "created_by_account_id": "u_alice"}
    assert can_access_demande(gest, offre) is True


def test_document_and_note_follow_planned_dossier_owner():
    """Documents / notes : après bascule, l'UUID seul ne suffit pas — account_id requis."""
    alice = _user(ROLE_CONSEILLER, "u_alice", "Alice", "Conseil", "alice@test.ch")
    note_colleague = {"id": "n1", "client_id": "d-bob", "conseiller_account_id": "u_bob"}
    rappel_colleague = {"id": "r1", "client_id": "d-bob", "conseiller_account_id": "u_bob"}
    analyse_colleague = {"id": "an1", "client_id": "d-bob", "conseiller_account_id": "u_bob"}
    agenda_colleague = {"id": "ap1", "client_id": "d-bob", "conseiller_account_id": "u_bob"}
    for resource in (note_colleague, rappel_colleague, analyse_colleague, agenda_colleague):
        assert planned_access_by_account_id(alice, resource) is False
