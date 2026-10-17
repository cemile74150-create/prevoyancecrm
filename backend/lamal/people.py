"""Lecture seule des fiches clients pour le comparateur LAMal."""
from __future__ import annotations

from typing import Optional

from courrier_word import infer_country
from lamal.engine import fold_name, valid_email

STATUS_LABELS = {
    "informations_manquantes": "Informations manquantes",
    "pret_pour_analyse": "Prêt pour analyse",
    "analyse_effectuee": "Analyse effectuée",
    "economie_identifiee": "Économie identifiée",
    "aucune_economie": "Aucune économie identifiée",
    "email_a_valider": "E-mail à valider",
    "email_envoye": "E-mail envoyé",
    "client_interesse": "Client intéressé",
    "changement_en_cours": "Changement en cours",
    "termine": "Terminé",
}

OPT_OUT_FIELDS = (
    "opposition_prospection",
    "prospection_opposee",
    "ne_pas_contacter",
    "email_opt_out",
    "refus_prospection",
    "refus_email",
)


def _truthy(value) -> bool:
    if value is True:
        return True
    return fold_name(str(value or "")) in {"1", "oui", "true", "yes"}


def is_opted_out(client: dict, profile: Optional[dict] = None) -> bool:
    profile = profile or {}
    if _truthy(profile.get("prospection_opposee")):
        return True
    return any(_truthy(client.get(field)) for field in OPT_OUT_FIELDS)


def swiss_residence(client: dict) -> Optional[bool]:
    """True, False, ou None si le domicile ne peut pas être établi."""
    country = infer_country(client or {})
    if country == "France":
        return False
    if country == "Suisse":
        return True
    return None


def derive_status(client: dict, profile: dict, comparison: Optional[dict]) -> str:
    manual = (profile or {}).get("suivi")
    if manual in {"client_interesse", "changement_en_cours", "termine"}:
        return manual
    result = (comparison or {}).get("result") or {}
    if result.get("email_status") == "envoye":
        return "email_envoye"
    if not comparison:
        missing = _missing_inputs(client, profile)
        return "informations_manquantes" if missing else "pret_pour_analyse"
    if result.get("savings_reliable"):
        return "economie_identifiee"
    if result.get("ok") and result.get("reference"):
        return "aucune_economie"
    if result.get("ok"):
        return "analyse_effectuee"
    return "informations_manquantes"


def _missing_inputs(client: dict, profile: dict) -> list[str]:
    missing = []
    if not (profile.get("birth_year") or client.get("date_naissance")):
        missing.append("annee_naissance")
    if not (profile.get("commune") or profile.get("plz") or client.get("ville") or client.get("npa")):
        missing.append("commune")
    franchise = profile.get("franchise_chf")
    if franchise is None and not client.get("franchise") and not client.get("franchise_lamal"):
        missing.append("franchise")
    accident = profile.get("with_accident")
    if accident is None and client.get("couverture_accidents") is None and client.get("accident") is None:
        missing.append("accidents")
    return missing


def client_view(client: dict, profile: Optional[dict], comparison: Optional[dict]) -> dict:
    profile = profile or {}
    result = (comparison or {}).get("result") or {}
    status = derive_status(client, profile, comparison)
    best = (result.get("best_equivalent_alternative") or {})
    reference = result.get("reference") or {}
    return {
        "id": client.get("id"),
        "nom": client.get("nom") or None,
        "prenom": client.get("prenom") or None,
        "email": client.get("email") or None,
        "email_valid": valid_email(client.get("email")),
        "npa": profile.get("plz") or client.get("npa") or None,
        "commune": result.get("commune") or profile.get("commune") or client.get("ville") or None,
        "canton": result.get("canton") or profile.get("canton") or client.get("canton") or None,
        "conseiller": client.get("conseiller") or None,
        "insurer": reference.get("insurer_name") or profile.get("insurer_label") or client.get("caisse_maladie") or client.get("caisse") or None,
        "savings_year": best.get("year") if result.get("savings_reliable") else None,
        "savings_month": best.get("month") if result.get("savings_reliable") else None,
        "savings_reliable": bool(result.get("savings_reliable")),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "comparison_id": (comparison or {}).get("id"),
        "opt_out": is_opted_out(client, profile),
        "swiss": swiss_residence(client) is True,
    }
