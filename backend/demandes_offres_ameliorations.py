"""Évolutions demandes d'offres : urgence, tri, stats fiche, suivi.

Le champ `statut` historique reste la source du workflow (e-mails, signature,
offres à modifier). Le suivi d'avancement est un journal ajouté, pas un
remplacement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from demandes_offres_3p import (
    STATUT_ANNULEE,
    STATUT_ATTENTE_INFOS,
    STATUT_BROUILLON,
    STATUT_EN_CONCLUSION,
    STATUT_ENVOYEE,
    STATUT_INCOMPLETE,
    STATUT_OFFRE_COMPLETE,
    STATUT_OFFRE_ENVOYEE_CLIENT,
    STATUT_OFFRE_RECUE,
    STATUT_OFFRE_REFUSEE,
    STATUT_OFFRE_SIGNEE,
    STATUT_VALIDEE,
    compute_agent_stats,
    is_demande_annulee_statut,
    is_hors_cours,
    is_offre_non_signee_statut,
    normalize_statut,
)

PIECE_KINDS = ("Offre", "CGA", "Autre document")
PIECE_KIND_ALIASES = {
    "offre": "Offre",
    "cga": "CGA",
    "autre": "Autre document",
    "autre document": "Autre document",
}

SUIVI_PROCESS = (
    "en_attente",
    "en_cours",
    "attente_compagnie",
    "relance",
    "offre_transmise",
)
SUIVI_AGENT = ("envoyee_client",)
# « signée » n'est pas une transition libre : elle suit le workflow signature.
SUIVI_LABELS = {
    "en_attente": "En attente",
    "en_cours": "En cours de traitement",
    "attente_compagnie": "En attente de la compagnie",
    "relance": "Relance effectuée auprès de la compagnie",
    "offre_transmise": "Offre transmise à l'agent",
    "envoyee_client": "Offre envoyée au client",
    "signee": "Offre signée",
    "annulee": "Demande annulée",
    "non_signee": "Offre non signée",
    "refusee": "Offre refusée",
}

DEFAULT_URGENCE_SETTINGS = {
    "quota_actif": False,
    "max_par_agent": 5,
    "periode": "mois",
}


def normalize_piece_kind(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in PIECE_KINDS:
        return raw
    return PIECE_KIND_ALIASES.get(raw.casefold())


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "oui", "yes", "on"}


def urgence_payload(doc: dict) -> dict:
    return {
        "urgente": bool(doc.get("urgente")),
        "urgence_motif": str(doc.get("urgence_motif") or "").strip(),
        "urgence_at": doc.get("urgence_at"),
        "urgence_by": doc.get("urgence_by") or "",
        "urgence_exception": bool(doc.get("urgence_exception")),
    }


def validate_urgence_for_send(doc: dict) -> Optional[str]:
    """None si ok, sinon message bloquant. Les brouillons restent enregistrables."""
    if not doc.get("urgente"):
        return None
    if not str(doc.get("urgence_motif") or "").strip():
        return "Le motif de l'urgence est obligatoire pour une demande urgente."
    return None


def period_start_iso(periode: str, now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if periode == "annee":
        start = moment.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start.isoformat()


def count_urgences_agent(rows: list, agent_label: str, *, since_iso: str) -> int:
    target = (agent_label or "").strip().casefold()
    n = 0
    for row in rows:
        if row.get("is_deleted"):
            continue
        if not row.get("urgente"):
            continue
        label = str(row.get("agent_label") or "").strip().casefold()
        if label != target:
            continue
        stamp = str(row.get("urgence_at") or row.get("date_envoi") or row.get("created_at") or "")
        if stamp and stamp < since_iso:
            continue
        st = normalize_statut(row.get("statut") or STATUT_BROUILLON)
        if st == STATUT_BROUILLON or is_hors_cours(st):
            continue
        n += 1
    return n


def period_key(periode: str, now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if periode == "annee":
        return f"{moment.year}"
    return f"{moment.year}-{moment.month:02d}"


def agent_bonus(settings: dict, agent_label: str, now: Optional[datetime] = None) -> int:
    target = (agent_label or "").strip().casefold()
    key = period_key(str((settings or {}).get("periode") or "mois"), now)
    total = 0
    for item in (settings or {}).get("bonus_par_agent") or []:
        if str(item.get("agent") or "").strip().casefold() != target:
            continue
        if str(item.get("periode") or "") != key:
            continue
        total += max(0, int(item.get("extra") or 0))
    return total


def quota_limit(settings: dict, agent_label: str = "", now: Optional[datetime] = None) -> int:
    base = max(0, int((settings or {}).get("max_par_agent") or 0))
    return base + agent_bonus(settings or {}, agent_label, now)


def grant_agent_bonus(settings: dict, agent_label: str, now: Optional[datetime] = None) -> list:
    label = (agent_label or "").strip()
    if not label:
        raise ValueError("Agent requis")
    key = period_key(str((settings or {}).get("periode") or "mois"), now)
    items = [dict(item) for item in (settings.get("bonus_par_agent") or [])]
    for item in items:
        if str(item.get("agent") or "").strip().casefold() != label.casefold():
            continue
        if str(item.get("periode") or "") != key:
            continue
        item["extra"] = max(0, int(item.get("extra") or 0)) + 1
        item["periode"] = key
        return items
    items.append({"agent": label, "extra": 1, "periode": key})
    return items


def quota_block_message(settings: dict, used: int, agent_label: str = "") -> Optional[str]:
    if not settings or not settings.get("quota_actif"):
        return None
    limit = quota_limit(settings, agent_label)
    if limit <= 0:
        return None
    if used < limit:
        return None
    periode = "ce mois" if settings.get("periode") != "annee" else "cette année"
    extra = agent_bonus(settings, agent_label)
    extra_txt = f", dont {extra} exception(s)" if extra else ""
    return (
        f"Quota d'urgences atteint ({used}/{limit} {periode}{extra_txt}). "
        "Un administrateur peut accorder une urgence supplémentaire."
    )


def usages_urgences(rows: list, settings: dict, *, now: Optional[datetime] = None) -> list:
    since = period_start_iso(str((settings or {}).get("periode") or "mois"), now)
    labels: dict[str, str] = {}
    for row in rows:
        label = str(row.get("agent_label") or "").strip()
        if not label:
            continue
        key = label.casefold()
        labels.setdefault(key, label)
    for item in (settings or {}).get("bonus_par_agent") or []:
        label = str(item.get("agent") or "").strip()
        if label:
            labels.setdefault(label.casefold(), label)
    out = []
    for key, label in sorted(labels.items(), key=lambda pair: pair[1].casefold()):
        used = count_urgences_agent(rows, label, since_iso=since)
        extra = agent_bonus(settings or {}, label, now)
        out.append({
            "agent": label,
            "utilisees": used,
            "plafond": quota_limit(settings or {}, label, now),
            "exceptions": extra,
        })
    return out


def _rdv_key(row: dict) -> str:
    date = str(row.get("date_prochain_rdv") or "").strip()[:10]
    heure = str(row.get("heure_rdv") or "").strip()
    if not date:
        return ""
    return f"{date}T{heure}" if heure else date


def _zurich_today(now: Optional[datetime] = None) -> str:
    from zoneinfo import ZoneInfo

    moment = now or datetime.now(ZoneInfo("Europe/Zurich"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()


def sort_demandes(rows: list, tri: Optional[str], *, today: Optional[str] = None) -> list:
    mode = (tri or "").strip().lower()
    if mode in {"", "maj"}:
        return rows

    def submission(row: dict) -> str:
        return str(row.get("date_envoi") or row.get("created_at") or "")

    if mode == "soumission_asc":
        return sorted(rows, key=submission)
    if mode == "soumission_desc":
        return sorted(rows, key=submission, reverse=True)
    if mode == "urgentes":
        return sorted(rows, key=lambda r: (0 if r.get("urgente") else 1, _rdv_key(r) or "9999", submission(r)))
    if mode in {"rdv_asc", "rdv_desc"}:
        day = (today or _zurich_today())[:10]
        future: list = []
        past: list = []
        missing: list = []
        for row in rows:
            key = _rdv_key(row)
            date = key[:10]
            if not date:
                missing.append(row)
            elif date >= day:
                future.append((key, row))
            else:
                past.append((key, row))
        # Plus proche : prochains rendez-vous d'abord, puis les passés, jamais mélangés.
        # Plus éloigné : l'ordre inverse dans chaque groupe.
        future.sort(key=lambda item: item[0], reverse=mode == "rdv_desc")
        past.sort(key=lambda item: item[0], reverse=mode == "rdv_asc")
        return [row for _, row in future] + [row for _, row in past] + missing
    return rows


def filter_urgente(rows: list, only: bool) -> list:
    if not only:
        return rows
    return [r for r in rows if r.get("urgente")]


def filter_rdv_a_venir(rows: list, only: bool, today: Optional[str] = None) -> list:
    if not only:
        return rows
    day = today or datetime.now(timezone.utc).date().isoformat()
    out = []
    for row in rows:
        key = str(row.get("date_prochain_rdv") or "").strip()[:10]
        if key and key >= day:
            out.append(row)
    return out


def fiche_stats_agent(rows: list, agent_label: str) -> dict:
    """Mêmes compteurs que Gestion réponses offres (compute_agent_stats).

    Demandes = hors brouillon et hors annulées / non signées.
    Une demande signée compte une fois (statut), pas une fois par document.
    Le taux de signature reprend compute_stats : signées / dossiers
    déjà transmis au client (pas signées / toutes les demandes).
    """
    block = compute_agent_stats(rows).get("by_agent") or []
    target = (agent_label or "").strip().casefold()
    found = None
    for item in block:
        if str(item.get("agent") or "").strip().casefold() == target:
            found = item
            break
    if found is None and block and target:
        # compute_agent_stats fusionne les libellés : reprendre le premier seau si un seul agent filtré
        if len(block) == 1:
            found = block[0]
    demandes = int((found or {}).get("nb_demandes") or 0)
    signees = int((found or {}).get("offres_signees") or 0)
    envoyees = int((found or {}).get("offres_envoyees") or 0)
    # Même formule que compute_stats()["taux_signature"] :
    # signées / (envoyée au client + en conclusion + signée + refusée).
    taux = round((signees / envoyees) * 100, 1) if envoyees else 0.0
    return {
        "agent": (found or {}).get("agent") or agent_label or "—",
        "nb_demandes": demandes,
        "nb_brouillons": int((found or {}).get("nb_brouillons") or 0),
        "offres_signees": signees,
        "offres_envoyees": envoyees,
        "taux_signature": taux,
        "taux_signature_definition": (
            "Signées / dossiers déjà transmis au client "
            "(envoyée au client, en conclusion, signée ou refusée). "
            "Même calcul que le KPI Taux de signature de Gestion réponses offres."
        ),
        "taux_signature_denominateur": "offres_envoyees",
        "brouillons_exclus": True,
        "annulees_exclues": True,
    }


def should_send_offres_completes_email(doc: dict, note: Optional[str] = None) -> bool:
    """Évite un second e-mail qui répète « une offre est disponible ».

    « Transmettre une offre » prévient déjà l'agent. « Offres complètes »
    n'envoie un e-mail que s'il apporte une note du gestionnaire, ou si
    aucune offre n'a encore été notifiée par e-mail.
    """
    if (note or "").strip():
        return True
    return not bool(doc.get("offre_recue_email_sent"))


SUIVI_PIPELINE = (
    "en_attente",
    "en_cours",
    "attente_compagnie",
    "relance",
    "offre_transmise",
    "envoyee_client",
    "signee",
)
SUIVI_PIPELINE_PRINCIPAL = tuple(code for code in SUIVI_PIPELINE if code != "relance")


def etapes_visibles(doc: dict) -> list:
    """Sept étapes toujours listées. La relance est un événement, pas un remplacement."""
    current = etape_affichee(doc)
    if current not in SUIVI_PIPELINE_PRINCIPAL:
        current = ""
    index = SUIVI_PIPELINE_PRINCIPAL.index(current) if current else -1
    relances = [
        event for event in (doc.get("suivi_evenements") or [])
        if event.get("etape") == "relance"
    ]
    steps = []
    for code in SUIVI_PIPELINE:
        if code == "relance":
            steps.append({
                "id": code,
                "label": SUIVI_LABELS[code],
                "kind": "evenement",
                "reached": bool(relances),
                "current": False,
                "compagnie_conservee": "attente_compagnie",
            })
            continue
        position = SUIVI_PIPELINE_PRINCIPAL.index(code)
        steps.append({
            "id": code,
            "label": SUIVI_LABELS[code],
            "kind": "etape",
            "reached": index >= position,
            "current": code == current,
        })
    return steps


def etape_depuis_statut(statut: Any) -> str:
    st = normalize_statut(statut or STATUT_BROUILLON)
    if is_demande_annulee_statut(st) or st == STATUT_ANNULEE:
        return "annulee"
    if is_offre_non_signee_statut(st):
        return "non_signee"
    if st == STATUT_OFFRE_SIGNEE:
        return "signee"
    if st == STATUT_OFFRE_REFUSEE:
        return "refusee"
    if st in {STATUT_OFFRE_ENVOYEE_CLIENT, STATUT_EN_CONCLUSION}:
        return "envoyee_client"
    if st in {STATUT_OFFRE_RECUE, STATUT_OFFRE_COMPLETE, "Offre complète", "Offre choisie"}:
        return "offre_transmise"
    if st in {STATUT_INCOMPLETE, STATUT_ATTENTE_INFOS}:
        return "en_cours"
    if st in {STATUT_ENVOYEE, STATUT_VALIDEE}:
        return "en_attente"
    return "en_attente"


def etape_affichee(doc: dict) -> str:
    """L'étape choisie par le gestionnaire est affichée.

    Les issues du workflow officiel (envoyée au client, signée, refusée,
    annulée, non signée) restent prioritaires. Sans étape enregistrée,
    un ancien dossier est lu depuis son statut. Une relance n'est jamais
    l'étape affichée.
    """
    from_statut = etape_depuis_statut(doc.get("statut"))
    if from_statut in {"signee", "annulee", "refusee", "envoyee_client", "non_signee"}:
        return from_statut
    explicit = str(doc.get("suivi_etape") or "").strip()
    if explicit == "relance":
        explicit = "attente_compagnie"
    if explicit in {"en_attente", "en_cours", "attente_compagnie", "offre_transmise"}:
        return explicit
    return from_statut


def enregistrer_suivi(
    doc: dict,
    etape: str,
    *,
    auteur: str,
    auteur_id: str = "",
    commentaire: str = "",
    compagnie: str = "",
    at: Optional[str] = None,
) -> dict:
    code = (etape or "").strip()
    if code not in SUIVI_LABELS:
        raise ValueError("Étape de suivi inconnue")
    if code == "signee":
        raise ValueError("La signature passe par le workflow de document signé")
    current = etape_affichee(doc)
    if code == "relance" and current not in {"attente_compagnie", "relance", "en_cours", "offre_transmise"}:
        raise ValueError("Une relance suppose que le dossier a été transmis à une compagnie")
    stamp = at or datetime.now(timezone.utc).isoformat()
    previous = current
    event = {
        "at": stamp,
        "etape": code,
        "label": SUIVI_LABELS[code],
        "etape_precedente": previous,
        "etape_precedente_label": SUIVI_LABELS.get(previous, previous or "—"),
        "auteur": auteur,
        "auteur_id": auteur_id,
        "commentaire": (commentaire or "").strip(),
        "compagnie": (compagnie or "").strip(),
    }
    events = list(doc.get("suivi_evenements") or [])
    events.append(event)
    next_etape = previous if code == "relance" else code
    if code == "relance" and previous == "en_cours":
        next_etape = "attente_compagnie"
    return {
        "suivi_etape": next_etape,
        "suivi_evenements": events,
        "dernier_evenement": event,
    }
