"""
Génération de documents PDF préremplis à partir des données client.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, DictionaryObject, NameObject

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "forms"


DOCUMENT_TEMPLATES = [
    {
        "id": "procuration_avs_lpp",
        "label": "Procuration AVS/LPP",
        "description": "Procuration Agence Mendes pour AVS et 2e pilier",
        "filename": "procuration_avs_lpp.pdf",
        "mode": "acroform",
        "output_prefix": "Procuration_AVS_LPP",
        "category": "Procuration",
        "checklist_item": "Procuration",
    },
    {
        "id": "recherche_avoirs_lpp",
        "label": "Formulaire de recherche d'avoirs LPP",
        "description": "Demande de recherche d'avoirs auprès de la Centrale du 2e pilier",
        "filename": "recherche_avoirs_lpp.pdf",
        "mode": "acroform",
        "output_prefix": "Recherche_avoirs_LPP",
        "category": "Formulaire de recherche LPP",
        "checklist_item": "Formulaire Recherche LPP",
    },
    {
        "id": "calcul_rente_future",
        "label": "Demande de calcul d'une rente future (AVS)",
        "description": "Formulaire officiel de demande de calcul de rente future",
        "filename": "calcul_rente_future.pdf",
        "mode": "acroform",
        "output_prefix": "Calcul_rente_future_AVS",
        "category": "Formulaire AVS",
        "checklist_item": "Formulaire AVS",
    },
    {
        "id": "lettre_lpp",
        "label": "Lettre d'accompagnement — Recherche LPP",
        "description": "Courrier au Fonds de garantie LPP",
        "filename": "lettre_lpp.pdf",
        "mode": "acroform",
        "output_prefix": "Lettre_Recherche_LPP",
        "category": "Courriers",
        "checklist_item": "Formulaire Recherche LPP",
    },
    {
        "id": "lettre_avs",
        "label": "Lettre d'accompagnement — Demande AVS",
        "description": "Courrier à la Caisse suisse de compensation",
        "filename": "lettre_avs.pdf",
        "mode": "acroform",
        "output_prefix": "Lettre_Demande_AVS",
        "category": "Courriers",
        "checklist_item": "Formulaire AVS",
    },
    {
        "id": "lettre_decompte_lpp",
        "label": "Lettre de demande de décompte LPP",
        "description": "Courrier de demande de décompte adressé à une caisse de pension",
        "filename": "lettre_decompte_lpp.pdf",
        "mode": "acroform",
        "output_prefix": "Demande_decompte",
        "category": "Demande de décompte LPP",
        "checklist_item": "Certificat LPP",
    },
]

DEMAND_PACKS = {
    "recherche_lpp": {
        "label": "Demande LPP",
        "templates": ["recherche_avoirs_lpp", "procuration_avs_lpp", "lettre_lpp"],
        "options": {"demande_pour_moi_meme": True},
    },
    "demande_avs": {
        "label": "Demande AVS",
        "templates": ["calcul_rente_future", "lettre_avs"],
        "options": {},
    },
}


def list_templates() -> List[Dict[str, Any]]:
    return [
        {
            "id": t["id"],
            "label": t["label"],
            "description": t["description"],
            "category": t["category"],
            "checklist_item": t.get("checklist_item"),
            "available": (TEMPLATES_DIR / t["filename"]).exists(),
        }
        for t in DOCUMENT_TEMPLATES
    ]


def list_demand_packs() -> List[Dict[str, Any]]:
    return [
        {
            "id": pack_id,
            "label": pack["label"],
            "templates": pack["templates"],
        }
        for pack_id, pack in DEMAND_PACKS.items()
    ]


def get_template(template_id: str) -> Dict[str, Any]:
    for t in DOCUMENT_TEMPLATES:
        if t["id"] == template_id:
            return t
    raise KeyError(template_id)


def _format_date_long(value: Any = None) -> str:
    months = [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ]
    if value:
        text = _safe(value)
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(text[:10], fmt)
                return f"{dt.day} {months[dt.month - 1]} {dt.year}"
            except ValueError:
                continue
    now = datetime.now()
    return f"{now.day} {months[now.month - 1]} {now.year}"


def _safe(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _format_date(value: Any) -> str:
    text = _safe(value)
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return text


def _format_avs(value: Any) -> str:
    digits = re.sub(r"\D", "", _safe(value))
    if len(digits) == 13:
        return f"{digits[0:3]}.{digits[3:7]}.{digits[7:11]}.{digits[11:13]}"
    return _safe(value)


def _avs_after_756(value: Any) -> str:
    """Pour les formulaires où '756' est déjà imprimé : ne garder que la suite."""
    digits = re.sub(r"\D", "", _safe(value))
    if digits.startswith("756") and len(digits) > 3:
        return digits[3:]
    if len(digits) == 10:
        return digits
    if len(digits) == 13:
        return digits[3:]
    return digits


def _format_address(client: Dict[str, Any]) -> str:
    parts = [
        _safe(client.get("adresse")),
        " ".join(p for p in [_safe(client.get("npa")), _safe(client.get("ville"))] if p),
    ]
    return ", ".join(p for p in parts if p)


def _split_agent_name(full_name: str) -> tuple[str, str]:
    parts = [p for p in _safe(full_name).split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def _split_street(adresse: str) -> tuple[str, str]:
    text = _safe(adresse)
    if not text:
        return "", ""
    m = re.match(r"^(.*?)[,\s]+(\d+\s*[a-zA-Z]?)$", text)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m2 = re.match(r"^(\d+\s*[a-zA-Z]?)\s+(.+)$", text)
    if m2:
        return m2.group(2).strip(), m2.group(1).strip()
    return text, ""


def _norm(s: str) -> str:
    return (
        _safe(s)
        .lower()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("â", "a")
        .replace("î", "i")
        .replace("ô", "o")
        .replace("ù", "u")
        .replace("ç", "c")
    )


# Sources CRM disponibles pour le mapping manuel des formulaires bibliothèque
CRM_FIELD_SOURCES: List[Dict[str, str]] = [
    {"key": "", "label": "— Ne pas remplir —", "group": ""},
    {"key": "civilite", "label": "Civilité (M./Mme)", "group": "Client"},
    {"key": "nom", "label": "Nom du client", "group": "Client"},
    {"key": "prenom", "label": "Prénom du client", "group": "Client"},
    {"key": "date_naissance", "label": "Date de naissance du client", "group": "Client"},
    {"key": "avs", "label": "N° AVS du client", "group": "Client"},
    {"key": "sexe", "label": "Sexe du client", "group": "Client"},
    {"key": "nationalite", "label": "Nationalité du client", "group": "Client"},
    {"key": "pays", "label": "Pays", "group": "Client"},
    {"key": "email", "label": "Email du client", "group": "Client"},
    {"key": "telephone", "label": "Téléphone du client", "group": "Client"},
    {"key": "adresse", "label": "Adresse (ligne) du client", "group": "Client"},
    {"key": "adresse_complete", "label": "Adresse complète du client", "group": "Client"},
    {"key": "rue", "label": "Rue du client", "group": "Client"},
    {"key": "numero_rue", "label": "N° de rue du client", "group": "Client"},
    {"key": "npa", "label": "NPA du client", "group": "Client"},
    {"key": "ville", "label": "Ville du client", "group": "Client"},
    {"key": "etat_civil", "label": "État civil", "group": "Client"},
    {"key": "nombre_enfants", "label": "Nombre d'enfants", "group": "Client"},
    {"key": "employeur", "label": "Employeur", "group": "Client"},
    {"key": "profession", "label": "Profession", "group": "Client"},
    {"key": "taux_activite", "label": "Taux d'activité", "group": "Client"},
    {"key": "salaire_annuel", "label": "Salaire annuel", "group": "Client"},
    {"key": "numero_dossier", "label": "N° de dossier", "group": "Client"},
    {"key": "conjoint", "label": "Conjoint (nom complet)", "group": "Conjoint"},
    {"key": "conjoint_nom", "label": "Nom du conjoint", "group": "Conjoint"},
    {"key": "conjoint_prenom", "label": "Prénom du conjoint", "group": "Conjoint"},
    {"key": "conjoint_date_naissance", "label": "Date de naissance du conjoint", "group": "Conjoint"},
    {"key": "conjoint_avs", "label": "N° AVS du conjoint", "group": "Conjoint"},
    {"key": "conseiller", "label": "Nom du conseiller", "group": "Conseiller"},
    {"key": "agent_nom", "label": "Nom de l'agent", "group": "Conseiller"},
    {"key": "agent_prenom", "label": "Prénom de l'agent", "group": "Conseiller"},
    {"key": "agent_full", "label": "Agent (nom complet)", "group": "Conseiller"},
    {"key": "agent_apporteur", "label": "Agent apporteur", "group": "Conseiller"},
    {"key": "today", "label": "Date du jour (jj.mm.aaaa)", "group": "Dates"},
    {"key": "today_long", "label": "Date du jour (longue)", "group": "Dates"},
    {"key": "date_rdv", "label": "Date du rendez-vous", "group": "Dates"},
]


def _civilite_from_sexe(sexe: Any) -> str:
    s = _norm(_safe(sexe))
    if s.startswith("f") or "feminin" in s or s in {"f", "femme", "madame", "mme"}:
        return "Madame"
    if s.startswith("m") or "masculin" in s or s in {"h", "homme", "monsieur", "m."}:
        return "Monsieur"
    return ""


def client_field_values(
    client: Dict[str, Any],
    agent_name: str = "",
    spouse: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    agent_nom, agent_prenom = _split_agent_name(agent_name)
    rue, num_rue = _split_street(_safe(client.get("adresse")))
    conjoint_nom, conjoint_prenom = _split_agent_name(_safe(client.get("conjoint")))
    conjoint_date = ""
    conjoint_avs = ""
    if spouse:
        conjoint_nom = _safe(spouse.get("nom")) or conjoint_nom
        conjoint_prenom = _safe(spouse.get("prenom")) or conjoint_prenom
        conjoint_date = _format_date(spouse.get("date_naissance"))
        conjoint_avs = _format_avs(spouse.get("avs_number"))
        if not _safe(client.get("conjoint")):
            client_conjoint = f"{conjoint_prenom} {conjoint_nom}".strip()
        else:
            client_conjoint = _safe(client.get("conjoint"))
    else:
        client_conjoint = _safe(client.get("conjoint"))

    values = {
        "civilite": _civilite_from_sexe(client.get("sexe")),
        "nom": _safe(client.get("nom")).upper(),
        "prenom": _safe(client.get("prenom")),
        "date_naissance": _format_date(client.get("date_naissance")),
        "avs": _format_avs(client.get("avs_number")),
        "avs_raw": re.sub(r"\D", "", _safe(client.get("avs_number"))),
        "avs_after_756": _avs_after_756(client.get("avs_number")),
        "sexe": _safe(client.get("sexe")),
        "nationalite": _safe(client.get("nationalite")),
        "pays": _safe(client.get("pays")) or "Suisse",
        "email": _safe(client.get("email")),
        "telephone": _safe(client.get("telephone")),
        "adresse": _safe(client.get("adresse")),
        "rue": rue,
        "numero_rue": num_rue,
        "npa": _safe(client.get("npa")),
        "ville": _safe(client.get("ville")),
        "adresse_complete": _format_address(client),
        "etat_civil": _safe(client.get("etat_civil")),
        "nombre_enfants": _safe(client.get("nombre_enfants"), "0"),
        "conjoint": client_conjoint,
        "conjoint_nom": conjoint_nom.upper() if conjoint_nom else "",
        "conjoint_prenom": conjoint_prenom,
        "conjoint_date_naissance": conjoint_date,
        "conjoint_avs": conjoint_avs,
        "employeur": _safe(client.get("employeur")),
        "profession": _safe(client.get("profession")),
        "taux_activite": _safe(client.get("taux_activite")),
        "salaire_annuel": _safe(client.get("salaire_annuel")),
        "agent_nom": agent_nom,
        "agent_prenom": agent_prenom,
        "agent_full": _safe(agent_name),
        "numero_dossier": _safe(client.get("numero_dossier")),
        "today": datetime.now().strftime("%d.%m.%Y"),
        "today_long": _format_date_long(),
        "date_rdv": "",
        "conseiller": _safe(client.get("conseiller")) or _safe(agent_name),
        "agent_apporteur": _safe(client.get("agent_apporteur")),
    }
    if extra:
        for k, v in extra.items():
            if v is not None:
                values[k] = _safe(v)
    return values


def _ensure_need_appearances(writer: PdfWriter) -> None:
    if "/AcroForm" not in writer._root_object:
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(DictionaryObject())
    acro = writer._root_object["/AcroForm"]
    if isinstance(acro, DictionaryObject):
        acro.update({NameObject("/NeedAppearances"): BooleanObject(True)})


def _resolve_field_name(existing: Dict[str, Any], wanted: str) -> Optional[str]:
    if wanted in existing:
        return wanted
    wanted_n = _norm(wanted)
    for actual in existing:
        if _norm(actual) == wanted_n:
            return actual
    return None


def _map_recherche_lpp(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    mapping: Dict[str, Any] = {
        "Nom": values["nom"],
        "Nom 2": "",
        "Prénom": values["prenom"],
        "Prénom 2": "",
        "Date de naissance": values["date_naissance"],
        "AVS": values["avs"],
        "Adresse": values["adresse_complete"],
        "numero de tel": values["telephone"],
        "Texte10": values["email"] or values["agent_full"],
    }
    if options.get("demande_pour_moi_meme"):
        mapping["Case à cocher1"] = "/Oui"
    return mapping


def _map_calcul_rente(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {
        # Identité (page 1 du formulaire)
        "Texte1": values["nom"],
        "Texte2": values["prenom"],
        "Texte3": values["date_naissance"],
        "AVS": values["avs_after_756"] or values["avs_raw"] or values["avs"],
        "Suisse": values["nationalite"] or "Suisse",
        # Adresse
        "Rue": values["rue"] or values["adresse"],
        "Numero de rue": values["numero_rue"],
        "NPA": values["npa"],
        "Localité": values["ville"],
        "Texte11": values["telephone"],
        "Texte12": values["email"],
        "Nationalité": values["nationalite"],
        # Conjoint
        "Nom conjoint": values["conjoint_nom"],
        "Prenom conjoint": values["conjoint_prenom"],
        "Nationalité conjoint": "",
        "AVS Conjoint": "",
        "Date de naissance conjoint": "",
    }

    sexe = _norm(values["sexe"])
    if sexe.startswith("m") or "masculin" in sexe or sexe in {"h", "homme"}:
        mapping["Masculin"] = "/Oui"
        mapping["Féminin"] = "/Off"
    elif sexe.startswith("f") or "feminin" in sexe or sexe in {"f", "femme"}:
        mapping["Féminin"] = "/Oui"
        mapping["Masculin"] = "/Off"

    etat = _norm(values["etat_civil"])
    if "celibat" in etat:
        mapping["célibataire"] = "/Oui"
        mapping["marié(e)"] = "/Off"
    elif "marie" in etat:
        mapping["marié(e)"] = "/Oui"
        mapping["célibataire"] = "/Off"

    return mapping


def _map_lettre_lpp(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "NOM": values["nom"],
        "prénom": values["prenom"],
        "date": values["today_long"],
    }


def _map_lettre_avs(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "Nom": values["nom"],
        "Prénom": values["prenom"],
        "Date": values["today_long"],
    }


def _map_procuration(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "Nom": values["nom"],
        "Prénom": values["prenom"],
        "Date de naissance": values["date_naissance"],
        "Adresse": values["adresse_complete"],
        "N AVS": values["avs"],
        # Champs agent laissés vides volontairement
        "Nom de lAgent": "",
        "Prénom_2": "",
    }


def _map_lettre_decompte(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    fund = options.get("fund") or {}
    # Bloc destinataire complet (nom multi-lignes + adresse) pour le champ AcroForm
    recipient = _safe(
        fund.get("recipient_block")
        or fund.get("raw")
        or ""
    )
    if not recipient:
        name = _safe(fund.get("name") or fund.get("nom"))
        address = _safe(fund.get("address") or fund.get("adresse"))
        if name and address and _norm(name) not in _norm(address):
            recipient = f"{name}\n{address}"
        else:
            recipient = name or address
    return {
        "Adresse caisse": recipient,
        "date du jour": values["today_long"],
        "Nom": values["nom"],
        "Prenom": values["prenom"],
        "AVS": values["avs"],
    }


FIELD_MAPPERS = {
    "procuration_avs_lpp": _map_procuration,
    "recherche_avoirs_lpp": _map_recherche_lpp,
    "calcul_rente_future": _map_calcul_rente,
    "lettre_lpp": _map_lettre_lpp,
    "lettre_avs": _map_lettre_avs,
    "lettre_decompte_lpp": _map_lettre_decompte,
}


# Alias pour remplir dynamiquement n'importe quel AcroForm de la bibliothèque
_GENERIC_ALIASES: Dict[str, List[str]] = {
    "nom": ["nom", "name", "lastname", "last name", "family name", "nachname", "familienname"],
    "prenom": ["prenom", "prénom", "firstname", "first name", "vorname", "given name"],
    "date_naissance": [
        "date de naissance", "datedenaissance", "naissance", "birth", "birthday",
        "date of birth", "geburtsdatum", "dob",
    ],
    "avs": ["avs", "n avs", "navs", "ahv", "numero avs", "n° avs", "no avs", "social security"],
    "adresse": ["adresse", "address", "adresse complete", "adresse_complete", "strasse", "domicile"],
    "rue": ["rue", "street", "voie"],
    "numero_rue": ["numero de rue", "n° rue", "no rue", "hausnummer", "street number"],
    "npa": ["npa", "plz", "zip", "postal code", "code postal"],
    "ville": ["ville", "localite", "localité", "ort", "city", "lieu"],
    "telephone": ["telephone", "téléphone", "tel", "phone", "mobile", "handy", "numero de tel"],
    "email": ["email", "e-mail", "mail", "courriel"],
    "sexe": ["sexe", "gender", "geschlecht"],
    "nationalite": ["nationalite", "nationalité", "nationality", "staatsangehorigkeit"],
    "etat_civil": ["etat civil", "état civil", "civil status", "zivilstand"],
    "employeur": ["employeur", "employer", "arbeitgeber"],
    "profession": ["profession", "beruf", "occupation"],
    "today": ["date", "date du jour", "today", "datum"],
    "today_long": ["date longue", "date du jour long"],
    "conseiller": ["conseiller", "advisor", "agent"],
}


def _guess_source_key_for_field(field_name: str) -> str:
    """Propose une clé CRM pour un nom de champ PDF (suggestion initiale uniquement)."""
    n = _norm(field_name)
    if not n:
        return ""
    checks = [
        ("conjoint_date_naissance", ["date de naissance conjoint", "naissance conjoint", "geburtsdatum partner", "date naissance conjoint"]),
        ("conjoint_avs", ["avs conjoint", "ahv partner", "n avs conjoint", "avsc conjoint"]),
        ("conjoint_prenom", ["prenom conjoint", "prénom conjoint", "vorname partner", "prenom_2", "prenom 2", "prénom_2", "prénom 2"]),
        ("conjoint_nom", ["nom conjoint", "nachname partner", "nom_2", "nom 2"]),
        ("conjoint", ["conjoint", "époux", "epoux", "épouse", "epouse", "partner"]),
        ("date_naissance", [
            "date de naissance", "datedenaissance", "naissance", "birth", "birthday",
            "date of birth", "geburtsdatum", "dob",
        ]),
        ("avs", ["avs", "n avs", "navs", "ahv", "numero avs", "n° avs", "no avs", "social security"]),
        ("conseiller", ["conseiller", "advisor"]),
        ("agent_prenom", ["prenom de lagent", "prénom de lagent", "prenom agent", "prénom agent"]),
        ("agent_nom", ["nom de lagent", "nom agent"]),
        ("agent_full", ["agent", "apporteur"]),
        ("email", ["email", "e-mail", "mail", "courriel"]),
        ("telephone", ["telephone", "téléphone", "tel", "phone", "mobile", "handy", "numero de tel"]),
        ("adresse_complete", ["adresse complete", "adresse_complete", "adresse complète"]),
        ("adresse", ["adresse", "address", "domicile"]),
        ("numero_rue", ["numero de rue", "n° rue", "no rue", "hausnummer", "street number"]),
        ("rue", ["rue", "street", "voie"]),
        ("npa", ["npa", "plz", "zip", "postal code", "code postal"]),
        ("ville", ["ville", "localite", "localité", "ort", "city", "lieu"]),
        ("nationalite", ["nationalite", "nationalité", "nationality"]),
        ("etat_civil", ["etat civil", "état civil", "civil status", "zivilstand"]),
        ("employeur", ["employeur", "employer", "arbeitgeber"]),
        ("profession", ["profession", "beruf", "occupation"]),
        ("sexe", ["sexe", "gender", "geschlecht"]),
        ("today_long", ["date longue", "date du jour long"]),
        ("today", ["date du jour", "today", "datum"]),
        ("prenom", ["prenom", "prénom", "firstname", "first name", "vorname", "given name"]),
        ("nom", ["nom", "lastname", "last name", "family name", "nachname", "familienname"]),
        ("today", ["date"]),
    ]

    # 1) Correspondance exacte
    for key, aliases in checks:
        for alias in aliases:
            if n == _norm(alias):
                return key

    # 2) L'alias est contenu dans le nom du champ (pas l'inverse — évite nom ⊂ prenom)
    best_key = ""
    best_len = 0
    for key, aliases in checks:
        for alias in aliases:
            an = _norm(alias)
            if len(an) < 3:
                continue
            if an in n and len(an) > best_len:
                # Garde-fous
                if key == "nom" and any(x in n for x in ("prenom", "prénom", "conjoint", "agent")):
                    continue
                if key == "prenom" and any(x in n for x in ("agent", "conjoint")):
                    continue
                if key == "today" and any(x in n for x in ("naissance", "birth")):
                    continue
                if key == "adresse" and any(x in n for x in ("email", "mail")):
                    continue
                best_key = key
                best_len = len(an)
    return best_key


def suggest_field_mapping(field_names: List[str]) -> Dict[str, str]:
    """Suggestions initiales pdf_field -> crm_key (à confirmer par l'utilisateur)."""
    return {name: _guess_source_key_for_field(name) for name in field_names}


def suggest_widget_mapping(widgets: List[Dict[str, Any]]) -> Dict[str, str]:
    """Suggestions par widget unique (id -> crm_key)."""
    return {
        w["id"]: _guess_source_key_for_field(w.get("original_name") or "")
        for w in widgets
    }


def prepare_library_form_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Donne un nom interne unique à chaque widget AcroForm (même si le libellé est identique)
    et renvoie métadonnées de position pour l'éditeur visuel.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    widgets: List[Dict[str, Any]] = []
    idx = 0
    for page_index in range(len(doc)):
        page = doc[page_index]
        pw = float(page.rect.width) or 1.0
        ph = float(page.rect.height) or 1.0
        for widget in page.widgets() or []:
            original = (widget.field_name or "").strip() or f"Champ_{idx + 1}"
            unique = f"w_{idx:04d}"
            try:
                widget.field_name = unique
                widget.update()
            except Exception:
                # Certains widgets protégés : on garde le nom d'origine
                unique = widget.field_name or unique
            r = widget.rect
            widgets.append(
                {
                    "id": unique,
                    "original_name": original,
                    "unique_name": unique,
                    "page": page_index,
                    "field_type": str(getattr(widget, "field_type_string", None) or getattr(widget, "field_type", "") or "text"),
                    "rect": {
                        "x": max(0.0, min(1.0, float(r.x0) / pw)),
                        "y": max(0.0, min(1.0, float(r.y0) / ph)),
                        "w": max(0.0, min(1.0, float(r.x1 - r.x0) / pw)),
                        "h": max(0.0, min(1.0, float(r.y1 - r.y0) / ph)),
                    },
                }
            )
            idx += 1

    out = io.BytesIO()
    page_count = len(doc)
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    prepared = out.getvalue()
    return {
        "pdf_bytes": prepared,
        "widgets": widgets,
        "page_count": page_count,
        "field_names": [w["id"] for w in widgets],
        "field_mapping": suggest_widget_mapping(widgets),
    }


def render_pdf_page_png(pdf_bytes: bytes, page_index: int = 0, dpi: float = 144.0) -> bytes:
    """Rend une page PDF en PNG pour l'aperçu de mapping."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    if page_index < 0 or page_index >= len(doc):
        doc.close()
        raise IndexError("Page introuvable")
    page = doc[page_index]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    png = pix.tobytes("png")
    doc.close()
    return png


def _fill_with_pymupdf(
    pdf_bytes: bytes,
    values: Dict[str, str],
    field_mapping: Dict[str, str],
) -> bytes:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        for widget in page.widgets() or []:
            name = widget.field_name or ""
            source_key = field_mapping.get(name)
            if not source_key:
                continue
            text = values.get(source_key, "")
            try:
                widget.field_value = text
                widget.update()
            except Exception:
                continue
    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    return out.getvalue()


def _build_mapped_field_map(
    values: Dict[str, str],
    existing_fields: Dict[str, Any],
    field_mapping: Dict[str, str],
) -> Dict[str, Any]:
    """Construit le fill map strictement depuis la config utilisateur."""
    mapping: Dict[str, Any] = {}
    for pdf_field, source_key in (field_mapping or {}).items():
        if not source_key:
            continue
        actual = _resolve_field_name(existing_fields, pdf_field)
        if not actual:
            # Si le PDF a déjà été uniqueifié, la clé est le nom exact
            if pdf_field in existing_fields:
                actual = pdf_field
            else:
                continue
        mapping[actual] = values.get(source_key, "")
    return mapping


def _guess_value_for_field(field_name: str, values: Dict[str, str]) -> Optional[str]:
    """Associe un nom de champ AcroForm à une valeur client (heuristique)."""
    n = _norm(field_name)
    checks = [
        ("date_naissance", values.get("date_naissance")),
        ("avs", values.get("avs")),
        ("prenom", values.get("prenom")),
        ("nom", values.get("nom")),
        ("adresse", values.get("adresse_complete") or values.get("adresse")),
        ("rue", values.get("rue")),
        ("numero_rue", values.get("numero_rue")),
        ("npa", values.get("npa")),
        ("ville", values.get("ville")),
        ("telephone", values.get("telephone")),
        ("email", values.get("email")),
        ("sexe", values.get("sexe")),
        ("nationalite", values.get("nationalite")),
        ("etat_civil", values.get("etat_civil")),
        ("employeur", values.get("employeur")),
        ("profession", values.get("profession")),
        ("today_long", values.get("today_long")),
        ("today", values.get("today")),
        ("conseiller", values.get("conseiller")),
    ]
    for key, val in checks:
        if not val:
            continue
        aliases = _GENERIC_ALIASES.get(key, [key])
        for alias in aliases:
            an = _norm(alias)
            if n == an or an in n or n in an:
                if key == "nom" and ("prenom" in n or "prénom" in n or "agent" in n or "conjoint" in n):
                    continue
                if key == "prenom" and ("agent" in n or "conjoint" in n):
                    continue
                if key == "today" and ("naissance" in n or "birth" in n):
                    continue
                if key == "adresse" and ("email" in n or "mail" in n):
                    continue
                return val
    return None


def _build_generic_field_map(values: Dict[str, str], existing_fields: Dict[str, Any]) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for field_name in existing_fields:
        guessed = _guess_value_for_field(field_name, values)
        if guessed is not None:
            mapping[field_name] = guessed
    return mapping


def fill_pdf_bytes_with_client(
    pdf_bytes: bytes,
    client: Dict[str, Any],
    agent_name: str = "",
    field_mapping: Optional[Dict[str, str]] = None,
    spouse: Optional[Dict[str, Any]] = None,
    extra_values: Optional[Dict[str, str]] = None,
) -> bytes:
    """Préremplit un PDF AcroForm avec les données client (mapping manuel ou heuristique)."""
    values = client_field_values(
        client,
        agent_name=agent_name,
        spouse=spouse,
        extra=extra_values,
    )

    if field_mapping is not None:
        try:
            return _fill_with_pymupdf(pdf_bytes, values, field_mapping)
        except Exception:
            pass  # fallback pypdf ci-dessous

    from pypdf.generic import IndirectObject, NumberObject

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)
    existing = reader.get_fields() or {}
    if field_mapping is not None:
        field_map = _build_mapped_field_map(values, existing, field_mapping)
    else:
        field_map = _build_generic_field_map(values, existing)

    text_values: Dict[str, Any] = {}
    multiline_names: set = set()
    for name, val in field_map.items():
        text = "" if val is None else str(val)
        if "\n" in text or _norm(name).startswith("adresse"):
            multiline_names.add(name)
            text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r")
        text_values[name] = text

    MULTILINE = 1 << 12
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        if isinstance(annots, IndirectObject):
            annots = annots.get_object()
        for annot in annots:
            obj = annot.get_object() if isinstance(annot, IndirectObject) else annot
            name = obj.get("/T")
            if name and str(name) in multiline_names:
                ff = int(obj.get("/Ff", 0) or 0) | MULTILINE
                obj[NameObject("/Ff")] = NumberObject(ff)

    for page in writer.pages:
        if text_values:
            try:
                writer.update_page_form_field_values(page, text_values, auto_regenerate=True)
            except TypeError:
                try:
                    writer.update_page_form_field_values(page, text_values)
                except Exception:
                    continue
            except Exception:
                continue

    _ensure_need_appearances(writer)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def inspect_pdf_field_names(pdf_bytes: bytes) -> List[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return list((reader.get_fields() or {}).keys())


def _fill_acroform(
    template_path: Path,
    template_id: str,
    values: Dict[str, str],
    options: Optional[Dict[str, Any]] = None,
) -> bytes:
    from pypdf.generic import IndirectObject, NumberObject

    reader = PdfReader(str(template_path))
    writer = PdfWriter()
    writer.append(reader)

    mapper = FIELD_MAPPERS.get(template_id)
    if not mapper:
        raise ValueError(f"Aucun mapping AcroForm pour {template_id}")

    field_map = mapper(values, options)
    # #region agent log
    if template_id in ("procuration_avs_lpp", "lettre_decompte_lpp"):
        try:
            import json as _json
            _log = Path(__file__).resolve().parents[2] / "debug-5656aa.log"
            _log.open("a", encoding="utf-8").write(_json.dumps({
                "sessionId": "5656aa",
                "hypothesisId": "M",
                "location": "pdf_generator.py:_fill_acroform",
                "message": "acroform field map",
                "data": {
                    "template_id": template_id,
                    "Adresse caisse": (field_map.get("Adresse caisse") or "")[:500],
                    "adresse_len": len(field_map.get("Adresse caisse") or ""),
                },
                "timestamp": int(datetime.now().timestamp() * 1000),
                "runId": "post-fix",
            }) + "\n")
        except Exception:
            pass
    # #endregion
    existing = reader.get_fields() or {}
    text_values: Dict[str, Any] = {}
    button_values: Dict[str, str] = {}
    multiline_names: set[str] = set()

    for wanted, val in field_map.items():
        actual = _resolve_field_name(existing, wanted)
        if actual is None:
            continue
        if isinstance(val, str) and val.startswith("/"):
            button_values[actual] = val
        else:
            text = "" if val is None else str(val)
            # Champs adresse / multi-lignes : garder tout le texte, sauts PDF = \r
            if "\n" in text or wanted.lower().startswith("adresse") or actual.lower().startswith("adresse"):
                multiline_names.add(actual)
                text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r")
            text_values[actual] = text

    # Activer le flag Multiline (bit 13) + élargir le champ Adresse caisse
    MULTILINE = 1 << 12
    adresse_rect = None
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        if isinstance(annots, IndirectObject):
            annots = annots.get_object()
        for annot in annots:
            obj = annot.get_object() if isinstance(annot, IndirectObject) else annot
            name = obj.get("/T")
            if name is None:
                continue
            name_s = str(name)
            if name_s in multiline_names or name_s.lower().startswith("adresse"):
                ff = int(obj.get("/Ff", 0) or 0) | MULTILINE
                obj[NameObject("/Ff")] = NumberObject(ff)
                # Élargir la zone destinataire pour éviter toute troncature visuelle
                if "adresse" in name_s.lower():
                    rect = obj.get("/Rect")
                    if rect is not None and len(rect) >= 4:
                        from pypdf.generic import ArrayObject, FloatObject
                        x0, y0, x1, y1 = [float(v) for v in rect[:4]]
                        x0 = min(x0, 300.0)
                        y0 = min(y0, 575.0)
                        x1 = max(x1, 540.0)
                        y1 = max(y1, 705.0)
                        obj[NameObject("/Rect")] = ArrayObject([
                            FloatObject(x0), FloatObject(y0), FloatObject(x1), FloatObject(y1)
                        ])
                        adresse_rect = (x0, y0, x1, y1)

    for page in writer.pages:
        if text_values:
            try:
                writer.update_page_form_field_values(page, text_values, auto_regenerate=True)
            except TypeError:
                try:
                    writer.update_page_form_field_values(page, text_values)
                except Exception:
                    continue
            except Exception:
                continue

        annots = page.get("/Annots")
        if not annots:
            continue
        if isinstance(annots, IndirectObject):
            annots = annots.get_object()
        for annot in annots:
            obj = annot.get_object() if isinstance(annot, IndirectObject) else annot
            name = obj.get("/T")
            if name not in button_values:
                continue
            target = button_values[name]
            obj[NameObject("/V")] = NameObject(target)
            obj[NameObject("/AS")] = NameObject(target)

    _ensure_need_appearances(writer)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    # Overlay texte pour Adresse caisse (impression fiable, sans ellipsis mono-ligne)
    if template_id == "lettre_decompte_lpp":
        addr = field_map.get("Adresse caisse") or ""
        if addr:
            pdf_bytes = _overlay_multiline_text(
                pdf_bytes,
                addr.replace("\r", "\n"),
                rect=adresse_rect or (300.0, 575.0, 540.0, 705.0),
            )
    return pdf_bytes


def _overlay_multiline_text(pdf_bytes: bytes, text: str, rect: tuple[float, float, float, float]) -> bytes:
    """Dessine un bloc texte multi-lignes (wrap) par-dessus le champ formulaire."""
    try:
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.utils import simpleSplit
        from pypdf.generic import IndirectObject
    except Exception:
        return pdf_bytes

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes
    page0 = reader.pages[0]
    page_w = float(page0.mediabox.width)
    page_h = float(page0.mediabox.height)
    x0, y0, x1, y1 = rect
    box_w = max(40.0, x1 - x0)
    box_h = max(40.0, y1 - y0)

    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=(page_w, page_h))
    # Fond blanc pour masquer une éventuelle apparence tronquée du champ
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(x0 - 1, y0 - 1, box_w + 2, box_h + 2, fill=1, stroke=0)
    canvas.setFillColorRGB(0, 0, 0)

    font_size = 10
    leading = font_size + 2
    # Réduire la police si trop de lignes
    lines: List[str] = []
    while font_size >= 8:
        lines = []
        leading = font_size + 2
        for para in (text or "").splitlines() or [""]:
            wrapped = simpleSplit(para, "Helvetica", font_size, box_w - 4) or [""]
            lines.extend(wrapped)
        if len(lines) * leading <= box_h - 4:
            break
        font_size -= 1

    canvas.setFont("Helvetica", font_size)
    y = y1 - font_size - 2
    for line in lines:
        if y < y0:
            break
        canvas.drawString(x0 + 2, y, line)
        y -= leading
    canvas.save()
    packet.seek(0)

    overlay = PdfReader(packet)
    writer = PdfWriter()
    writer.append(reader)
    if overlay.pages:
        writer.pages[0].merge_page(overlay.pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def generate_document_pdf(
    template_id: str,
    client: Dict[str, Any],
    agent_name: str = "",
    custom_filename: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> tuple[bytes, Dict[str, Any]]:
    template = get_template(template_id)
    template_path = TEMPLATES_DIR / template["filename"]
    if not template_path.exists():
        raise FileNotFoundError(f"Modèle introuvable: {template['filename']}")

    values = client_field_values(client, agent_name=agent_name)
    pdf_bytes = _fill_acroform(template_path, template_id, values, options=options)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    client_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{values['nom']}_{values['prenom']}").strip("_") or "client"
    if custom_filename:
        output_name = custom_filename if custom_filename.lower().endswith(".pdf") else f"{custom_filename}.pdf"
        output_name = re.sub(r"[\\\\/:*?\"<>|]+", "_", output_name)
    else:
        output_name = f"{template['output_prefix']}_{client_slug}_{stamp}.pdf"

    meta = {
        "original_filename": output_name,
        "category": template["category"],
        "template_id": template["id"],
        "template_label": template["label"],
        "checklist_item": template.get("checklist_item"),
        "content_type": "application/pdf",
    }
    return pdf_bytes, meta


def generate_demand_pack(
    pack_id: str,
    client: Dict[str, Any],
    agent_name: str = "",
) -> List[tuple[bytes, Dict[str, Any]]]:
    pack = DEMAND_PACKS.get(pack_id)
    if not pack:
        raise KeyError(pack_id)
    results = []
    for template_id in pack["templates"]:
        results.append(
            generate_document_pdf(
                template_id,
                client,
                agent_name=agent_name,
                options=pack.get("options") or {},
            )
        )
    # #region agent log
    try:
        import json as _json
        from pathlib import Path as _Path
        _log = _Path(__file__).resolve().parents[2] / "debug-5656aa.log"
        _lettre = TEMPLATES_DIR / "lettre_avs.pdf"
        _log.open("a", encoding="utf-8").write(_json.dumps({
            "sessionId": "5656aa",
            "hypothesisId": "A",
            "location": "pdf_generator.py:generate_demand_pack",
            "message": "demand pack generated",
            "data": {
                "pack_id": pack_id,
                "templates": list(pack["templates"]),
                "output_template_ids": [m.get("template_id") for _, m in results],
                "output_names": [m.get("original_filename") for _, m in results],
                "lettre_avs_bytes": _lettre.stat().st_size if _lettre.exists() else None,
            },
            "timestamp": int(datetime.now().timestamp() * 1000),
            "runId": "post-fix",
        }) + "\n")
    except Exception:
        pass
    # #endregion
    return results


def generate_decompte_letters(
    client: Dict[str, Any],
    funds: List[Dict[str, Any]],
    agent_name: str = "",
) -> List[tuple[bytes, Dict[str, Any]]]:
    """Une lettre de décompte par caisse sélectionnée."""
    results: List[tuple[bytes, Dict[str, Any]]] = []
    for fund in funds:
        name = _safe(fund.get("name") or fund.get("nom") or "Caisse")
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:60] or "Caisse"
        pdf_bytes, meta = generate_document_pdf(
            "lettre_decompte_lpp",
            client,
            agent_name=agent_name,
            custom_filename=f"Demande_decompte_{slug}.pdf",
            options={"fund": fund},
        )
        meta["caisse_name"] = name
        meta["caisse_address"] = _safe(fund.get("address") or fund.get("adresse"))
        meta["caisse_reference"] = _safe(fund.get("reference") or fund.get("ref"))
        results.append((pdf_bytes, meta))
    return results


def _find_tessdata() -> Optional[str]:
    import os
    candidates = [
        os.environ.get("TESSDATA_PREFIX", "").rstrip("/\\"),
        *(os.environ.get("OCR_TESSDATA_CANDIDATES", "").split(":")),
        r"C:\Program Files\Tesseract-OCR\tessdata",
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
    ]
    for p in candidates:
        if not p:
            continue
        path = Path(p)
        if path.exists() and any(path.glob("*.traineddata")):
            return str(path)
    # Walk common roots
    for root in (Path("/usr/share/tesseract-ocr"), Path("/usr/share")):
        if not root.exists():
            continue
        for child in root.rglob("tessdata"):
            if child.is_dir() and any(child.glob("*.traineddata")):
                return str(child)
    return None


def _ocr_languages(tessdata: Optional[str]) -> str:
    preferred = ("fra", "deu", "eng")
    if not tessdata:
        return "eng"
    available = []
    for lang in preferred:
        if (Path(tessdata) / f"{lang}.traineddata").exists():
            available.append(lang)
    return "+".join(available) if available else "eng"


def _ocr_pdf_text(pdf_bytes: bytes) -> str:
    """OCR via PyMuPDF (render) + Tesseract — robuste pour PDF scannés."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return ""

    import os
    import logging

    log = logging.getLogger("server")
    tessdata = _find_tessdata()
    language = _ocr_languages(tessdata)
    if tessdata:
        os.environ.setdefault("TESSDATA_PREFIX", tessdata)

    text_parts: List[str] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        # 1) pytesseract on rendered pages (most reliable)
        try:
            import pytesseract
            from PIL import Image

            tess_cmd = os.environ.get("TESSERACT_CMD")
            if not tess_cmd:
                for candidate in (
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    "/usr/bin/tesseract",
                    "tesseract",
                ):
                    if candidate == "tesseract" or Path(candidate).exists():
                        tess_cmd = candidate
                        break
            if tess_cmd and tess_cmd != "tesseract":
                pytesseract.pytesseract.tesseract_cmd = tess_cmd

            for page in doc:
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                page_text = pytesseract.image_to_string(img, lang=language) or ""
                text_parts.append(page_text)
            joined = "\n".join(text_parts)
            if len(re.sub(r"\s+", "", joined)) >= 40:
                log.info("OCR pytesseract ok pages=%s chars=%s langs=%s tessdata=%s", len(doc), len(joined), language, tessdata)
                return joined
        except Exception as e:
            log.warning("OCR pytesseract failed: %s", e)
            text_parts = []

        # 2) Fallback PyMuPDF built-in OCR
        for page in doc:
            try:
                kwargs = {"dpi": 200, "language": language}
                if tessdata:
                    kwargs["tessdata"] = tessdata
                tp = page.get_textpage_ocr(**kwargs)
                text_parts.append(page.get_text(textpage=tp) or "")
            except Exception as e:
                log.warning("OCR fitz page failed: %s", e)
                text_parts.append(page.get_text("text") or "")
    finally:
        doc.close()

    joined = "\n".join(text_parts)
    log.info("OCR fitz fallback chars=%s langs=%s tessdata=%s", len(joined), language, tessdata)
    return joined


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if len(re.sub(r"\s+", "", text)) >= 80:
        return text
    ocr_text = _ocr_pdf_text(pdf_bytes)
    return ocr_text if ocr_text.strip() else text


def _parse_funds_from_text(text: str) -> List[Dict[str, str]]:
    """
    Détection générique des institutions dans une réponse de la Centrale du 2e pilier.
    Basée sur la structure du courrier (bloc après « institution suivante »),
    sans liste fixe de noms de caisses.
    """
    reference = ""
    ref_m = re.search(r"(?:n[°o]\.?\s*de\s*r[ée]f[ée]rence|reference)\s*[:\s]\s*([0-9./-]+)", text, re.I)
    if ref_m:
        reference = ref_m.group(1).strip()

    found: List[Dict[str, str]] = []
    seen = set()

    def _is_address_line(line: str) -> bool:
        """Lignes d'adresse postale (pas le début d'un nom du type 'CP paritaire…')."""
        low = line.lower().strip()
        if re.match(r"^\d{4}\b", low):  # NPA en tête
            return True
        if re.match(
            r"^(c/o\b|postfach\b|case\s+postale\b|case\s+postal\b|p\.?\s*o\.?\s*box\b|"
            r"rue\b|route\b|avenue\b|chemin\b|boulevard\b|quai\b|place\b|"
            r"strasse\b|weg\b|gasse\b|allee\b|allée\b)",
            low,
            re.I,
        ):
            return True
        # Case postale / Postfach au milieu, ou NPA + localité
        if re.search(r"\b(case\s+postale|postfach)\b", low) and re.search(r"\d", low):
            return True
        if re.search(r"\b\d{4}\s+[A-Za-zÀ-ÿ]", line):
            return True
        return False

    def _is_boilerplate(line: str) -> bool:
        low = _norm(line)
        starts = (
            "nous attirons", "la comparaison", "nous esperons", "nous vous",
            "afin d", "chaque annee", "madame monsieur", "agence mendes",
            "centrale du", "fonds de garantie",
        )
        return any(low.startswith(s) for s in starts)

    def _is_name_continuation(line: str) -> bool:
        if not line or _is_boilerplate(line) or _is_address_line(line):
            return False
        if len(line) > 90:
            return False
        # Phrases de courrier, pas des noms d'institution
        low = line.lower()
        if any(x in low for x in ("nous ", "votre attention", "seul l", "competente", "compétente")):
            return False
        return True

    def _add_block(lines: List[str]) -> None:
        if not lines:
            return
        # Séparer nom (une ou plusieurs lignes) et adresse
        name_lines = [lines[0]]
        idx = 1
        while idx < len(lines) and _is_name_continuation(lines[idx]):
            name_lines.append(lines[idx])
            idx += 1
        addr_lines = lines[idx:]
        # Si aucune adresse reconnue mais lignes restantes, tout garder dans le bloc destinataire
        name = re.sub(r"\s+", " ", " ".join(name_lines)).strip(" :.-")
        # Réparer coupures OCR fréquentes en fin de ligne (« … de », « … et »)
        name = re.sub(r"\s+", " ", name)
        if len(name) < 5 or len(name) > 200:
            return
        low = name.lower()
        # Rejeter uniquement le vrai bruit (pas « fondation de libre passage … »)
        reject_starts = (
            "nous ", "votre ", "vos ", "afin ", "chaque ", "depuis ", "vue d",
            "il existe", "la comparaison", "en raison", "eu egard", "eu égard",
            "responsable", "madame", "monsieur", "demande de recherche",
        )
        if any(low.startswith(s) for s in reject_starts):
            return
        if low.startswith("c/o ") or low.startswith("postfach") or low.startswith("rue "):
            return
        if any(x in low for x in ("agence mendes", "centrale du 2", "fonds de garantie")):
            return

        address = "\n".join(addr_lines)
        recipient_block = "\n".join(lines)
        key = _norm(name)
        if key in seen:
            return
        seen.add(key)
        found.append({
            "name": name,
            "address": address,
            "reference": reference,
            "raw": recipient_block,
            "recipient_block": recipient_block,
        })

    # 1) Blocs structurés après « institution(s) suivante(s) »
    for m in re.finditer(r"institutions?\s+suivantes?", text, re.I):
        chunk = text[m.end(): m.end() + 800]
        colon = re.search(r"[:：]\s*", chunk)
        body = chunk[colon.end():] if colon else chunk
        stop = re.search(
            r"\n\s*Nous\s+attirons|\n\s*La\s+comparaison|\n\s*Nous\s+esp[ée]rons|\n\s*En\s+raison",
            body,
            re.I,
        )
        if stop:
            body = body[: stop.start()]
        lines = []
        for ln in body.splitlines():
            cleaned = re.sub(r"\s+", " ", ln).strip(" :\t•-")
            if not cleaned or cleaned in {":", "-", "•"}:
                continue
            if _is_boilerplate(cleaned):
                break
            lines.append(cleaned)
        _add_block(lines)

    if found:
        return found[:40]

    # 2) Fallback générique : bloc se terminant par NPA + localité, précédé d'un nom d'institution
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    i = 0
    while i < len(lines):
        # Chercher une ligne NPA (fin d'adresse suisse)
        if not re.search(r"\b\d{4}\s+[A-Za-zÀ-ÿ]", lines[i]) and not re.match(r"^\d{4}\b", lines[i]):
            i += 1
            continue
        # Remonter pour trouver le début du bloc (max 6 lignes)
        start = i
        for back in range(1, 7):
            j = i - back
            if j < 0:
                break
            if _is_boilerplate(lines[j]):
                break
            start = j
        block = lines[start: i + 1]
        # Le nom ne doit pas être une simple ligne d'adresse
        if block and not _is_address_line(block[0]):
            # Éviter en-têtes / pied de page
            head = block[0].lower()
            if not any(x in head for x in ("agence mendes", "centrale", "fonds de garantie", "route de saint")):
                _add_block(block)
        i += 1

    return found[:40]


def extract_pension_funds_from_pdf(pdf_bytes: bytes) -> List[Dict[str, str]]:
    """Extrait une liste de caisses / fondations depuis un PDF de réponse LPP."""
    import logging
    text = _extract_pdf_text(pdf_bytes)
    funds = _parse_funds_from_text(text)
    # #region agent log
    try:
        import json as _json
        _log = Path(__file__).resolve().parents[2] / "debug-5656aa.log"
        _log.open("a", encoding="utf-8").write(_json.dumps({
            "sessionId": "5656aa",
            "hypothesisId": "L",
            "location": "pdf_generator.py:extract_pension_funds_from_pdf",
            "message": "LPP response parsed generic",
            "data": {
                "text_len": len(text),
                "fund_count": len(funds),
                "funds": [{
                    "name": f.get("name"),
                    "address": f.get("address"),
                    "recipient_block": f.get("recipient_block") or f.get("raw"),
                    "reference": f.get("reference"),
                } for f in funds],
                "tessdata": _find_tessdata(),
            },
            "timestamp": int(datetime.now().timestamp() * 1000),
            "runId": "post-fix",
        }) + "\n")
    except Exception:
        pass
    # #endregion
    logging.getLogger("server").info(
        "LPP parse text_len=%s funds=%s names=%s",
        len(text),
        len(funds),
        [f.get("name") for f in funds],
    )
    return funds