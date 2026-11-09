"""Pilotage du service des offres : attribution, traitement, résultat commercial.

Trois dimensions indépendantes, calculées ici et seulement ici :
- attribution : gestionnaire responsable (``gestionnaire_id``) ou non attribuée ;
- traitement : l'une des six étapes d'« Avancement du traitement » ;
- commercial : décision renseignée par l'agent, lue dans le workflow existant
  (« Offre envoyée au client », « Offre signée », « Offre non signée »).

Le tableau de bord général et l'espace personnel du gestionnaire appellent
``compute_pilotage`` sur des lots différents. Les définitions sont les mêmes,
seul le périmètre change.

Aucun statut n'est réécrit : les anciens dossiers sans gestionnaire restent
« non attribués » et ceux sans décision « Statut non renseigné ».
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from demandes_offres_3p import (
    OFFRES_DELAI_SURVEILLER_JOURS,
    STATUT_BROUILLON,
    STATUT_EN_CONCLUSION,
    STATUT_OFFRE_ENVOYEE_CLIENT,
    STATUT_OFFRE_NON_SIGNEE,
    STATUT_OFFRE_REFUSEE,
    STATUT_OFFRE_SIGNEE,
    count_offres_recues,
    is_demande_annulee_statut,
    normalize_statut,
)
from demandes_offres_ameliorations import (
    ETAPE_OFFRES_PARTIELLES,
    SUIVI_LABELS,
    etape_depuis_statut,
    etape_transmission_cible,
)

RELANCE_DECISION_JOURS = 14

TRAITEMENT_CODES = (
    "en_attente",
    "en_cours",
    "attente_compagnie",
    "relance",
    ETAPE_OFFRES_PARTIELLES,
    "offre_transmise",
)
TRAITEMENT_LABELS = {code: SUIVI_LABELS[code] for code in TRAITEMENT_CODES}
TRAITEMENT_EN_COURS_GLOBAL = {"en_cours", "attente_compagnie", "relance", ETAPE_OFFRES_PARTIELLES}
TRAITEMENT_NON_TERMINE = {"en_attente", *TRAITEMENT_EN_COURS_GLOBAL}
# Un RDV dans ce délai laisse moins que le délai minimum de réponse des compagnies.
RDV_RETARD_JOURS = OFFRES_DELAI_SURVEILLER_JOURS

COMMERCIAL_NON_RENSEIGNE = "non_renseigne"
COMMERCIAL_TRANSMISE = "transmise_client"
COMMERCIAL_SIGNEE = "signee"
COMMERCIAL_NON_SIGNEE = "non_signee"
COMMERCIAL_CODES = (
    COMMERCIAL_NON_RENSEIGNE,
    COMMERCIAL_TRANSMISE,
    COMMERCIAL_SIGNEE,
    COMMERCIAL_NON_SIGNEE,
)
COMMERCIAL_LABELS = {
    COMMERCIAL_NON_RENSEIGNE: "Statut non renseigné",
    COMMERCIAL_TRANSMISE: "Offre transmise au client",
    COMMERCIAL_SIGNEE: "Offre signée",
    COMMERCIAL_NON_SIGNEE: "Offre non signée",
}
COMMERCIAL_FINAUX = {COMMERCIAL_SIGNEE, COMMERCIAL_NON_SIGNEE}

# Bouton d'ouverture du dossier dans la file : libellé et couleur suivent l'étape.
BOUTONS_TRAITER = {
    "en_attente": {"label": "Traiter", "couleur": "bleu"},
    "en_cours": {"label": "En cours", "couleur": "orange"},
    "attente_compagnie": {"label": "Attente compagnie", "couleur": "jaune"},
    "relance": {"label": "Relancée", "couleur": "violet"},
    ETAPE_OFFRES_PARTIELLES: {"label": "Transmission partielle", "couleur": "turquoise"},
    "offre_transmise": {"label": "Transmise", "couleur": "vert"},
}
BOUTON_VOIR = {"label": "Voir", "couleur": "gris"}

NON_ATTRIBUE_ID = "non_attribue"
NON_ATTRIBUE_LABEL = "Non attribué"

INDICATEURS = {
    "soumises": "Total des demandes soumises",
    "non_attribuees": "Demandes non attribuées",
    "attribuees": "Demandes attribuées",
    "en_cours_global": "Dossiers en cours de traitement",
    "termines": "Dossiers terminés",
    "en_retard": "Dossiers en retard",
    "offres_recues": "Offres reçues",
    "transmises_client": "Offres transmises au client",
    "attente_decision": "Offres en attente de décision du client",
    "commercial:signee": "Offres signées",
    "commercial:non_signee": "Offres non signées",
    "commercial:non_renseigne": "Statuts commerciaux non renseignés",
    "decision_a_renseigner": "Décision client à renseigner",
    "decision_depassee_14j": "Sans décision 14 jours après la transmission à l'agent",
    "relance_14j_envoyee": "Agents relancés (14 jours)",
    "urgentes": "Urgences agent",
    **{f"traitement:{code}": label for code, label in TRAITEMENT_LABELS.items()},
}

PIPELINE_SECTIONS = [
    {
        "id": "attribution",
        "label": "Attribution",
        "etapes": [
            {"tag": "non_attribuees", "label": "Non attribué"},
            {"tag": "attribuees", "label": "Attribué"},
        ],
    },
    {
        "id": "traitement",
        "label": "Traitement",
        "etapes": [
            {"tag": "traitement:en_attente", "label": "En attente"},
            {"tag": "traitement:en_cours", "label": "En cours"},
            {"tag": "traitement:attente_compagnie", "label": "En attente de compagnie"},
            {"tag": "traitement:relance", "label": "Relance compagnie"},
            {"tag": f"traitement:{ETAPE_OFFRES_PARTIELLES}", "label": "Offres reçues (transmission partielle)"},
            {"tag": "traitement:offre_transmise", "label": "Offres transmises à l'agent"},
        ],
    },
    {
        "id": "commercial",
        "label": "Résultat commercial",
        "etapes": [
            {"tag": "attente_decision", "label": "Transmise au client"},
            {"tag": "commercial:signee", "label": "Signée"},
            {"tag": "commercial:non_signee", "label": "Non signée"},
        ],
    },
]

TAUX_SIGNATURE_DEFINITION = (
    "Offres signées / (offres signées + offres non signées). "
    "Les dossiers sans décision finale ne comptent pas comme des refus."
)


# --------------------------------------------------------------------------- dates

def _parse_iso(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _zurich_date(moment: datetime):
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo("Europe/Zurich")).date()


def _zurich_today(now: Optional[datetime] = None) -> date:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return _zurich_date(moment)


def jours_calendaires_depuis(stamp: Any, now: Optional[datetime] = None) -> Optional[int]:
    """Jours calendaires entre la date (Europe/Zurich) de ``stamp`` et aujourd'hui."""
    start = _parse_iso(stamp)
    if start is None:
        return None
    return max(0, (_zurich_today(now) - _zurich_date(start)).days)


# --------------------------------------------------------------------------- périmètre

def dans_pilotage(doc: dict) -> bool:
    """Demande soumise : ni brouillon, ni supprimée, ni demande annulée."""
    if not isinstance(doc, dict) or doc.get("is_deleted"):
        return False
    if normalize_statut(doc.get("statut")) == STATUT_BROUILLON:
        return False
    return not is_demande_annulee_statut(doc.get("statut"))


# --------------------------------------------------------------------------- traitement

def _derniere_etape_evenement(doc: dict) -> str:
    events = [e for e in (doc.get("suivi_evenements") or []) if isinstance(e, dict)]
    return str(events[-1].get("etape") or "") if events else ""


def traitement_code(doc: dict) -> str:
    """Étape d'avancement du gestionnaire, jamais remplacée par la décision commerciale.

    Mêmes règles que ``etape_affichee`` pour l'étape choisie. Un ancien dossier
    sans étape enregistrée est lu depuis son statut ; s'il est déjà chez le
    client (ou signé / non signé), ses offres ont été transmises à l'agent.
    La relance reste un événement : elle est comptée à part tant que la
    dernière action est une relance en attente de la compagnie.
    """
    if not dans_pilotage(doc):
        return ""
    explicit = str(doc.get("suivi_etape") or "").strip()
    if explicit == "relance":
        explicit = "attente_compagnie"
    if explicit in {"en_attente", "en_cours", "attente_compagnie"}:
        code = explicit
    elif explicit == ETAPE_OFFRES_PARTIELLES or (explicit == "offre_transmise" and doc.get("suivi_auto")):
        code = etape_transmission_cible(doc) or explicit
    elif explicit == "offre_transmise":
        code = explicit
    else:
        legacy = etape_depuis_statut(doc.get("statut"))
        if legacy in TRAITEMENT_CODES:
            code = legacy
        elif count_offres_recues(doc) > 0:
            code = etape_transmission_cible(doc) or "offre_transmise"
        else:
            code = "en_attente"
    if code in {"en_attente", "en_cours", "attente_compagnie"} and commercial_code(doc) != COMMERCIAL_NON_RENSEIGNE:
        return "offre_transmise"
    if code == "attente_compagnie" and _derniere_etape_evenement(doc) == "relance":
        return "relance"
    return code


def rdv_client_date(doc: dict) -> Optional[date]:
    """Date du RDV client affichée : ``date_prochain_rdv``, sinon celle du formulaire."""
    try:
        from offre_form_types import rdv_client_effectif

        raw, _heure = rdv_client_effectif(doc)
    except Exception:
        raw = str((doc or {}).get("date_prochain_rdv") or "")
    try:
        return date.fromisoformat(str(raw or "").strip()[:10])
    except ValueError:
        return None


def en_retard_rdv(doc: dict, now: Optional[datetime] = None) -> bool:
    """« Dossiers en retard » : traitement non terminé et RDV client proche ou passé.

    Non terminé : en attente, en cours, attente compagnie, relance ou
    transmission partielle (tout sauf « Offres transmises à l'agent »).
    RDV proche : au plus ``RDV_RETARD_JOURS`` jours calendaires (Europe/Zurich)
    avant le RDV, ou RDV déjà passé. Sans date de RDV, le dossier n'est pas en retard.
    Le délai de décision commerciale (14 jours) n'intervient pas.
    """
    if traitement_code(doc) not in TRAITEMENT_NON_TERMINE:
        return False
    rdv = rdv_client_date(doc)
    if rdv is None:
        return False
    return (rdv - _zurich_today(now)).days <= RDV_RETARD_JOURS


def bouton_traiter(doc: dict) -> dict:
    code = traitement_code(doc)
    return dict(BOUTONS_TRAITER.get(code) or BOUTON_VOIR, code=code or "")


# --------------------------------------------------------------------------- commercial

def commercial_code(doc: dict) -> str:
    """Décision de l'agent, lue depuis le statut posé par les boutons existants."""
    st = normalize_statut((doc or {}).get("statut"))
    if st == STATUT_OFFRE_SIGNEE:
        return COMMERCIAL_SIGNEE
    if st in {STATUT_OFFRE_NON_SIGNEE, STATUT_OFFRE_REFUSEE}:
        return COMMERCIAL_NON_SIGNEE
    if st in {STATUT_OFFRE_ENVOYEE_CLIENT, STATUT_EN_CONCLUSION}:
        return COMMERCIAL_TRANSMISE
    return COMMERCIAL_NON_RENSEIGNE


def commercial_trace(doc: dict) -> dict:
    """Date et auteur de la dernière décision commerciale enregistrée."""
    code = commercial_code(doc)
    at = by = by_id = None
    refusee = normalize_statut(doc.get("statut")) == STATUT_OFFRE_REFUSEE
    if code == COMMERCIAL_SIGNEE or refusee:
        sig = doc.get("signature") if isinstance(doc.get("signature"), dict) else {}
        at, by, by_id = sig.get("recorded_at"), sig.get("recorded_by"), sig.get("recorded_by_id")
    elif code == COMMERCIAL_NON_SIGNEE:
        block = doc.get("offre_non_signee") if isinstance(doc.get("offre_non_signee"), dict) else {}
        at, by, by_id = block.get("at"), block.get("by"), block.get("by_id")
    elif code == COMMERCIAL_TRANSMISE:
        block = doc.get("envoi_client") if isinstance(doc.get("envoi_client"), dict) else {}
        at, by, by_id = block.get("at"), block.get("by"), block.get("by_id")
    envoi = doc.get("envoi_client") if isinstance(doc.get("envoi_client"), dict) else {}
    return {
        "code": code,
        "label": COMMERCIAL_LABELS[code],
        "at": at,
        "by": by,
        "by_id": by_id,
        "transmise_client_at": envoi.get("at"),
    }


# --------------------------------------------------------------------------- mise à disposition

def _premiere_transmission_at(doc: dict) -> Optional[str]:
    stamps = []
    for offer in (doc or {}).get("offres") or []:
        if not isinstance(offer, dict):
            continue
        for item in offer.get("transmissions") or []:
            if isinstance(item, dict) and item.get("at"):
                stamps.append(str(item["at"]))
        if offer.get("received_at") and (offer.get("documents") or offer.get("document_id")):
            stamps.append(str(offer["received_at"]))
    return min(stamps) if stamps else None


def transmis_agent_at(doc: dict) -> Optional[str]:
    """Premier passage effectif à « Offres transmises à l'agent » (transmission complète).

    Dans l'ordre : ``offres_transmises_agent_at`` (posé à ce passage), le premier
    événement de suivi ``offre_transmise``, puis ``offre_transmise_agent_at`` pour
    un dossier sans transmission partielle (ce champ est aussi posé à la première
    transmission partielle). Une transmission partielle ou la mise à disposition
    d'un premier document ne fait jamais partir le délai.
    """
    doc = doc or {}
    stamp = str(doc.get("offres_transmises_agent_at") or "").strip()
    if stamp:
        return stamp
    events = [e for e in (doc.get("suivi_evenements") or []) if isinstance(e, dict)]
    for event in events:
        if event.get("etape") == "offre_transmise" and str(event.get("at") or "").strip():
            return str(event["at"]).strip()
    partielle = any(event.get("etape") == ETAPE_OFFRES_PARTIELLES for event in events)
    legacy = str(doc.get("offre_transmise_agent_at") or "").strip()
    if legacy and not partielle and count_offres_recues(doc) > 0:
        return legacy
    return None


def relance_depart_at(doc: dict) -> Optional[str]:
    """Départ du délai de 14 jours : passage à « Offres transmises à l'agent »."""
    return transmis_agent_at(doc)


def docs_disponibles_at(doc: dict) -> Optional[str]:
    """Date affichée de première mise à disposition des documents (y compris partielle)."""
    stamp = str((doc or {}).get("docs_mis_a_disposition_at") or "").strip()
    if stamp:
        return stamp
    legacy = str((doc or {}).get("offre_transmise_agent_at") or "").strip()
    if legacy and count_offres_recues(doc) > 0:
        return legacy
    return transmis_agent_at(doc) or _premiere_transmission_at(doc)


def rappel_decision_at(doc: dict) -> Optional[str]:
    return (doc or {}).get("relance_agent_14j_sent_at") or (doc or {}).get("relance_agent_21j_sent_at") or None


def decision_client(doc: dict, now: Optional[datetime] = None) -> dict:
    """Décision client attendue de l'agent.

    ``a_renseigner`` : documents mis à disposition, sans décision finale.
    ``jours`` et ``depasse_14j`` partent du passage à « Offres transmises à
    l'agent », comme le rappel automatique ; sans ce passage, aucun délai ne court.
    """
    code = commercial_code(doc)
    actif = dans_pilotage(doc)
    depuis = docs_disponibles_at(doc) if actif else None
    transmis = transmis_agent_at(doc) if actif else None
    jours = jours_calendaires_depuis(transmis, now) if transmis else None
    a_renseigner = bool(depuis) and code not in COMMERCIAL_FINAUX
    return {
        "docs_transmis_at": depuis,
        "transmis_agent_at": transmis,
        "jours": jours,
        "a_renseigner": a_renseigner,
        "depasse_14j": bool(a_renseigner and jours is not None and jours >= RELANCE_DECISION_JOURS),
        "rappel_envoye_at": rappel_decision_at(doc),
    }


# --------------------------------------------------------------------------- attribution

def gestionnaire_info(doc: dict) -> dict:
    gid = str((doc or {}).get("gestionnaire_id") or "").strip()
    return {
        "id": gid or None,
        "nom": (str(doc.get("gestionnaire_nom") or "").strip() or None) if gid else None,
        "attribue_at": doc.get("gestionnaire_attribue_at") if gid else None,
        "attribue_par": doc.get("gestionnaire_attribue_par") if gid else None,
    }


def est_attribuee(doc: dict) -> bool:
    return bool(gestionnaire_info(doc)["id"])


def non_attribuee_filter() -> dict:
    """Filtre Mongo : aucun gestionnaire enregistré (champ absent, nul ou vide)."""
    return {"$or": [
        {"gestionnaire_id": {"$exists": False}},
        {"gestionnaire_id": None},
        {"gestionnaire_id": ""},
    ]}


def attribution_event(
    *,
    kind: str,
    at: str,
    par_id: str,
    par_nom: str,
    ancien_id: Optional[str],
    ancien_nom: Optional[str],
    nouveau_id: str,
    nouveau_nom: str,
    motif: str = "",
) -> dict:
    return {
        "type": kind,
        "at": at,
        "par_id": par_id,
        "par_nom": par_nom,
        "ancien_id": ancien_id or None,
        "ancien_nom": ancien_nom or None,
        "nouveau_id": nouveau_id,
        "nouveau_nom": nouveau_nom,
        "motif": (motif or "").strip(),
    }


def passe_en_cours_apres_attribution(doc: dict) -> bool:
    """Seule une demande encore « En attente » passe « En cours de traitement »."""
    return traitement_code(doc) == "en_attente"


# --------------------------------------------------------------------------- droits

def peut_reattribuer(user) -> bool:
    """Administrateur (users.manage) ou responsable CEO / Direction."""
    from access_control import PERM_USERS_MANAGE, ROLE_ADMIN, ROLE_CEO, has_perm

    if user is None:
        return False
    return has_perm(user, PERM_USERS_MANAGE) or getattr(user, "role", None) in {ROLE_ADMIN, ROLE_CEO}


def peut_sattribuer(user) -> bool:
    from access_control import can_process_offres

    return bool(user is not None and can_process_offres(user))


def peut_suivre_commercial(user, doc: dict) -> bool:
    """Agent créateur de la demande, ou administrateur habilité."""
    from access_control import PERM_USERS_MANAGE, has_perm
    from demandes_offres_3p import can_follow_signature

    if user is None:
        return False
    return can_follow_signature(user, doc) or has_perm(user, PERM_USERS_MANAGE)


def refus_ecriture_gestion(doc: dict, user) -> Optional[str]:
    """Motif de refus si un gestionnaire agit sur le dossier d'un collègue.

    Un dossier non attribué reste modifiable par tout gestionnaire (anciens
    dossiers). L'agent créateur garde ses propres actions.
    """
    from access_control import can_process_offres
    from demandes_offres_3p import can_follow_signature

    info = gestionnaire_info(doc or {})
    if not info["id"] or user is None:
        return None
    if info["id"] == str(getattr(user, "account_id", "") or ""):
        return None
    if peut_reattribuer(user) or not can_process_offres(user) or can_follow_signature(user, doc):
        return None
    return (
        f"Dossier attribué à {info['nom'] or 'un autre gestionnaire'}. "
        "Seul ce gestionnaire ou un responsable peut le modifier."
    )


# --------------------------------------------------------------------------- indicateurs

def pilotage_tags(doc: dict, now: Optional[datetime] = None) -> list[str]:
    """Indicateurs auxquels appartient la demande. Compteurs et filtres les lisent."""
    if not dans_pilotage(doc):
        return []
    tags = ["soumises", "attribuees" if est_attribuee(doc) else "non_attribuees"]
    traitement = traitement_code(doc)
    tags.append(f"traitement:{traitement}")
    if traitement in TRAITEMENT_EN_COURS_GLOBAL:
        tags.append("en_cours_global")
    elif traitement == "offre_transmise":
        tags.append("termines")
    if en_retard_rdv(doc, now):
        tags.append("en_retard")
    if count_offres_recues(doc) > 0:
        tags.append("offres_recues")
    if doc.get("urgente"):
        tags.append("urgentes")
    commercial = commercial_code(doc)
    decision = decision_client(doc, now)
    if commercial != COMMERCIAL_NON_RENSEIGNE:
        tags.append(f"commercial:{commercial}")
        tags.append("transmises_client")
    elif decision["docs_transmis_at"]:
        tags.append(f"commercial:{COMMERCIAL_NON_RENSEIGNE}")
    if commercial == COMMERCIAL_TRANSMISE:
        tags.append("attente_decision")
    if decision["a_renseigner"]:
        tags.append("decision_a_renseigner")
    if decision["depasse_14j"]:
        tags.append("decision_depassee_14j")
    if rappel_decision_at(doc):
        tags.append("relance_14j_envoyee")
    return tags


def enrich_pilotage_fields(doc: dict, out: dict, *, viewer=None, now: Optional[datetime] = None) -> None:
    """Champs calculés exposés par l'API pour la liste, la fiche et les tableaux de bord."""
    traitement = traitement_code(doc)
    trace = commercial_trace(doc)
    info = gestionnaire_info(doc)
    out["statut_traitement"] = traitement
    out["statut_traitement_label"] = TRAITEMENT_LABELS.get(traitement, "")
    out["statut_commercial"] = trace["code"]
    out["statut_commercial_label"] = trace["label"]
    out["statut_commercial_at"] = trace["at"]
    out["statut_commercial_by"] = trace["by"]
    out["offre_transmise_client_at"] = trace["transmise_client_at"]
    out["gestionnaire_id"] = info["id"]
    out["gestionnaire_nom"] = info["nom"]
    out["gestionnaire_attribue_at"] = info["attribue_at"]
    out["attribution"] = "attribuee" if info["id"] else "non_attribuee"
    out["decision_client"] = decision_client(doc, now)
    out["docs_mis_a_disposition_at"] = out["decision_client"]["docs_transmis_at"]
    out["offres_transmises_agent_at"] = out["decision_client"]["transmis_agent_at"]
    out["en_retard_rdv"] = en_retard_rdv(doc, now)
    out["relance_agent_14j_sent_at"] = doc.get("relance_agent_14j_sent_at") or None
    out["bouton_traiter"] = bouton_traiter(doc)
    out["pilotage_tags"] = pilotage_tags(doc, now)
    out["can_attribuer"] = bool(
        viewer is not None and dans_pilotage(doc) and not info["id"] and peut_sattribuer(viewer)
    )
    out["can_reattribuer"] = bool(viewer is not None and dans_pilotage(doc) and peut_reattribuer(viewer))
    out["can_suivi_commercial"] = bool(viewer is not None and peut_suivre_commercial(viewer, doc))
    from access_control import can_process_offres

    if viewer is not None and (can_process_offres(viewer) or peut_reattribuer(viewer)):
        out["attributions_historique"] = list(doc.get("attributions_historique") or [])
    else:
        out["attributions_historique"] = []


def _gestionnaire_bucket(gid: str, nom: str) -> dict:
    return {
        "id": gid,
        "nom": nom,
        "attribues": 0,
        "en_cours": 0,
        "attente_compagnie": 0,
        "transmis_agent": 0,
        "signes": 0,
        "non_signes": 0,
        "en_retard": 0,
    }


def repartition_gestionnaires(
    rows: Iterable[dict],
    gestionnaires: Optional[Iterable[dict]] = None,
    *,
    now: Optional[datetime] = None,
) -> list[dict]:
    """Une ligne par gestionnaire habilité, plus « Non attribué ».

    « Attribués » est le stock actuel. Les autres colonnes décrivent le statut
    ou le résultat de ces dossiers : elles ne s'additionnent pas entre elles.
    « En attente compagnie » inclut les dossiers relancés.
    """
    buckets: dict[str, dict] = {}
    for item in gestionnaires or []:
        gid = str(item.get("id") or "").strip()
        if gid:
            buckets[gid] = _gestionnaire_bucket(gid, str(item.get("nom") or gid))
    unassigned = _gestionnaire_bucket(NON_ATTRIBUE_ID, NON_ATTRIBUE_LABEL)
    for row in rows or []:
        tags = set(pilotage_tags(row, now))
        if "soumises" not in tags:
            continue
        info = gestionnaire_info(row)
        if info["id"]:
            bucket = buckets.get(info["id"])
            if bucket is None:
                bucket = buckets[info["id"]] = _gestionnaire_bucket(info["id"], info["nom"] or info["id"])
        else:
            bucket = unassigned
        bucket["attribues"] += 1
        if "traitement:en_cours" in tags:
            bucket["en_cours"] += 1
        if "traitement:attente_compagnie" in tags or "traitement:relance" in tags:
            bucket["attente_compagnie"] += 1
        if "traitement:offre_transmise" in tags:
            bucket["transmis_agent"] += 1
        if "commercial:signee" in tags:
            bucket["signes"] += 1
        if "commercial:non_signee" in tags:
            bucket["non_signes"] += 1
        if "en_retard" in tags:
            bucket["en_retard"] += 1
    out = sorted(buckets.values(), key=lambda b: (-b["attribues"], str(b["nom"]).casefold()))
    out.append(unassigned)
    return out


def ligne_decision(doc: dict, now: Optional[datetime] = None) -> dict:
    decision = decision_client(doc, now)
    prenom = str(doc.get("prenom") or "").strip()
    nom = str(doc.get("nom") or "").strip()
    return {
        "id": doc.get("id"),
        "numero": doc.get("numero"),
        "client": f"{prenom} {nom}".strip() or str(doc.get("client_label") or "").strip() or "—",
        "agent": doc.get("agent_label") or "—",
        "gestionnaire": gestionnaire_info(doc)["nom"],
        "docs_transmis_at": decision["docs_transmis_at"],
        "transmis_agent_at": decision["transmis_agent_at"],
        "jours": decision["jours"],
        "statut_commercial": commercial_code(doc),
        "statut_commercial_label": COMMERCIAL_LABELS[commercial_code(doc)],
        "rappel_envoye_at": decision["rappel_envoye_at"],
        "depasse_14j": decision["depasse_14j"],
    }


def compute_pilotage(
    rows: Iterable[dict],
    *,
    gestionnaires: Optional[Iterable[dict]] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Indicateurs du service ou d'un gestionnaire, selon le lot reçu."""
    rows = [r for r in rows or [] if isinstance(r, dict)]
    counts: Counter = Counter()
    decisions = []
    for row in rows:
        tags = pilotage_tags(row, now)
        counts.update(tags)
        if "decision_a_renseigner" in tags:
            decisions.append(ligne_decision(row, now))
    decisions.sort(key=lambda d: (-(d["jours"] or 0), str(d["numero"] or "")))
    signees = counts["commercial:signee"]
    non_signees = counts["commercial:non_signee"]
    decided = signees + non_signees
    indicateurs = {key: int(counts.get(key, 0)) for key in INDICATEURS}
    return {
        "indicateurs": indicateurs,
        "labels": dict(INDICATEURS),
        "traitement": [
            {"code": code, "tag": f"traitement:{code}", "label": label, "count": indicateurs[f"traitement:{code}"]}
            for code, label in TRAITEMENT_LABELS.items()
        ],
        "taux_signature": round(signees / decided * 100, 1) if decided else None,
        "taux_signature_definition": TAUX_SIGNATURE_DEFINITION,
        "pipeline": [
            {
                "id": section["id"],
                "label": section["label"],
                "etapes": [
                    {**step, "count": indicateurs.get(step["tag"], 0)} for step in section["etapes"]
                ],
            }
            for section in PIPELINE_SECTIONS
        ],
        "gestionnaires": repartition_gestionnaires(rows, gestionnaires, now=now),
        "decisions_a_renseigner": decisions,
        "delai_decision_jours": RELANCE_DECISION_JOURS,
    }


def filtrer_lignes(
    rows: Iterable[dict],
    *,
    tag: Optional[str] = None,
    statut_traitement: Optional[str] = None,
    statut_commercial: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[dict]:
    """Filtres calculés (non stockés) de la liste des demandes."""
    want_tag = (tag or "").strip()
    want_t = (statut_traitement or "").strip()
    want_c = (statut_commercial or "").strip()
    if want_t in {"", "all"} and want_c in {"", "all"} and want_tag in {"", "all"}:
        return list(rows or [])
    out = []
    for row in rows or []:
        if want_tag not in {"", "all"} and want_tag not in pilotage_tags(row, now):
            continue
        if want_t not in {"", "all"} and traitement_code(row) != want_t:
            continue
        if want_c not in {"", "all"} and (not dans_pilotage(row) or commercial_code(row) != want_c):
            continue
        out.append(row)
    return out
