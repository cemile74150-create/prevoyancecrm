"""Saisie du journal d'action d'un dossier client."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def normalize_journal_fields(
    libelle: Optional[str],
    date: Optional[str],
    note: Optional[str] = None,
) -> dict:
    label = (libelle or "").strip()
    if not label:
        raise ValueError("Indiquez ce qui a été fait.")
    if len(label) > 300:
        raise ValueError("Le libellé est trop long.")
    day = (date or "").strip()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("La date doit être au format AAAA-MM-JJ.") from exc
    extra = (note or "").strip()
    if len(extra) > 4000:
        raise ValueError("La note est trop longue.")
    return {"libelle": label, "date": day, "note": extra or None}


def sort_journal_actions(rows: list[dict]) -> list[dict]:
    """La date d'action la plus récente en premier, puis la saisie la plus récente."""
    return sorted(
        rows,
        key=lambda row: (str(row.get("date") or ""), str(row.get("created_at") or "")),
        reverse=True,
    )


def journal_belongs_to_scope(row: dict, scope: dict) -> bool:
    members = set(scope.get("member_ids") or [])
    if row.get("client_id") in members:
        return True
    dossier_id = scope.get("dossier_id")
    return bool(dossier_id) and row.get("dossier_id") == dossier_id
