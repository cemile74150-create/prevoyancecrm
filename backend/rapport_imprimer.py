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


def is_planification_document(doc: Dict[str, Any]) -> bool:
    """
    PDF issus de « Enregistrer dans le dossier » (Planifications).
    Exclut les comparatifs de rentes (même catégorie historique).
    """
    title = str(doc.get("title") or "").casefold()
    filename = str(doc.get("original_filename") or doc.get("filename") or "").casefold()
    category = str(doc.get("category") or "").casefold()
    checklist = str(doc.get("checklist_item") or "").casefold()
    if "comparatif" in title or filename.startswith("comparatif_rentes"):
        return False
    if title.startswith("analyse de prévoyance") or title.startswith("analyse de prevoyance"):
        return True
    if filename.startswith("analyse_prevoyance"):
        return True
    if category == "analyse de prévoyance" or checklist == "analyse de prévoyance":
        return "comparatif" not in filename
    if category == "analyse de prevoyance" or checklist == "analyse de prevoyance":
        return "comparatif" not in filename
    return False


PLANIFICATION_VIRTUAL_PREFIX = "planif-analyse:"


def is_virtual_planification_id(doc_id: Any) -> bool:
    return str(doc_id or "").startswith(PLANIFICATION_VIRTUAL_PREFIX)


def virtual_planification_id(analyse_id: str) -> str:
    return f"{PLANIFICATION_VIRTUAL_PREFIX}{str(analyse_id or '').strip()}"


def analyse_id_from_virtual(doc_id: Any) -> str:
    raw = str(doc_id or "")
    if not raw.startswith(PLANIFICATION_VIRTUAL_PREFIX):
        return ""
    return raw[len(PLANIFICATION_VIRTUAL_PREFIX) :].strip()


def pick_latest_planification(
    docs: Sequence[Dict[str, Any]],
    *,
    preferred_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Une seule planification : id préféré (lien analyses.document_id / virtuel),
    sinon dernière version détectée par métadonnées.
    """
    preferred = str(preferred_id or "").strip()
    if preferred:
        for doc in docs:
            if str(doc.get("id") or "").strip() == preferred:
                return doc
    plans = [doc for doc in docs if is_planification_document(doc) or doc.get("is_planification")]
    if not plans:
        return None
    plans.sort(
        key=lambda doc: (
            str(doc.get("created_at") or ""),
            str(doc.get("id") or ""),
        ),
        reverse=True,
    )
    return plans[0]


def _blob(doc: Dict[str, Any]) -> str:
    return " ".join(
        str(doc.get(key) or "")
        for key in ("category", "checklist_item", "template_id", "original_filename", "title")
    ).casefold()


def document_sort_rank(doc: Dict[str, Any]) -> Tuple[int, str, str]:
    """Classe les PDF hors planification pour l'ordre proposé."""
    blob = _blob(doc)
    rank = 900
    for needle, value in _CATEGORY_RANK:
        if needle in blob:
            rank = min(rank, value)
    created = str(doc.get("created_at") or "")
    name = str(doc.get("original_filename") or doc.get("title") or doc.get("id") or "").casefold()
    return (rank, created, name)


def sort_documents_for_rapport(
    docs: Sequence[Dict[str, Any]],
    *,
    preferred_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Liste UI : dernière planification en tête (sans doublon d'anciennes versions),
    puis les autres PDF triés par famille.
    """
    latest = pick_latest_planification(docs, preferred_id=preferred_id)
    latest_id = str((latest or {}).get("id") or "").strip()
    plan_ids = {
        str(doc.get("id") or "").strip()
        for doc in docs
        if (is_planification_document(doc) or doc.get("is_planification")) and doc.get("id")
    }
    if latest_id:
        plan_ids.add(latest_id)
    others = [doc for doc in docs if str(doc.get("id") or "").strip() not in plan_ids]
    others_sorted = sorted(others, key=document_sort_rank)
    if latest:
        return [latest, *others_sorted]
    return others_sorted


def ensure_planification_first(
    document_ids: Sequence[str],
    docs: Sequence[Dict[str, Any]],
    *,
    preferred_id: Optional[str] = None,
    default_select: bool = True,
) -> List[str]:
    """
    Force la dernière planification en 1re position, sélectionnée,
    et retire les anciennes versions / doublons de planification.
    """
    latest = pick_latest_planification(docs, preferred_id=preferred_id)
    latest_id = str((latest or {}).get("id") or "").strip()
    plan_ids = {
        str(doc.get("id") or "").strip()
        for doc in docs
        if (is_planification_document(doc) or doc.get("is_planification")) and doc.get("id")
    }
    if latest_id:
        plan_ids.add(latest_id)
    # Anciens ids virtuels / anciennes versions de planification exclus du reste
    rest = [
        doc_id
        for doc_id in normalize_document_ids(document_ids)
        if doc_id not in plan_ids and not is_virtual_planification_id(doc_id)
    ]
    if latest_id:
        return [latest_id, *rest]
    if default_select:
        return rest
    return rest


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
