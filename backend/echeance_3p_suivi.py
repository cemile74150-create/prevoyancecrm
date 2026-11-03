"""Suivi des échéances 3e pilier : la ligne de suivi n'emporte pas les PDF."""
from __future__ import annotations

from typing import Optional


def echeance_3p_line_removal_plan(line: Optional[dict]) -> dict:
    """
    Suppression d'une ligne « Échéance 3e pilier ».

    Seule la ligne de suivi disparaît. Aucun document n'est effacé, même
    s'il est lié à la ligne (police, confirmation de rachat) ou s'il existe
    d'autres PDF pour le même contrat.

    Le document source est seulement marqué ``echeance_3p_exclu`` pour que
    la synchro ne recrée pas la ligne toute seule. La correction reste manuelle.
    """
    source = None
    if isinstance(line, dict):
        raw = line.get("source_doc_id")
        text = str(raw).strip() if raw else ""
        source = text or None
    return {
        "delete_document_ids": [],
        "exclude_from_auto_line_doc_ids": [source] if source else [],
    }


def document_excluded_from_new_echeance_line(doc: Optional[dict]) -> bool:
    """Un PDF retiré du suivi à la main ne recrée pas une ligne."""
    return bool(isinstance(doc, dict) and doc.get("echeance_3p_exclu"))
