"""
Notes externes / demandes de complément sur une offre.

Une note informative reste une note. Si le gestionnaire coche « Attendre une
réponse », le conseiller propriétaire peut transmettre une seule réponse
(texte et/ou documents). Les types document/information historiques restent
lisibles, avec les mêmes règles d'envoi assouplies.
"""
from __future__ import annotations

from typing import Optional

# Historique : document / information. Nouveau : reponse (case unique).
TYPE_DOCUMENT = "document"
TYPE_INFORMATION = "information"
TYPE_REPONSE = "reponse"
COMPLEMENT_TYPES = frozenset({TYPE_DOCUMENT, TYPE_INFORMATION, TYPE_REPONSE})

STATUS_EN_ATTENTE = "en_attente"
STATUS_REPONSE_RECUE = "reponse_recue"
STATUS_CLOTUREE = "cloturee"

STATUS_LABELS = {
    STATUS_EN_ATTENTE: "Réponse attendue",
    STATUS_REPONSE_RECUE: "Réponse reçue",
    STATUS_CLOTUREE: "Clôturée",
}
TYPE_LABELS = {
    TYPE_DOCUMENT: "Réponse attendue",
    TYPE_INFORMATION: "Réponse attendue",
    TYPE_REPONSE: "Réponse attendue",
}

CATEGORY_COMPLEMENT = "Complément conseiller"
CATEGORY_NOTE_EXTERNE = "Note externe"
MAX_REPLY_TEXT = 8000
MAX_REPLY_FILES = 15
MAX_NOTE_FILES = 15

_TYPE_ALIASES = {
    "document": TYPE_DOCUMENT,
    "documents": TYPE_DOCUMENT,
    "fichier": TYPE_DOCUMENT,
    "piece": TYPE_DOCUMENT,
    "pièce": TYPE_DOCUMENT,
    "information": TYPE_INFORMATION,
    "informations": TYPE_INFORMATION,
    "info": TYPE_INFORMATION,
    "question": TYPE_INFORMATION,
    "reponse": TYPE_REPONSE,
    "réponse": TYPE_REPONSE,
    "message": TYPE_REPONSE,
}


def normalize_complement_type(value) -> Optional[str]:
    key = str(value or "").strip().lower()
    return _TYPE_ALIASES.get(key)


def type_label(value) -> str:
    kind = normalize_complement_type(value) or str(value or "").strip().lower()
    return TYPE_LABELS.get(kind, "Réponse attendue")


def status_label(value) -> str:
    return STATUS_LABELS.get(str(value or "").strip(), "Réponse attendue")


def new_complement(*, complement_type: Optional[str] = None, at: str) -> dict:
    kind = normalize_complement_type(complement_type) or TYPE_REPONSE
    return {
        "type": kind,
        "status": STATUS_EN_ATTENTE,
        "created_at": at,
        "reply": None,
        "closed_at": None,
        "closed_by": None,
        "closed_by_id": None,
    }


def find_external_note(notes, note_id: str) -> Optional[dict]:
    target = str(note_id or "").strip()
    if not target:
        return None
    for note in notes or []:
        if isinstance(note, dict) and str(note.get("id") or "") == target:
            return note
    return None


def reply_is_open(note: Optional[dict]) -> bool:
    if not isinstance(note, dict) or not note.get("reply_expected"):
        return False
    comp = note.get("complement")
    if not isinstance(comp, dict):
        return False
    if comp.get("reply"):
        return False
    return comp.get("status") == STATUS_EN_ATTENTE


def user_can_answer_complement(user, doc: Optional[dict]) -> bool:
    """
    Seul le conseiller agent demandeur peut répondre.
    Si agent_account_id est posé : pas l'opérateur créateur (gestionnaire/admin).
    Sans agent_account_id : créateur legacy, puis can_follow_signature.
    """
    if user is None or not isinstance(doc, dict):
        return False
    from demandes_offres_3p import can_follow_signature

    account_id = str(getattr(user, "account_id", None) or "").strip()
    agent = str(doc.get("agent_account_id") or "").strip()
    if account_id and agent:
        return account_id == agent
    if account_id:
        for key in ("created_by_account_id", "created_by"):
            if str(doc.get(key) or "").strip() == account_id:
                return True
    return bool(can_follow_signature(user, doc))


def validate_reply(note: Optional[dict], text: Optional[str], file_count: int) -> Optional[str]:
    """None si la réponse peut être enregistrée, sinon un code stable."""
    if not isinstance(note, dict):
        return "missing"
    if not note.get("reply_expected"):
        return "not_expected"
    comp = note.get("complement") if isinstance(note.get("complement"), dict) else {}
    if comp.get("reply") or comp.get("status") == STATUS_REPONSE_RECUE:
        return "already"
    if comp.get("status") == STATUS_CLOTUREE or comp.get("status") != STATUS_EN_ATTENTE:
        return "closed"
    comment = str(text or "").strip()
    count = int(file_count or 0)
    if len(comment) > MAX_REPLY_TEXT:
        return "too_long"
    if count > MAX_REPLY_FILES:
        return "too_many_files"
    if count < 0:
        return "text_required"
    # Texte seul, documents seuls, ou les deux.
    # Une pièce n'est exigée que si le gestionnaire a coché le retour de document.
    if note.get("retour_document") and count < 1:
        return "document_required"
    if not comment and count < 1:
        return "text_required"
    kind = comp.get("type")
    if kind is not None and normalize_complement_type(kind) is None and kind not in COMPLEMENT_TYPES:
        # Ancienne note corrompue : si statut en_attente, on laisse répondre.
        if kind not in ("",):
            pass
    return None


REPLY_ERROR_HTTP = {
    "missing": (404, "Demande de complément introuvable"),
    "not_expected": (422, "Cette note n'attend pas de réponse"),
    "already": (409, "Une réponse a déjà été transmise pour cette demande"),
    "closed": (409, "Cette demande de complément est clôturée"),
    "document_required": (422, "Saisissez une réponse ou joignez un document"),
    "text_required": (422, "Saisissez une réponse ou joignez un document"),
    "too_long": (422, "La réponse est trop longue"),
    "too_many_files": (422, f"Maximum {MAX_REPLY_FILES} documents"),
}


def reply_claim_filter(complement_id: str) -> dict:
    """
    Filtre Mongo : la note est encore ouverte.
    Une deuxième écriture simultanée ne matche plus.
    """
    return {
        "n.id": str(complement_id),
        "n.reply_expected": True,
        "n.complement.status": STATUS_EN_ATTENTE,
        "n.complement.reply": None,
    }


def claim_reply(notes, note_id: str, reply: dict) -> tuple[list, bool]:
    """
    Applique une réponse à une seule note encore ouverte.
    Les autres notes de la même offre ne changent pas.
    """
    claimed = False
    out = []
    target = str(note_id or "")
    for note in list(notes or []):
        if not isinstance(note, dict) or str(note.get("id") or "") != target or not reply_is_open(note):
            out.append(note)
            continue
        claimed = True
        comp = dict(note.get("complement") or {})
        comp["status"] = STATUS_REPONSE_RECUE
        comp["reply"] = reply
        updated = dict(note)
        updated["complement"] = comp
        out.append(updated)
    return out, claimed


def count_pending_complements(notes) -> int:
    return sum(1 for note in notes or [] if reply_is_open(note))


def public_document_refs(docs) -> list[dict]:
    documents = []
    for doc in docs or []:
        if not isinstance(doc, dict) or not doc.get("id"):
            continue
        documents.append({
            "id": doc.get("id"),
            "original_filename": doc.get("original_filename") or "Document",
            "content_type": doc.get("content_type") or "application/octet-stream",
            "size": doc.get("size"),
            "category": doc.get("category") or CATEGORY_NOTE_EXTERNE,
            "created_at": doc.get("created_at"),
        })
    return documents


def reply_document_ids(notes) -> set[str]:
    """Pièces jointes de réponse + pièces jointes de la note gestionnaire (verrouillage)."""
    ids: set[str] = set()
    for note in notes or []:
        if not isinstance(note, dict):
            continue
        for doc in note.get("documents") or []:
            if isinstance(doc, dict) and doc.get("id"):
                ids.add(str(doc.get("id")))
        comp = note.get("complement") if isinstance(note.get("complement"), dict) else {}
        reply = comp.get("reply") if isinstance(comp.get("reply"), dict) else {}
        for doc in reply.get("documents") or []:
            if isinstance(doc, dict) and doc.get("id"):
                ids.add(str(doc.get("id")))
    return ids


def _public_reply(reply: Optional[dict]) -> Optional[dict]:
    if not isinstance(reply, dict):
        return None
    return {
        "text": reply.get("text") or "",
        "at": reply.get("at"),
        "by_name": reply.get("by_name") or "",
        "by_id": reply.get("by_id"),
        "documents": public_document_refs(reply.get("documents")),
    }


def enrich_external_notes(notes, *, can_answer: bool) -> list[dict]:
    """Vue API. N'écrit rien en base : les anciennes notes restent telles quelles."""
    out = []
    for note in notes or []:
        if not isinstance(note, dict):
            continue
        raw = dict(note)
        raw["documents"] = public_document_refs(raw.get("documents"))
        expected = bool(raw.get("reply_expected")) and isinstance(raw.get("complement"), dict)
        if not expected:
            raw["reply_expected"] = False
            raw["complement"] = None
            raw["can_reply"] = False
            out.append(raw)
            continue
        comp = dict(raw.get("complement") or {})
        status = comp.get("status") or STATUS_EN_ATTENTE
        if comp.get("reply") and status == STATUS_EN_ATTENTE:
            status = STATUS_REPONSE_RECUE
        public = {
            "type": normalize_complement_type(comp.get("type")) or comp.get("type") or TYPE_REPONSE,
            "type_label": type_label(comp.get("type")),
            "status": status,
            "status_label": status_label(status),
            "created_at": comp.get("created_at") or raw.get("at"),
            "reply": _public_reply(comp.get("reply")),
            "closed_at": comp.get("closed_at"),
            "closed_by": comp.get("closed_by"),
        }
        raw["reply_expected"] = True
        raw["complement"] = public
        raw["can_reply"] = bool(can_answer and reply_is_open(note))
        out.append(raw)
    return out


def creator_account_ids(doc: Optional[dict]) -> list[str]:
    ids = []
    for key in ("created_by_account_id", "agent_account_id", "created_by"):
        val = str((doc or {}).get(key) or "").strip()
        if val and val not in ids:
            ids.append(val)
    return ids
