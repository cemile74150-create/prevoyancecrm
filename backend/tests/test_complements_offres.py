"""Notes externes / compléments : une réponse libre (texte et/ou docs)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import email_service as es  # noqa: E402
from access_control import (  # noqa: E402
    PERM_DEMANDES_OFFRES_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    permission_for_request,
    user_from_doc,
)
from complements_offres import (  # noqa: E402
    TYPE_REPONSE,
    claim_reply,
    count_pending_complements,
    enrich_external_notes,
    new_complement,
    reply_claim_filter,
    reply_document_ids,
    reply_is_open,
    user_can_answer_complement,
    validate_reply,
)
from demandes_offres_3p import serialize_demande  # noqa: E402


def _user(role, **kwargs):
    doc = {
        "user_id": "agent-1",
        "email": "camille@test.ch",
        "prenom": "Camille",
        "nom": "Durand",
        "name": "Camille Durand",
        "role": role,
        "conseiller": "Camille Durand",
        "active": True,
        **kwargs,
    }
    return user_from_doc(doc)


def _open(note_id, kind, text, documents=None):
    return {
        "id": note_id,
        "at": "2026-11-03T08:00:00+00:00",
        "by_name": "Lea Gestion",
        "by_id": "gest-1",
        "note": text,
        "reply_expected": True,
        "documents": documents or [],
        "complement": new_complement(complement_type=kind, at="2026-11-03T08:00:00+00:00"),
    }


def _reply(text="La date est le 12.03.1980", docs=None):
    return {
        "text": text,
        "at": "2026-11-03T09:00:00+00:00",
        "by_name": "Camille Durand",
        "by_id": "agent-1",
        "documents": docs or [],
    }


def test_informative_note_has_no_reply_right():
    note = {"id": "n1", "note": "Zurich revient sous 10 jours", "email_to": "camille@test.ch"}
    assert validate_reply(note, "je réponds", 0) == "not_expected"
    assert reply_is_open(note) is False
    updated, claimed = claim_reply([note], "n1", _reply())
    assert claimed is False
    assert updated[0]["note"] == "Zurich revient sous 10 jours"
    assert "complement" not in updated[0]


def test_reply_accepts_text_only_docs_only_or_both_even_for_legacy_document_type():
    document = _open("d1", "document", "Mandat de gestion signé manquant")
    information = _open("i1", "information", "Quelle est la date de naissance du client ?")
    reponse = _open("r1", TYPE_REPONSE, "Merci de compléter le formulaire joint")
    assert validate_reply(document, "", 0) == "text_required"
    assert validate_reply(document, "Voici le mandat scanné demain", 0) is None
    assert validate_reply(document, "", 1) is None
    assert validate_reply(document, "Voici le mandat", 2) is None
    assert validate_reply(information, "", 0) == "text_required"
    assert validate_reply(information, "12.03.1980", 0) is None
    assert validate_reply(information, "", 1) is None
    assert validate_reply(reponse, "Ok", 0) is None
    assert validate_reply(reponse, "", 1) is None


def test_one_reply_closes_only_that_request():
    notes = [
        {"id": "old", "note": "Ancienne note", "email_sent": True},
        _open("d1", "document", "Mandat manquant"),
        _open("i1", "information", "Date de naissance ?"),
    ]
    updated, claimed = claim_reply(
        notes,
        "d1",
        _reply(text="Ci-joint", docs=[{"id": "doc-1", "original_filename": "Mandat signé.pdf"}]),
    )
    assert claimed is True
    assert validate_reply(updated[1], "encore", 1) == "already"
    again, claimed_again = claim_reply(updated, "d1", _reply("deuxième"))
    assert claimed_again is False
    assert again[1]["complement"]["reply"]["documents"][0]["original_filename"] == "Mandat signé.pdf"
    assert reply_is_open(again[2]) is True
    assert again[0]["note"] == "Ancienne note"
    assert count_pending_complements(again) == 1
    closed_info, claimed_info = claim_reply(again, "i1", _reply("12.03.1980"))
    assert claimed_info is True
    assert reply_is_open(closed_info[2]) is False
    assert count_pending_complements(closed_info) == 0


def test_other_agent_and_offer_manager_cannot_answer():
    demande = {
        "id": "d1",
        "created_by_account_id": "agent-1",
        "agent_label": "Camille Durand",
        "agent_email": "camille@test.ch",
    }
    owner = _user(ROLE_CONSEILLER, user_id="agent-1")
    other = _user(
        ROLE_CONSEILLER,
        user_id="agent-2",
        email="paul@test.ch",
        prenom="Paul",
        nom="Martin",
        name="Paul Martin",
        conseiller="Paul Martin",
    )
    manager = _user(
        ROLE_GESTIONNAIRE_OFFRES,
        user_id="gest-1",
        email="lea@test.ch",
        prenom="Lea",
        nom="Gestion",
        name="Lea Gestion",
        conseiller="Lea Gestion",
    )
    assert user_can_answer_complement(owner, demande) is True
    assert user_can_answer_complement(other, demande) is False
    assert user_can_answer_complement(manager, demande) is False


def test_serialize_keeps_old_notes_and_manager_attachments():
    stored = {
        "id": "d1",
        "statut": "Demande envoyée",
        "created_by_account_id": "agent-1",
        "agent_label": "Camille Durand",
        "notes_internes": [{"note": "secret"}],
        "notes_externes": [
            {"id": "old", "note": "Note déjà envoyée", "email_to": "camille@test.ch"},
            _open(
                "d1",
                "document",
                "Merci de remplir le formulaire",
                documents=[{"id": "form-1", "original_filename": "formulaire.pdf", "category": "Note externe"}],
            ),
            _open("i1", "information", "Date de naissance ?"),
        ],
    }
    answered, _claimed = claim_reply(
        stored["notes_externes"],
        "d1",
        _reply(text="Formulaire rempli", docs=[{"id": "doc-1", "original_filename": "rempli.pdf"}]),
    )
    stored = {**stored, "notes_externes": answered}
    owner = _user(ROLE_CONSEILLER, user_id="agent-1")
    out = serialize_demande(
        stored,
        docs=[
            {"id": "form-1", "original_filename": "formulaire.pdf", "category": "Note externe"},
            {"id": "doc-1", "original_filename": "rempli.pdf", "category": "Complément conseiller"},
        ],
        viewer=owner,
    )
    assert out["statut"] == "Demande envoyée"
    assert out["notes_externes"][0]["note"] == "Note déjà envoyée"
    assert out["notes_externes"][0]["reply_expected"] is False
    assert out["notes_externes"][0]["can_reply"] is False
    assert out["notes_externes"][0]["complement"] is None
    document = out["notes_externes"][1]
    assert document["can_reply"] is False
    assert document["complement"]["status_label"] == "Réponse reçue"
    assert document["documents"][0]["original_filename"] == "formulaire.pdf"
    assert document["complement"]["reply"]["documents"][0]["original_filename"] == "rempli.pdf"
    information = out["notes_externes"][2]
    assert information["can_reply"] is True
    assert information["complement"]["status_label"] == "Réponse attendue"
    assert out["nb_complements_en_attente"] == 1
    locked = {d["id"] for d in out["documents"] if d.get("locked")}
    assert "doc-1" in locked
    assert "form-1" in locked


def test_enrich_shows_note_attachments_without_reply():
    notes = [
        {
            "id": "n1",
            "note": "Voici le modèle",
            "reply_expected": False,
            "documents": [{"id": "a1", "original_filename": "modele.pdf"}],
        }
    ]
    out = enrich_external_notes(notes, can_answer=False)
    assert out[0]["documents"][0]["original_filename"] == "modele.pdf"
    assert out[0]["can_reply"] is False


def test_claim_filter_rejects_a_second_write():
    note = _open("d1", "document", "Mandat")
    filt = reply_claim_filter("d1")
    assert filt["n.reply_expected"] is True
    assert filt["n.complement.status"] == note["complement"]["status"]
    assert filt["n.complement.reply"] is None
    assert "doc-9" in reply_document_ids([
        {
            **note,
            "complement": {
                **note["complement"],
                "status": "reponse_recue",
                "reply": _reply(docs=[{"id": "doc-9", "original_filename": "a.pdf"}]),
            },
        }
    ])
    assert "att-1" in reply_document_ids([
        {**note, "documents": [{"id": "att-1", "original_filename": "pj.pdf"}]}
    ])


def test_complement_email_goes_to_the_creator_with_a_direct_link(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://leosoft.example")
    doc = {
        "id": "demande-1",
        "numero": "OFF-2026-0042",
        "prenom": "Jean",
        "nom": "Dupont",
        "complement_document_names": ["formulaire.pdf"],
    }
    subject, text, html = es.format_complement_demande_email(
        doc,
        note="Pouvez-vous remplir le formulaire ci-joint ?",
        complement_type="reponse",
        complement_id="comp-1",
    )
    assert subject == "LeoSoft — Action requise : complément demandé pour l'offre OFF-2026-0042"
    assert "Client : Jean Dupont" in text
    assert "Référence : OFF-2026-0042" in text
    assert "Type :" not in text
    assert "formulaire.pdf" in text
    assert "Pouvez-vous remplir le formulaire ci-joint ?" in text
    assert "https://leosoft.example/demandes-offres/demande-1?complement=comp-1" in text
    assert "Répondre à la demande sur LeoSoft" in html
    assert es.offre_notify_role("complement_demande") == "createur"
    assert es.offre_notify_role("note_externe") == "createur"


def test_reply_email_uses_the_existing_offres_route_once(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://leosoft.example")
    doc = {"id": "demande-1", "numero": "OFF-2026-0042", "prenom": "Jean", "nom": "Dupont"}
    subject, text, html = es.format_complement_reponse_email(
        doc,
        note="Mandat manquant",
        reply_text="Ci-joint",
        author="Camille Durand",
        complement_type="document",
        complement_id="comp-1",
        document_names=["Mandat signé.pdf"],
    )
    assert subject.startswith("LeoSoft — Réponse reçue")
    assert "OFF-2026-0042" in subject
    assert "Mandat signé.pdf" in text
    assert "Camille Durand" in text
    assert "Type :" not in text
    assert "complement=comp-1" in html
    assert es.offre_notify_role("complement_reponse") == "offres_mailbox"

    routes = (ROOT / "demandes_offres_routes.py").read_text(encoding="utf-8")
    branch = routes.split('event_key in {"complement_reponse"', 1)[1].split("elif event_key", 1)[0]
    assert "offres_email_to()" in branch
    assert "resolve_demande_creator_email" not in branch
    handler = routes.split("async def reply_to_complement", 1)[1].split("@api_router.", 1)[0]
    assert handler.count("try_send_email(") == 1
    assert handler.count("write_offre_notification(") == 1
    assert "reply_claim_filter" in handler
    assert "discard_complement_uploads" in handler
    assert "matched_count" in handler
    assert "Accès refusé" in handler
    assert "require_demande" in handler
    assert "save_status(" not in handler
    assert 'event="complement_reponse"' in handler


def test_reply_and_close_permissions_follow_the_roles():
    reply = permission_for_request(
        "POST", "/api/demandes-offres/abc/complements/comp-1/reponse"
    )
    close = permission_for_request(
        "POST", "/api/demandes-offres/abc/complements/comp-1/cloturer"
    )
    assert reply == (PERM_DEMANDES_OFFRES_EDIT, PERM_DEMANDES_OFFRES_PROCESS)
    assert close == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/abc/notes-externes") == PERM_DEMANDES_OFFRES_PROCESS


def test_external_note_route_still_targets_the_creator_for_informative_notes():
    routes = (ROOT / "demandes_offres_routes.py").read_text(encoding="utf-8")
    handler = routes.split("async def add_external_note", 1)[1].split("@api_router.", 1)[0]
    assert 'event="note_externe"' in handler
    assert 'event="complement_demande"' in handler
    assert "resolve_demande_creator_email(doc)" in handler
    assert handler.count("write_offre_notification(") == 1
    assert '"Note externe"' in handler
    assert "CATEGORY_NOTE_EXTERNE" in handler
    assert "attendre_reponse" in handler
    assert "type_complement" not in handler
    assert "Choisissez le type de complément" not in handler
