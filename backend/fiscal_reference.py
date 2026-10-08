"""Année fiscale de référence du calculateur — réglage interne, hors formulaire conseiller.

2025 reste le défaut. Le passage à une autre année est manuel.
L'alerte du 01/01/2027 ne disparaît qu'après validation explicite des barèmes
pour l'année de référence courante. Changer l'année seule ne valide pas.
"""
from __future__ import annotations

from datetime import date, datetime

FISCAL_REFERENCE_YEAR_DEFAULT = 2025
FISCAL_ALERT_FROM = date(2027, 1, 1)
FISCAL_ALERT_TEXT = (
    "Mise à jour fiscale nécessaire : les calculs utilisent actuellement les paramètres fiscaux de 2025. "
    "Veuillez vérifier et actualiser l'année fiscale de référence ainsi que les données correspondantes."
)
CONFIG_ID = "analyse-fiscal"


def default_config() -> dict:
    return {
        "id": CONFIG_ID,
        "referenceYear": FISCAL_REFERENCE_YEAR_DEFAULT,
        "validatedReferenceYear": None,
        "validatedAt": None,
    }


def parse_as_of(value: str | None, today: date | None = None) -> date:
    """Date injectée pour les tests (AAAA-MM-JJ). Sinon la date du jour, sans toucher à l'horloge."""
    if value:
        raw = str(value).strip()[:10]
        return date.fromisoformat(raw)
    return today or date.today()


def fiscal_alert(
    as_of: date,
    reference_year: int,
    validated_reference_year: int | None,
) -> str | None:
    if as_of < FISCAL_ALERT_FROM:
        return None
    if validated_reference_year is not None and int(validated_reference_year) == int(reference_year):
        return None
    return FISCAL_ALERT_TEXT


def normalize_config(doc: dict | None) -> dict:
    base = default_config()
    if not isinstance(doc, dict):
        return base
    year = doc.get("referenceYear", FISCAL_REFERENCE_YEAR_DEFAULT)
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = FISCAL_REFERENCE_YEAR_DEFAULT
    validated = doc.get("validatedReferenceYear")
    if validated is not None:
        try:
            validated = int(validated)
        except (TypeError, ValueError):
            validated = None
    return {
        "id": CONFIG_ID,
        "referenceYear": year,
        "validatedReferenceYear": validated,
        "validatedAt": doc.get("validatedAt"),
    }


def apply_year_change(config: dict, year: int) -> dict:
    """Change l'année affichée. Ne valide pas les barèmes."""
    year = int(year)
    if year < 2000 or year > 2100:
        raise ValueError("Année fiscale hors plage")
    next_config = dict(config)
    next_config["referenceYear"] = year
    return next_config


def apply_validation(config: dict, validated_at: str | None = None) -> dict:
    """Validation explicite : les barèmes correspondent à l'année de référence courante."""
    next_config = dict(config)
    next_config["validatedReferenceYear"] = int(config["referenceYear"])
    next_config["validatedAt"] = validated_at or datetime.now().isoformat(timespec="seconds")
    return next_config


def public_status(config: dict, as_of: date) -> dict:
    normalized = normalize_config(config)
    return {
        "referenceYear": normalized["referenceYear"],
        "validatedReferenceYear": normalized["validatedReferenceYear"],
        "validatedAt": normalized["validatedAt"],
        "asOf": as_of.isoformat(),
        "alert": fiscal_alert(
            as_of,
            normalized["referenceYear"],
            normalized["validatedReferenceYear"],
        ),
    }
