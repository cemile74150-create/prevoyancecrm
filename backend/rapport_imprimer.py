"""Rapport à imprimer — sélection ordonnée de PDF client + fusion pypdf."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pypdf import PdfReader, PdfWriter

# Priorité d'affichage / ordre proposé (plus petit = plus haut).
_CATEGORY_RANK: Tuple[Tuple[str, int], ...] = (
    ("analyse de prévoyance", 10),
    ("planification", 10),
    ("comparatif", 15),
    ("impôt", 20),
    ("impot", 20),
    ("déclaration", 20),
    ("declaration", 20),
    ("avs", 30),
    ("réponse recherche lpp", 40),
    ("reponse recherche lpp", 40),
    ("fonds de garantie", 40),
    ("certificat lpp", 50),
    ("lpp", 55),
    ("3e pilier", 60),
    ("3ème pilier", 60),
    ("3a", 60),
    ("3b", 60),
    ("police 3e", 60),
    ("offre", 70),
)


def is_pdf_document(doc: Dict[str, Any]) -> bool:
    name = str(doc.get("original_filename") or doc.get("filename") or "").casefold()
    ctype = str(doc.get("content_type") or "").casefold()
    if name.endswith(".pdf"):
        return True
    if "pdf" in ctype:
        return True
    # Documents générés parfois sans extension explicite
    if ctype.startswith("application/octet-stream") and doc.get("template_id"):
        return True
    return False


def _blob(doc: Dict[str, Any]) -> str:
    return " ".join(
        str(doc.get(key) or "")
        for key in ("category", "checklist_item", "template_id", "original_filename", "title")
    ).casefold()


def document_sort_rank(doc: Dict[str, Any]) -> Tuple[int, str, str]:
    """Classe les PDF pour proposer la planification en premier, puis les familles usuelles."""
    blob = _blob(doc)
    rank = 900
    for needle, value in _CATEGORY_RANK:
        if needle in blob:
            rank = min(rank, value)
    created = str(doc.get("created_at") or "")
    name = str(doc.get("original_filename") or doc.get("title") or doc.get("id") or "").casefold()
    return (rank, created, name)


def sort_documents_for_rapport(docs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(docs, key=document_sort_rank)


def normalize_document_ids(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen = set()
    for item in raw:
        doc_id = str(item or "").strip()
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(doc_id)
    return out


def resolve_ordered_documents(
    document_ids: Sequence[str],
    available_by_id: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Retourne (docs trouvés dans l'ordre, ids manquants/inaccessibles).
    Les ids absents de available_by_id sont signalés (supprimés ou hors périmètre).
    """
    found: List[Dict[str, Any]] = []
    missing: List[str] = []
    for doc_id in document_ids:
        doc = available_by_id.get(doc_id)
        if not doc:
            missing.append(doc_id)
            continue
        found.append(doc)
    return found, missing


def merge_pdf_bytes(parts: Iterable[bytes]) -> bytes:
    """Fusionne des PDF page par page sans altérer le contenu source."""
    writer = PdfWriter()
    count = 0
    for data in parts:
        raw = bytes(data or b"")
        if not raw:
            raise ValueError("PDF vide")
        reader = PdfReader(io.BytesIO(raw))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ValueError("PDF protégé impossible à fusionner") from exc
        for page in reader.pages:
            writer.add_page(page)
            count += 1
    if count == 0:
        raise ValueError("Aucun PDF à fusionner")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def rapport_filename(nom: str = "", prenom: str = "") -> str:
    slug_nom = re.sub(r"[^A-Za-z0-9_-]+", "_", (nom or "").strip()).strip("_") or "Client"
    slug_prenom = re.sub(r"[^A-Za-z0-9_-]+", "_", (prenom or "").strip()).strip("_") or "X"
    return f"Rapport_Planification_{slug_nom}_{slug_prenom}.pdf"


def missing_labels(
    missing_ids: Sequence[str],
    known_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[str]:
    known_by_id = known_by_id or {}
    labels: List[str] = []
    for doc_id in missing_ids:
        doc = known_by_id.get(doc_id) or {}
        label = (
            doc.get("original_filename")
            or doc.get("title")
            or doc_id
        )
        labels.append(str(label))
    return labels
