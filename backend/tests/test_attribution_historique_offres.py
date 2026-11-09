"""Migration : attribution des anciennes demandes d'offres d'après l'historique."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    PERM_DEMANDES_OFFRES_PROCESS,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    can_process_offres,
    user_from_doc,
)
from demandes_offres_attribution_historique import (  # noqa: E402
    DECISION_AMBIGUE,
    DECISION_ATTRIBUABLE,
    DECISION_DEJA_MANUELLE,
    DECISION_DEJA_MIGREE,
    DECISION_HORS_PILOTAGE,
    DECISION_NON_IDENTIFIEE,
    DECISION_SANS_DROITS,
    DECISION_SANS_TRAITEMENT,
    SOURCE_MIGRATION,
    Annuaire,
    analyser,
    patch_attribution,
)
from demandes_offres_pilotage import gestionnaire_info  # noqa: E402

AGENT_ID = "user_agent"
JORDAN_ID = "user_jordan"


def _user(uid, prenom, nom, role=ROLE_GESTIONNAIRE_OFFRES, **extra):
    return {"user_id": uid, "email": f"{prenom}.{nom}@example.com".lower(), "prenom": prenom, "nom": nom,
            "name": f"{prenom} {nom}", "role": role, "active": True, **extra}


USERS = [
    _user(JORDAN_ID, "Jordan", "PEREIRA"),
    _user("user_lea", "Léa", "Gestion"),
    _user(AGENT_ID, "Sabrina", "Agent", role=ROLE_CONSEILLER),
    _user("user_old", "Marc", "Ancien", active=False),
    _user("user_nope", "Paul", "Conseil", role=ROLE_CONSEILLER),
    _user("user_dup1", "Anne", "Martin"),
    _user("user_dup2", "Anne", "Martin"),
]


def annuaire(users=USERS):
    return Annuaire.depuis_users(users, user_from_doc, can_process_offres)


def h(action, at, by_name, by_id=None):
    return {"action": action, "at": at, "by_name": by_name, "by_id": by_id}


def demande(historique, **extra):
    base = {
        "id": "d1", "numero": "OFF-2026-0042", "prenom": "Sophie", "nom": "Perseguers",
        "statut": "Offre reçue", "agent_label": "Sabrina Agent", "agent_account_id": AGENT_ID,
        "created_by_account_id": AGENT_ID, "historique": historique,
    }
    base.update(extra)
    return base


def test_sophie_perseguers_attribuee_a_jordan_pereira():
    doc = demande([
        h("Demande créée", "2026-03-01T08:00:00+00:00", "Sabrina Agent", AGENT_ID),
        h("Demande envoyée", "2026-03-01T08:05:00+00:00", "Sabrina Agent", AGENT_ID),
        h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Jordan PEREIRA"),
        h("Offres transmises à l'agent", "2026-03-05T10:00:00+00:00", "jordan pereira"),
        h("Offre envoyée au client", "2026-03-06T10:00:00+00:00", "Sabrina Agent", AGENT_ID),
    ])
    d = analyser(doc, annuaire())
    assert d.decision == DECISION_ATTRIBUABLE
    assert (d.gestionnaire_id, d.gestionnaire_nom) == (JORDAN_ID, "Jordan PEREIRA")
    assert d.action == "Offres transmises à l'agent"
    assert d.gestionnaires_vus == ["Jordan PEREIRA"]


def test_actions_offre_prioritaires_et_dernier_gestionnaire():
    doc = demande([
        h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Léa Gestion", "user_lea"),
        h("Offre compagnie reçue", "2026-03-08T10:00:00+00:00", "PEREIRA Jordan"),
        h("En cours de traitement", "2026-03-09T10:00:00+00:00", "Lea Gestion", "user_lea"),
    ])
    d = analyser(doc, annuaire())
    assert d.decision == DECISION_ATTRIBUABLE
    assert d.gestionnaire_id == JORDAN_ID
    assert d.gestionnaires_vus == ["Léa Gestion", "Jordan PEREIRA"]


def test_action_de_traitement_secondaire_si_aucune_offre():
    doc = demande([h("Soumis à la compagnie", "2026-03-04T10:00:00+00:00", "lea gestion")], statut="Demande envoyée")
    d = analyser(doc, annuaire())
    assert (d.decision, d.gestionnaire_id) == (DECISION_ATTRIBUABLE, "user_lea")


def test_actions_agent_ignorees():
    doc = demande([
        h("Demande créée", "2026-03-01T08:00:00+00:00", "Sabrina Agent", AGENT_ID),
        h("Demande envoyée", "2026-03-01T08:05:00+00:00", "Sabrina Agent", AGENT_ID),
        h("Demande marquée urgente", "2026-03-02T08:05:00+00:00", "Jordan PEREIRA"),
    ], statut="Demande envoyée")
    assert analyser(doc, annuaire()).decision == DECISION_SANS_TRAITEMENT


def test_nom_homonyme_ambigu():
    doc = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Anne Martin")])
    d = analyser(doc, annuaire())
    assert d.decision == DECISION_AMBIGUE
    assert {c["id"] for c in d.candidats} == {"user_dup1", "user_dup2"}


def test_auteur_inconnu_inactif_ou_sans_droits():
    inconnu = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Personne Inconnue")])
    assert analyser(inconnu, annuaire()).decision == DECISION_NON_IDENTIFIEE
    id_inconnu = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Jordan PEREIRA", "user_x")])
    assert analyser(id_inconnu, annuaire()).decision == DECISION_NON_IDENTIFIEE
    inactif = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Marc Ancien")])
    assert analyser(inactif, annuaire()).decision == DECISION_SANS_DROITS
    sans_droit = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Paul Conseil")])
    assert analyser(sans_droit, annuaire()).decision == DECISION_SANS_DROITS


def test_droit_process_retire_par_permission():
    users = [_user(JORDAN_ID, "Jordan", "PEREIRA", permissions={PERM_DEMANDES_OFFRES_PROCESS: False})]
    doc = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Jordan PEREIRA")])
    assert analyser(doc, annuaire(users)).decision == DECISION_SANS_DROITS


def test_correspondance_email():
    doc = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "JORDAN.pereira@example.com")])
    assert analyser(doc, annuaire()).gestionnaire_id == JORDAN_ID


def test_deja_attribuee_jamais_ecrasee():
    hist = [h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Jordan PEREIRA")]
    manuelle = demande(hist, gestionnaire_id="user_lea", gestionnaire_nom="Léa Gestion",
                       attributions_historique=[{"type": "auto_attribution"}])
    assert analyser(manuelle, annuaire()).decision == DECISION_DEJA_MANUELLE
    migree = demande(hist, gestionnaire_id=JORDAN_ID, gestionnaire_attribution_source=SOURCE_MIGRATION)
    assert analyser(migree, annuaire()).decision == DECISION_DEJA_MIGREE


def test_hors_pilotage():
    for extra in ({"statut": "Brouillon"}, {"is_deleted": True}, {"statut": "Demande d'offre annulée"}):
        doc = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Jordan PEREIRA")], **extra)
        assert analyser(doc, annuaire()).decision == DECISION_HORS_PILOTAGE


def test_trace_dans_les_offres_sans_historique():
    doc = demande([], offres=[{"received_by": "Jordan PEREIRA", "received_at": "2026-03-04T10:00:00+00:00"}])
    assert analyser(doc, annuaire()).gestionnaire_id == JORDAN_ID


def test_patch_ne_touche_que_l_attribution_et_est_idempotent():
    doc = demande([h("Offre compagnie reçue", "2026-03-04T10:00:00+00:00", "Jordan PEREIRA")])
    d = analyser(doc, annuaire())
    patch = patch_attribution(d, stamp="2026-11-09T12:00:00+00:00")
    assert set(patch) == {"$set", "$push"}
    assert set(patch["$set"]) == {
        "gestionnaire_id", "gestionnaire_nom", "gestionnaire_attribue_at",
        "gestionnaire_attribue_par", "gestionnaire_attribution_source",
    }
    assert set(patch["$push"]) == {"attributions_historique"}
    assert patch["$set"]["gestionnaire_attribue_at"] == "2026-03-04T10:00:00+00:00"
    after = {**doc, **patch["$set"], "attributions_historique": [patch["$push"]["attributions_historique"]]}
    assert gestionnaire_info(after)["id"] == JORDAN_ID
    assert after["historique"] == doc["historique"] and after["statut"] == doc["statut"]
    assert analyser(after, annuaire()).decision == DECISION_DEJA_MIGREE
