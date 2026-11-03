"""
Mandat de gestion obligatoire pour les demandes d'offres professionnelles
lorsqu'Allianz et/ou Vaudoise sont sollicitées.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

DOC_CATEGORY_MANDAT = "Mandat de gestion"
# Ancienne catégorie encore acceptée pour les pièces déjà jointes
DOC_CATEGORY_MANDAT_LEGACY = "Mandat"

MANDAT_INFO_MESSAGE = (
    "Pour toute demande d'offre professionnelle adressée à Allianz ou Vaudoise, "
    "un mandat de gestion d'une durée minimale de 1 an est obligatoire. "
    "Merci de joindre ce document avant de transmettre votre demande au service Offres."
)

# Sous-chaînes (libellés schéma : « Allianz (Romandie…) », « La Vaudoise », etc.)
MANDAT_REQUIRED_COMPANY_MARKERS = ("allianz", "vaudoise")

_MANDAT_CATEGORY_KEYS = {
    "mandat",
    "mandat de gestion",
    "mandat_gestion",
}


def is_mandat_document_category(category: Optional[str]) -> bool:
    key = (category or "").strip().lower()
    return key in _MANDAT_CATEGORY_KEYS


def normalize_mandat_upload_category(category: Optional[str]) -> Optional[str]:
    """Retourne DOC_CATEGORY_MANDAT si la catégorie uploadée est un mandat, sinon None."""
    if is_mandat_document_category(category):
        return DOC_CATEGORY_MANDAT
    return None


def parse_mandat_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            text = text[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _anniversary_plus_one_year(start: date) -> date:
    try:
        return date(start.year + 1, start.month, start.day)
    except ValueError:
        # 29 février → 28 février année suivante
        return date(start.year + 1, start.month, 28)


def mandat_covers_at_least_one_year(start: date, end: date) -> bool:
    if end < start:
        return False
    return end >= _anniversary_plus_one_year(start)


def has_mandat_document(docs: Optional[list]) -> bool:
    for doc in docs or []:
        if not isinstance(doc, dict):
            continue
        if doc.get("is_deleted"):
            continue
        if is_mandat_document_category(doc.get("category")):
            return True
    return False


def is_professionnelle_demande(doc: Optional[dict]) -> bool:
    if not doc:
        return False
    try:
        from offre_form_types import is_professionnelle_form

        return is_professionnelle_form(
            doc.get("form_type"),
            form_category=doc.get("form_category"),
        )
    except Exception:
        return False


def is_mandat_required_company(name: Any) -> bool:
    key = " ".join(str(name or "").strip().casefold().split())
    if not key:
        return False
    return any(marker in key for marker in MANDAT_REQUIRED_COMPANY_MARKERS)


def compagnies_of_demande(doc: Optional[dict]) -> list[str]:
    """Compagnies sollicitées (schéma + colonne CRM), sans importer demandes_offres_3p."""
    if not doc:
        return []
    names: list[str] = []
    try:
        from offre_form_types import compagnies_selectionnees, is_mode_traitement

        names.extend(
            compagnies_selectionnees(
                doc.get("form_type"),
                doc.get("form_payload") or {},
            )
        )
        for raw in doc.get("compagnies") or []:
            text = str(raw or "").strip()
            if text and not is_mode_traitement(text):
                names.append(text)
    except Exception:
        for raw in (doc.get("compagnies") or []):
            text = str(raw or "").strip()
            if text:
                names.append(text)
    # Dédupliquer en conservant l'ordre
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = " ".join(name.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def demande_requires_mandat_gestion(doc: Optional[dict]) -> bool:
    """True uniquement si formulaire pro ET au moins Allianz ou Vaudoise sollicitée."""
    if not is_professionnelle_demande(doc):
        return False
    return any(is_mandat_required_company(name) for name in compagnies_of_demande(doc))


def mandat_gestion_missing(doc: dict, *, docs: Optional[list] = None, today: Optional[date] = None) -> list[str]:
    """
    Erreurs bloquant l'envoi quand Allianz/Vaudoise sont sollicitées.
    Si docs est None, la présence du fichier n'est pas contrôlée (dates seulement).
    """
    if not demande_requires_mandat_gestion(doc):
        return []

    missing: list[str] = []
    start = parse_mandat_date(doc.get("mandat_debut"))
    end = parse_mandat_date(doc.get("mandat_fin"))
    ref = today or date.today()

    if docs is not None and not has_mandat_document(docs):
        missing.append("Mandat de gestion (document manquant)")

    if start is None or end is None:
        missing.append("Dates du mandat de gestion (début et fin)")
    else:
        if end < start:
            missing.append("Dates du mandat incohérentes (fin avant début)")
        elif not mandat_covers_at_least_one_year(start, end):
            missing.append("Durée du mandat inférieure à 1 an")
        elif end < ref:
            missing.append("Mandat de gestion expiré")

    return missing
