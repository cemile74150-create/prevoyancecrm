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

ETAPE_OFFRES_PARTIELLES = "offres_partielles"
URGENCE_DELAI_24H = "moins_24h"
URGENCE_DELAI_24H_LABEL = "À traiter en moins de 24 heures"

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
    ETAPE_OFFRES_PARTIELLES,
    "offre_transmise",
)
SUIVI_AGENT = ("envoyee_client",)
# « signée » n'est pas une transition libre : elle suit le workflow signature.
SUIVI_LABELS = {
    "en_attente": "En attente",
    "en_cours": "En cours de traitement",
    "attente_compagnie": "En attente de la compagnie",
    "relance": "Relance effectuée auprès de la compagnie",
    "offre_transmise": "Offres transmises à l'agent",
    ETAPE_OFFRES_PARTIELLES: "Offres partiellement transmises à l'agent",
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
        "urgence_delai": str(doc.get("urgence_delai") or ""),
        "urgence_echeance_at": doc.get("urgence_echeance_at"),
    }


def validate_urgence_request(urgente: bool, motif: Any, delai_24h: Any) -> Optional[str]:
    """None si la pose est acceptable, sinon le motif du refus.

    Le retrait (urgente=False) ne demande ni case ni motif.
    """
    if not urgente:
        return None
    if not parse_bool(delai_24h):
        return "Cochez « Demande à traiter sous moins de 24 h » pour confirmer l'urgence."
    if not str(motif or "").strip():
        return "Le motif de l'urgence est obligatoire"
    return None


def urgence_echeance_iso(stamp: str) -> str:
    from datetime import timedelta

    moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (moment + timedelta(hours=24)).isoformat()


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
    """Même date que la colonne RDV client : formulaire si date_prochain_rdv est vide."""
    try:
        from offre_form_types import rdv_client_effectif

        date, heure = rdv_client_effectif(row)
    except Exception:
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
        key = _rdv_key(row)[:10]
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
    partielle = current == ETAPE_OFFRES_PARTIELLES
    if partielle:
        current = "attente_compagnie"
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
        if partielle and code == "offre_transmise":
            steps.append({
                "id": code,
                "label": SUIVI_LABELS[ETAPE_OFFRES_PARTIELLES],
                "kind": "etape",
                "reached": False,
                "current": True,
                "partielle": True,
            })
            continue
        steps.append({
            "id": code,
            "label": SUIVI_LABELS[code],
            "kind": "etape",
            "reached": index >= position,
            "current": code == current and not partielle,
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


def compagnies_transmises(doc: dict) -> list[str]:
    """Compagnies ayant au moins une offre transmise à l'agent.

    Une compagnie compte une fois, quel que soit son nombre de variantes ou
    de transmissions. Un document déposé hors « Transmettre une offre »
    ne crée pas d'offre et ne compte donc pas. Une compagnie seulement
    marquée « Incomplète », sans offre reçue, ne compte pas non plus.
    """
    from demandes_offres_3p import company_key, company_offer_data_present, normalize_offres_list

    out: list[str] = []
    seen: set[str] = set()
    for offer in normalize_offres_list(doc or {}):
        key = company_key(offer.get("compagnie"))
        if not key or key in seen or not company_offer_data_present(offer):
            continue
        seen.add(key)
        out.append(str(offer.get("compagnie") or "").strip())
    return out


def etat_transmission(doc: dict) -> dict:
    """Compagnies sollicitées face aux compagnies transmises.

    etat : « aucune », « partielle » ou « complete ». Sans compagnie
    sollicitée connue, une transmission suffit pour être complète.
    """
    from demandes_offres_3p import company_key, effective_compagnies

    sollicitees = effective_compagnies(doc or {})
    transmises = compagnies_transmises(doc or {})
    transmises_keys = {company_key(name) for name in transmises}
    manquantes = [name for name in sollicitees if company_key(name) not in transmises_keys]
    if not transmises:
        etat = "aucune"
    elif not sollicitees or not manquantes:
        etat = "complete"
    else:
        etat = "partielle"
    nb_sollicitees_transmises = len(sollicitees) - len(manquantes)
    return {
        "etat": etat,
        "sollicitees": sollicitees,
        "transmises": transmises,
        "manquantes": manquantes,
        "nb_sollicitees": len(sollicitees),
        "nb_transmises": nb_sollicitees_transmises if sollicitees else len(transmises),
    }


def etape_transmission_cible(doc: dict) -> Optional[str]:
    """Étape à enregistrer après une transmission effective, ou None si aucune."""
    etat = etat_transmission(doc)["etat"]
    if etat == "complete":
        return "offre_transmise"
    if etat == "partielle":
        return ETAPE_OFFRES_PARTIELLES
    return None


def etape_affichee(doc: dict) -> str:
    """L'étape choisie par le gestionnaire est affichée.

    Les issues du workflow officiel (envoyée au client, signée, refusée,
    annulée, non signée) restent prioritaires. Sans étape enregistrée,
    un ancien dossier est lu depuis son statut. Une relance n'est jamais
    l'étape affichée.

    Une étape posée par une transmission (suivi_auto) suit les compagnies
    réellement transmises : partielle ou complète. Un choix manuel
    « offre_transmise » et les anciens dossiers sans suivi_auto gardent
    leur étape.
    """
    from_statut = etape_depuis_statut(doc.get("statut"))
    if from_statut in {"signee", "annulee", "refusee", "envoyee_client", "non_signee"}:
        return from_statut
    explicit = str(doc.get("suivi_etape") or "").strip()
    if explicit == "relance":
        explicit = "attente_compagnie"
    if explicit in {"en_attente", "en_cours", "attente_compagnie"}:
        return explicit
    if explicit == ETAPE_OFFRES_PARTIELLES or (explicit == "offre_transmise" and doc.get("suivi_auto")):
        return etape_transmission_cible(doc) or explicit
    if explicit == "offre_transmise":
        return explicit
    return from_statut


def est_nouvelle_demande(doc: dict) -> bool:
    """Vrai seulement pour un envoi qui a posé gestion_vue=False et n'a pas été ouvert.

    L'absence du champ, sur un dossier ancien, ne signifie pas qu'il est nouveau.
    Charger la liste ne consulte pas le dossier.
    """
    if doc.get("gestion_vue") is not False:
        return False
    if str(doc.get("gestion_consultee_at") or "").strip():
        return False
    if str(doc.get("statut") or "").strip() in {"Brouillon", ""}:
        return False
    explicit = str(doc.get("suivi_etape") or "").strip()
    if explicit and explicit not in {"en_attente"}:
        return False
    return etape_affichee(doc) == "en_attente"


def relance_en_cours(doc: dict) -> bool:
    """La dernière action est une relance, sans avoir quitté l'attente compagnie."""
    if etape_affichee(doc) != "attente_compagnie":
        return False
    events = [event for event in (doc.get("suivi_evenements") or []) if isinstance(event, dict)]
    return bool(events) and events[-1].get("etape") == "relance"


def compteurs_avancement(rows: list) -> dict:
    counts = {
        "nouvelles": 0,
        "en_cours": 0,
        "attente_compagnie": 0,
        "relances": 0,
        "offre_transmise": 0,
        ETAPE_OFFRES_PARTIELLES: 0,
    }
    for row in rows or []:
        if row.get("is_deleted"):
            continue
        if str(row.get("statut") or "") == "Brouillon":
            continue
        if est_nouvelle_demande(row):
            counts["nouvelles"] += 1
            continue
        if relance_en_cours(row):
            counts["relances"] += 1
            continue
        step = etape_affichee(row)
        if step in counts:
            counts[step] += 1
    return counts


def urgentes_en_tete(rows: list) -> list:
    """Place les demandes urgentes agent (flag `urgente`) avant tout le monde.

    Primauté distincte de la priorité système (`priorite` normal/surveiller/urgent) :
    une urgence agent avec priorité « Normal » passe devant une non-urgente
    même si celle-ci a une priorité système « Urgent ».
    """
    urgent = [row for row in rows if row.get("urgente")]
    autres = [row for row in rows if not row.get("urgente")]
    return urgent + autres


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
    if code == "relance" and current not in {"attente_compagnie", "relance", "en_cours", "offre_transmise", ETAPE_OFFRES_PARTIELLES}:
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
