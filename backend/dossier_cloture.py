"""Clôture de dossiers prévoyance + agrégats stats (Suivi de vos dossiers).

Règle taux de réussite
----------------------
taux = affaires_abouties / (affaires_abouties + affaires_non_abouties) × 100

Les dossiers clôturés sans motif (« Non renseigné ») sont exclus du
dénominateur et ne sont comptés ni en abouties ni en non abouties.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

CLOTURE_MOTIF_ABOUTIE = "affaire_aboutie"
CLOTURE_MOTIF_NON_ABOUTIE = "affaire_non_aboutie"
CLOTURE_MOTIFS = (CLOTURE_MOTIF_ABOUTIE, CLOTURE_MOTIF_NON_ABOUTIE)

CLOTURE_MOTIF_LABELS = {
    CLOTURE_MOTIF_ABOUTIE: "Affaire aboutie",
    CLOTURE_MOTIF_NON_ABOUTIE: "Affaire non aboutie",
}

STATUT_CLOTURE = "Clôturé"
STATUT_NOUVEAU = "Nouveau"
STATUT_EN_ATTENTE = "Documents en attente"
STATUTS_EN_COURS = (
    "Analyse en cours",
    "Stand-by",
    "À présenter",
    "Dossier présenté — en cours",
)

ZURICH = ZoneInfo("Europe/Zurich")


def today_zurich_iso() -> str:
    return datetime.now(ZURICH).date().isoformat()


def normalize_cloture_motif(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip().casefold().replace(" ", "_").replace("-", "_")
    aliases = {
        "affaire_aboutie": CLOTURE_MOTIF_ABOUTIE,
        "aboutie": CLOTURE_MOTIF_ABOUTIE,
        "affaire_non_aboutie": CLOTURE_MOTIF_NON_ABOUTIE,
        "non_aboutie": CLOTURE_MOTIF_NON_ABOUTIE,
        "affaire_nonaboutie": CLOTURE_MOTIF_NON_ABOUTIE,
    }
    return aliases.get(raw)


def cloture_motif_label(value: Optional[str]) -> str:
    motif = normalize_cloture_motif(value)
    if not motif:
        return "Non renseigné"
    return CLOTURE_MOTIF_LABELS.get(motif, "Non renseigné")


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def validate_cloture_payload(
    *,
    statut: str,
    cloture_date: Optional[str],
    cloture_motif: Optional[str],
    require_motif: bool = True,
) -> Tuple[Optional[str], Optional[str]]:
    """Valide / normalise date+motif pour un passage à Clôturé.

    Retourne (date_iso, motif_normalisé). Lève ValueError si invalide.
    """
    if statut != STATUT_CLOTURE:
        return None, None

    motif = normalize_cloture_motif(cloture_motif)
    if require_motif and motif not in CLOTURE_MOTIFS:
        raise ValueError("Motif de clôture obligatoire (Affaire aboutie / Affaire non aboutie)")

    date_iso = (cloture_date or "").strip()[:10] or today_zurich_iso()
    if parse_iso_date(date_iso) is None:
        raise ValueError("Date de clôture invalide (attendu AAAA-MM-JJ)")
    return date_iso, motif


def pick_dossier_fields(members: List[dict]) -> dict:
    """Agrège date/motif de clôture au niveau dossier (premier membre renseigné)."""
    date_val = None
    motif_val = None
    for m in members or []:
        if not date_val and m.get("cloture_date"):
            date_val = m.get("cloture_date")
        if not motif_val and m.get("cloture_motif"):
            motif_val = m.get("cloture_motif")
        if date_val and motif_val:
            break
    return {
        "cloture_date": (str(date_val)[:10] if date_val else None),
        "cloture_motif": normalize_cloture_motif(motif_val),
        "cloture_motif_label": cloture_motif_label(motif_val),
    }


def _in_period(iso_stamp: Optional[str], date_from: Optional[date], date_to: Optional[date]) -> bool:
    if date_from is None and date_to is None:
        return True
    d = parse_iso_date(iso_stamp)
    if d is None:
        return False
    if date_from and d < date_from:
        return False
    if date_to and d > date_to:
        return False
    return True


def resolve_period_bounds(
    period: Optional[str],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    *,
    today: Optional[date] = None,
) -> Tuple[Optional[date], Optional[date]]:
    """period: all | month | year | custom."""
    today = today or datetime.now(ZURICH).date()
    p = (period or "all").strip().lower()
    if p in ("", "all", "toute", "toutes"):
        return None, None
    if p == "month":
        return today.replace(day=1), today
    if p == "year":
        return date(today.year, 1, 1), today
    if p == "custom":
        return parse_iso_date(date_from), parse_iso_date(date_to)
    return None, None


def dossier_reference_date(dossier: dict) -> Optional[str]:
    """Date de référence pour le filtre période : clôture si clôturé, sinon création."""
    if dossier.get("statut") == STATUT_CLOTURE:
        return dossier.get("cloture_date") or dossier.get("updated_at") or dossier.get("created_at")
    return dossier.get("created_at")


def compute_taux_reussite(abouties: int, non_abouties: int) -> Optional[float]:
    denom = abouties + non_abouties
    if denom <= 0:
        return None
    return round(100.0 * abouties / denom, 1)


def empty_stats() -> dict:
    return {
        "total": 0,
        "nouveaux": 0,
        "en_attente": 0,
        "en_cours": 0,
        "clotures": 0,
        "affaires_abouties": 0,
        "affaires_non_abouties": 0,
        "clotures_non_renseignees": 0,
        "taux_reussite": None,
        "by_statut": {},
        "abouties_par_agent": [],
        "evolution_mensuelle": [],
        "taux_reussite_regle": (
            "abouties / (abouties + non abouties) × 100 ; "
            "clôturés sans motif exclus du dénominateur"
        ),
    }


def aggregate_dossier_stats(
    dossiers: Iterable[dict],
    *,
    statut_filter: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    months: int = 6,
    today: Optional[date] = None,
) -> dict:
    """Agrège les stats à partir de dossiers déjà isolés (permissions appliquées en amont).

    Chaque dossier attend : statut, created_at, updated_at?, cloture_date?, cloture_motif?,
    conseiller? (libellé agent).
    """
    today = today or datetime.now(ZURICH).date()
    stats = empty_stats()
    by_statut: Dict[str, int] = {}
    by_agent: Dict[str, Dict[str, Any]] = {}

    filtered: List[dict] = []
    for d in dossiers:
        if statut_filter and d.get("statut") != statut_filter:
            continue
        if not _in_period(dossier_reference_date(d), date_from, date_to):
            continue
        filtered.append(d)

    for d in filtered:
        statut = d.get("statut") or STATUT_NOUVEAU
        by_statut[statut] = by_statut.get(statut, 0) + 1
        stats["total"] += 1

        if statut == STATUT_NOUVEAU:
            stats["nouveaux"] += 1
        elif statut == STATUT_EN_ATTENTE:
            stats["en_attente"] += 1
        elif statut in STATUTS_EN_COURS:
            stats["en_cours"] += 1
        elif statut == STATUT_CLOTURE:
            stats["clotures"] += 1
            motif = normalize_cloture_motif(d.get("cloture_motif"))
            agent = (d.get("conseiller") or "").strip() or "Non attribué"
            entry = by_agent.setdefault(
                agent.casefold(),
                {"agent": agent, "abouties": 0, "non_abouties": 0, "non_renseignees": 0},
            )
            if motif == CLOTURE_MOTIF_ABOUTIE:
                stats["affaires_abouties"] += 1
                entry["abouties"] += 1
            elif motif == CLOTURE_MOTIF_NON_ABOUTIE:
                stats["affaires_non_abouties"] += 1
                entry["non_abouties"] += 1
            else:
                stats["clotures_non_renseignees"] += 1
                entry["non_renseignees"] += 1

    stats["by_statut"] = by_statut
    stats["taux_reussite"] = compute_taux_reussite(
        stats["affaires_abouties"],
        stats["affaires_non_abouties"],
    )
    stats["abouties_par_agent"] = sorted(
        by_agent.values(),
        key=lambda x: (-(x["abouties"] + x["non_abouties"]), x["agent"].lower()),
    )

    # Évolution mensuelle : ouverts (created_at) et clôturés (cloture_date) sur N mois.
    # Basée sur le même filtre agent/statut déjà appliqué à `filtered`, sans re-couper
    # la période mois-par-mois (le filtre période global a déjà réduit l'ensemble).
    month_keys: List[str] = []
    for i in range(months - 1, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        month_keys.append(f"{y:04d}-{m:02d}")

    evo = {k: {"mois": k, "ouverts": 0, "clotures": 0} for k in month_keys}
    for d in filtered:
        created = (d.get("created_at") or "")[:7]
        if created in evo:
            evo[created]["ouverts"] += 1
        if d.get("statut") == STATUT_CLOTURE:
            closed = (d.get("cloture_date") or d.get("updated_at") or "")[:7]
            if closed in evo:
                evo[closed]["clotures"] += 1

    stats["evolution_mensuelle"] = [evo[k] for k in month_keys]
    return stats
