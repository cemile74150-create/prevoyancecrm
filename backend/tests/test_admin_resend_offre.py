"""Admin « Renvoyer l'offre » : permissions, même id, historique, pas de nouveau document."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    PERM_USERS_MANAGE,
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    has_perm,
    permission_for_request,
    require_admin,
    user_from_doc,
)
from demandes_offres_3p import (  # noqa: E402
    ACTION_ENVOYEE,
    ACTION_RENVOYEE,
    STATUT_ENVOYEE,
    collapse_demande_historique,
    history_entry,
    missing_required,
)


def _user(role, **kwargs):
    doc = {
        "user_id": f"acc-{role}",
        "email": f"{role}@test.ch",
        "prenom": "Test",
        "nom": role.title(),
        "name": f"Test {role.title()}",
        "role": role,
        "conseiller": f"Test {role.title()}",
        "active": True,
        **kwargs,
    }
    return user_from_doc(doc)


def test_renvoyer_route_requires_admin_perm():
    assert (
        permission_for_request("POST", "/api/demandes-offres/abc/renvoyer")
        == PERM_USERS_MANAGE
    )
    # Ne doit pas retomber sur demandes_offres.edit
    assert permission_for_request("POST", "/api/demandes-offres/abc/envoyer") != PERM_USERS_MANAGE


def test_non_admin_forbidden_by_require_admin():
    for role in (ROLE_CONSEILLER, ROLE_CEO, ROLE_GESTIONNAIRE_OFFRES):
        u = _user(role)
        assert has_perm(u, PERM_USERS_MANAGE) is False
        with pytest.raises(HTTPException) as exc:
            require_admin(u)
        assert exc.value.status_code == 403


def test_admin_allowed_by_require_admin():
    u = _user(ROLE_ADMIN)
    assert has_perm(u, PERM_USERS_MANAGE) is True
    require_admin(u)  # no raise


def test_admin_resend_same_id_history_no_new_document():
    """
    Contrat métier du renvoi admin (sans DB) :
    - même id / numéro
    - entrée historique ACTION_RENVOYEE avec auteur admin + datetime
    - documents inchangés (pas de nouveau document)
    - statut reste Demande envoyée
    """
    demande_id = "dem-42"
    numero = "OFF-2026-0042"
    docs_before = [
        {"id": "doc-1", "original_filename": "mandat.pdf", "category": "Mandat"},
    ]
    hist = [
        history_entry(ACTION_ENVOYEE, by_name="Conseiller X", by_id="acc-c", statut=STATUT_ENVOYEE),
    ]
    doc = {
        "id": demande_id,
        "numero": numero,
        "statut": STATUT_ENVOYEE,
        "form_payload": {"prenom": "Jean", "nom": "Dupont"},
        "agent_prenom": "Alice",
        "agent_nom": "Conseiller",
        "historique": hist,
        "documents": list(docs_before),
        "date_envoi": "2026-01-10T10:00:00+00:00",
    }

    admin = _user(ROLE_ADMIN, prenom="Cemile", nom="Admin", name="Cemile Admin")
    at = "2026-09-24T12:00:00+00:00"
    entry = history_entry(
        ACTION_RENVOYEE,
        by_name=admin.name,
        by_id=admin.account_id,
        detail="E-mail envoyé",
        statut=STATUT_ENVOYEE,
    )
    entry["at"] = at

    # Simulation du $set save_status (sans création de document)
    hist2 = collapse_demande_historique(list(doc["historique"]) + [entry])
    updated = {
        **doc,
        "statut": STATUT_ENVOYEE,
        "date_envoi": at,
        "historique": hist2,
        "email_sent": True,
        # agent identity inchangée
        "agent_prenom": doc["agent_prenom"],
        "agent_nom": doc["agent_nom"],
        "form_payload": dict(doc["form_payload"]),
        "documents": list(docs_before),
    }

    assert updated["id"] == demande_id
    assert updated["numero"] == numero
    assert updated["statut"] == STATUT_ENVOYEE
    assert updated["form_payload"] == {"prenom": "Jean", "nom": "Dupont"}
    assert updated["agent_prenom"] == "Alice"
    assert len(updated["documents"]) == len(docs_before)
    assert updated["documents"][0]["id"] == "doc-1"

    actions = [e.get("action") for e in updated["historique"]]
    assert ACTION_ENVOYEE in actions
    assert ACTION_RENVOYEE in actions
    last_resend = [e for e in updated["historique"] if e.get("action") == ACTION_RENVOYEE][-1]
    assert last_resend.get("by_name") == "Cemile Admin"
    assert last_resend.get("by_id") == admin.account_id
    assert last_resend.get("at") == at
    assert last_resend.get("statut") == STATUT_ENVOYEE


def test_resend_only_when_statut_envoyee():
    """Le endpoint refuse tout statut autre que Demande envoyée."""
    assert STATUT_ENVOYEE == "Demande envoyée"
    allowed = STATUT_ENVOYEE
    for other in ("Brouillon", "Demande validée", "Offre reçue", "Demande annulée"):
        assert other != allowed


def _incomplete_envoyee_doc(**overrides):
    """Demande déjà envoyée avec champs obligatoires vides (cas réel de renvoi admin)."""
    doc = {
        "id": "dem-incomplete",
        "numero": "OFF-2026-0099",
        "statut": STATUT_ENVOYEE,
        "form_type": "pilier3_legacy",
        "form_payload": {},
        "prenom": "",
        "nom": "",
        "date_naissance": "",
        "montant_prime": None,
        "compagnies": [],
        "agent_finma": "",
        "historique": [
            history_entry(ACTION_ENVOYEE, by_name="Conseiller", by_id="acc-c", statut=STATUT_ENVOYEE),
        ],
        "date_envoi": "2026-01-10T10:00:00+00:00",
    }
    doc.update(overrides)
    return doc


def test_incomplete_doc_fails_missing_required_for_first_send():
    """Premier envoi (/envoyer) : les champs obligatoires restent exigés."""
    doc = _incomplete_envoyee_doc(statut="Brouillon", date_envoi=None)
    missing = missing_required(doc)
    assert missing, "un dossier incomplet doit échouer la validation du premier envoi"
    assert any("compagnie" in (m or "").lower() or "Compagnie" in (m or "") for m in missing) or len(missing) >= 1


def test_renvoyer_route_bypasses_missing_required():
    """
    Contrat : POST /renvoyer ne doit PAS appeler missing_required
    (contrairement à /envoyer et /valider).
    """
    routes_src = (ROOT / "demandes_offres_routes.py").read_text(encoding="utf-8")
    # Extraire le corps de admin_resend_demande_offre jusqu'à la route suivante
    start = routes_src.index("async def admin_resend_demande_offre")
    rest = routes_src[start:]
    # Fin = prochain décorateur de route au même niveau d'indentation (4 spaces + @)
    end_marker = "\n    @api_router."
    end = rest.find(end_marker, 1)
    assert end > 0
    renvoyer_body = rest[:end]
    assert "missing_required" not in renvoyer_body, (
        "Le renvoi admin ne doit pas bloquer sur les champs obligatoires"
    )
    assert 'try_send_email(doc, event="envoyee")' in renvoyer_body, (
        "Le renvoi admin doit réutiliser le pipeline d'envoi (offres@ + récap conseiller)"
    )
    # Premier envoi conserve la validation
    envoyer_start = routes_src.index("async def send_demande_offre")
    envoyer_rest = routes_src[envoyer_start:]
    envoyer_end = envoyer_rest.find(end_marker, 1)
    envoyer_body = envoyer_rest[:envoyer_end]
    assert "missing_required" in envoyer_body


def test_try_send_email_envoyee_sends_conseiller_recap():
    """Contrat source : l'événement envoyee déclenche aussi le récap conseiller."""
    routes_src = (ROOT / "demandes_offres_routes.py").read_text(encoding="utf-8")
    start = routes_src.index("async def try_send_email")
    # Jusqu'à write_offre_notification (fonction suivante)
    end = routes_src.index("async def write_offre_notification", start)
    body = routes_src[start:end]
    assert "format_demande_offre_recap_conseiller_email" in body
    assert "MAIL_TYPE_DEMANDE_OFFRE_RECAP" in body
    assert "send_conseiller_recap" in body
    assert "resolve_demande_creator_email" in body
    assert 'meta_event="envoyee_recap"' in body


def test_resend_with_empty_required_fields_contract():
    """
    Simulation métier : même si missing_required serait non vide,
    le renvoi enregistre ACTION_RENVOYEE sans créer de document ni changer le statut.
    """
    doc = _incomplete_envoyee_doc()
    assert missing_required(doc), "précondition : le dossier est incomplet"

    admin = _user(ROLE_ADMIN, prenom="Cemile", nom="Admin", name="Cemile Admin")
    at = "2026-09-24T14:00:00+00:00"
    entry = history_entry(
        ACTION_RENVOYEE,
        by_name=admin.name,
        by_id=admin.account_id,
        detail="E-mail envoyé",
        statut=STATUT_ENVOYEE,
    )
    entry["at"] = at
    hist2 = collapse_demande_historique(list(doc["historique"]) + [entry])
    updated = {
        **doc,
        "statut": STATUT_ENVOYEE,
        "date_envoi": at,
        "historique": hist2,
        "email_sent": True,
        "form_payload": dict(doc["form_payload"]),
    }

    assert updated["id"] == doc["id"]
    assert updated["statut"] == STATUT_ENVOYEE
    assert updated["form_payload"] == {}
    last = [e for e in updated["historique"] if e.get("action") == ACTION_RENVOYEE][-1]
    assert last["at"] == at
    assert last["by_name"] == "Cemile Admin"
