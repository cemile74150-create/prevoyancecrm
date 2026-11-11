"""Fil de discussion agent / gestionnaire, un fil par demande d'offre.

Les messages sont dans leur propre collection : poster un message ne
modifie ni la demande, ni son statut, ni son updated_at.

Pièces jointes : stockées comme documents demandes-offres (catégorie
« Fil de discussion »), référencées sur le message. Texte seul OK ;
documents seuls acceptés avec un libellé minimal.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

COLLECTION_MESSAGES = "demandes_offres_messages"
MAX_MESSAGE_LENGTH = 5000
MAX_MESSAGE_FILES = 15
MAX_MESSAGE_FILE_BYTES = 20 * 1024 * 1024  # aligné sur les uploads LAMAL / notes
CATEGORY_FIL_DISCUSSION = "Fil de discussion"
DEFAULT_ATTACHMENT_MESSAGE = "(Pièce(s) jointe(s))"
ALLOWED_MESSAGE_EXTENSIONS = frozenset({
    "pdf",
    "png", "jpg", "jpeg", "gif", "webp",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "odt", "ods",
    "txt", "csv",
})
ROLE_AGENT = "agent"
ROLE_GESTIONNAIRE = "gestionnaire"
ROLE_LABELS = {ROLE_AGENT: "Agent", ROLE_GESTIONNAIRE: "Gestionnaire"}


def clean_message_content(raw: Any, *, has_attachments: bool = False) -> str:
    """Valide le texte. Sans pièce jointe, le message ne peut pas être vide."""
    text = str(raw or "").replace("\r\n", "\n").strip()
    if not text:
        if has_attachments:
            return DEFAULT_ATTACHMENT_MESSAGE
        raise ValueError("Le message est vide.")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Le message dépasse {MAX_MESSAGE_LENGTH} caractères.")
    return text


def message_file_extension(filename: Any) -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    return suffix[1:] if suffix.startswith(".") else ""


def validate_message_attachment(filename: Any, size: Optional[int] = None) -> str:
    """Retourne l'extension normalisée ou lève ValueError."""
    ext = message_file_extension(filename)
    if not ext or ext not in ALLOWED_MESSAGE_EXTENSIONS:
        raise ValueError(
            "Type de fichier non autorisé. Formats acceptés : PDF, images, Office courants."
        )
    if size is not None and int(size) > MAX_MESSAGE_FILE_BYTES:
        raise ValueError(
            f"Fichier trop volumineux (max {MAX_MESSAGE_FILE_BYTES // (1024 * 1024)} Mo)."
        )
    return ext


def public_message_documents(docs: Any) -> list[dict]:
    """Références publiques (sans chemin de stockage) pour l'UI du fil."""
    out: list[dict] = []
    for doc in docs or []:
        if not isinstance(doc, dict) or not doc.get("id"):
            continue
        out.append({
            "id": doc.get("id"),
            "original_filename": doc.get("original_filename") or "Document",
            "content_type": doc.get("content_type") or "application/octet-stream",
            "size": doc.get("size"),
            "category": doc.get("category") or CATEGORY_FIL_DISCUSSION,
            "created_at": doc.get("created_at"),
        })
    return out


def _account_id(user: Any) -> str:
    return str(getattr(user, "account_id", None) or getattr(user, "user_id", None) or "").strip()


def is_agent_of_demande(user: Any, doc: dict) -> bool:
    """Créateur, agent attribué, ou conseiller qui voit la demande par son périmètre."""
    from access_control import can_view_all_offres
    from demandes_offres_3p import can_access_demande
    from offre_agent_identity import viewer_is_demande_creator

    if viewer_is_demande_creator(doc, user):
        return True
    aid = _account_id(user)
    if aid and aid == str(doc.get("agent_account_id") or "").strip():
        return True
    return not can_view_all_offres(user) and can_access_demande(user, doc)


def message_role(user: Any, doc: dict) -> Optional[str]:
    """Rôle d'écriture, ou None si l'utilisateur peut seulement lire."""
    from access_control import can_process_offres

    if is_agent_of_demande(user, doc):
        return ROLE_AGENT
    if can_process_offres(user):
        return ROLE_GESTIONNAIRE
    return None


def can_read_thread(user: Any, doc: dict) -> bool:
    from demandes_offres_3p import can_access_demande

    return bool(doc) and can_access_demande(user, doc)


def build_message(
    *,
    demande_id: str,
    user: Any,
    role: str,
    contenu: str,
    at: str,
    documents: Optional[list] = None,
) -> dict:
    name = (getattr(user, "name", "") or f"{getattr(user, 'prenom', '')} {getattr(user, 'nom', '')}").strip()
    sender = _account_id(user)
    return {
        "id": str(uuid.uuid4()),
        "demande_id": demande_id,
        "expediteur_id": sender,
        "expediteur_nom": name or "Utilisateur",
        "expediteur_role": role,
        "contenu": contenu,
        "documents": public_message_documents(documents),
        "created_at": at,
        "read_by": [sender] if sender else [],
    }


def public_message(row: dict, viewer: Any) -> dict:
    aid = _account_id(viewer)
    return {
        "id": row.get("id"),
        "demande_id": row.get("demande_id"),
        "expediteur_id": row.get("expediteur_id"),
        "expediteur_nom": row.get("expediteur_nom") or "Utilisateur",
        "expediteur_role": row.get("expediteur_role") or ROLE_AGENT,
        "expediteur_role_label": ROLE_LABELS.get(row.get("expediteur_role"), "Agent"),
        "contenu": row.get("contenu") or "",
        "documents": public_message_documents(row.get("documents")),
        "created_at": row.get("created_at"),
        "mine": bool(aid) and row.get("expediteur_id") == aid,
        "lu": bool(aid) and aid in (row.get("read_by") or []),
    }


def count_unread(rows: list, viewer: Any) -> int:
    aid = _account_id(viewer)
    if not aid:
        return 0
    return sum(
        1 for row in rows or []
        if row.get("expediteur_id") != aid and aid not in (row.get("read_by") or [])
    )
