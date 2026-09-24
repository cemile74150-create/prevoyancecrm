"""Module Demandes d'offres 3e pilier — collection Mongo dédiée."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Tuple

COLLECTION = "demandes_offres_3p"
COLLECTION_DOCS = "demandes_offres_3p_documents"
COLLECTION_COUNTERS = "demandes_offres_3p_counters"
COLLECTION_ERREURS = "demande_offre_erreurs"


def _offres_email_to() -> str:
    from email_service import offres_email_to

    return offres_email_to()


def _offres_email_enabled() -> bool:
    from email_service import offres_email_enabled

    return offres_email_enabled()


STATUT_BROUILLON = "Brouillon"
STATUT_VALIDEE = "Demande validée"
STATUT_ENVOYEE = "Demande envoyée"
STATUT_INCOMPLETE = "Demande incomplète"
STATUT_ATTENTE_INFOS = "En attente d'informations"
STATUT_OFFRE_RECUE = "Offre reçue"
STATUT_OFFRE_COMPLETE = "Offres complètes"
# Ancien libellé (singulier) — normalisé vers STATUT_OFFRE_COMPLETE
STATUT_OFFRE_COMPLETE_LEGACY = "Offre complète"
STATUT_OFFRE_CHOISIE = "Offre choisie"
STATUT_EN_CONCLUSION = "En conclusion"
STATUT_OFFRE_ENVOYEE_CLIENT = "Offre envoyée au client"
STATUT_OFFRE_A_MODIFIER = "Offre à modifier"
STATUT_OFFRE_MODIFIEE = "Offre modifiée"
STATUT_OFFRE_SIGNEE = "Offre signée"
STATUT_OFFRE_REFUSEE = "Offre refusée"
STATUT_ANNULEE = "Demande annulée"

# Champ persisté à l'annulation (historique / audit) ; la restauration
# remet toujours en brouillon (choix produit : éviter de ré-envoyer).
FIELD_STATUT_AVANT_ANNULATION = "statut_avant_annulation"
# Statut cible de toute restauration d'une demande annulée.
DEFAULT_RESTORE_STATUT = STATUT_BROUILLON

STATUTS = [
    STATUT_BROUILLON,
    STATUT_VALIDEE,
    STATUT_ENVOYEE,
    STATUT_INCOMPLETE,
    STATUT_ATTENTE_INFOS,
    STATUT_OFFRE_RECUE,
    STATUT_OFFRE_COMPLETE,
    STATUT_OFFRE_CHOISIE,
    STATUT_EN_CONCLUSION,
    STATUT_OFFRE_ENVOYEE_CLIENT,
    STATUT_OFFRE_A_MODIFIER,
    STATUT_OFFRE_MODIFIEE,
    STATUT_OFFRE_SIGNEE,
    STATUT_OFFRE_REFUSEE,
    STATUT_ANNULEE,
]

DEMANDE_ORIGINE_CONSEILLER = "conseiller"
DEMANDE_ORIGINE_ATTRIBUEE = "attribuee"
DEMANDE_ORIGINES = [DEMANDE_ORIGINE_CONSEILLER, DEMANDE_ORIGINE_ATTRIBUEE]

TYPE_CLIENT_EXISTANT = "existant"
TYPE_CLIENT_NOUVEAU = "nouveau"
TYPES_CLIENT = [TYPE_CLIENT_EXISTANT, TYPE_CLIENT_NOUVEAU]

ERREURS_INCOMPLETE_CATALOG = [
    {"code": "document_manquant", "label": "Document manquant"},
    {"code": "info_client_manquante", "label": "Information client manquante"},
    {"code": "signature_manquante", "label": "Signature manquante"},
    {"code": "champ_vide", "label": "Champ non rempli"},
    {"code": "mauvaise_info", "label": "Mauvaise information"},
    {"code": "mauvais_formulaire", "label": "Mauvais formulaire"},
    {"code": "autre", "label": "Autre"},
]
ERREURS_INCOMPLETE_CODES = {e["code"] for e in ERREURS_INCOMPLETE_CATALOG}

# Catalogue stable des champs / catégories d'erreurs agent (bouton « Erreurs »).
# Évolutif : ajouter des entrées ici sans migration.
ERREURS_CHAMPS_CATALOG = [
    {"code": "nom_prenom", "label": "Nom / prénom"},
    {"code": "date_naissance", "label": "Date de naissance"},
    {"code": "adresse", "label": "Adresse"},
    {"code": "salaire", "label": "Salaire"},
    {"code": "taux_activite", "label": "Taux d'activité"},
    {"code": "vehicule", "label": "Véhicule"},
    {"code": "date_effet", "label": "Date d'effet"},
    {"code": "type_assurance", "label": "Type d'assurance"},
    {"code": "informations_client", "label": "Informations client"},
    {"code": "profession", "label": "Profession"},
    {"code": "montant_prime", "label": "Montant / prime"},
    {"code": "compagnie", "label": "Compagnie"},
    {"code": "documents", "label": "Documents joints"},
    {"code": "autre", "label": "Autre"},
]
ERREURS_CHAMPS_CODES = {e["code"] for e in ERREURS_CHAMPS_CATALOG}
ERREUR_TYPE_DEFAUT = "Erreur"


def erreurs_champs_label(code: str) -> str:
    for item in ERREURS_CHAMPS_CATALOG:
        if item["code"] == code:
            return item["label"]
    return (code or "—").replace("_", " ").capitalize()


def build_erreurs_checklist(doc: Optional[dict] = None) -> list:
    """
    Checklist pour le formulaire Erreurs : catalogue stable + champs du schéma formulaire.
    Les codes catalogue sont prioritaires ; les champs schéma viennent en complément.
    """
    seen = set()
    out: list = []
    for item in ERREURS_CHAMPS_CATALOG:
        code = item["code"]
        if code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "label": item["label"], "source": "catalog"})

    form_type = (doc or {}).get("form_type") or ""
    if form_type and form_type != "pilier3_legacy":
        try:
            from offre_form_types import load_form_schema

            schema = load_form_schema(form_type) or {}
            for field in schema.get("fields") or []:
                if not isinstance(field, dict):
                    continue
                ftype = (field.get("type") or "").strip().lower()
                if ftype in {"section", "html", "hidden", "page"}:
                    continue
                name = (field.get("name") or field.get("id") or "").strip()
                label = (field.get("label") or name or "").strip()
                if not name or not label:
                    continue
                # Normaliser en code stable (évite collisions avec le catalogue)
                code = f"schema:{name}"
                if code in seen or name in ERREURS_CHAMPS_CODES:
                    continue
                seen.add(code)
                out.append({"code": code, "label": label, "source": "schema"})
        except Exception:
            pass
    return out


def normalize_erreurs_agent_fields(raw: Any) -> list:
    """Normalise la sélection multi-champs du bouton Erreurs."""
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for item in raw:
        if isinstance(item, str):
            code = item.strip()
            label = None
        elif isinstance(item, dict):
            code = (item.get("code") or item.get("field") or "").strip()
            label = (item.get("label") or item.get("field_label") or "").strip() or None
        else:
            continue
        if not code or code in seen:
            continue
        seen.add(code)
        if code.startswith("schema:"):
            field_label = label or code.split(":", 1)[-1].replace("_", " ").capitalize()
        elif code in ERREURS_CHAMPS_CODES:
            field_label = label or erreurs_champs_label(code)
        else:
            # Accepte codes catalogue futurs / libres
            field_label = label or erreurs_champs_label(code)
        out.append({"code": code, "label": field_label})
    return out


def build_erreur_agent_records(
    doc: dict,
    fields: list,
    *,
    by_user,
    error_type: str = ERREUR_TYPE_DEFAUT,
    comment: Optional[str] = None,
) -> list:
    """Construit les enregistrements d'erreurs rattachés à l'agent créateur."""
    at = now_iso()
    client = (
        f"{(doc.get('prenom') or '').strip()} {(doc.get('nom') or '').strip()}".strip()
        or (doc.get("client_label") or "").strip()
        or "—"
    )
    agent_id = (
        doc.get("created_by_account_id")
        or doc.get("agent_account_id")
        or None
    )
    agent_label = (doc.get("agent_label") or doc.get("created_by_name") or "").strip() or "—"
    by_name = ""
    by_id = None
    if by_user is not None:
        by_name = (
            getattr(by_user, "name", None)
            or f"{getattr(by_user, 'prenom', '')} {getattr(by_user, 'nom', '')}".strip()
            or getattr(by_user, "email", "")
            or ""
        )
        by_id = getattr(by_user, "account_id", None)
    records = []
    for field in fields:
        code = field.get("code")
        label = field.get("label") or erreurs_champs_label(code)
        records.append({
            "id": str(uuid.uuid4()),
            "at": at,
            "date": at[:10],
            "client": client,
            "error_type": (error_type or ERREUR_TYPE_DEFAUT).strip() or ERREUR_TYPE_DEFAUT,
            "field": code,
            "field_label": label,
            "agent_id": agent_id,
            "agent_label": agent_label,
            "demande_id": doc.get("id"),
            "demande_numero": doc.get("numero"),
            "comment": (comment or "").strip() or None,
            "by_id": by_id,
            "by_name": by_name,
        })
    return records


def compute_erreurs_agent_stats(records: list) -> dict:
    """
    Agrège les erreurs champ par agent.
    Retourne total + répartition par champ, plus détail tabulaire.
    """
    from conseiller_identity import display_conseiller_name, merge_conseiller_display, normalize_conseiller_key

    by_agent: dict = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        raw_label = (rec.get("agent_label") or "").strip() or "Non attribué"
        key = normalize_conseiller_key(raw_label) or (rec.get("agent_id") or "unknown")
        if key not in by_agent:
            by_agent[key] = {
                "agent": display_conseiller_name(raw_label),
                "agent_id": rec.get("agent_id"),
                "total": 0,
                "by_field": {},
                "items": [],
            }
        else:
            by_agent[key]["agent"] = merge_conseiller_display(by_agent[key]["agent"], raw_label)
            if not by_agent[key].get("agent_id") and rec.get("agent_id"):
                by_agent[key]["agent_id"] = rec.get("agent_id")
        field_code = rec.get("field") or "autre"
        field_label = rec.get("field_label") or erreurs_champs_label(field_code)
        by_agent[key]["total"] += 1
        bucket = by_agent[key]["by_field"].setdefault(
            field_code, {"code": field_code, "label": field_label, "count": 0}
        )
        bucket["count"] += 1
        by_agent[key]["items"].append(rec)

    out = []
    for a in by_agent.values():
        fields = sorted(a["by_field"].values(), key=lambda x: (-x["count"], x["label"].casefold()))
        out.append({
            "agent": a["agent"],
            "agent_id": a.get("agent_id"),
            "total": a["total"],
            "by_field": fields,
            "items": a["items"],
        })
    out.sort(key=lambda x: (-x["total"], x["agent"].casefold()))
    return {"by_agent": out, "total": sum(a["total"] for a in out)}


def can_follow_signature(user, doc: dict) -> bool:
    """
    Suivi Offre signée / non signée : réservé à l'agent créateur (ou conseiller de la demande).
    Les gestionnaires purs (sans lien agent) ne doivent pas actionner ces boutons.
    """
    from access_control import (
        email_matches_conseiller,
        labels_match_conseiller,
    )

    account_id = getattr(user, "account_id", None)
    if account_id and doc.get("created_by_account_id") == account_id:
        return True
    if labels_match_conseiller(doc.get("agent_label"), user):
        return True
    if email_matches_conseiller(doc, user):
        return True
    return False

# Pipeline clair (onglet Pipeline) — du brouillon à la signature
KANBAN_COLUMNS = [
    STATUT_BROUILLON,
    STATUT_ENVOYEE,
    STATUT_ATTENTE_INFOS,
    STATUT_INCOMPLETE,
    STATUT_OFFRE_RECUE,
    STATUT_OFFRE_COMPLETE,
    STATUT_OFFRE_A_MODIFIER,
    STATUT_OFFRE_MODIFIEE,
    STATUT_OFFRE_CHOISIE,
    STATUT_EN_CONCLUSION,
    STATUT_OFFRE_ENVOYEE_CLIENT,
    STATUT_OFFRE_SIGNEE,
]

# Délais métier déjà communiqués aux conseillers (délai min. compagnies = 5 jours)
OFFRES_DELAI_SURVEILLER_JOURS = 5
OFFRES_DELAI_URGENT_JOURS = 10  # 2 × délai minimum documenté

# Catégories d'affichage gestionnaire (pas de nouveaux statuts DB)
GESTION_CATEGORIES = {
    "a_traiter": {
        "label": "À traiter",
        "statuts": [STATUT_ENVOYEE, STATUT_VALIDEE, STATUT_OFFRE_RECUE],
    },
    "attribuees": {
        "label": "Demandes attribuées",
        "statuts": None,  # filtre via demande_origine
    },
    "envoyees": {
        "label": "Envoyées",
        "statuts": [STATUT_ENVOYEE, STATUT_VALIDEE],
    },
    "en_attente": {
        "label": "En attente",
        "statuts": [STATUT_ENVOYEE, STATUT_VALIDEE, STATUT_ATTENTE_INFOS],
    },
    "incompletes": {
        "label": "Incomplètes",
        "statuts": [STATUT_INCOMPLETE],
    },
    "offres_recues": {
        "label": "Offres reçues",
        "statuts": [STATUT_OFFRE_RECUE],
    },
    "a_modifier": {
        "label": "Offres à modifier",
        "statuts": [STATUT_OFFRE_A_MODIFIER],
    },
    "modifiees": {
        "label": "Offres modifiées",
        "statuts": [STATUT_OFFRE_MODIFIEE],
    },
    "completes": {
        "label": "Complètes",
        "statuts": [STATUT_OFFRE_COMPLETE, STATUT_OFFRE_CHOISIE, STATUT_EN_CONCLUSION],
    },
    "attente_signature": {
        "label": "En attente de signature",
        "statuts": [STATUT_OFFRE_ENVOYEE_CLIENT, STATUT_EN_CONCLUSION],
    },
    "signees": {
        "label": "Signées",
        "statuts": [STATUT_OFFRE_SIGNEE],
    },
}

# Colonnes Kanban gestionnaire — 1 statut → 1 colonne (pas de doublon)
GESTION_KANBAN_COLUMNS = [
    {"id": "a_traiter", "label": "À traiter", "statuts": [STATUT_ENVOYEE, STATUT_VALIDEE]},
    {"id": "en_attente", "label": "En attente", "statuts": [STATUT_ATTENTE_INFOS]},
    {"id": "incompletes", "label": "Incomplètes", "statuts": [STATUT_INCOMPLETE]},
    {"id": "offres_recues", "label": "Offres reçues", "statuts": [STATUT_OFFRE_RECUE]},
    {"id": "a_modifier", "label": "À modifier", "statuts": [STATUT_OFFRE_A_MODIFIER]},
    {"id": "modifiees", "label": "Modifiées", "statuts": [STATUT_OFFRE_MODIFIEE]},
    {"id": "completes", "label": "Complètes", "statuts": [STATUT_OFFRE_COMPLETE, STATUT_OFFRE_CHOISIE, STATUT_EN_CONCLUSION]},
    {"id": "envoyee_client", "label": "Chez le client", "statuts": [STATUT_OFFRE_ENVOYEE_CLIENT]},
    {"id": "signees", "label": "Signées", "statuts": [STATUT_OFFRE_SIGNEE]},
]

# Statuts encore « ouverts » pour le calcul d'urgence / retard
STATUTS_OUVERTS_GESTION = {
    STATUT_ENVOYEE,
    STATUT_VALIDEE,
    STATUT_ATTENTE_INFOS,
    STATUT_INCOMPLETE,
    STATUT_OFFRE_RECUE,
}

CIVILITES = ["Monsieur", "Madame"]
SEXES = ["Homme", "Femme"]
STATUTS_PRO = ["Salarié", "Indépendant", "Pas d'activité lucrative"]
SITUATIONS = ["Célibataire", "Marié(e)", "Veuf/Veuve"]
TYPES_PILIER = ["Pilier lié 3a", "Pilier libre 3b"]
PERIODICITES = ["Mensuel", "Trimestriel", "Semestriel", "Annuel", "Prime unique"]
TYPES_PAIEMENT = [
    "BVR",
    "Débit direct",
    "LSV",
    "Compte de dépôt de prime fermé",
    "Compte de dépôt de prime ouvert",
    "Prime unique",
]
EXONERATIONS = ["Aucun", "3 mois", "6 mois", "12 mois", "24 mois"]
LANGUES = ["Français", "Allemand", "Italien", "Anglais"]

ACTIVITES_RISQUE = [
    "Alpinisme / Escalade",
    "Aviation",
    "Canyonning",
    "Deltaplane / Parapente",
    "Équitation",
    "Kitesurf",
    "Parachutisme",
    "Plongée subaquatique sportive",
    "Ski / Snowboarding",
    "Spéléologie",
    "Sport de combat",
    "Sports mécaniques",
    "Voile",
    "Vol à voile",
]

COMPAGNIES_DEFAUT = [
    "PAX",
    "Helvetia",
    "Swiss Life",
    "AXA",
    "Zurich",
    "Generali",
    "Baloise",
    "Allianz",
    "Vaudoise",
    "Mobilière",
    "Groupe Mutuel",
    "Retraites Populaires",
    "Swica",
    "CSS",
    "Smile Direct",
]

REQUIRED_FOR_VALIDATE = [
    ("agent_prenom", "Prénom de l'agent"),
    ("agent_nom", "Nom de l'agent"),
    ("agent_email", "E-mail de l'agent"),
    ("civilite", "Civilité"),
    ("prenom", "Prénom du preneur"),
    ("nom", "Nom du preneur"),
    ("date_naissance", "Date de naissance"),
    ("adresse", "Adresse"),
    ("ville", "Ville"),
    ("npa", "Code postal"),
    ("pays", "Pays"),
    ("statut_professionnel", "Statut professionnel"),
    ("type_pilier", "Type de pilier"),
    ("periodicite_prime", "Périodicité de la prime"),
    ("montant_prime", "Montant de la prime"),
    ("langue_offre", "Langue souhaitée"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_statut(value: Any) -> str:
    s = str(value or "").strip()
    if s == STATUT_OFFRE_COMPLETE_LEGACY:
        return STATUT_OFFRE_COMPLETE
    return s if s in STATUTS else STATUT_BROUILLON


def parse_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("'", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


# Colonnes CRM propres au wizard legacy 3P — jamais préremplies / affichées hors pilier3_legacy
LEGACY_3P_CRM_KEYS: tuple[str, ...] = (
    "statut_professionnel",
    "profession",
    "travail_bureau_80",
    "affilie_lpp",
    "fumeur",
    "situation",
    "activites_risque",
    "activites_risque_liste",
    "type_pilier",
    "date_debut",
    "periodicite_prime",
    "montant_prime",
    "deja_piliers_pax",
    "type_paiement",
    "duree_contrat",
    "age_terme",
    "exoneration_primes",
    "rente_invalidite",
    "diplome",
    "adaptation_auto_primes",
    "risque_pur",
    "taille",
    "poids",
    "renseignements_complementaires",
    "inclure_cga",
    "date_prochain_rdv",
    "mandat_gestion",
)


def clear_legacy_3p_crm_fields(target: dict) -> None:
    """Efface les colonnes 3P legacy pour éviter qu'elles polluent un autre form_type."""
    for key in LEGACY_3P_CRM_KEYS:
        if key == "activites_risque":
            target[key] = False
        elif key == "activites_risque_liste":
            target[key] = []
        elif key in ("inclure_cga", "mandat_gestion"):
            target[key] = False
        elif key == "montant_prime":
            target[key] = None
        else:
            target[key] = ""


def empty_form_defaults(user=None, *, form_type: Optional[str] = None) -> dict:
    """
    Defaults agent / identité pour une nouvelle demande.
    Les defaults 3P (type_pilier, périodicité, exonération…) uniquement pour pilier3_legacy.
    """
    prenom = (getattr(user, "prenom", None) or "").strip()
    nom = (getattr(user, "nom", None) or "").strip()
    name = (getattr(user, "name", None) or "").strip()
    if not prenom and not nom and name:
        parts = name.split(None, 1)
        prenom = parts[0] if parts else ""
        nom = parts[1] if len(parts) > 1 else ""
    agent_finma = (getattr(user, "finma_number", None) or "").strip()
    form_type_id = (form_type or "pilier3_legacy").strip() or "pilier3_legacy"
    is_legacy = form_type_id == "pilier3_legacy"
    base = {
        "agent_prenom": prenom,
        "agent_nom": nom,
        "agent_email": (getattr(user, "email", None) or "").strip(),
        "agent_finma": agent_finma,
        "civilite": "",
        "nom": "",
        "prenom": "",
        "sexe": "",
        "date_naissance": "",
        "nationalite": "Suisse" if is_legacy else "",
        "permis": "",
        "adresse": "",
        "ville": "",
        "npa": "",
        "pays": "Suisse" if is_legacy else "",
        "statut_professionnel": "",
        "profession": "",
        "travail_bureau_80": "",
        "affilie_lpp": "",
        "fumeur": "",
        "situation": "",
        "activites_risque": False,
        "activites_risque_liste": [],
        "type_pilier": "Pilier lié 3a" if is_legacy else "",
        "date_debut": "",
        "periodicite_prime": "Mensuel" if is_legacy else "",
        "montant_prime": None,
        "deja_piliers_pax": "",
        "type_paiement": "",
        "duree_contrat": "",
        "age_terme": "",
        "exoneration_primes": "Aucun" if is_legacy else "",
        "rente_invalidite": "",
        "diplome": "",
        "adaptation_auto_primes": "",
        "risque_pur": "",
        "taille": "",
        "poids": "",
        "renseignements_complementaires": "",
        "compagnies": [],
        "commentaires": "",
        "inclure_cga": False,
        "date_prochain_rdv": "",
        "langue_offre": "Français",
        "mandat_gestion": False,
    }
    if not is_legacy:
        clear_legacy_3p_crm_fields(base)
        base["langue_offre"] = "Français"
    return base


def missing_required(doc: dict) -> list:
    form_type = (doc.get("form_type") or "pilier3_legacy").strip()
    missing: list = []
    if form_type and form_type != "pilier3_legacy":
        try:
            from offre_form_types import missing_schema_required

            missing = list(missing_schema_required(form_type, doc.get("form_payload") or {}))
        except Exception:
            missing = []
    else:
        for key, label in REQUIRED_FOR_VALIDATE:
            val = doc.get(key)
            if key == "montant_prime":
                if parse_float(val) is None:
                    missing.append(label)
                continue
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(label)
        if not (doc.get("compagnies") or []):
            missing.append("Au moins une compagnie")
        if doc.get("activites_risque") and not (doc.get("activites_risque_liste") or []):
            missing.append("Activités à risque (sélection)")

    # FINMA profil obligatoire pour envoyer une offre (tous types)
    try:
        from offre_agent_identity import missing_agent_finma_message

        finma_msg = missing_agent_finma_message(doc)
        if finma_msg and finma_msg not in missing:
            missing.append(finma_msg)
    except Exception:
        pass
    return missing


def history_entry(
    action: str,
    *,
    by_name: str = "",
    by_id: str = "",
    detail: str = "",
    statut: Optional[str] = None,
    document_id: Optional[str] = None,
    email_log_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> dict:
    entry = {
        "id": str(uuid.uuid4()),
        "at": now_iso(),
        "action": action,
        "detail": detail or None,
        "by_name": by_name or None,
        "by_id": by_id or None,
    }
    if statut:
        entry["statut"] = statut
    if document_id:
        entry["document_id"] = document_id
    if email_log_id:
        entry["email_log_id"] = email_log_id
    if meta:
        entry["meta"] = meta
    return entry


# --- Historique demandes d'offre (événements métier uniquement) ---
ACTION_CREEE = "Demande créée"
ACTION_VALIDEE = "Demande validée"
ACTION_ENVOYEE = "Demande envoyée"
ACTION_RENVOYEE = "Demande renvoyée"
ACTION_MODIFIEE = "Demande modifiée"
ACTION_ANNULEE = "Demande annulée"
ACTION_RESTAUREE = "Demande restaurée"
# Ancien libellé conservé pour lecture / collapse
ACTION_COMPLETEE_RENVOYEE_LEGACY = "Demande complétée et renvoyée"


def resolve_statut_avant_annulation(doc: Optional[dict] = None) -> str:
    """
    Statut à rétablir lors d'une restauration.

    Choix produit : toujours « Brouillon », y compris pour les anciennes
    annulations et même si ``statut_avant_annulation`` était « Demande envoyée ».
    Le paramètre ``doc`` est conservé pour compatibilité d'appel.
    """
    _ = doc  # historique / statut_avant_annulation : info seule, pas de reprise
    return DEFAULT_RESTORE_STATUT

DETAIL_EMAIL_ENVOYE = "E-mail envoyé"

# Après ces jalons, une seule « Demande modifiée » peut apparaître jusqu'au prochain jalon.
HISTORIQUE_MILESTONE_ACTIONS = frozenset({
    ACTION_VALIDEE,
    ACTION_ENVOYEE,
    ACTION_RENVOYEE,
    ACTION_COMPLETEE_RENVOYEE_LEGACY,
})

HISTORIQUE_ENVOI_ACTIONS = frozenset({
    ACTION_ENVOYEE,
    ACTION_RENVOYEE,
    ACTION_COMPLETEE_RENVOYEE_LEGACY,
})


def collapse_demande_historique(hist: Any) -> list:
    """
    Nettoie un historique bruyant : au plus une « Demande modifiée » entre deux jalons
    (validée / envoyée / renvoyée). Conserve la plus récente (at / auteur).
    """
    if not isinstance(hist, list) or not hist:
        return []
    out: list = []
    mod_slot: Optional[int] = None
    for raw in hist:
        entry = raw if isinstance(raw, dict) else None
        if entry is None:
            continue
        action = str(entry.get("action") or "").strip()
        if action == ACTION_MODIFIEE:
            if mod_slot is not None:
                # Remplace la précédente dans la même fenêtre (même id si possible)
                prev = out[mod_slot] if 0 <= mod_slot < len(out) else {}
                merged = dict(entry)
                if prev.get("id") and not merged.get("id"):
                    merged["id"] = prev["id"]
                elif prev.get("id"):
                    merged["id"] = prev["id"]
                out[mod_slot] = merged
            else:
                mod_slot = len(out)
                out.append(dict(entry))
            continue
        if action in HISTORIQUE_MILESTONE_ACTIONS:
            mod_slot = None
        out.append(dict(entry))
    return out


def should_track_demande_modification(doc: dict) -> bool:
    """Pas d'événement « modifiée » tant que la demande est encore un brouillon."""
    statut = (doc.get("statut") or "").strip()
    if statut == STATUT_BROUILLON or not statut:
        return False
    return True


def demande_was_already_sent(doc: dict) -> bool:
    """True si un envoi (ou renvoi) a déjà eu lieu."""
    if doc.get("date_envoi"):
        return True
    for entry in list(doc.get("historique") or []):
        if str((entry or {}).get("action") or "").strip() in HISTORIQUE_ENVOI_ACTIONS:
            return True
    return False


def apply_modification_to_historique(hist: Any, entry: dict) -> list:
    """
    Ajoute ou rafraîchit une seule « Demande modifiée » depuis le dernier jalon.
    Ne crée pas de ligne supplémentaire si une modification existe déjà dans la fenêtre.
    """
    base = collapse_demande_historique(hist)
    mod_slot: Optional[int] = None
    for i in range(len(base) - 1, -1, -1):
        action = str((base[i] or {}).get("action") or "").strip()
        if action in HISTORIQUE_MILESTONE_ACTIONS:
            break
        if action == ACTION_MODIFIEE and mod_slot is None:
            mod_slot = i
    if mod_slot is not None:
        prev = dict(base[mod_slot])
        updated = dict(entry)
        updated["id"] = prev.get("id") or updated.get("id") or str(uuid.uuid4())
        # Conserver un éventuel détail précédent si le nouvel entry n'en a pas
        if not updated.get("detail") and prev.get("detail"):
            updated["detail"] = prev.get("detail")
        base[mod_slot] = updated
        return base
    return base + [dict(entry)]


def normalize_demande_origine(value: Any) -> str:
    v = (str(value or "").strip().lower())
    if v in {"attribuee", "attribuée", "assigned", "service"}:
        return DEMANDE_ORIGINE_ATTRIBUEE
    return DEMANDE_ORIGINE_CONSEILLER


def normalize_type_client(value: Any, *, client_id: Optional[str] = None) -> Optional[str]:
    v = (str(value or "").strip().lower())
    if v in {"existant", "existing", "client_existant"}:
        return TYPE_CLIENT_EXISTANT
    if v in {"nouveau", "new", "nouveau_client"}:
        return TYPE_CLIENT_NOUVEAU
    if client_id:
        return TYPE_CLIENT_EXISTANT
    return None


def normalize_erreurs_incomplete(raw: Any) -> list:
    """Normalise la liste d'erreurs structurées pour une offre incomplète."""
    if not isinstance(raw, list):
        return []
    labels = {e["code"]: e["label"] for e in ERREURS_INCOMPLETE_CATALOG}
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = (item.get("code") or "autre").strip()
        if code not in ERREURS_INCOMPLETE_CODES:
            code = "autre"
        detail = (item.get("detail") or "").strip()
        out.append({
            "id": item.get("id") or str(uuid.uuid4()),
            "code": code,
            "label": item.get("label") or labels.get(code) or code,
            "detail": detail or None,
            "at": item.get("at") or now_iso(),
            "by_name": item.get("by_name"),
            "by_id": item.get("by_id"),
        })
    return out


def build_field_changes(original: dict, current: dict, fields: Optional[list] = None) -> list:
    """Compare deux dicts et retourne la liste des champs modifiés."""
    keys = fields or sorted(set(list(original.keys()) + list(current.keys())))
    skip = {
        "id", "numero", "historique", "notes_internes", "documents", "offres", "offre",
        "updated_at", "created_at", "email_subject", "modifications", "snapshot_original",
        "erreurs_incomplete", "signature", "envoi_client", "conclusion",
    }
    changes = []
    for key in keys:
        if key in skip or key.startswith("_"):
            continue
        old = original.get(key)
        new = current.get(key)
        if old == new:
            continue
        if (old is None or old == "") and (new is None or new == ""):
            continue
        changes.append({
            "field": key,
            "label": key.replace("_", " ").capitalize(),
            "old": old,
            "new": new,
        })
    return changes


def pick_conseiller_email_from_demande(doc: dict) -> Optional[str]:
    """Retourne agent_email s'il est valide (sans accès DB)."""
    direct = (doc.get("agent_email") or "").strip()
    if "@" in direct:
        return direct
    return None


def demandes_offres_base_query(user, conseiller: Optional[str] = None) -> dict:
    from access_control import (
        can_view_all_offres,
        TENANT_USER_ID,
        conseiller_scope_mongo_filter,
    )
    import re

    q: dict = {"user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}}
    if can_view_all_offres(user):
        if conseiller and conseiller != "all":
            q["agent_label"] = {"$regex": f"^{re.escape(conseiller.strip())}$", "$options": "i"}
        return q
    # Conseiller : uniquement ses demandes
    scope = conseiller_scope_mongo_filter(user)
    ors = list(scope.get("$or") or [])
    account_id = getattr(user, "account_id", None)
    if account_id:
        ors.append({"created_by_account_id": account_id})
    if ors:
        q["$or"] = ors
    else:
        q["created_by_account_id"] = account_id
    return q


def can_access_demande(user, doc: dict) -> bool:
    from access_control import (
        can_view_all_offres,
        labels_match_conseiller,
        email_matches_conseiller,
    )

    if can_view_all_offres(user):
        return True
    if doc.get("created_by_account_id") and doc.get("created_by_account_id") == getattr(user, "account_id", None):
        return True
    if labels_match_conseiller(doc.get("agent_label"), user):
        return True
    if email_matches_conseiller(doc, user):
        return True
    return False


def serialize_demande(doc: dict, *, docs: Optional[list] = None, viewer=None) -> dict:
    statut = normalize_statut(doc.get("statut"))
    offres_norm = normalize_offres_list(doc)
    legacy_offre = (
        normalize_offre_entry(doc["offre"])
        if isinstance(doc.get("offre"), dict)
        else None
    )
    offre_compat = offres_norm[-1] if offres_norm else legacy_offre
    out = {
        "id": doc.get("id"),
        "numero": doc.get("numero"),
        "statut": statut,
        FIELD_STATUT_AVANT_ANNULATION: (
            normalize_statut(doc.get(FIELD_STATUT_AVANT_ANNULATION))
            if doc.get(FIELD_STATUT_AVANT_ANNULATION)
            else None
        ),
        "agent_prenom": doc.get("agent_prenom") or "",
        "agent_nom": doc.get("agent_nom") or "",
        "agent_email": doc.get("agent_email") or "",
        "agent_finma": doc.get("agent_finma") or "",
        "agent_label": doc.get("agent_label") or "",
        "civilite": doc.get("civilite") or "",
        "nom": doc.get("nom") or "",
        "prenom": doc.get("prenom") or "",
        "sexe": doc.get("sexe") or "",
        "date_naissance": doc.get("date_naissance") or "",
        "nationalite": doc.get("nationalite") or "",
        "permis": doc.get("permis") or "",
        "adresse": doc.get("adresse") or "",
        "ville": doc.get("ville") or "",
        "npa": doc.get("npa") or "",
        "pays": doc.get("pays") or "",
        "statut_professionnel": doc.get("statut_professionnel") or "",
        "profession": doc.get("profession") or "",
        "travail_bureau_80": doc.get("travail_bureau_80") or "",
        "affilie_lpp": doc.get("affilie_lpp") or "",
        "fumeur": doc.get("fumeur") or "",
        "situation": doc.get("situation") or "",
        "activites_risque": bool(doc.get("activites_risque")),
        "activites_risque_liste": list(doc.get("activites_risque_liste") or []),
        "type_pilier": doc.get("type_pilier") or "",
        "date_debut": doc.get("date_debut") or "",
        "periodicite_prime": doc.get("periodicite_prime") or "",
        "montant_prime": parse_float(doc.get("montant_prime")),
        "deja_piliers_pax": doc.get("deja_piliers_pax") or "",
        "type_paiement": doc.get("type_paiement") or "",
        "duree_contrat": doc.get("duree_contrat") or "",
        "age_terme": doc.get("age_terme") or "",
        "exoneration_primes": doc.get("exoneration_primes") or "",
        "rente_invalidite": doc.get("rente_invalidite") or "",
        "diplome": doc.get("diplome") or "",
        "adaptation_auto_primes": doc.get("adaptation_auto_primes") or "",
        "risque_pur": doc.get("risque_pur") or "",
        "taille": doc.get("taille") or "",
        "poids": doc.get("poids") or "",
        "renseignements_complementaires": doc.get("renseignements_complementaires") or "",
        "compagnies": list(doc.get("compagnies") or []),
        "commentaires": doc.get("commentaires") or "",
        "inclure_cga": bool(doc.get("inclure_cga")),
        "date_prochain_rdv": doc.get("date_prochain_rdv") or "",
        "langue_offre": doc.get("langue_offre") or "",
        "mandat_gestion": bool(doc.get("mandat_gestion")),
        "incomplete_comment": doc.get("incomplete_comment") or "",
        "incomplete_at": doc.get("incomplete_at"),
        "incomplete_by": doc.get("incomplete_by"),
        "form_type": doc.get("form_type") or "pilier3_legacy",
        "form_type_label": doc.get("form_type_label") or "3ème pilier (formulaire CRM actuel)",
        "form_category": doc.get("form_category") or "3ème pilier",
        "form_payload": dict(doc.get("form_payload") or {}),
        "client_id": doc.get("client_id") or None,
        "offres": offres_norm,
        # Legacy fields kept in DB; never exposed for UI/selection workflow
        "offre_choisie_id": None,
        "offre_retenue": None,
        "offre": offre_compat,
        "envoi_client": doc.get("envoi_client") or None,
        "signature": doc.get("signature") or None,
        "conclusion": doc.get("conclusion") or None,
        "date_envoi": doc.get("date_envoi"),
        "email_sent": bool(doc.get("email_sent")),
        "email_error": doc.get("email_error"),
        "email_subject": doc.get("email_subject") or "",
        "demande_origine": normalize_demande_origine(doc.get("demande_origine")),
        "type_client": normalize_type_client(doc.get("type_client"), client_id=doc.get("client_id")),
        "erreurs_incomplete": list(doc.get("erreurs_incomplete") or []),
        "erreurs_agent": list(doc.get("erreurs_agent") or []),
        "modifications": list(doc.get("modifications") or []),
        "note_service_offre": doc.get("note_service_offre") or "",
        "snapshot_original": doc.get("snapshot_original") or None,
        "assigned_to_account_id": doc.get("assigned_to_account_id"),
        "assigned_to_name": doc.get("assigned_to_name") or "",
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "created_by_name": doc.get("created_by_name"),
        "created_by_account_id": doc.get("created_by_account_id"),
        "historique": collapse_demande_historique(doc.get("historique") or []),
        "documents": docs if docs is not None else None,
        "client_label": f"{(doc.get('prenom') or '').strip()} {(doc.get('nom') or '').strip()}".strip() or "—",
        "nb_variantes_sollicitees": len(list(doc.get("compagnies") or [])),
        "nb_offres_recues_detail": count_offres_recues(doc),
        "message_conseiller": doc.get("message_conseiller") or doc.get("incomplete_comment") or "",
        "documents_manquants": doc.get("documents_manquants") or "",
        "can_process": False,
        "can_follow_signature": False,
        "client_signe": bool(
            (isinstance(doc.get("signature"), dict) and doc["signature"].get("signee"))
            or statut == STATUT_OFFRE_SIGNEE
        ),
    }
    enrich_gestion_fields(doc, out)
    # Notes internes : uniquement pour les gestionnaires
    from access_control import can_process_offres
    if viewer is not None and can_process_offres(viewer):
        out["notes_internes"] = list(doc.get("notes_internes") or [])
        out["can_process"] = True
    else:
        out["notes_internes"] = []
        # Filtrer l'historique : masquer les événements purement internes
        hist = []
        for entry in list(out.get("historique") or []):
            action = str((entry or {}).get("action") or "")
            if action.casefold().startswith("note interne"):
                continue
            hist.append(entry)
        out["historique"] = hist
    if viewer is not None:
        out["can_follow_signature"] = can_follow_signature(viewer, doc)
    return out


# Statuts par compagnie (indépendants du statut global de la demande)
STATUT_COMPAGNIE_EN_ATTENTE = "En attente"
STATUT_COMPAGNIE_RECUE = "Offre reçue"
STATUT_COMPAGNIE_INCOMPLETE = "Incomplète"
# Legacy label — never written/displayed; normalized to Offre reçue
STATUT_COMPAGNIE_RETENUE = "Offre retenue"

STATUTS_COMPAGNIE_AVEC_OFFRE = {
    STATUT_COMPAGNIE_RECUE,
    STATUT_COMPAGNIE_INCOMPLETE,
    STATUT_COMPAGNIE_RETENUE,  # legacy DB values still count as received
    "Reçue",
    "Complète",
    "Choisie",
}


def _row_offres(doc: dict) -> list:
    offres = list(doc.get("offres") or [])
    if not offres and doc.get("offre") and isinstance(doc.get("offre"), dict):
        return [doc["offre"]]
    return offres


def document_ref_from_stored(stored: Optional[dict]) -> Optional[dict]:
    """Résumé document stocké, attachable à une offre compagnie."""
    if not stored or not isinstance(stored, dict):
        return None
    return {
        "id": stored.get("id"),
        "original_filename": stored.get("original_filename") or stored.get("filename") or "Document",
        "content_type": stored.get("content_type") or "application/octet-stream",
        "size": stored.get("size"),
        "category": stored.get("category") or "Offre compagnie",
        "created_at": stored.get("created_at") or now_iso(),
        "uploaded_by_name": stored.get("uploaded_by_name"),
    }


def normalize_offre_documents(offer: dict) -> list:
    """
    Migre document_id / document legacy vers documents[].
    N'écrase jamais les fichiers déjà présents.
    """
    if not isinstance(offer, dict):
        return []
    docs = []
    seen = set()
    for item in list(offer.get("documents") or []):
        if not isinstance(item, dict):
            continue
        did = item.get("id")
        if did and did in seen:
            continue
        if did:
            seen.add(did)
        docs.append({
            "id": did,
            "original_filename": item.get("original_filename") or item.get("filename") or "Document",
            "content_type": item.get("content_type") or "application/octet-stream",
            "size": item.get("size"),
            "category": item.get("category") or "Offre compagnie",
            "created_at": item.get("created_at") or offer.get("received_at") or now_iso(),
            "uploaded_by_name": item.get("uploaded_by_name"),
        })
    legacy_id = offer.get("document_id")
    if legacy_id and legacy_id not in seen:
        docs.append({
            "id": legacy_id,
            "original_filename": offer.get("document_filename") or "Document offre",
            "content_type": offer.get("document_content_type") or "application/octet-stream",
            "size": offer.get("document_size"),
            "category": "Offre compagnie",
            "created_at": offer.get("received_at") or now_iso(),
            "uploaded_by_name": offer.get("received_by"),
        })
        seen.add(legacy_id)
    return docs


def normalize_company_offer_statut(raw: Any, *, retenue: bool = False) -> str:
    """
    Statuts compagnie actifs : En attente | Offre reçue | Incomplète.
    Anciens « Offre retenue / choisie » (et flag retenue) → Offre reçue.
    Le paramètre ``retenue`` est ignoré (rétrocompat appelants).
    """
    _ = retenue  # legacy kwarg — selection workflow removed
    s = str(raw or "").strip()
    low = s.casefold()
    if low in {"incomplète", "incomplete", "incomplet"}:
        return STATUT_COMPAGNIE_INCOMPLETE
    if low in {
        "choisie", "retenue", "offre retenue", "offre choisie",
        "reçue", "recue", "complète", "complete",
        "offre reçue", "offre recue", "offre complète", "offre complete",
    }:
        return STATUT_COMPAGNIE_RECUE
    if s == STATUT_COMPAGNIE_INCOMPLETE:
        return STATUT_COMPAGNIE_INCOMPLETE
    if s in STATUTS_COMPAGNIE_AVEC_OFFRE or s == STATUT_COMPAGNIE_RECUE:
        return STATUT_COMPAGNIE_RECUE
    if s:
        return s
    return STATUT_COMPAGNIE_RECUE


def normalize_offre_entry(offer: dict) -> dict:
    """Normalise une entrée offres[] (rétrocompat document_id → documents)."""
    o = dict(offer or {})
    o.setdefault("id", str(uuid.uuid4()))
    o["compagnie"] = str(o.get("compagnie") or "").strip()
    # Stop propagating selection; leave raw DB keys untouched on write paths that merge dicts
    o["retenue"] = False
    o["documents"] = normalize_offre_documents(o)
    if o["documents"] and not o.get("document_id"):
        o["document_id"] = o["documents"][0].get("id")
    o["statut"] = normalize_company_offer_statut(o.get("statut"))
    return o


def normalize_offres_list(doc: dict) -> list:
    """Liste d'offres normalisées, avec migration de l'ancienne clé `offre`."""
    raw = _row_offres(doc)
    return [normalize_offre_entry(o) for o in raw if isinstance(o, dict)]


def company_key(name: Any) -> str:
    return str(name or "").strip().casefold()


def find_offre_for_compagnie(offres: list, compagnie: str) -> Optional[dict]:
    key = company_key(compagnie)
    if not key:
        return None
    for o in offres:
        if company_key(o.get("compagnie")) == key:
            return o
    return None


def offer_has_received_payload(offer: Optional[dict]) -> bool:
    """True si la compagnie a effectivement une offre (pas seulement une fiche vide)."""
    if not offer or not isinstance(offer, dict):
        return False
    st = normalize_company_offer_statut(offer.get("statut"))
    if st == STATUT_COMPAGNIE_EN_ATTENTE:
        return False
    if offer.get("date_reception") or offer.get("received_at"):
        return True
    if normalize_offre_documents(offer):
        return True
    if offer.get("reference") or offer.get("montant_prime") is not None or offer.get("garanties"):
        return True
    return st in STATUTS_COMPAGNIE_AVEC_OFFRE


def append_documents_to_offre(offer: dict, stored_list: list) -> dict:
    """Ajoute des documents sans remplacer les existants."""
    o = normalize_offre_entry(offer)
    docs = list(o.get("documents") or [])
    seen = {d.get("id") for d in docs if d.get("id")}
    for stored in stored_list:
        ref = document_ref_from_stored(stored)
        if not ref or not ref.get("id") or ref["id"] in seen:
            continue
        docs.append(ref)
        seen.add(ref["id"])
    o["documents"] = docs
    if docs and not o.get("document_id"):
        o["document_id"] = docs[0].get("id")
    return o


def upsert_company_offre(offres: list, offer: dict) -> list:
    """Met à jour l'offre d'une compagnie ou l'ajoute (une fiche par compagnie)."""
    normalized = normalize_offre_entry(offer)
    key = company_key(normalized.get("compagnie"))
    out = []
    replaced = False
    for existing in offres:
        e = normalize_offre_entry(existing)
        if key and company_key(e.get("compagnie")) == key:
            # Conserver l'id existant ; fusionner documents
            merged_docs = normalize_offre_documents(e)
            seen = {d.get("id") for d in merged_docs if d.get("id")}
            for d in normalized.get("documents") or []:
                if d.get("id") and d["id"] not in seen:
                    merged_docs.append(d)
                    seen.add(d["id"])
            merged = {**e, **{k: v for k, v in normalized.items() if k != "documents"}}
            merged["id"] = e.get("id") or normalized.get("id")
            merged["documents"] = merged_docs
            if merged_docs and not merged.get("document_id"):
                merged["document_id"] = merged_docs[0].get("id")
            merged["retenue"] = False
            out.append(normalize_offre_entry(merged))
            replaced = True
        else:
            out.append(e)
    if not replaced:
        out.append(normalized)
    return out


def all_solicited_companies_have_offer(doc: dict, offres: Optional[list] = None) -> bool:
    """True si chaque compagnie sollicitée a une réponse offre."""
    compagnies = [str(c).strip() for c in (doc.get("compagnies") or []) if str(c).strip()]
    items = offres if offres is not None else normalize_offres_list(doc)
    if not compagnies:
        # Pas de liste : au moins une offre reçue suffit
        return any(offer_has_received_payload(o) for o in items)
    for comp in compagnies:
        found = find_offre_for_compagnie(items, comp)
        if not offer_has_received_payload(found):
            return False
    return True


def resolve_statut_apres_reception_offre(doc: dict, offres: list) -> str:
    """
    Le statut global ne passe à « Offre reçue » que lorsque toutes les compagnies
    sollicitées ont une réponse. Une seule réponse partielle ne bascule pas la demande.
    """
    current = normalize_statut(doc.get("statut"))
    locked = {STATUT_OFFRE_SIGNEE, STATUT_OFFRE_REFUSEE, STATUT_ANNULEE, STATUT_OFFRE_CHOISIE}
    if current in locked:
        return current
    if all_solicited_companies_have_offer(doc, offres):
        return STATUT_OFFRE_RECUE
    # Réponses partielles : rester sur un statut d'attente / envoi
    if current in {STATUT_OFFRE_RECUE, STATUT_OFFRE_COMPLETE}:
        # Ne pas afficher « Offre reçue » global tant que des compagnies manquent
        return STATUT_ENVOYEE if (doc.get("date_envoi") or current) else STATUT_ENVOYEE
    if current in {STATUT_BROUILLON, STATUT_VALIDEE}:
        return STATUT_ENVOYEE if doc.get("date_envoi") else current
    return current


def build_reponses_compagnies(doc: dict) -> list:
    """
    Cartes « RÉPONSES DES COMPAGNIES » : une entrée par compagnie sollicitée,
    plus les offres orphelines (compagnie hors liste).
    """
    compagnies = [str(c).strip() for c in (doc.get("compagnies") or []) if str(c).strip()]
    offres = normalize_offres_list(doc)
    by_comp = {}
    for o in offres:
        key = company_key(o.get("compagnie"))
        if key and key not in by_comp:
            by_comp[key] = o

    out = []
    seen = set()
    for idx, comp in enumerate(compagnies, start=1):
        offer = by_comp.get(comp.casefold())
        seen.add(comp.casefold())
        if offer and offer_has_received_payload(offer):
            st = normalize_company_offer_statut(offer.get("statut"))
            out.append({
                "index": idx,
                "compagnie": comp,
                "statut": st,
                "offre_id": offer.get("id"),
                "date_reception": offer.get("date_reception") or offer.get("received_at"),
                "reference": offer.get("reference"),
                "montant_prime": offer.get("montant_prime"),
                "type_contrat": offer.get("type_contrat"),
                "duree": offer.get("duree"),
                "garanties": offer.get("garanties"),
                "commentaires": offer.get("commentaires"),
                "documents": normalize_offre_documents(offer),
                "retenue": False,
                "has_offre": True,
                "incomplete_comment": offer.get("incomplete_comment"),
                "incomplete_at": offer.get("incomplete_at"),
                "received_by": offer.get("received_by"),
                "retenue_at": None,
                "retenue_by": None,
            })
        else:
            out.append({
                "index": idx,
                "compagnie": comp,
                "statut": STATUT_COMPAGNIE_EN_ATTENTE,
                "offre_id": (offer or {}).get("id") if offer else None,
                "date_reception": None,
                "reference": None,
                "montant_prime": None,
                "type_contrat": None,
                "duree": None,
                "garanties": None,
                "commentaires": None,
                "documents": [],
                "retenue": False,
                "has_offre": False,
                "incomplete_comment": None,
                "incomplete_at": None,
                "received_by": None,
                "retenue_at": None,
                "retenue_by": None,
            })

    # Offres pour compagnies hors liste initiale
    for o in offres:
        key = company_key(o.get("compagnie"))
        if not key or key in seen:
            continue
        st = normalize_company_offer_statut(o.get("statut"))
        out.append({
            "index": len(out) + 1,
            "compagnie": o.get("compagnie") or "Compagnie",
            "statut": st if offer_has_received_payload(o) else STATUT_COMPAGNIE_EN_ATTENTE,
            "offre_id": o.get("id"),
            "date_reception": o.get("date_reception") or o.get("received_at"),
            "reference": o.get("reference"),
            "montant_prime": o.get("montant_prime"),
            "type_contrat": o.get("type_contrat"),
            "duree": o.get("duree"),
            "garanties": o.get("garanties"),
            "commentaires": o.get("commentaires"),
            "documents": normalize_offre_documents(o),
            "retenue": False,
            "has_offre": offer_has_received_payload(o),
            "incomplete_comment": o.get("incomplete_comment"),
            "incomplete_at": o.get("incomplete_at"),
            "received_by": o.get("received_by"),
            "retenue_at": None,
            "retenue_by": None,
        })
    return out


def count_variantes_sollicitees(doc: dict) -> int:
    """Variantes = compagnies sollicitées dans une même demande."""
    return len(list(doc.get("compagnies") or []))


def count_offres_recues(doc: dict) -> int:
    return sum(1 for o in normalize_offres_list(doc) if offer_has_received_payload(o))


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def jours_depuis_reference(doc: dict, *, now: Optional[datetime] = None) -> int:
    """Jours depuis date_envoi (sinon created_at)."""
    now = now or datetime.now(timezone.utc)
    ref = _parse_dt(doc.get("date_envoi")) or _parse_dt(doc.get("created_at"))
    if not ref:
        return 0
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max(0, int((now - ref).total_seconds() // 86400))


def derniere_action_info(doc: dict) -> dict:
    hist = collapse_demande_historique(doc.get("historique") or [])
    if hist:
        last = hist[-1] or {}
        return {
            "action": last.get("action") or "",
            "at": last.get("at"),
            "by_name": last.get("by_name") or "",
            "detail": last.get("detail") or "",
        }
    return {
        "action": "Création",
        "at": doc.get("updated_at") or doc.get("created_at"),
        "by_name": doc.get("created_by_name") or "",
        "detail": "",
    }


def build_variantes(doc: dict) -> list:
    """Une variante = une compagnie sollicitée + statut d'offre lié si présent."""
    cards = build_reponses_compagnies(doc)
    out = []
    for card in cards:
        docs = card.get("documents") or []
        out.append({
            "index": card.get("index"),
            "compagnie": card.get("compagnie"),
            "statut": card.get("statut") or STATUT_COMPAGNIE_EN_ATTENTE,
            "offre_id": card.get("offre_id"),
            "document_id": (docs[0].get("id") if docs else None) or None,
            "documents": docs,
            "date_reception": card.get("date_reception"),
            "has_offre": bool(card.get("has_offre")),
            "retenue": False,
        })
    return out


def compute_priorite(doc: dict, *, now: Optional[datetime] = None) -> dict:
    """
    Priorité auto basée sur l'âge et le statut ouvert.
    Réutilise le délai minimum compagnies déjà affiché (5 j.) :
    - < 5 j. → normal
    - >= 5 j. → à surveiller
    - >= 10 j. → urgent (+ en_retard)
    """
    now = now or datetime.now(timezone.utc)
    st = normalize_statut(doc.get("statut"))
    jours = jours_depuis_reference(doc, now=now)
    ouvert = st in STATUTS_OUVERTS_GESTION
    if not ouvert:
        return {
            "niveau": "normal",
            "label": "Normal",
            "jours": jours,
            "en_retard": False,
        }
    if jours >= OFFRES_DELAI_URGENT_JOURS:
        return {
            "niveau": "urgent",
            "label": "Urgent",
            "jours": jours,
            "en_retard": True,
        }
    if jours >= OFFRES_DELAI_SURVEILLER_JOURS:
        return {
            "niveau": "surveiller",
            "label": "À surveiller",
            "jours": jours,
            "en_retard": False,
        }
    return {
        "niveau": "normal",
        "label": "Normal",
        "jours": jours,
        "en_retard": False,
    }


def gestion_categorie_ids(doc: dict) -> list:
    """Catégories d'affichage auxquelles appartient la demande."""
    st = normalize_statut(doc.get("statut"))
    ids = []
    for cid, conf in GESTION_CATEGORIES.items():
        if cid == "attribuees":
            if normalize_demande_origine(doc.get("demande_origine")) == DEMANDE_ORIGINE_ATTRIBUEE:
                ids.append(cid)
            continue
        statuts = conf.get("statuts") or []
        if st in statuts:
            ids.append(cid)
    prio = compute_priorite(doc)
    if prio.get("en_retard"):
        ids.append("en_retard")
    return ids


def enrich_gestion_fields(doc: dict, out: dict) -> None:
    """Ajoute champs de pilotage (jours, priorité, variantes, dernière action)."""
    prio = compute_priorite(doc)
    last = derniere_action_info(doc)
    out["jours_depuis"] = prio["jours"]
    out["priorite"] = prio["niveau"]
    out["priorite_label"] = prio["label"]
    out["en_retard"] = bool(prio["en_retard"])
    out["derniere_action"] = last.get("action") or ""
    out["derniere_action_at"] = last.get("at")
    out["derniere_action_by"] = last.get("by_name") or ""
    out["gestion_categories"] = gestion_categorie_ids(doc)
    out["variantes"] = build_variantes(doc)
    out["reponses_compagnies"] = build_reponses_compagnies(doc)
    out["delai_surveiller_jours"] = OFFRES_DELAI_SURVEILLER_JOURS
    out["delai_urgent_jours"] = OFFRES_DELAI_URGENT_JOURS


def compute_gestion_kpis(rows: list) -> dict:
    """KPIs cliquables de l'espace gestionnaire."""
    now = datetime.now(timezone.utc)
    counts = {
        "a_traiter": 0,
        "attribuees": 0,
        "envoyees": 0,
        "en_attente": 0,
        "incompletes": 0,
        "offres_recues": 0,
        "a_modifier": 0,
        "modifiees": 0,
        "completes": 0,
        "attente_signature": 0,
        "signees": 0,
        "en_retard": 0,
        "urgentes": 0,
        "a_surveiller": 0,
        "nouvelles": 0,
    }
    for r in rows:
        if r.get("is_deleted"):
            continue
        st = normalize_statut(r.get("statut"))
        cats = set(gestion_categorie_ids(r))
        for key in (
            "a_traiter",
            "attribuees",
            "envoyees",
            "en_attente",
            "incompletes",
            "offres_recues",
            "a_modifier",
            "modifiees",
            "completes",
            "attente_signature",
            "signees",
            "en_retard",
        ):
            if key in cats:
                counts[key] += 1
        prio = compute_priorite(r, now=now)
        if prio["niveau"] == "urgent":
            counts["urgentes"] += 1
        elif prio["niveau"] == "surveiller":
            counts["a_surveiller"] += 1
        if st in {STATUT_ENVOYEE, STATUT_VALIDEE} and prio["jours"] <= 1:
            counts["nouvelles"] += 1
    return counts


def compute_erreur_stats(rows: list) -> dict:
    """Taux d'erreur (incomplètes) par conseiller."""
    from conseiller_identity import display_conseiller_name, merge_conseiller_display, normalize_conseiller_key

    agents: dict = {}
    for r in rows:
        if r.get("is_deleted"):
            continue
        st = normalize_statut(r.get("statut"))
        if st in {STATUT_BROUILLON, STATUT_ANNULEE}:
            continue
        raw = (r.get("agent_label") or "").strip() or "Non attribué"
        key = normalize_conseiller_key(raw) or "non attribue"
        if key not in agents:
            agents[key] = {
                "agent": display_conseiller_name(raw),
                "demandes": 0,
                "incompletes": 0,
                "erreurs": [],
            }
        else:
            agents[key]["agent"] = merge_conseiller_display(agents[key]["agent"], raw)
        agents[key]["demandes"] += 1
        was_incomplete = st == STATUT_INCOMPLETE or bool(r.get("incomplete_at"))
        if was_incomplete:
            agents[key]["incompletes"] += 1
            for err in list(r.get("erreurs_incomplete") or []):
                agents[key]["erreurs"].append({
                    "demande_id": r.get("id"),
                    "numero": r.get("numero"),
                    "client": f"{(r.get('prenom') or '').strip()} {(r.get('nom') or '').strip()}".strip(),
                    "code": err.get("code"),
                    "label": err.get("label"),
                    "detail": err.get("detail"),
                    "at": err.get("at") or r.get("incomplete_at"),
                })
    out = []
    for a in agents.values():
        demandes = a["demandes"]
        incompletes = a["incompletes"]
        taux = round((incompletes / demandes) * 100, 1) if demandes else 0.0
        out.append({**a, "taux_erreur": taux})
    out.sort(key=lambda x: (-x["taux_erreur"], -x["incompletes"], x["agent"].casefold()))
    return {"by_agent": out}


def offer_type_label(doc: dict) -> str:
    return (doc.get("form_type_label") or doc.get("type_pilier") or "—").strip() or "—"


def offer_category_label(doc: dict) -> str:
    cat = (doc.get("form_category") or "").strip()
    if cat:
        return cat
    ft = (doc.get("form_type") or "").strip().casefold()
    label = (doc.get("form_type_label") or "").strip().casefold()
    if any(x in ft or x in label for x in ("rc", "menage", "ménage")):
        return "RC / Ménage"
    if any(x in ft or x in label for x in ("pilier", "prevoyance", "prévoyance", "lpp", "laaf")):
        return "Prévoyance / 3e pilier"
    if any(x in ft or x in label for x in ("vehicule", "véhicule", "motocycle", "voyage")):
        return "Véhicules / Mobilité"
    if any(x in ft or x in label for x in ("entreprise", "professionnel", "rc_entreprise")):
        return "Assurances professionnelles"
    if any(x in ft or x in label for x in ("batiment", "bâtiment", "choses")):
        return "Assurances choses"
    return (doc.get("form_type_label") or "Autre").strip() or "Autre"


def period_bounds(
    periode: Optional[str] = None,
    date_de: Optional[str] = None,
    date_a: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Bornes UTC pour filtrer created_at (début inclusif, fin exclusive).
    Retourne (start_iso, end_iso, periode_normalisee).
    """
    raw = (periode or "all").strip().lower()
    aliases = {
        "": "all",
        "tout": "all",
        "all": "all",
        "aujourdhui": "today",
        "aujourd'hui": "today",
        "today": "today",
        "cette_semaine": "week",
        "semaine": "week",
        "week": "week",
        "mois_en_cours": "month",
        "month": "month",
        "mois_dernier": "last_month",
        "last_month": "last_month",
        "6_mois": "6months",
        "6months": "6months",
        "6_derniers_mois": "6months",
        "1_an": "year",
        "year": "year",
        "1_derniere_annee": "year",
        "personnalisee": "custom",
        "personnalise": "custom",
        "custom": "custom",
    }
    p = aliases.get(raw, raw)
    if p == "all":
        return None, None, "all"

    now = datetime.now(timezone.utc)
    today = now.date()

    if p == "today":
        start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
    elif p == "week":
        start_day = today - timedelta(days=today.weekday())
        start = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=7)
    elif p == "month":
        start = datetime.combine(today.replace(day=1), datetime.min.time(), tzinfo=timezone.utc)
        end = now + timedelta(seconds=1)
    elif p == "last_month":
        first_this = today.replace(day=1)
        last_day_prev = first_this - timedelta(days=1)
        start = datetime.combine(last_day_prev.replace(day=1), datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(first_this, datetime.min.time(), tzinfo=timezone.utc)
    elif p == "6months":
        start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=183)
        end = now + timedelta(seconds=1)
    elif p == "year":
        start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=365)
        end = now + timedelta(seconds=1)
    elif p == "custom":
        if not (date_de or "").strip():
            return None, None, "all"
        start_day = date.fromisoformat(str(date_de)[:10])
        end_day = date.fromisoformat(str(date_a or date_de)[:10])
        if end_day < start_day:
            start_day, end_day = end_day, start_day
        start = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    else:
        return None, None, "all"

    return start.isoformat(), end.isoformat(), p


def filter_rows_by_period(
    rows: list,
    *,
    periode: Optional[str] = None,
    date_de: Optional[str] = None,
    date_a: Optional[str] = None,
) -> tuple[list, dict]:
    start, end, norm = period_bounds(periode, date_de, date_a)
    if not start and not end:
        return list(rows), {"periode": norm, "date_de": None, "date_a": None}

    out = []
    for r in rows:
        created = str(r.get("created_at") or "")
        if not created:
            continue
        if start and created < start:
            continue
        if end and created >= end:
            continue
        out.append(r)

    meta = {
        "periode": norm,
        "date_de": (date_de or start)[:10] if norm == "custom" else start[:10],
        "date_a": (date_a or date_de or "")[:10] if norm == "custom" else None,
    }
    if norm != "custom" and start:
        meta["date_de"] = start[:10]
    if norm != "custom" and end:
        meta["date_a"] = (datetime.fromisoformat(end.replace("Z", "+00:00")) - timedelta(days=1)).date().isoformat()
    return out, meta


def _inc_bucket(buckets: dict, key: str, amount: int = 1) -> None:
    k = (key or "—").strip() or "—"
    buckets[k] = buckets.get(k, 0) + amount


def compute_agent_stats(rows: list) -> dict:
    """Statistiques par agent (brouillons inclus, annulées exclues)."""
    from conseiller_identity import display_conseiller_name, merge_conseiller_display, normalize_conseiller_key

    agents: dict = {}

    def bucket(raw_agent: str) -> dict:
        key = normalize_conseiller_key(raw_agent) or "non attribue"
        if key not in agents:
            agents[key] = {
                "agent": display_conseiller_name(raw_agent),
                "nb_demandes": 0,
                "nb_brouillons": 0,
                "nb_variantes_sollicitees": 0,
                "nb_offres_recues": 0,
                "offres_envoyees": 0,
                "offres_signees": 0,
                "offres_refusees": 0,
                "en_attente": 0,
                "incompletes": 0,
                "completes": 0,
                "by_form_type": {},
                "by_category": {},
                "by_compagnie": {},
            }
        else:
            agents[key]["agent"] = merge_conseiller_display(agents[key]["agent"], raw_agent)
        return agents[key]

    for r in rows:
        if r.get("is_deleted"):
            continue
        st = r.get("statut") or STATUT_BROUILLON
        if st == STATUT_ANNULEE:
            continue
        agent = (r.get("agent_label") or "Non attribué").strip() or "Non attribué"
        b = bucket(agent)
        if st == STATUT_BROUILLON:
            b["nb_brouillons"] += 1
        else:
            b["nb_demandes"] += 1
            n_var = count_variantes_sollicitees(r)
            b["nb_variantes_sollicitees"] += n_var
            b["nb_offres_recues"] += count_offres_recues(r)
            _inc_bucket(b["by_form_type"], offer_type_label(r))
            _inc_bucket(b["by_category"], offer_category_label(r))
            for comp in r.get("compagnies") or []:
                _inc_bucket(b["by_compagnie"], str(comp).strip())
        if st in {STATUT_ENVOYEE, STATUT_VALIDEE, STATUT_ATTENTE_INFOS}:
            b["en_attente"] += 1
        if st == STATUT_INCOMPLETE:
            b["incompletes"] += 1
        if st in {STATUT_OFFRE_COMPLETE, STATUT_OFFRE_CHOISIE, STATUT_EN_CONCLUSION}:
            b["completes"] += 1
        if st in {
            STATUT_OFFRE_ENVOYEE_CLIENT,
            STATUT_EN_CONCLUSION,
            STATUT_OFFRE_SIGNEE,
            STATUT_OFFRE_REFUSEE,
        }:
            b["offres_envoyees"] += 1
        if st == STATUT_OFFRE_SIGNEE:
            b["offres_signees"] += 1
        if st == STATUT_OFFRE_REFUSEE:
            b["offres_refusees"] += 1

    rows_out = sorted(
        agents.values(),
        key=lambda x: (-(x["nb_demandes"] + x["nb_brouillons"]), x["agent"].casefold()),
    )
    chart = [
        {
            "agent": a["agent"],
            "demandes": a["nb_demandes"],
            "brouillons": a["nb_brouillons"],
            "variantes": a["nb_variantes_sollicitees"],
            "envoyees": a["offres_envoyees"],
            "recues": a["nb_offres_recues"],
            "signees": a["offres_signees"],
            "refusees": a["offres_refusees"],
        }
        for a in rows_out
    ]
    return {"by_agent": rows_out, "chart_agents": chart}


# Étapes du pipeline de pilotage (agrégats cliquables)
PIPELINE_STAGES = [
    {"id": "brouillon", "label": "Brouillon", "statuts": [STATUT_BROUILLON]},
    {
        "id": "demande_envoyee",
        "label": "Demande envoyée",
        "statuts": [STATUT_ENVOYEE, STATUT_VALIDEE],
    },
    {
        "id": "en_attente",
        "label": "En attente",
        "statuts": [STATUT_ATTENTE_INFOS, STATUT_INCOMPLETE],
    },
    {
        "id": "offre_recue",
        "label": "Offre reçue",
        "statuts": [STATUT_OFFRE_RECUE, STATUT_OFFRE_COMPLETE, STATUT_OFFRE_CHOISIE, STATUT_EN_CONCLUSION],
    },
    {
        "id": "envoyee_client",
        "label": "Envoyée au client",
        "statuts": [STATUT_OFFRE_ENVOYEE_CLIENT],
    },
    {"id": "signee", "label": "Signée", "statuts": [STATUT_OFFRE_SIGNEE]},
    {"id": "refusee", "label": "Refusée", "statuts": [STATUT_OFFRE_REFUSEE]},
]


def compute_pipeline(rows: list) -> list:
    counts = {s["id"]: 0 for s in PIPELINE_STAGES}
    statut_to_stage = {}
    for stage in PIPELINE_STAGES:
        for st in stage["statuts"]:
            statut_to_stage[st] = stage["id"]
    for r in rows:
        if r.get("is_deleted"):
            continue
        st = r.get("statut") or STATUT_BROUILLON
        sid = statut_to_stage.get(st)
        if sid:
            counts[sid] += 1
    return [
        {"id": s["id"], "label": s["label"], "count": counts[s["id"]], "statuts": list(s["statuts"])}
        for s in PIPELINE_STAGES
    ]


def compute_stats(rows: list, *, period_meta: Optional[dict] = None) -> dict:
    now = datetime.now(timezone.utc)
    month_prefix = now.strftime("%Y-%m")
    total = len(rows)
    this_month = 0
    en_attente = 0
    incompletes = 0
    offres_recues = 0
    offres_envoyees = 0
    offres_attente_reponse = 0
    signees = 0
    refusees = 0
    nb_brouillons = 0
    nb_demandes = 0
    by_statut = {s: 0 for s in STATUTS}

    for r in rows:
        st = r.get("statut") or STATUT_BROUILLON
        by_statut[st] = by_statut.get(st, 0) + 1
        created = str(r.get("created_at") or "")[:7]
        if created == month_prefix:
            this_month += 1

        # Compteurs indépendants : brouillon ≠ demande envoyée / pipeline
        if st == STATUT_BROUILLON:
            nb_brouillons += 1
        elif st != STATUT_ANNULEE:
            nb_demandes += 1

        if st in {STATUT_ENVOYEE, STATUT_VALIDEE, STATUT_ATTENTE_INFOS}:
            en_attente += 1
        if st in {STATUT_INCOMPLETE, STATUT_ATTENTE_INFOS}:
            incompletes += 1
        # KPI « Offres complètes » : uniquement le statut final (pas « Offre reçue »)
        if normalize_statut(st) == STATUT_OFFRE_COMPLETE:
            offres_recues += 1
        if st in {
            STATUT_OFFRE_ENVOYEE_CLIENT,
            STATUT_EN_CONCLUSION,
            STATUT_OFFRE_SIGNEE,
            STATUT_OFFRE_REFUSEE,
        }:
            offres_envoyees += 1
        if st in {STATUT_OFFRE_ENVOYEE_CLIENT, STATUT_EN_CONCLUSION}:
            offres_attente_reponse += 1
        if st == STATUT_OFFRE_SIGNEE:
            signees += 1
        if st == STATUT_OFFRE_REFUSEE:
            refusees += 1

    taux = round((signees / offres_envoyees) * 100, 1) if offres_envoyees else 0.0

    nb_variantes_sollicitees = 0
    nb_offres_recues_detail = 0
    nb_origine_conseiller = 0
    nb_origine_attribuee = 0
    by_form_type: dict = {}
    by_category: dict = {}
    by_compagnie: dict = {}
    for r in rows:
        st = r.get("statut") or STATUT_BROUILLON
        if st != STATUT_ANNULEE:
            if normalize_demande_origine(r.get("demande_origine")) == DEMANDE_ORIGINE_ATTRIBUEE:
                nb_origine_attribuee += 1
            else:
                nb_origine_conseiller += 1
        if st in {STATUT_ANNULEE, STATUT_BROUILLON}:
            continue
        nb_variantes_sollicitees += count_variantes_sollicitees(r)
        nb_offres_recues_detail += count_offres_recues(r)
        _inc_bucket(by_form_type, offer_type_label(r))
        _inc_bucket(by_category, offer_category_label(r))
        for comp in r.get("compagnies") or []:
            _inc_bucket(by_compagnie, str(comp).strip())

    agent_block = compute_agent_stats(rows)
    gestion = compute_gestion_kpis(rows)
    result = {
        "total": total,
        "nb_demandes": nb_demandes,
        "nb_brouillons": nb_brouillons,
        "nb_origine_conseiller": nb_origine_conseiller,
        "nb_origine_attribuee": nb_origine_attribuee,
        "nb_demandes_conseiller": nb_origine_conseiller,
        "nb_demandes_attribuees": nb_origine_attribuee,
        "by_origine": {
            DEMANDE_ORIGINE_CONSEILLER: nb_origine_conseiller,
            DEMANDE_ORIGINE_ATTRIBUEE: nb_origine_attribuee,
        },
        "nb_variantes_sollicitees": nb_variantes_sollicitees,
        "nb_offres_recues_detail": nb_offres_recues_detail,
        "ce_mois": this_month,
        "en_attente": en_attente,
        "incompletes": incompletes,
        "offres_recues": offres_recues,
        "offres_envoyees": offres_envoyees,
        "offres_attente_reponse": offres_attente_reponse,
        "offres_signees": signees,
        "offres_refusees": refusees,
        "taux_signature": taux,
        "by_statut": by_statut,
        "by_form_type": by_form_type,
        "by_category": by_category,
        "by_compagnie": by_compagnie,
        "pipeline": compute_pipeline(rows),
        "gestion": gestion,
        "gestion_categories": {
            cid: {"label": conf["label"], "statuts": list(conf["statuts"] or [])}
            for cid, conf in GESTION_CATEGORIES.items()
        },
        "gestion_kanban": GESTION_KANBAN_COLUMNS,
        "delai_surveiller_jours": OFFRES_DELAI_SURVEILLER_JOURS,
        "delai_urgent_jours": OFFRES_DELAI_URGENT_JOURS,
        **agent_block,
    }
    if period_meta:
        result["periode"] = period_meta
    return result


def apply_form_fields(target: dict, data: dict) -> None:
    str_keys = [
        "agent_prenom", "agent_nom", "agent_email", "agent_finma",
        "civilite", "nom", "prenom", "sexe", "date_naissance", "nationalite", "permis",
        "adresse", "ville", "npa", "pays", "statut_professionnel", "profession",
        "travail_bureau_80", "affilie_lpp", "fumeur", "situation",
        "type_pilier", "date_debut", "periodicite_prime", "deja_piliers_pax",
        "type_paiement", "duree_contrat", "age_terme", "exoneration_primes",
        "rente_invalidite", "diplome", "adaptation_auto_primes", "risque_pur",
        "taille", "poids", "renseignements_complementaires", "commentaires",
        "date_prochain_rdv", "langue_offre",
    ]
    # form_type avant le reste pour savoir si on accepte les colonnes legacy 3P
    if "form_type" in data and data.get("form_type"):
        target["form_type"] = str(data.get("form_type")).strip()
    form_type_id = (target.get("form_type") or data.get("form_type") or "").strip() or "pilier3_legacy"
    is_schema_form = form_type_id != "pilier3_legacy"
    legacy_key_set = set(LEGACY_3P_CRM_KEYS)

    for key in str_keys:
        if key not in data:
            continue
        # Ne pas réinjecter des colonnes 3P via un PUT générique sur un formulaire schéma
        if is_schema_form and key in legacy_key_set:
            continue
        val = data.get(key)
        target[key] = (str(val).strip() if val is not None else "") or None

    if not is_schema_form:
        if "montant_prime" in data:
            target["montant_prime"] = parse_float(data.get("montant_prime"))
        if "activites_risque" in data:
            target["activites_risque"] = bool(data.get("activites_risque"))
        if "activites_risque_liste" in data:
            raw = data.get("activites_risque_liste") or []
            target["activites_risque_liste"] = [str(x).strip() for x in raw if str(x).strip()]
        if "inclure_cga" in data:
            target["inclure_cga"] = bool(data.get("inclure_cga"))
        if "mandat_gestion" in data:
            target["mandat_gestion"] = bool(data.get("mandat_gestion"))

    if "compagnies" in data:
        raw = data.get("compagnies") or []
        target["compagnies"] = [str(x).strip() for x in raw if str(x).strip()]
    if "type_client" in data:
        target["type_client"] = normalize_type_client(
            data.get("type_client"), client_id=data.get("client_id") or target.get("client_id")
        )
    if "demande_origine" in data:
        target["demande_origine"] = normalize_demande_origine(data.get("demande_origine"))
    if "note_service_offre" in data:
        target["note_service_offre"] = (str(data.get("note_service_offre") or "").strip()) or None
    if "client_id" in data:
        cid = data.get("client_id")
        target["client_id"] = (str(cid).strip() if cid else None) or None
    if "form_payload" in data and isinstance(data.get("form_payload"), dict):
        raw_payload = dict(data.get("form_payload") or {})
        if is_schema_form:
            try:
                from offre_form_types import filter_form_payload_to_schema

                raw_payload = filter_form_payload_to_schema(form_type_id, raw_payload)
            except Exception:
                pass
        target["form_payload"] = raw_payload

    # Synchroniser identité / agent pour le tableau CRM quand un schéma GF est utilisé
    if is_schema_form:
        # Nettoyer d'éventuelles colonnes 3P résiduelles (création ancienne / pollution)
        clear_legacy_3p_crm_fields(target)
        if isinstance(target.get("form_payload"), dict):
            try:
                from offre_form_types import sync_crm_fields_from_payload

                sync_crm_fields_from_payload(target, form_type_id, target.get("form_payload") or {})
            except Exception:
                pass

    ap = (target.get("agent_prenom") or "").strip()
    an = (target.get("agent_nom") or "").strip()
    target["agent_label"] = f"{ap} {an}".strip() or target.get("agent_label")
