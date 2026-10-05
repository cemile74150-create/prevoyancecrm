"""
Génération de documents PDF préremplis à partir des données client.
"""
from __future__ import annotations

import io
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, DictionaryObject, NameObject

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "forms"

# Bornes de sécurité pour le shrink-to-fit (la taille cible vient du PDF)
PDF_FILL_ABS_MIN_FONT = 6.0
PDF_FILL_ABS_MAX_FONT = 14.0
PDF_FILL_FALLBACK_SIZE = 11.0
PDF_FILL_FALLBACK_ACRO = "Helv"
PDF_FILL_FALLBACK_RL = "Helvetica"

_REPORTLAB_FONT_CACHE: Dict[str, str] = {}


DOCUMENT_TEMPLATES = [
    {
        "id": "mandat_de_gestion",
        "label": "Mandat de gestion",
        "description": "Mandat de gestion + devoir d'information LSA (modèle MG + LSA)",
        "filename": "mandat_mg_lsa.pdf",
        "mode": "acroform",
        "output_prefix": "Mandat_MG_LSA",
        "category": "Mandat de gestion",
        "checklist_item": "Mandat de gestion",
        "filename_no_stamp": True,
        "template_version": "mg_lsa_v2",
    },
    {
        "id": "procuration_avs_lpp",
        "label": "Procuration AVS/LPP",
        "description": "Procuration Agence Mendes pour AVS et 2e pilier",
        "filename": "procuration_avs_lpp.pdf",
        "mode": "acroform",
        "output_prefix": "Procuration_AVS_LPP",
        "category": "Procuration",
        "checklist_item": "Demande LPP",
    },
    {
        "id": "recherche_avoirs_lpp",
        "label": "Formulaire de recherche d'avoirs LPP",
        "description": "Demande de recherche d'avoirs auprès de la Centrale du 2e pilier",
        "filename": "recherche_avoirs_lpp.pdf",
        "mode": "acroform",
        "output_prefix": "Recherche_avoirs_LPP",
        "category": "Formulaire de recherche LPP",
        "checklist_item": "Demande LPP",
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
        "filename": "lettre_recherche_avoirs_lpp.template.docx",
        "mode": "word_template",
        "output_prefix": "Lettre_Recherche_LPP",
        "category": "Courriers",
        "checklist_item": "Demande LPP",
    },
    {
        "id": "lettre_avs",
        "label": "Lettre d'accompagnement — Demande AVS",
        "description": "Courrier à la Caisse suisse de compensation",
        "filename": "lettre_demande_avs.original.docx",
        "mode": "word_docx",
        "output_prefix": "Lettre_Demande_AVS",
        "output_ext": "pdf",
        "filename_no_stamp": True,
        "category": "Courriers",
        "checklist_item": "Formulaire AVS",
        "word_download": True,
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
    out: List[Dict[str, Any]] = []
    for t in DOCUMENT_TEMPLATES:
        path = TEMPLATES_DIR / t["filename"]
        item = {
            "id": t["id"],
            "label": t["label"],
            "description": t["description"],
            "category": t["category"],
            "checklist_item": t.get("checklist_item"),
            "available": _template_is_available(t),
        }
        if t.get("template_version"):
            item["template_version"] = t["template_version"]
        if path.exists():
            item["template_bytes"] = path.stat().st_size
        out.append(item)
    return out


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


def _template_is_available(template: Dict[str, Any]) -> bool:
    path = TEMPLATES_DIR / template["filename"]
    if path.exists():
        return True
    if template.get("id") == "lettre_lpp":
        return (TEMPLATES_DIR / "lettre_recherche_avoirs_lpp.original.docx").exists()
    if template.get("id") == "lettre_avs":
        return (TEMPLATES_DIR / "lettre_demande_avs.original.docx").exists()
    return False


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


def _clean_pdf_text(value: Any) -> str:
    """Texte PDF : jamais undefined / null / None."""
    text = _safe(value)
    if text.lower() in {"undefined", "null", "none", "nan"}:
        return ""
    return text


def _format_date(value: Any) -> str:
    """Normalise une date CRM vers JJ.MM.AAAA (jamais année seule / jamais double-expansion)."""
    try:
        from swiss_dates import format_swiss_date

        return format_swiss_date(value)
    except Exception:
        text = _safe(value)
        if not text:
            return ""
        if "T" in text:
            text = text.split("T", 1)[0]
        text = text.strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text[:10], fmt).strftime("%d.%m.%Y")
            except ValueError:
                continue
        m = re.match(r"^(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,6})$", text)
        if m:
            day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
            if len(year) == 6 and year.startswith("20"):
                year = year[2:]
            elif len(year) == 2:
                year = ("20" if int(year) <= 30 else "19") + year
            return f"{day}.{month}.{year}"
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
    {"key": "pays_residence", "label": "Pays de résidence", "group": "Client"},
    {"key": "frontalier", "label": "Frontalier (oui/non)", "group": "Client"},
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
    if _safe(client.get("conjoint_nom")):
        conjoint_nom = _safe(client.get("conjoint_nom"))
    if _safe(client.get("conjoint_prenom")):
        conjoint_prenom = _safe(client.get("conjoint_prenom"))
    conjoint_date = _format_date(client.get("conjoint_date_naissance"))
    conjoint_avs = ""
    conjoint_avs_crm = ""
    if spouse:
        conjoint_nom = _safe(spouse.get("nom")) or conjoint_nom
        conjoint_prenom = _safe(spouse.get("prenom")) or conjoint_prenom
        conjoint_date = _format_date(spouse.get("date_naissance"))
        conjoint_avs = _format_avs(spouse.get("avs_number"))
        conjoint_avs_crm = _safe(spouse.get("avs_number"))
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
        # Valeur telle que saisie dans le CRM, séparateurs et espaces conservés.
        "avs_crm": _safe(client.get("avs_number")),
        "avs_raw": re.sub(r"\D", "", _safe(client.get("avs_number"))),
        "avs_after_756": _avs_after_756(client.get("avs_number")),
        "sexe": _safe(client.get("sexe")),
        "nationalite": _safe(client.get("nationalite")),
        # Pas de valeur inventée : vide si non renseigné
        "pays_residence": _safe(client.get("pays_residence") or client.get("pays")),
        "pays": _safe(client.get("pays_residence") or client.get("pays")),
        "frontalier": _safe(client.get("frontalier")).lower(),
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
        "conjoint_avs_crm": conjoint_avs_crm,
        "conjoint_sexe": _safe((spouse or {}).get("sexe") or client.get("conjoint_sexe") or client.get("sexe_conjoint")),
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
        "conseiller_finma": _safe(client.get("conseiller_finma") or client.get("finma_number")),
        "finma_number": _safe(client.get("conseiller_finma") or client.get("finma_number")),
        "agent_apporteur": _safe(client.get("agent_apporteur")),
        "raison_sociale": _safe(client.get("raison_sociale") or client.get("societe")),
    }
    if extra:
        for k, v in extra.items():
            if v is not None:
                values[k] = _safe(v)
    return values


def _ensure_need_appearances(writer: PdfWriter, acro_font: str = PDF_FILL_FALLBACK_ACRO, size: float = PDF_FILL_FALLBACK_SIZE) -> None:
    if "/AcroForm" not in writer._root_object:
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(DictionaryObject())
    acro = writer._root_object["/AcroForm"]
    if isinstance(acro, DictionaryObject):
        from pypdf.generic import TextStringObject
        acro.update({
            NameObject("/NeedAppearances"): BooleanObject(True),
            NameObject("/DA"): TextStringObject(_acroform_da_string(size, acro_font)),
        })


def _parse_da_string(da: Any) -> tuple[Optional[str], Optional[float]]:
    """Extrait (font, size) depuis une chaîne /DA AcroForm, ex. '/Helv 11 Tf 0 g'."""
    if da is None:
        return None, None
    s = str(da)
    m = re.search(r"/([A-Za-z0-9_-]+)\s+(\d+(?:\.\d+)?)\s+Tf", s)
    if not m:
        return None, None
    try:
        return m.group(1), float(m.group(2))
    except ValueError:
        return m.group(1), None


def _font_is_bold(font_name: str, flags: int = 0) -> bool:
    n = (font_name or "").lower()
    return bool(flags & 16) or any(tok in n for tok in ("bold", "black", "heavy", "semibold"))


def _map_to_acroform_font(font_name: str, bold: bool = False) -> str:
    """Police AcroForm standard (Base-14) la plus proche."""
    n = (font_name or "").lower()
    if any(t in n for t in ("times", "georgia", "garamond", "serif")):
        return "Times-Bold" if bold else "Times-Roman"
    if any(t in n for t in ("courier", "consolas", "mono")):
        return "CourB" if bold else "Cour"
    return "HelvB" if bold else "Helv"


def _bundled_font_path(filename: str) -> Optional[Path]:
    candidate = Path(__file__).resolve().parent / "fonts" / filename
    return candidate if candidate.exists() else None


def _windows_font_path(filename: str) -> Optional[Path]:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidate = windir / "Fonts" / filename
    return candidate if candidate.exists() else None


def _linux_font_candidates(bold: bool = False) -> List[Path]:
    """Polices système usuelles sur Linux (Railway / Docker)."""
    if bold:
        return [
            Path("/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
        ]
    return [
        Path("/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
    ]


def _resolve_ttf_candidates(win_files: List[str], bold: bool) -> List[Path]:
    """Priorité : polices embarquées → Windows → Linux."""
    candidates: List[Path] = []
    for fname in win_files:
        for resolver in (_bundled_font_path, _windows_font_path):
            p = resolver(fname)
            if p:
                candidates.append(p)
    candidates.extend(_linux_font_candidates(bold))
    return candidates


def _register_reportlab_font(pdf_font: str, bold: bool = False) -> str:
    """
    Enregistre une police TTF proche de celle du PDF (Calibri, Arial…) pour les overlays.
    Retourne le nom ReportLab à utiliser dans setFont.
    """
    key = f"{(pdf_font or '').lower()}|{'b' if bold else 'n'}"
    if key in _REPORTLAB_FONT_CACHE:
        return _REPORTLAB_FONT_CACHE[key]

    n = (pdf_font or "").lower()
    if "opensans" in n or "open sans" in n:
        win_files = ["OpenSans-Regular.ttf", "opensans.ttf"]
        rl_name = "FillOpenSansBold" if bold else "FillOpenSans"
    elif "calibri" in n:
        win_files = ["calibrib.ttf", "calibri.ttf"] if bold else ["calibri.ttf", "arial.ttf"]
        rl_name = "FillCalibriBold" if bold else "FillCalibri"
    elif "arial" in n or "liberation" in n or "helvetica" in n or "helv" in n:
        win_files = ["arialbd.ttf", "arial.ttf"] if bold else ["arial.ttf", "calibri.ttf"]
        rl_name = "FillArialBold" if bold else "FillArial"
    elif "times" in n or "georgia" in n:
        win_files = ["timesbd.ttf", "times.ttf"] if bold else ["times.ttf", "calibri.ttf"]
        rl_name = "FillTimesBold" if bold else "FillTimes"
    else:
        # Corps de lettre Mendes = Calibri en pratique
        win_files = ["calibrib.ttf", "arialbd.ttf"] if bold else ["calibri.ttf", "arial.ttf"]
        rl_name = "FillBodyBold" if bold else "FillBody"

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        if rl_name not in pdfmetrics.getRegisteredFontNames():
            for path in _resolve_ttf_candidates(win_files, bold):
                if path.exists():
                    pdfmetrics.registerFont(TTFont(rl_name, str(path)))
                    _REPORTLAB_FONT_CACHE[key] = rl_name
                    return rl_name
    except Exception:
        pass

    fallback = "Helvetica-Bold" if bold else "Helvetica"
    _REPORTLAB_FONT_CACHE[key] = fallback
    return fallback


def _detect_fill_style_from_pdf(source: Any) -> Dict[str, Any]:
    """
    Détecte la police / taille / graisse dominantes du corps de texte du PDF
    pour homogénéiser le préremplissage.
    """
    style = {
        "pdf_font": "Calibri",
        "acro_font": PDF_FILL_FALLBACK_ACRO,
        "reportlab_font": PDF_FILL_FALLBACK_RL,
        "size": PDF_FILL_FALLBACK_SIZE,
        "bold": False,
    }
    try:
        import fitz
    except Exception:
        style["reportlab_font"] = _register_reportlab_font(style["pdf_font"], False)
        return style

    try:
        if isinstance(source, (bytes, bytearray)):
            doc = fitz.open(stream=bytes(source), filetype="pdf")
        else:
            doc = fitz.open(str(source))
    except Exception:
        style["reportlab_font"] = _register_reportlab_font(style["pdf_font"], False)
        return style

    counts: Dict[tuple, int] = {}
    try:
        for page in doc:
            data = page.get_text("dict")
            for block in data.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font = str(span.get("font") or "")
                        size = float(span.get("size") or 0)
                        flags = int(span.get("flags") or 0)
                        if size < 8.0 or size > 13.5:
                            continue
                        # Titres / pieds de page peu représentatifs du corps
                        fl = font.lower()
                        if "black" in fl or "gothic" in fl:
                            continue
                        bold = _font_is_bold(font, flags)
                        key = (font, round(size * 2) / 2.0, bold)
                        counts[key] = counts.get(key, 0) + max(1, len(str(span.get("text") or "")))
    finally:
        try:
            doc.close()
        except Exception:
            pass

    if counts:
        font, size, bold = max(counts.items(), key=lambda kv: kv[1])[0]
        style["pdf_font"] = font
        style["size"] = float(size)
        style["bold"] = bool(bold)
        style["acro_font"] = _map_to_acroform_font(font, bold)

    style["reportlab_font"] = _register_reportlab_font(style["pdf_font"], style["bold"])
    return style


def _acroform_da_string(font_size: float, acro_font: str = PDF_FILL_FALLBACK_ACRO) -> str:
    size = max(PDF_FILL_ABS_MIN_FONT, min(PDF_FILL_ABS_MAX_FONT, float(font_size)))
    font = acro_font or PDF_FILL_FALLBACK_ACRO
    return f"/{font} {size:g} Tf 0 g"


def _estimate_fit_font_size(
    text: str,
    box_w: float,
    box_h: float,
    *,
    multiline: bool = False,
    max_font: float = PDF_FILL_FALLBACK_SIZE,
    min_font: float = PDF_FILL_ABS_MIN_FONT,
    reportlab_font: str = "Helvetica",
) -> float:
    """Réduit la taille si le texte dépasse la zone, sans dépasser max_font."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return float(max_font)

    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.lib.utils import simpleSplit
    except Exception:
        return float(max_font)

    font_name = reportlab_font or "Helvetica"
    pad_w = max(10.0, box_w - 4.0)
    pad_h = max(8.0, box_h - 2.0)
    size = float(max_font)
    floor = max(PDF_FILL_ABS_MIN_FONT, float(min_font))
    while size >= floor:
        leading = size + 1.5
        max_lines = max(1, int(pad_h // leading)) if multiline or "\n" in raw else 1
        lines = raw.split("\n") if ("\n" in raw or multiline) else [raw]
        wrapped: List[str] = []
        for para in lines:
            wrapped.extend(simpleSplit(para, font_name, size, pad_w) or [""])
        if len(wrapped) <= max_lines and all(
            stringWidth(ln, font_name, size) <= pad_w for ln in wrapped
        ):
            return size
        size -= 0.5
    return float(floor)


def _apply_text_field_font_sizes(
    writer: PdfWriter,
    text_values: Dict[str, Any],
    multiline_names: set[str],
    style: Optional[Dict[str, Any]] = None,
) -> None:
    """Applique /DA (police + taille du document, shrink-to-fit) sur chaque champ rempli."""
    from pypdf.generic import IndirectObject, TextStringObject

    style = style or {}
    base_size = float(style.get("size") or PDF_FILL_FALLBACK_SIZE)
    acro_font = str(style.get("acro_font") or PDF_FILL_FALLBACK_ACRO)
    rl_font = str(style.get("reportlab_font") or "Helvetica")
    min_font = max(PDF_FILL_ABS_MIN_FONT, base_size - 4.0)

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
            if name_s not in text_values:
                continue

            # Préférer la police déjà définie sur le champ, si présente
            field_font, field_size = _parse_da_string(obj.get("/DA"))
            use_font = field_font or acro_font
            # Si le champ a une taille 0 (= auto viewer), utiliser la taille du corps
            target_max = base_size
            if field_size and field_size >= 7:
                # 12 est souvent le défaut générique Helv des modèles : préférer le corps
                target_max = base_size if abs(field_size - 12.0) < 0.1 else field_size

            rect = obj.get("/Rect")
            if rect is None or len(rect) < 4:
                font_size = target_max
            else:
                x0, y0, x1, y1 = [float(v) for v in rect[:4]]
                font_size = _estimate_fit_font_size(
                    str(text_values.get(name_s) or ""),
                    abs(x1 - x0),
                    abs(y1 - y0),
                    multiline=name_s in multiline_names or "adresse" in name_s.casefold(),
                    max_font=target_max,
                    min_font=min_font,
                    reportlab_font=rl_font,
                )
            obj[NameObject("/DA")] = TextStringObject(_acroform_da_string(font_size, use_font))
            if "/AP" in obj:
                try:
                    del obj["/AP"]
                except Exception:
                    pass


def _resolve_field_name(existing: Dict[str, Any], wanted: str) -> Optional[str]:
    if wanted in existing:
        return wanted
    wanted_n = _norm(wanted)
    for actual in existing:
        if _norm(actual) == wanted_n:
            return actual
    return None


def _compose_address_lines(values: Dict[str, str]) -> List[str]:
    """
    Compose une adresse suisse lisible :
    - ligne 1 : rue (+ n°)
    - ligne 2 : NPA + localité
    """
    street = _safe(values.get("rue") or values.get("adresse"))
    num = _safe(values.get("numero_rue"))
    if street and num and not re.search(rf"\b{re.escape(num)}\b", street):
        street = f"{street} {num}".strip()
    npa = _safe(values.get("npa"))
    ville = _safe(values.get("ville"))
    npa_ville = " ".join(p for p in (npa, ville) if p).strip()

    if street and npa_ville:
        return [street, npa_ville]

    raw = _safe(values.get("adresse_complete") or street or npa_ville)
    if not raw:
        return []
    # "Rue 12, 1202 Genève" → 2 lignes
    m = re.match(r"^(.+?),\s*(\d{4}\b.*)$", raw)
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    return [re.sub(r"\s+", " ", raw).strip()]


def _fit_text_in_box(
    preferred_lines: List[str],
    box_w: float,
    box_h: float,
    *,
    font_name: str = "Helvetica",
    max_font: float = PDF_FILL_FALLBACK_SIZE,
    min_font: float = PDF_FILL_ABS_MIN_FONT,
    single_line: bool = False,
) -> tuple[float, float, List[str]]:
    """
    Choisit fontSize + leading + lignes finales pour tenir dans (box_w x box_h).
    Préfère 1 ligne si ça rentre, sinon les lignes préférées, sinon word-wrap.
    """
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.lib.utils import simpleSplit
    except Exception:
        text = "\n".join(preferred_lines)
        return PDF_FILL_FALLBACK_SIZE, PDF_FILL_FALLBACK_SIZE + 1.5, (text.splitlines() or [text])[:3]

    prefs = [re.sub(r"\s+", " ", ln).strip() for ln in preferred_lines if _safe(ln)]
    if not prefs:
        return max_font, max_font + 2, [""]

    size = float(max_font)
    while size >= min_font:
        leading = size + 1.5
        max_lines = max(1, int((box_h - 2) // leading))
        pad_w = max(8.0, box_w - 4.0)

        # 1) Tout sur une ligne si possible
        joined = ", ".join(prefs)
        if stringWidth(joined, font_name, size) <= pad_w and (single_line or max_lines >= 1):
            return size, leading, [joined]
        if single_line:
            size -= 0.5
            continue

        # 2) Lignes préférées (rue / NPA ville) si chacune tient
        if len(prefs) <= max_lines and all(stringWidth(ln, font_name, size) <= pad_w for ln in prefs):
            return size, leading, prefs

        # 3) Word-wrap sur les lignes préférées
        wrapped: List[str] = []
        for para in prefs:
            wrapped.extend(simpleSplit(para, font_name, size, pad_w) or [""])
        if len(wrapped) <= max_lines and len(wrapped) * leading <= box_h - 2:
            return size, leading, wrapped

        size -= 0.5

    joined = ", ".join(prefs)
    if single_line:
        return min_font, min_font + 1.5, [joined]

    # Dernier recours : wrap agressif à min_font
    leading = min_font + 1.5
    max_lines = max(1, int((box_h - 2) // leading))
    pad_w = max(8.0, box_w - 4.0)
    wrapped = []
    for para in prefs:
        wrapped.extend(simpleSplit(para, font_name, min_font, pad_w) or [""])
    return min_font, leading, wrapped[:max_lines]


def _map_recherche_lpp(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    # Adresse dessinée via overlay (fit police + wrap) — champ vidé pour éviter le double rendu.
    mapping: Dict[str, Any] = {
        "Nom": values["nom"],
        "Nom 2": "",
        "Prénom": values["prenom"],
        "Prénom 2": "",
        "Date de naissance": values["date_naissance"],
        "AVS": values["avs"],
        "Adresse": "",
        "numero de tel": values["telephone"],
        "Texte10": values["email"] or values["agent_full"],
    }
    if options.get("demande_pour_moi_meme"):
        mapping["Case à cocher1"] = "/Oui"
    return mapping


def _map_calcul_rente(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Mapping pour le formulaire officiel « Demande de calcul d'une rente future »
    (template calcul_rente_future.pdf — champs sémantiques NOM/PRENOM/…).

    Groupe34 (radio) :
      /MASCULIN, /FEMININ — sexe
      /Choix2 (plus haut) — célibataire
      /Choix1 (plus bas) — marié(e)
    Ne coche rien si la donnée CRM est absente ou inconnue.
    """
    mapping: Dict[str, Any] = {
        "NOM": values.get("nom") or "",
        "PRENOM": values.get("prenom") or "",
        "DATE DE NAISSANCE": values.get("date_naissance") or "",
        # Ce formulaire reproduit volontairement la saisie CRM sans la reformater.
        "AVS": values.get("avs_crm") or "",
        "Pays de résidence": values.get("pays_residence") or values.get("pays") or "",
        "ADRESSE": values.get("rue") or values.get("adresse") or "",
        "NUMERO": values.get("numero_rue") or "",
        "Texte8": values.get("npa") or "",  # NPA
        "Localité": values.get("ville") or "",
        "Telephone": values.get("telephone") or "",
        "Courriel": values.get("email") or "",
        "Nationalité": values.get("nationalite") or "",
        "NOM CONJOINT": values.get("conjoint_nom") or "",
        "PRENOM CONJOINT": values.get("conjoint_prenom") or "",
        "DATE DE NAISSANCE CONJOINT": values.get("conjoint_date_naissance") or "",
        "AVS CONJOINT": values.get("conjoint_avs_crm") or "",
    }

    # Radios Groupe34 : activer chaque état compatible (sexe + état civil).
    # Ne rien cocher si la donnée CRM est absente.
    desired_states: List[str] = []
    sexe = _norm(values.get("sexe") or "")
    etat = _norm(values.get("etat_civil") or "")
    if sexe.startswith("m") or "masculin" in sexe or sexe in {"h", "homme"}:
        desired_states.append("/MASCULIN")
    elif sexe.startswith("f") or "feminin" in sexe or sexe in {"f", "femme"}:
        desired_states.append("/FEMININ")
    if "celibat" in etat:
        desired_states.append("/Choix2")
    elif "marie" in etat:
        desired_states.append("/Choix1")

    if desired_states:
        mapping["Groupe34"] = desired_states

    # Frontalier : pas de widget dédié dans ce PDF (34 champs) — rien à cocher.
    # Ne jamais inventer de valeur pour Texte13+ (enfants, revenus, etc.)
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
    # Identité = assuré de CETTE lettre (déjà basculé avant appel), jamais un autre membre.
    nom = _safe(values.get("nom")).upper()
    prenom = _safe(values.get("prenom"))
    avs = _safe(values.get("avs"))
    return {
        # Modèle actuel : champ « Adresse » ; anciens modèles : « Adresse caisse »
        "Adresse": recipient,
        "Adresse caisse": recipient,
        "date du jour": values["today_long"],
        "Nom": nom,
        "Prenom": prenom,
        "AVS": avs,
        # Ligne objet visuelle = « Objet : Demande de décompte pour » + Nom + Prénom + AVS
        "Objet": f"Demande de décompte pour {nom}, {prenom}, {avs}".strip(", "),
    }


def _civility_checkbox(values: Dict[str, str], *, person: str = "client") -> Dict[str, str]:
    """Coche Monsieur / Madame uniquement si le sexe CRM est connu."""
    if person == "spouse":
        sexe = _norm(values.get("conjoint_sexe") or "")
        keys = ("Monsieur 2", "Madame 2")
    else:
        sexe = _norm(values.get("sexe") or "")
        keys = ("Monsieur", "Madame")
    if sexe.startswith("f") or "feminin" in sexe or sexe in {"f", "femme", "madame", "mme"}:
        return {keys[1]: "/Oui"}
    if sexe.startswith("m") or "masculin" in sexe or sexe in {"h", "homme", "monsieur", "mr"}:
        return {keys[0]: "/Oui"}
    civ = _norm(values.get("civilite") or "")
    if person == "client":
        if civ in {"madame", "mme"}:
            return {keys[1]: "/Oui"}
        if civ in {"monsieur", "mr", "m"}:
            return {keys[0]: "/Oui"}
    return {}


def _split_ch_date(value: Any) -> tuple[str, str, str]:
    """Découpe une date JJ.MM.AAAA (ou ISO) dans les cases séparées par des / imprimés."""
    text = _clean_pdf_text(value)
    if not text:
        return "", "", ""
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(text[:10], fmt)
            return f"{dt.day:02d}", f"{dt.month:02d}", f"{dt.year:04d}"
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,6})$", text)
    if not m:
        return "", "", ""
    day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
    if len(year) == 6 and year.startswith("20"):
        year = year[2:]
    elif len(year) == 2:
        year = ("20" if int(year) <= 30 else "19") + year
    return day, month, year


def _mandat_de_gestion_fill_style() -> Dict[str, Any]:
    """Police / taille des libellés du mandat (OpenSans 10 pt), pas le corps 8 pt."""
    return {
        "pdf_font": "OpenSans-Regular",
        "acro_font": "Helv",
        "reportlab_font": _register_reportlab_font("OpenSans-Regular", False),
        "size": 10.0,
        "bold": False,
        "erase_background": False,
        "valign": "baseline",
        "baseline_pad": 1.0,
        "min_font": 9.5,
        "text_inset_x": 3.5,
        # Centrer JJ / MM / AAAA dans les cases séparées par des barres (naissance + signature)
        "center_field_names": [
            "née le", "undefined", "undefined_2",
            "née le_2", "undefined_3", "undefined_4",
            "le", "undefined_7", "undefined_8",
        ],
    }


def _map_mandat_de_gestion(values: Dict[str, str], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Mandat de gestion + devoir d'info (MG+LSA) — client, conjoint, conseiller, FINMA."""
    spouse_prenom = _clean_pdf_text(values.get("conjoint_prenom"))
    spouse_nom = _clean_pdf_text(values.get("conjoint_nom"))
    has_spouse = bool(spouse_prenom or spouse_nom)
    sig_d, sig_m, sig_y = _split_ch_date(values.get("today"))
    birth_d, birth_m, birth_y = _split_ch_date(values.get("date_naissance"))
    spouse_d, spouse_m, spouse_y = _split_ch_date(values.get("conjoint_date_naissance"))
    raison = _clean_pdf_text(
        values.get("raison_sociale")
        or values.get("societe")
        or values.get("employeur")
        or ""
    )
    conseiller = _clean_pdf_text(values.get("conseiller") or values.get("agent_full") or "")
    finma = _clean_pdf_text(values.get("conseiller_finma") or values.get("finma_number") or "")
    # Ne jamais injecter le FINMA agence (déjà imprimé sur le modèle) dans le champ conseiller.
    if finma.replace(" ", "").upper() in {"F01101452", "01101452"}:
        finma = ""
    conseiller_upper = conseiller.upper() if conseiller else ""

    mapping: Dict[str, Any] = {
        "Nom": _safe(values.get("nom")),
        "Prénom": _safe(values.get("prenom")),
        # Cases JJ / MM / AAAA (barres déjà imprimées)
        "née le": birth_d,
        "undefined": birth_m,
        "undefined_2": birth_y,
        "Nom_2": spouse_nom if has_spouse else "",
        "Prénom_2": spouse_prenom if has_spouse else "",
        "née le_2": spouse_d if has_spouse else "",
        "undefined_3": spouse_m if has_spouse else "",
        "undefined_4": spouse_y if has_spouse else "",
        "Adresse": _safe(values.get("adresse")),
        "undefined_5": _safe(values.get("npa")),
        "undefined_6": _safe(values.get("ville")),
        "Ville": _safe(values.get("ville")),  # ancien modèle éventuel
        "Tel": _safe(values.get("telephone")),
        "Email": _safe(values.get("email")),
        "Raison Sociale": raison,
        "Fait à": "Perly",
        "le": sig_d,
        "undefined_7": sig_m,
        "undefined_8": sig_y,
        # Page 1 — « Et le Mandataire » (champs Text1 / Text2 du PDF)
        "Text1": conseiller_upper,  # Conseillé par (en lettre majuscule)
        "Text2": finma,  # Numéro Finma du conseiller (personnel)
        # Page 2 — devoir d'information LSA
        "Représenté par le courtier": conseiller_upper or conseiller,
        "Le représentant du Mandataire inscrit au registre de la FINMA sous le numéro": finma,
    }
    # Civilité : nouveaux noms de cases (MG+LSA) + anciens si présents
    mapping.update(_civility_checkbox_mandat(values, person="client"))
    if has_spouse:
        mapping.update(_civility_checkbox_mandat(values, person="spouse"))
    if raison:
        mapping["Check Box2"] = "/Oui"
    return {k: _clean_pdf_text(v) if isinstance(v, str) and not v.startswith("/") else v for k, v in mapping.items()}


def _civility_checkbox_mandat(values: Dict[str, str], *, person: str = "client") -> Dict[str, str]:
    """Coche M./Mme sur le modèle MG+LSA (Check Box*) et l'ancien modèle (Monsieur/Madame)."""
    if person == "spouse":
        sexe = _norm(values.get("conjoint_sexe") or "")
        modern = ("Check Box1", "Check Box6")  # M / Mme conjoint
        legacy = ("Monsieur 2", "Madame 2")
    else:
        sexe = _norm(values.get("sexe") or "")
        modern = ("Check Box4", "Check Box11")  # M / Mme client
        legacy = ("Monsieur", "Madame")

    chosen: Optional[str] = None
    if sexe.startswith("f") or "feminin" in sexe or sexe in {"f", "femme", "madame", "mme"}:
        chosen = "F"
    elif sexe.startswith("m") or "masculin" in sexe or sexe in {"h", "homme", "monsieur", "mr"}:
        chosen = "M"
    elif person == "client":
        civ = _norm(values.get("civilite") or "")
        if civ in {"madame", "mme"}:
            chosen = "F"
        elif civ in {"monsieur", "mr", "m"}:
            chosen = "M"
    if chosen == "F":
        return {modern[1]: "/Oui", legacy[1]: "/Oui"}
    if chosen == "M":
        return {modern[0]: "/Oui", legacy[0]: "/Oui"}
    return {}


FIELD_MAPPERS = {
    "procuration_avs_lpp": _map_procuration,
    "recherche_avoirs_lpp": _map_recherche_lpp,
    "calcul_rente_future": _map_calcul_rente,
    "lettre_lpp": _map_lettre_lpp,
    "lettre_avs": _map_lettre_avs,
    "lettre_decompte_lpp": _map_lettre_decompte,
    "mandat_de_gestion": _map_mandat_de_gestion,
}

# Champs texte attendus par modèle (validation au remplissage)
TEMPLATE_EXPECTED_TEXT_FIELDS: Dict[str, List[str]] = {
    "calcul_rente_future": [
        "NOM", "PRENOM", "DATE DE NAISSANCE", "AVS", "Pays de résidence",
        "ADRESSE", "NUMERO", "Texte8", "Localité", "Telephone", "Courriel", "Nationalité",
        "NOM CONJOINT", "PRENOM CONJOINT", "DATE DE NAISSANCE CONJOINT", "AVS CONJOINT",
    ],
    "procuration_avs_lpp": ["Nom", "Prénom", "Date de naissance", "Adresse", "N AVS"],
    "recherche_avoirs_lpp": ["Nom", "Prénom", "Date de naissance", "AVS", "Adresse", "numero de tel"],
    "lettre_decompte_lpp": ["Nom", "Prenom", "AVS", "date du jour"],
    "mandat_de_gestion": [
        "Nom", "Prénom", "née le", "Nom_2", "Prénom_2",
        "Text1", "Text2",
        "Représenté par le courtier",
        "Le représentant du Mandataire inscrit au registre de la FINMA sous le numéro",
    ],
}


def validate_template_fields(template_id: str, template_path: Path) -> List[str]:
    """Retourne la liste des champs attendus introuvables dans le PDF."""
    if str(template_path).lower().endswith(".docx"):
        return []
    expected = TEMPLATE_EXPECTED_TEXT_FIELDS.get(template_id) or []
    if not expected:
        return []
    reader = PdfReader(str(template_path))
    existing = reader.get_fields() or {}
    missing: List[str] = []
    for name in expected:
        if _resolve_field_name(existing, name) is None:
            missing.append(name)
    return missing


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
    """Suggestions par widget. Pas d'auto-mapping des cases questionnaire ni US Person."""
    mapping: Dict[str, str] = {}
    for w in widgets:
        original = w.get("original_name") or ""
        ftype = w.get("field_type") or ""
        if _is_us_person_label(original):
            mapping[w["id"]] = ""
            continue
        if _is_checkbox_or_radio_type(ftype) and not _is_safe_identity_checkbox(original):
            mapping[w["id"]] = ""
            continue
        mapping[w["id"]] = _guess_source_key_for_field(original)
    return mapping


def _is_checkbox_or_radio_type(field_type: str) -> bool:
    t = (field_type or "").lower()
    return any(x in t for x in ("check", "radio", "button"))


def _is_safe_identity_checkbox(original_name: str) -> bool:
    """Cases d'identité (sexe / état civil) — pas les questionnaires profil."""
    n = _norm(original_name)
    safe = (
        "masculin", "feminin", "féminin", "homme", "femme",
        "celibat", "célibat", "marie", "marié", "divorce", "veuf", "pacse",
        "sexe", "genre", "gender",
    )
    return any(s in n for s in safe)


def _is_us_person_label(name: str) -> bool:
    n = _norm(name)
    needles = (
        "us person", "usperson", "us-person", "us_person",
        "personne us", "personne americaine", "personne américaine",
        "citoyen americain", "citoyen américain", "american person",
        "fatca",
    )
    return any(x in n for x in needles)


def _looks_like_yes(name: str) -> bool:
    n = _norm(name)
    if n in ("oui", "yes", "ja", "true", "1"):
        return True
    if _looks_like_no(name):
        return False
    return bool(re.search(r"(^|[\s_\-./])(oui|yes|ja)([\s_\-./]|$)", n))


def _looks_like_no(name: str) -> bool:
    n = _norm(name)
    if n in ("non", "no", "nein", "false", "0"):
        return True
    return bool(re.search(r"(^|[\s_\-./])(non|no|nein)([\s_\-./]|$)", n))


def _widget_on_value(widget) -> Any:
    try:
        on = widget.on_state()
        if callable(on):
            on = on()
        return on
    except Exception:
        return "Yes"


def _widget_off_value(widget) -> Any:
    try:
        states = widget.button_states() or {}
        offs = states.get("off") or states.get("Off") or []
        if offs:
            return offs[0]
    except Exception:
        pass
    return "Off"


def _set_widget_checked(widget, checked: bool) -> None:
    """
    Coche une case. Pour décocher : valeur Off SANS widget.update()
    (update() régénère souvent un glyphe « rond » indésirable).
    """
    try:
        if checked:
            widget.field_value = _widget_on_value(widget)
            try:
                widget.update()
            except Exception:
                pass
        else:
            widget.field_value = _widget_off_value(widget)
            # Ne pas appeler update() : laisse la case vide visuellement
    except Exception:
        try:
            widget.field_value = _widget_on_value(widget) if checked else "Off"
            if checked:
                widget.update()
        except Exception:
            pass


def _scrub_checkbox_circle_artifacts(doc) -> None:
    """
    Supprime les apparences corrompues (petits ronds) sur les cases non cochées.
    Causées typiquement par widget.update() après renommage.
    """
    for page in doc:
        for widget in page.widgets() or []:
            ftype = str(getattr(widget, "field_type_string", None) or getattr(widget, "field_type", "") or "")
            if not _is_checkbox_or_radio_type(ftype):
                continue
            try:
                val = widget.field_value
            except Exception:
                val = None
            on_val = _widget_on_value(widget)
            # Si la case n'est pas explicitement cochée → nettoyer
            checked = False
            try:
                checked = val == on_val or val is True or str(val) == str(on_val)
            except Exception:
                checked = False
            if checked:
                continue
            try:
                widget.field_value = _widget_off_value(widget)
            except Exception:
                try:
                    widget.field_value = "Off"
                except Exception:
                    pass
            # Effacer le flux d'apparence qui dessine le rond
            try:
                xref = getattr(widget, "xref", None)
                if xref:
                    doc.xref_set_key(xref, "AP", "null")
            except Exception:
                pass


def _ensure_pdf_bytes(pdf_bytes: Any, *, label: str = "pdf") -> bytes:
    """Garantit des bytes PDF (refuse une coroutine non awaitée)."""
    import inspect as _inspect

    if _inspect.isawaitable(pdf_bytes):
        raise TypeError(
            f"{label}: coroutine non awaitée — un await manque avant l'ouverture du PDF"
        )
    if isinstance(pdf_bytes, memoryview):
        pdf_bytes = pdf_bytes.tobytes()
    elif isinstance(pdf_bytes, bytearray):
        pdf_bytes = bytes(pdf_bytes)
    if not isinstance(pdf_bytes, bytes):
        raise TypeError(f"{label}: bytes attendus, reçu {type(pdf_bytes).__name__}")
    return pdf_bytes


def prepare_library_form_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Donne un nom interne unique à chaque widget AcroForm (même si le libellé est identique)
    et renvoie métadonnées de position pour l'éditeur visuel.
    """
    import fitz

    pdf_bytes = _ensure_pdf_bytes(pdf_bytes, label="prepare_library_form_pdf")
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
            field_type = str(
                getattr(widget, "field_type_string", None)
                or getattr(widget, "field_type", "")
                or "text"
            )
            try:
                widget.field_name = unique
                # Important : ne PAS appeler update() sur les cases à cocher
                # (régénère des ronds / glyphes parasites).
                if not _is_checkbox_or_radio_type(field_type):
                    widget.update()
                else:
                    try:
                        widget.field_value = _widget_off_value(widget)
                    except Exception:
                        pass
            except Exception:
                unique = widget.field_name or unique
            r = widget.rect
            widgets.append(
                {
                    "id": unique,
                    "original_name": original,
                    "unique_name": unique,
                    "page": page_index,
                    "field_type": field_type,
                    "rect": {
                        "x": max(0.0, min(1.0, float(r.x0) / pw)),
                        "y": max(0.0, min(1.0, float(r.y0) / ph)),
                        "w": max(0.0, min(1.0, float(r.x1 - r.x0) / pw)),
                        "h": max(0.0, min(1.0, float(r.y1 - r.y0) / ph)),
                    },
                }
            )
            idx += 1

    try:
        _scrub_checkbox_circle_artifacts(doc)
    except Exception:
        pass

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


def repair_library_pdf_bytes(pdf_bytes: bytes) -> bytes:
    """Nettoie les ronds parasites dans les cases à cocher d'un PDF bibliothèque."""
    import fitz

    pdf_bytes = _ensure_pdf_bytes(pdf_bytes, label="repair_library_pdf_bytes")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        _scrub_checkbox_circle_artifacts(doc)
    except Exception:
        pass
    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    return out.getvalue()


def render_pdf_page_png(pdf_bytes: bytes, page_index: int = 0, dpi: float = 144.0) -> bytes:
    """Rend une page PDF en PNG pour l'aperçu de mapping."""
    import fitz

    pdf_bytes = _ensure_pdf_bytes(pdf_bytes, label="render_pdf_page_png")
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


def _apply_us_person_default(widget, original_name: str, field_type: str = "") -> bool:
    """US Person = toujours Non (sans mapping CRM). Retourne True si traité."""
    if not _is_us_person_label(original_name):
        return False
    if _looks_like_no(original_name):
        _set_widget_checked(widget, True)
        return True
    if _looks_like_yes(original_name):
        _set_widget_checked(widget, False)
        return True
    if _is_checkbox_or_radio_type(field_type):
        # Case unique « je suis US Person » → Non = décochée
        _set_widget_checked(widget, False)
        return True
    try:
        widget.field_value = "Non"
        widget.update()
        return True
    except Exception:
        return False


def _near_us_person_row(meta: Dict[str, Any], us_metas: List[Dict[str, Any]], max_dy: float = 0.06) -> bool:
    """True si le widget est sur la même ligne approximative qu'un champ US Person."""
    r = meta.get("rect") or {}
    y = float(r.get("y") or 0)
    page = meta.get("page")
    for u in us_metas:
        if u.get("page") != page:
            continue
        uy = float((u.get("rect") or {}).get("y") or 0)
        if abs(uy - y) <= max_dy:
            return True
    return False


def _apply_us_person_oui_non_siblings(doc, meta_by_id: Dict[str, Dict[str, Any]]) -> None:
    """
    Si la question US Person existe, coche « Non » / décoche « Oui » pour les cases
    voisines nommées uniquement Oui/Non (sans US dans le libellé).
    """
    us_metas = [
        m for m in meta_by_id.values()
        if _is_us_person_label(m.get("original_name") or "")
    ]
    if not us_metas:
        return
    for page in doc:
        for widget in page.widgets() or []:
            name = widget.field_name or ""
            meta = meta_by_id.get(name) or {}
            original = meta.get("original_name") or ""
            if _is_us_person_label(original):
                continue  # déjà traité
            n = _norm(original)
            if n not in ("non", "no", "nein", "oui", "yes", "ja"):
                continue
            if not _is_checkbox_or_radio_type(meta.get("field_type") or ""):
                # type runtime
                ft = str(getattr(widget, "field_type_string", None) or "")
                if not _is_checkbox_or_radio_type(ft):
                    continue
            if not _near_us_person_row(meta, us_metas):
                continue
            if n in ("non", "no", "nein"):
                _set_widget_checked(widget, True)
            else:
                _set_widget_checked(widget, False)


def _fill_checkbox_from_value(widget, text: str, original_name: str = "") -> None:
    """Coche uniquement si la valeur CRM est explicitement affirmative."""
    raw = _norm(text)
    if not raw:
        _set_widget_checked(widget, False)
        return
    label = _norm(original_name)
    # Cases d'identité : ne cocher que si le libellé correspond à la valeur CRM
    identity_tokens = (
        "masculin", "feminin", "féminin", "homme", "femme",
        "celibat", "célibat", "marie", "marié", "divorce", "veuf",
    )
    if label and any(tok in label for tok in identity_tokens):
        _set_widget_checked(widget, raw in label or label in raw or any(tok in raw and tok in label for tok in identity_tokens if tok in label))
        return
    truthy = raw in {
        "1", "true", "oui", "yes", "ja", "x", "on", "checked", "vrai",
        "masculin", "feminin", "féminin", "marie", "marié", "celibataire", "célibataire",
    }
    if raw.startswith("/") and len(raw) > 1:
        truthy = raw[1:] not in ("off", "no", "non")
    _set_widget_checked(widget, bool(truthy))


def _resolve_mapped_value(values: Dict[str, str], source_key: str) -> str:
    """Récupère la valeur CRM pour une clé de mapping (avec alias courants)."""
    key = (source_key or "").strip()
    if not key:
        return ""
    if key in values and str(values.get(key) or "").strip():
        return str(values.get(key) or "")
    aliases = {
        "avs_number": "avs",
        "numero_avs": "avs",
        "n_avs": "avs",
        "date_of_birth": "date_naissance",
        "dob": "date_naissance",
        "naissance": "date_naissance",
        "address": "adresse",
        "adresse_ligne": "adresse",
        "phone": "telephone",
        "tel": "telephone",
        "mail": "email",
        "e_mail": "email",
        "lastname": "nom",
        "firstname": "prenom",
        "full_address": "adresse_complete",
    }
    alt = aliases.get(key) or aliases.get(_norm(key).replace(" ", "_"))
    if alt and alt in values:
        return str(values.get(alt) or "")
    # Cherche aussi une clé normalisée dans values
    wanted = _norm(key)
    for k, v in values.items():
        if _norm(k) == wanted and str(v or "").strip():
            return str(v)
    return str(values.get(key) or "")


def _rect_key(page_index: int, rect: Dict[str, Any], decimals: int = 3) -> tuple:
    return (
        int(page_index),
        round(float(rect.get("x") or 0), decimals),
        round(float(rect.get("y") or 0), decimals),
        round(float(rect.get("w") or 0), decimals),
        round(float(rect.get("h") or 0), decimals),
    )


def _widget_norm_rect(page, widget) -> Dict[str, float]:
    pw = float(page.rect.width) or 1.0
    ph = float(page.rect.height) or 1.0
    r = widget.rect
    return {
        "x": max(0.0, min(1.0, float(r.x0) / pw)),
        "y": max(0.0, min(1.0, float(r.y0) / ph)),
        "w": max(0.0, min(1.0, float(r.x1 - r.x0) / pw)),
        "h": max(0.0, min(1.0, float(r.y1 - r.y0) / ph)),
    }


def _index_widgets_meta(doc, widgets_meta: Optional[List[Dict[str, Any]]]) -> Dict[Any, Dict[str, Any]]:
    """
    Indexe les métadonnées par nom PDF courant et par position.
    Ne conserve PAS de références Widget (elles se détachent hors de la page).
    """
    by_name_counts: Dict[str, int] = {}
    # Pré-index positions des widgets meta
    meta_by_pos: Dict[tuple, Dict[str, Any]] = {}
    meta_by_id: Dict[str, Dict[str, Any]] = {}
    meta_by_original: Dict[str, List[Dict[str, Any]]] = {}
    for meta in widgets_meta or []:
        mid = meta.get("id") or meta.get("unique_name") or ""
        if mid:
            meta_by_id[mid] = meta
        oname = meta.get("original_name") or ""
        if oname:
            meta_by_original.setdefault(oname, []).append(meta)
        rect = meta.get("rect") or {}
        meta_by_pos[_rect_key(int(meta.get("page") or 0), rect)] = meta

    return {
        "by_id": meta_by_id,
        "by_pos": meta_by_pos,
        "by_original": meta_by_original,
        "used_meta_ids": set(),
    }


def _match_meta_for_live_widget(
    index: Dict[str, Any],
    page_index: int,
    page,
    widget,
) -> Dict[str, Any]:
    name = widget.field_name or ""
    used = index["used_meta_ids"]

    meta = index["by_id"].get(name)
    if meta and meta.get("id") not in used:
        used.add(meta.get("id"))
        return meta

    pos = _rect_key(page_index, _widget_norm_rect(page, widget))
    meta = index["by_pos"].get(pos)
    if meta and meta.get("id") not in used:
        used.add(meta.get("id"))
        return meta

    for cand in index["by_original"].get(name, []):
        cid = cand.get("id")
        if cid not in used:
            used.add(cid)
            return cand

    return {
        "id": name,
        "unique_name": name,
        "original_name": name,
        "field_type": str(
            getattr(widget, "field_type_string", None)
            or getattr(widget, "field_type", "")
            or ""
        ),
        "page": page_index,
    }


def _source_key_for_widget(
    field_mapping: Dict[str, str],
    meta: Dict[str, Any],
    current_name: str,
) -> str:
    mapping = field_mapping or {}
    for key in (
        meta.get("id"),
        meta.get("unique_name"),
        current_name,
        meta.get("original_name"),
    ):
        if not key:
            continue
        src = mapping.get(key)
        if src:
            return str(src)
    return ""


def _set_widget_text(widget, text: str, style: Optional[Dict[str, Any]] = None) -> bool:
    """Affecte une valeur texte (police/taille du document + shrink-to-fit) et régénère l'apparence."""
    value = "" if text is None else str(text)
    style = style or {}
    base_size = float(style.get("size") or PDF_FILL_FALLBACK_SIZE)
    acro_font = str(style.get("acro_font") or PDF_FILL_FALLBACK_ACRO)
    rl_font = str(style.get("reportlab_font") or "Helvetica")
    min_font = max(PDF_FILL_ABS_MIN_FONT, base_size - 4.0)
    try:
        rect = getattr(widget, "rect", None)
        if rect is not None:
            box_w = abs(float(rect.x1) - float(rect.x0))
            box_h = abs(float(rect.y1) - float(rect.y0))
        else:
            box_w, box_h = 120.0, 16.0
        multiline = bool(getattr(widget, "field_flags", 0) & (1 << 12)) or ("\n" in value or "\r" in value)
        font_size = _estimate_fit_font_size(
            value,
            box_w,
            box_h,
            multiline=multiline,
            max_font=base_size,
            min_font=min_font,
            reportlab_font=rl_font,
        )
        try:
            widget.text_fontsize = font_size
        except Exception:
            pass
        try:
            if hasattr(widget, "text_font"):
                widget.text_font = acro_font
        except Exception:
            pass
        widget.field_value = value
    except Exception:
        return False
    try:
        widget.update()
    except Exception:
        # La valeur /V peut rester même si l'apparence échoue
        pass
    try:
        current = widget.field_value
        return ("" if current is None else str(current)) == value
    except Exception:
        return bool(value)


def _fill_with_pymupdf(
    pdf_bytes: bytes,
    values: Dict[str, str],
    field_mapping: Dict[str, str],
    widgets: Optional[List[Dict[str, Any]]] = None,
) -> bytes:
    import fitz
    import logging

    log = logging.getLogger("server")

    # Nettoyer d'abord les artefacts (ronds) déjà présents dans le modèle
    try:
        pdf_bytes = repair_library_pdf_bytes(pdf_bytes)
    except Exception:
        pass

    fill_style = _detect_fill_style_from_pdf(pdf_bytes)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    index = _index_widgets_meta(doc, widgets)
    meta_by_id = {w.get("id") or w.get("unique_name"): w for w in (widgets or []) if w}
    filled = 0
    attempted = 0

    # Important : remplir pendant l'itération page.widgets() (widget lié à la page)
    for page_index, page in enumerate(doc):
        for widget in page.widgets() or []:
            meta = _match_meta_for_live_widget(index, page_index, page, widget)
            current_name = widget.field_name or ""
            original = meta.get("original_name") or current_name
            field_type = str(
                meta.get("field_type")
                or getattr(widget, "field_type_string", None)
                or getattr(widget, "field_type", "")
                or ""
            )

            # Défaut codé : US Person → Non (sans mapping)
            if _apply_us_person_default(widget, original, field_type):
                continue

            source_key = _source_key_for_widget(field_mapping, meta, current_name)
            if not source_key:
                continue

            text = _resolve_mapped_value(values, source_key)
            attempted += 1
            try:
                if _is_checkbox_or_radio_type(field_type):
                    if text is None or str(text).strip() == "":
                        continue
                    _fill_checkbox_from_value(widget, str(text), original_name=original)
                    filled += 1
                else:
                    if _set_widget_text(widget, text, style=fill_style):
                        filled += 1
            except Exception:
                log.exception("Échec remplissage champ %s → %s", current_name, source_key)
                continue

    # Cases Oui/Non voisines de la question US Person
    try:
        _apply_us_person_oui_non_siblings(doc, meta_by_id)
    except Exception:
        pass

    # Nettoyage final des cases non cochées (supprime les ronds restants)
    try:
        _scrub_checkbox_circle_artifacts(doc)
    except Exception:
        pass

    try:
        if hasattr(doc, "set_need_appearances"):
            doc.set_need_appearances(True)
    except Exception:
        pass

    log.info(
        "PDF library fill: attempted=%s filled=%s mapped_keys=%s",
        attempted,
        filled,
        sum(1 for v in (field_mapping or {}).values() if v),
    )

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    return out.getvalue()


# Conservé pour compatibilité éventuelle (évite de stocker des Widget détachés)
def _pair_widgets_with_meta(doc, widgets_meta: Optional[List[Dict[str, Any]]]) -> List[tuple]:
    pairs: List[tuple] = []
    index = _index_widgets_meta(doc, widgets_meta)
    for page_index, page in enumerate(doc):
        for widget in page.widgets() or []:
            meta = _match_meta_for_live_widget(index, page_index, page, widget)
            pairs.append((meta, widget, widget.field_name or ""))
    return pairs


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
        mapping[actual] = _resolve_mapped_value(values, str(source_key))
    return mapping


def _guess_value_for_field(field_name: str, values: Dict[str, str]) -> Optional[str]:
    """Associe un nom de champ AcroForm à une valeur client (heuristique texte)."""
    n = _norm(field_name)
    # Ne jamais préremplir cases questionnaire / US Person
    if n.startswith("case a cocher") or n.startswith("checkbox") or n.startswith("caseacocher"):
        return None
    if _is_us_person_label(field_name):
        return None
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
    widgets: Optional[List[Dict[str, Any]]] = None,
) -> bytes:
    """Préremplit un PDF AcroForm avec les données client (mapping manuel ou heuristique)."""
    pdf_bytes = _ensure_pdf_bytes(pdf_bytes, label="fill_pdf_bytes_with_client")

    values = client_field_values(
        client,
        agent_name=agent_name,
        spouse=spouse,
        extra=extra_values,
    )

    if field_mapping is not None:
        try:
            return _fill_with_pymupdf(pdf_bytes, values, field_mapping, widgets=widgets)
        except Exception:
            import logging
            logging.getLogger("server").exception(
                "Remplissage PyMuPDF échoué — bascule pypdf"
            )
            # fallback pypdf ci-dessous

    from pypdf.generic import IndirectObject, NumberObject

    fill_style = _detect_fill_style_from_pdf(pdf_bytes)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)
    existing = reader.get_fields() or {}
    if field_mapping is not None:
        field_map = _build_mapped_field_map(values, existing, field_mapping)
    else:
        field_map = _build_generic_field_map(values, existing)

    # Défaut US Person (noms d'origine si non uniqueifiés / fallback)
    for fname in list(existing.keys()):
        if not _is_us_person_label(fname):
            continue
        if _looks_like_no(fname):
            field_map[fname] = "/Oui"
        elif _looks_like_yes(fname):
            field_map[fname] = "/Off"
        else:
            field_map[fname] = "/Off"

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

    _ensure_need_appearances(
        writer,
        acro_font=str(fill_style.get("acro_font") or PDF_FILL_FALLBACK_ACRO),
        size=float(fill_style.get("size") or PDF_FILL_FALLBACK_SIZE),
    )
    _apply_text_field_font_sizes(writer, text_values, multiline_names, style=fill_style)
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
    from pypdf.generic import IndirectObject, NumberObject, TextStringObject, ArrayObject, FloatObject

    fill_style = _detect_fill_style_from_pdf(template_path)
    if template_id == "mandat_de_gestion":
        fill_style = _mandat_de_gestion_fill_style()
    elif template_id == "procuration_avs_lpp":
        # Ne pas peindre de rectangles blancs : les encadrés du modèle sont gris clair.
        fill_style["erase_background"] = False
        fill_style["size"] = 12.0
    elif template_id in {"lettre_lpp", "lettre_avs"}:
        # Corps Calibri 11 pt — pas de fond blanc (recouvre la ligne du dessus).
        fill_style["erase_background"] = False
        fill_style["size"] = 11.0
        fill_style["min_font"] = 9.0
        fill_style["valign"] = "baseline"
        fill_style["baseline_pad"] = 2.2
        fill_style["single_line"] = True
        fill_style["reportlab_font"] = _register_reportlab_font("Calibri", False)
        fill_style["pdf_font"] = "Calibri"
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
                    "fill_style": {
                        "pdf_font": fill_style.get("pdf_font"),
                        "size": fill_style.get("size"),
                        "bold": fill_style.get("bold"),
                        "acro_font": fill_style.get("acro_font"),
                        "reportlab_font": fill_style.get("reportlab_font"),
                    },
                },
                "timestamp": int(datetime.now().timestamp() * 1000),
                "runId": "font-match",
            }) + "\n")
        except Exception:
            pass
    # #endregion
    existing = reader.get_fields() or {}
    text_values: Dict[str, Any] = {}
    button_values: Dict[str, Any] = {}  # str | list[str]
    multiline_names: set[str] = set()

    for wanted, val in field_map.items():
        actual = _resolve_field_name(existing, wanted)
        if actual is None:
            continue
        if isinstance(val, (list, tuple)):
            # Plusieurs états radio désirés (ex. sexe + état civil sur le même groupe)
            cleaned = [str(v) for v in val if isinstance(v, str) and v.startswith("/")]
            if cleaned:
                button_values[actual] = cleaned
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

    # Valeurs réelles pour le dessin unique (Calibri). Les champs AcroForm
    # resteront vides pour éviter le double rendu (formulaire + overlay).
    overlay_draw_values: Dict[str, str] = {
        k: str(v).replace("\r", "\n")
        for k, v in text_values.items()
        if str(v or "").strip()
    }
    if template_id in {"lettre_lpp", "lettre_avs"}:
        for k in list(overlay_draw_values):
            if k.casefold() in {"nom", "prénom", "prenom"}:
                overlay_draw_values.pop(k, None)

    # Adresse destinataire décompte : overlay dédié (zone haut-droite).
    decompte_adresse_text = ""
    if template_id == "lettre_decompte_lpp":
        for key in list(overlay_draw_values.keys()):
            if key.casefold() in ("adresse", "adresse caisse"):
                if not decompte_adresse_text:
                    decompte_adresse_text = overlay_draw_values[key].strip()
                del overlay_draw_values[key]
        if not decompte_adresse_text:
            decompte_adresse_text = (
                field_map.get("Adresse") or field_map.get("Adresse caisse") or ""
            ).replace("\r", "\n").strip()

    # Activer Multiline si besoin. Sur la lettre de décompte, le champ
    # destinataire (« Adresse » / « Adresse caisse ») est multi-lignes.
    MULTILINE = 1 << 12
    adresse_rect = None
    recherche_adresse_rect = None
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        if isinstance(annots, IndirectObject):
            annots = annots.get_object()
        for annot in annots:
            obj = annot.get_object() if isinstance(annot, IndirectObject) else annot
            name_s = _annot_field_name(obj)
            if not name_s:
                continue
            name_low = name_s.casefold()
            is_decompte_adresse = (
                template_id == "lettre_decompte_lpp"
                and name_low in ("adresse", "adresse caisse")
            )
            if name_s in multiline_names or is_decompte_adresse:
                ff = int(obj.get("/Ff", 0) or 0) | MULTILINE
                obj[NameObject("/Ff")] = NumberObject(ff)
            if is_decompte_adresse:
                rect = obj.get("/Rect")
                if rect is not None and len(rect) >= 4:
                    # Préférer le vrai cadre Adresse (pas un widget parasite)
                    x0, y0, x1, y1 = (float(v) for v in rect[:4])
                    if abs(y1 - y0) >= 20.0:
                        adresse_rect = (x0, y0, x1, y1)
            # Capturer le cadre Adresse du formulaire Recherche LPP (sans le déformer)
            if template_id == "recherche_avoirs_lpp" and name_low == "adresse":
                rect = obj.get("/Rect")
                if rect is not None and len(rect) >= 4:
                    recherche_adresse_rect = tuple(float(v) for v in rect[:4])

    # Remplir les champs texte à vide (le texte visible vient uniquement de l'overlay).
    blank_text_values = {k: "" for k in text_values}
    skip_regen = template_id in {
        "lettre_lpp",
        "lettre_avs",
        "mandat_de_gestion",
        "procuration_avs_lpp",
    }
    for page in writer.pages:
        if blank_text_values and not skip_regen:
            try:
                writer.update_page_form_field_values(page, blank_text_values, auto_regenerate=True)
            except TypeError:
                try:
                    writer.update_page_form_field_values(page, blank_text_values)
                except Exception:
                    continue
            except Exception:
                continue

        annots = page.get("/Annots")
        if annots:
            if isinstance(annots, IndirectObject):
                annots = annots.get_object()
            for annot in annots:
                obj = annot.get_object() if isinstance(annot, IndirectObject) else annot
                name_s = _annot_field_name(obj)
                if not name_s:
                    continue
                # Effacer toute apparence texte résiduelle
                if name_s in text_values:
                    obj[NameObject("/V")] = TextStringObject("")
                    if "/AP" in obj:
                        try:
                            del obj["/AP"]
                        except Exception:
                            pass
                    if template_id in {"lettre_lpp", "lettre_avs"}:
                        # Masquer le widget (bordure / fond) : le texte est dessiné en overlay.
                        obj[NameObject("/F")] = NumberObject(int(obj.get("/F", 0) or 0) | 2)
                        rect = obj.get("/Rect")
                        if rect is not None and len(rect) >= 4:
                            x0, y0, x1, y1 = (float(v) for v in rect[:4])
                            if name_s.casefold() in {"nom", "prénom", "prenom"}:
                                mid = min(y0, y1) + 2.0
                                obj[NameObject("/Rect")] = ArrayObject([
                                    FloatObject(x0), FloatObject(mid),
                                    FloatObject(x1), FloatObject(mid + 0.4),
                                ])

        # Boutons / radios : activation sûre par widget (états /AP locaux)
        if button_values:
            _apply_button_states_on_page(page, button_values)

    if template_id not in {"mandat_de_gestion", "procuration_avs_lpp", "lettre_lpp", "lettre_avs"}:
        _ensure_need_appearances(
            writer,
            acro_font=str(fill_style.get("acro_font") or PDF_FILL_FALLBACK_ACRO),
            size=float(fill_style.get("size") or PDF_FILL_FALLBACK_SIZE),
        )
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    # Une seule écriture visible : police du document (Calibri…).
    pdf_bytes = _overlay_filled_acroform_fields(
        pdf_bytes, overlay_draw_values, multiline_names, style=fill_style
    )
    if template_id == "mandat_de_gestion":
        # Nouveau modèle MG+LSA : dates déjà en cases séparées via AcroForm.
        # Ancien modèle : une seule zone → overlay JJ/MM/AAAA.
        try:
            field_names = set(inspect_pdf_field_names(pdf_bytes))
        except Exception:
            field_names = set()
        if "undefined" not in field_names:
            pdf_bytes = _overlay_mandat_slash_dates(pdf_bytes, values, style=fill_style)
    elif template_id == "lettre_lpp":
        pdf_bytes = _overlay_lettre_lpp_name_sentence(pdf_bytes, values, style=fill_style)
    elif template_id == "lettre_avs":
        pdf_bytes = _overlay_lettre_avs_names(pdf_bytes, values, style=fill_style)

    # Une seule écriture de l'adresse destinataire (haut droite).
    if template_id == "lettre_decompte_lpp" and decompte_adresse_text:
        default_rect = (340.0, 650.0, 560.0, 790.0)
        pdf_bytes = _overlay_multiline_text(
            pdf_bytes,
            decompte_adresse_text,
            rect=adresse_rect or default_rect,
            style=fill_style,
        )

    # Adresse Recherche LPP : fit police + wrap intelligent dans le cadre (évent. 2 lignes)
    if template_id == "recherche_avoirs_lpp" and recherche_adresse_rect:
        lines = _compose_address_lines(values)
        if lines:
            x0, y0, x1, y1 = recherche_adresse_rect
            # Le widget PDF est souvent trop bas (≈22pt) pour 2 lignes lisibles :
            # on étend légèrement vers le bas uniquement pour le dessin, sans toucher
            # aux autres champs (téléphone ≈ y=39–61).
            draw_h = max(y1 - y0, 36.0)
            draw_y0 = max(70.0, y1 - draw_h)
            base = float(fill_style.get("size") or PDF_FILL_FALLBACK_SIZE)
            pdf_bytes = _overlay_fitted_text(
                pdf_bytes,
                lines,
                rect=(x0, draw_y0, x1, y1),
                style=fill_style,
                max_font=base,
                min_font=max(PDF_FILL_ABS_MIN_FONT, base - 4.0),
            )
    return pdf_bytes


def _overlay_fitted_text(
    pdf_bytes: bytes,
    preferred_lines: List[str],
    rect: tuple[float, float, float, float],
    *,
    style: Optional[Dict[str, Any]] = None,
    max_font: Optional[float] = None,
    min_font: Optional[float] = None,
) -> bytes:
    """Dessine un texte adapté (police du document + shrink-to-fit) entièrement dans rect."""
    try:
        from reportlab.pdfgen.canvas import Canvas
    except Exception:
        return pdf_bytes

    style = style or _detect_fill_style_from_pdf(pdf_bytes)
    rl_font = str(style.get("reportlab_font") or PDF_FILL_FALLBACK_RL)
    base = float(style.get("size") or PDF_FILL_FALLBACK_SIZE)
    use_max = float(max_font if max_font is not None else base)
    use_min = float(min_font if min_font is not None else max(PDF_FILL_ABS_MIN_FONT, base - 4.0))

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes
    page0 = reader.pages[0]
    page_w = float(page0.mediabox.width)
    page_h = float(page0.mediabox.height)
    x0, y0, x1, y1 = rect
    box_w = max(40.0, x1 - x0)
    box_h = max(14.0, y1 - y0)

    font_size, leading, lines = _fit_text_in_box(
        preferred_lines,
        box_w,
        box_h,
        font_name=rl_font,
        max_font=use_max,
        min_font=use_min,
    )

    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=(page_w, page_h))
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(x0 - 0.5, y0 - 0.5, box_w + 1, box_h + 1, fill=1, stroke=0)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(rl_font, font_size)
    y = y1 - font_size - 1.5
    for line in lines:
        if y < y0 - 0.5:
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


def _overlay_multiline_text(
    pdf_bytes: bytes,
    text: str,
    rect: tuple[float, float, float, float],
    *,
    style: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Dessine un bloc texte multi-lignes (police du document + shrink-to-fit) par-dessus le champ formulaire."""
    preferred = [ln for ln in (text or "").replace("\r", "\n").split("\n")]
    return _overlay_fitted_text(
        pdf_bytes,
        preferred or [""],
        rect,
        style=style,
    )


def _annot_field_name(obj) -> Optional[str]:
    """Nom du champ AcroForm, y compris via /Parent (widgets sans /T local)."""
    cur = obj
    for _ in range(6):
        if cur is None:
            break
        try:
            if hasattr(cur, "get_object"):
                cur = cur.get_object()
        except Exception:
            break
        name = cur.get("/T") if hasattr(cur, "get") else None
        if name is not None:
            return str(name)
        parent = cur.get("/Parent") if hasattr(cur, "get") else None
        if parent is None:
            break
        cur = parent
    return None


def _widget_appearance_states(obj) -> set[str]:
    """États disponibles dans /AP /N d'un widget bouton (ex. /MASCULIN, /Off)."""
    states: set[str] = set()
    try:
        ap = obj.get("/AP")
        if not ap:
            return states
        if hasattr(ap, "get_object"):
            ap = ap.get_object()
        n = ap.get("/N") if hasattr(ap, "get") else None
        if n is None:
            return states
        if hasattr(n, "get_object"):
            try:
                n = n.get_object()
            except Exception:
                pass
        if hasattr(n, "keys"):
            for k in n.keys():
                states.add(str(k))
    except Exception:
        return states
    return states


def _normalize_button_targets(raw: Any) -> List[str]:
    if isinstance(raw, (list, tuple)):
        return [str(v) for v in raw if isinstance(v, str) and v.startswith("/")]
    if isinstance(raw, str) and raw.startswith("/"):
        return [raw]
    return []


def _apply_button_states_on_page(page, button_values: Dict[str, Any]) -> None:
    """
    Active les cases/radios de façon sûre :
    - remet /Off les widgets du groupe non sélectionnés
    - n'active un état que s'il existe dans /AP du widget
    - ne coche jamais une case sans donnée CRM (les cibles viennent du mapping)
    """
    from pypdf.generic import IndirectObject, NameObject

    annots = page.get("/Annots")
    if not annots:
        return
    if isinstance(annots, IndirectObject):
        annots = annots.get_object()
    for annot in annots:
        obj = annot.get_object() if isinstance(annot, IndirectObject) else annot
        name_s = _annot_field_name(obj)
        if not name_s or name_s not in button_values:
            continue
        targets = _normalize_button_targets(button_values[name_s])
        states = _widget_appearance_states(obj)
        # Widget radio enfant : ne cocher que si un état désiré est supporté localement
        chosen = None
        for t in targets:
            if t in states:
                chosen = t
                break
        if chosen is None:
            # Checkbox simple sans liste d'états riches, ou état non applicable
            if len(targets) == 1 and (not states or targets[0] in states or "/Yes" in states or "/Oui" in states):
                chosen = targets[0]
            else:
                chosen = "/Off" if "/Off" in states or not states else None
        if chosen is None:
            continue
        try:
            obj[NameObject("/V")] = NameObject(chosen)
            obj[NameObject("/AS")] = NameObject(chosen)
        except Exception:
            continue
        # Propager /V sur le parent du groupe radio
        try:
            parent = obj.get("/Parent")
            if parent is not None:
                pobj = parent.get_object() if hasattr(parent, "get_object") else parent
                if chosen != "/Off" and chosen in targets:
                    pobj[NameObject("/V")] = NameObject(chosen)
        except Exception:
            pass


def _overlay_filled_acroform_fields(
    pdf_bytes: bytes,
    text_values: Dict[str, Any],
    multiline_names: set[str],
    style: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Redessine toutes les valeurs texte avec la police du document (Calibri…).
    Les champs AcroForm doivent être vides pour éviter un double rendu.
    """
    if not text_values:
        return pdf_bytes

    try:
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception:
        return pdf_bytes

    style = style or _detect_fill_style_from_pdf(pdf_bytes)
    rl_font = str(style.get("reportlab_font") or PDF_FILL_FALLBACK_RL)
    base = float(style.get("size") or PDF_FILL_FALLBACK_SIZE)
    min_font = float(style.get("min_font") or max(PDF_FILL_ABS_MIN_FONT, base - 4.0))
    erase_background = bool(style.get("erase_background", True))
    valign = str(style.get("valign") or "center")
    baseline_pad = float(style.get("baseline_pad") or 3.2)
    inset_x = float(style.get("text_inset_x") or 1.5)
    center_names = {str(n) for n in (style.get("center_field_names") or [])}

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes

    from pypdf.generic import IndirectObject

    # Collecter (page_index, rect, text, multiline, name)
    seen_names: set[str] = set()
    jobs: List[tuple[int, tuple[float, float, float, float], str, bool, str]] = []
    for page_index, page in enumerate(reader.pages):
        annots = page.get("/Annots")
        if not annots:
            continue
        if isinstance(annots, IndirectObject):
            annots = annots.get_object()
        for annot in annots:
            obj = annot.get_object() if isinstance(annot, IndirectObject) else annot
            name_s = _annot_field_name(obj)
            if not name_s or name_s not in text_values or name_s in seen_names:
                continue
            rect = obj.get("/Rect")
            if rect is None or len(rect) < 4:
                continue
            raw = str(text_values.get(name_s) or "").replace("\r", "\n")
            if not raw.strip():
                continue
            # Ignorer widgets parasites (hauteur trop faible = traits / signatures)
            x0, y0, x1, y1 = (float(v) for v in rect[:4])
            if abs(y1 - y0) < 8.0 or abs(x1 - x0) < 12.0:
                continue
            seen_names.add(name_s)
            jobs.append(
                (
                    page_index,
                    (x0, y0, x1, y1),
                    raw,
                    name_s in multiline_names or "adresse" in name_s.casefold() or "\n" in raw,
                    name_s,
                )
            )

    if not jobs:
        return pdf_bytes

    writer = PdfWriter()
    writer.append(reader)

    # Une couche ReportLab par page concernée
    pages_needed = sorted({j[0] for j in jobs})
    for page_index in pages_needed:
        page = reader.pages[page_index]
        page_w = float(page.mediabox.width)
        page_h = float(page.mediabox.height)
        packet = io.BytesIO()
        canvas = Canvas(packet, pagesize=(page_w, page_h))

        for pidx, rect, raw, multiline, field_name in jobs:
            if pidx != page_index:
                continue
            x0, y0, x1, y1 = rect
            box_w = max(20.0, abs(x1 - x0))
            box_h = max(10.0, abs(y1 - y0))
            left, bottom = min(x0, x1), min(y0, y1)
            top = max(y0, y1)

            preferred = [ln for ln in raw.split("\n")]
            font_size, leading, lines = _fit_text_in_box(
                preferred,
                box_w,
                box_h,
                font_name=rl_font,
                max_font=base,
                min_font=min_font,
                single_line=bool(style.get("single_line")) and not multiline,
            )
            if erase_background:
                canvas.setFillColorRGB(1, 1, 1)
                canvas.rect(left - 0.4, bottom - 0.4, box_w + 0.8, box_h + 0.8, fill=1, stroke=0)
            canvas.setFillColorRGB(0, 0, 0)
            canvas.setFont(rl_font, font_size)
            block_h = leading * max(0, len(lines) - 1) + font_size
            if valign == "baseline":
                y = bottom + baseline_pad
            else:
                y = bottom + (box_h - block_h) / 2.0 + (block_h - font_size)
            for line in lines:
                if y < bottom - 0.5:
                    break
                while line and stringWidth(line, rl_font, font_size) > max(8.0, box_w - 3.0):
                    line = line[:-1]
                if field_name in center_names:
                    tw = stringWidth(line, rl_font, font_size)
                    x = left + max(0.0, (box_w - tw) / 2.0)
                else:
                    x = left + inset_x
                canvas.drawString(x, y, line)
                y -= leading

        canvas.save()
        packet.seek(0)
        overlay = PdfReader(packet)
        if overlay.pages:
            writer.pages[page_index].merge_page(overlay.pages[0])

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _overlay_mandat_slash_dates(
    pdf_bytes: bytes,
    values: Dict[str, str],
    style: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Écrit JJ / MM / AAAA dans les cases déjà séparées par des barres imprimées."""
    try:
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception:
        return pdf_bytes

    style = style or _mandat_de_gestion_fill_style()
    rl_font = str(style.get("reportlab_font") or PDF_FILL_FALLBACK_RL)
    font_size = float(style.get("size") or 10.0)
    pad = float(style.get("baseline_pad") or 3.2)

    rows = [
        ((461.04, 655.8, 546.20, 675.0), _split_ch_date(values.get("date_naissance"))),
    ]
    spouse_prenom = _clean_pdf_text(values.get("conjoint_prenom"))
    spouse_nom = _clean_pdf_text(values.get("conjoint_nom"))
    if spouse_prenom or spouse_nom:
        rows.append(
            ((461.04, 627.84, 546.72, 647.04), _split_ch_date(values.get("conjoint_date_naissance")))
        )

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes
    page = reader.pages[0]
    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)
    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=(page_w, page_h))
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(rl_font, font_size)

    def _center(text: str, x0: float, x1: float, y: float) -> None:
        if not text:
            return
        tw = stringWidth(text, rl_font, font_size)
        x = x0 + max(0.0, (x1 - x0 - tw) / 2.0)
        canvas.drawString(x, y, text)

    for (x0, y0, x1, y1), (day, month, year) in rows:
        if not (day or month or year):
            continue
        y = min(y0, y1) + pad
        # Slashes imprimés à x=485.7 et x=511.3
        _center(day, x0, 483.5, y)
        _center(month, 493.0, 508.5, y)
        _center(year, 519.0, x1, y)

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


def _overlay_wrapped_sentence(
    pdf_bytes: bytes,
    text: str,
    *,
    left: float,
    width: float,
    baseline_pdf: float,
    leading: float,
    cover: tuple[float, float, float, float],
    style: Optional[Dict[str, Any]] = None,
    max_lines: int = 3,
) -> bytes:
    """Recouvre une bande (fond blanc) puis redessine une phrase Calibri, avec retour à la ligne si besoin."""
    try:
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.utils import simpleSplit
    except Exception:
        return pdf_bytes

    style = style or {}
    rl_font = str(style.get("reportlab_font") or _register_reportlab_font("Calibri", False))
    font_size = float(style.get("size") or 11.0)
    raw = re.sub(r"\s+", " ", _safe(text)).strip()
    if not raw:
        return pdf_bytes

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes
    page = reader.pages[0]
    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)
    lines = simpleSplit(raw, rl_font, font_size, max(40.0, width)) or [raw]
    lines = lines[:max_lines]
    cover_top = min(baseline_pdf + 8.6, 519.2)
    cover_bottom = baseline_pdf - max(0, len(lines) - 1) * leading - 3.0
    cover = (50.0, cover_bottom, 560.0, cover_top)

    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=(page_w, page_h))
    cx0, cy0, cx1, cy1 = cover
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(min(cx0, cx1), min(cy0, cy1), abs(cx1 - cx0), abs(cy1 - cy0), fill=1, stroke=0)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(rl_font, font_size)
    y = baseline_pdf
    for line in lines:
        canvas.drawString(left, y, line)
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


def _overlay_lettre_lpp_name_sentence(
    pdf_bytes: bytes,
    values: Dict[str, str],
    style: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Insère NOM + prénom dans la phrase, une seule ligne, sans encadré blanc sur la ligne du dessus."""
    try:
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.lib.utils import simpleSplit
    except Exception:
        return pdf_bytes

    nom = _safe(values.get("nom"))
    prenom = _safe(values.get("prenom"))
    who = " ".join(p for p in (nom, prenom) if p)
    if not who:
        return pdf_bytes

    style = style or {}
    rl_font = str(style.get("reportlab_font") or _register_reportlab_font("Calibri", False))
    font_size = float(style.get("size") or 11.0)
    # Après « procuration signée par » ; avant « nous permettant… »
    left = 158.2
    line_right = 540.0
    baseline = 509.8
    leading = 14.5
    suffix = " nous permettant de faire la recherche de ses avoirs"
    # Bande strictement sur la ligne du nom (pas la ligne « Vous trouverez ci-joint »).
    line_top_pdf = 518.15
    line_bot_pdf = 507.15

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes
    page = reader.pages[0]
    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)

    rest = who + suffix
    lines = simpleSplit(rest.replace(" ", "\u00a0", who.count(" ")), rl_font, font_size, max(40.0, line_right - left))
    if not lines:
        lines = [rest]
    # 1re ligne : coller le nom ; si trop long, simpleSplit a déjà renvoyé 2 lignes
    n_lines = min(3, len(lines))

    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=(page_w, page_h))
    cover_bottom = line_bot_pdf - max(0, n_lines - 1) * leading
    canvas.setFillColorRGB(1, 1, 1)
    canvas.rect(left - 1.0, cover_bottom, line_right - left + 2.0, line_top_pdf - cover_bottom, fill=1, stroke=0)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(rl_font, font_size)
    y = baseline
    for line in lines[:n_lines]:
        canvas.drawString(left, y, line.replace("\u00a0", " "))
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


def _overlay_lettre_avs_names(
    pdf_bytes: bytes,
    values: Dict[str, str],
    style: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Nom + prénom sur une seule ligne, à la suite de « complété par », sans fond blanc."""
    try:
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception:
        return pdf_bytes

    nom = _safe(values.get("nom"))
    prenom = _safe(values.get("prenom"))
    who = " ".join(p for p in (nom, prenom) if p)
    if not who:
        return pdf_bytes

    style = style or {}
    rl_font = str(style.get("reportlab_font") or _register_reportlab_font("Calibri", False))
    font_size = float(style.get("size") or 11.0)
    min_font = float(style.get("min_font") or 9.0)
    left = 226.0
    max_x = 540.0
    baseline_pdf = 384.6  # aligne « de rente future dûment complété par » (Calibri 11)

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        return pdf_bytes
    page = reader.pages[0]
    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)

    size = font_size
    while size >= min_font and stringWidth(who, rl_font, size) > (max_x - left):
        size -= 0.5

    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=(page_w, page_h))
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(rl_font, size)
    canvas.drawString(left, baseline_pdf, who)
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
    spouse: Optional[Dict[str, Any]] = None,
) -> tuple[bytes, Dict[str, Any]]:
    template = get_template(template_id)
    template_path = TEMPLATES_DIR / template["filename"]
    values = client_field_values(client, agent_name=agent_name, spouse=spouse)
    output_ext = (template.get("output_ext") or "pdf").lstrip(".")
    content_type = "application/pdf"

    if template.get("mode") == "word_docx":
        from lettre_avs_word import generate_lettre_avs_pdf_and_docx

        file_bytes, docx_bytes, extra = generate_lettre_avs_pdf_and_docx(values)
        content_type = extra.get("content_type") or "application/pdf"
        output_ext = extra.get("output_ext") or "pdf"
    elif template.get("mode") == "word_template":
        from lettre_lpp_word import generate_lettre_lpp_pdf

        file_bytes = generate_lettre_lpp_pdf(values)
        docx_bytes = None
    else:
        docx_bytes = None
        if not template_path.exists():
            raise FileNotFoundError(f"Modèle introuvable: {template['filename']}")
        missing = validate_template_fields(template_id, template_path)
        if missing:
            raise ValueError(
                f"Le modèle PDF « {template['filename']} » ne correspond plus au mapping "
                f"({template_id}). Champs manquants : {', '.join(missing)}"
            )
        file_bytes = _fill_acroform(template_path, template_id, values, options=options)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if template.get("id") == "lettre_avs":
        # Ex. Lettre_Demande_AVS_Thierry_Bauer
        prenom_part = re.sub(r"[^A-Za-z0-9_-]+", "_", values.get("prenom") or "").strip("_")
        nom_raw = (values.get("nom") or "").strip()
        nom_part = nom_raw.title() if nom_raw.isupper() else nom_raw
        nom_part = re.sub(r"[^A-Za-z0-9_-]+", "_", nom_part).strip("_")
        client_slug = f"{prenom_part}_{nom_part}".strip("_") or "client"
    else:
        client_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{values['nom']}_{values['prenom']}").strip("_") or "client"
    if custom_filename:
        output_name = custom_filename
        if not output_name.lower().endswith(f".{output_ext}"):
            output_name = f"{output_name}.{output_ext}"
        output_name = re.sub(r"[\\\\/:*?\"<>|]+", "_", output_name)
    elif template.get("filename_no_stamp"):
        output_name = f"{template['output_prefix']}_{client_slug}.{output_ext}"
    else:
        output_name = f"{template['output_prefix']}_{client_slug}_{stamp}.{output_ext}"

    meta = {
        "original_filename": output_name,
        "category": template["category"],
        "template_id": template["id"],
        "template_label": template["label"],
        "checklist_item": template.get("checklist_item"),
        "content_type": content_type,
    }
    if template.get("template_version"):
        meta["template_version"] = template["template_version"]
    if template_path.exists() and template.get("mode") == "acroform":
        meta["template_bytes"] = template_path.stat().st_size
    if docx_bytes:
        stem = output_name.rsplit(".", 1)[0] if "." in output_name else output_name
        meta["docx_bytes"] = docx_bytes
        meta["docx_filename"] = f"{stem}.docx"
        meta["has_word_download"] = True
    return file_bytes, meta


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


def infer_lpp_person_from_filename(filename: Optional[str]) -> str:
    """Déduit Monsieur/Madame depuis le nom de fichier (Recherche LPP Mme/Mr…)."""
    stem = Path(str(filename or "")).stem.casefold()
    stem = stem.replace("_", " ").replace("-", " ")
    if re.search(r"\b(mme|madame|épouse|epouse|wife|frau)\b", stem):
        return "Madame"
    if re.search(r"\b(mr|m\.|monsieur|époux|epoux|husband|herr)\b", stem):
        return "Monsieur"
    # Variantes collées : RechercheLPPMme / RechercheLPPMr
    if re.search(r"(?:^|[^a-z])mme(?:[^a-z]|$)|madame", stem):
        return "Madame"
    if re.search(r"(?:^|[^a-z])(?:mr|monsieur)(?:[^a-z]|$)", stem):
        return "Monsieur"
    return ""


def infer_lpp_person_from_text(text: str, client: Optional[Dict[str, Any]] = None) -> str:
    """Déduit Monsieur/Madame depuis le contenu OCR + identité client/conjoint."""
    low = (text or "").casefold()
    client = client or {}
    prenom = _safe(client.get("prenom")).casefold()
    nom = _safe(client.get("nom")).casefold()
    spouse_prenom = _safe(
        client.get("conjoint_prenom")
        or (str(client.get("conjoint") or "").split(" ")[0] if client.get("conjoint") else "")
    ).casefold()
    spouse_nom = _safe(
        client.get("conjoint_nom")
        or (" ".join(str(client.get("conjoint") or "").split(" ")[1:]) if client.get("conjoint") else "")
    ).casefold()

    def _mentions(p: str, n: str) -> bool:
        if not p and not n:
            return False
        if p and n and p in low and n in low:
            return True
        if p and len(p) >= 3 and p in low:
            return True
        return False

    client_hit = _mentions(prenom, nom)
    spouse_hit = _mentions(spouse_prenom, spouse_nom)
    sexe = _safe(client.get("sexe") or client.get("civilite")).casefold()
    client_is_madame = sexe in {"f", "femme", "female", "madame", "mme"}
    client_is_monsieur = sexe in {"m", "homme", "male", "monsieur", "mr", "m."}

    if client_hit and not spouse_hit:
        if client_is_madame:
            return "Madame"
        if client_is_monsieur:
            return "Monsieur"
    if spouse_hit and not client_hit:
        if client_is_madame:
            return "Monsieur"
        if client_is_monsieur:
            return "Madame"

    if re.search(r"\bmadame\b|\bmme\b", low) and not re.search(r"\bmonsieur\b|\bmr\b", low):
        return "Madame"
    if re.search(r"\bmonsieur\b|\bmr\b", low) and not re.search(r"\bmadame\b|\bmme\b", low):
        return "Monsieur"
    return ""


def resolve_lpp_person(
    *,
    filename: Optional[str] = None,
    text: Optional[str] = None,
    client: Optional[Dict[str, Any]] = None,
    explicit: Optional[str] = None,
) -> str:
    """Priorité : valeur explicite → nom de fichier → texte OCR/client."""
    raw = _safe(explicit).strip()
    if raw.casefold() in {"madame", "mme", "f", "femme"}:
        return "Madame"
    if raw.casefold() in {"monsieur", "mr", "m.", "m", "homme"}:
        return "Monsieur"
    from_file = infer_lpp_person_from_filename(filename)
    if from_file:
        return from_file
    return infer_lpp_person_from_text(text or "", client)


def _opposite_lpp_person(person: str) -> str:
    if person == "Madame":
        return "Monsieur"
    if person == "Monsieur":
        return "Madame"
    return ""


def _spouse_identity_from_client(
    client: Dict[str, Any],
    spouse: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Construit le profil conjoint (fiche liée ou champs conjoint_* du dossier)."""
    if spouse and (_safe(spouse.get("prenom")) or _safe(spouse.get("nom"))):
        return {
            "prenom": _safe(spouse.get("prenom")),
            "nom": _safe(spouse.get("nom")),
            "avs_number": _safe(spouse.get("avs_number")),
            "sexe": _safe(spouse.get("sexe") or spouse.get("civilite")),
            "date_naissance": spouse.get("date_naissance"),
            "civilite": _safe(spouse.get("civilite")),
        }

    conjoint_nom, conjoint_prenom = _split_agent_name(_safe(client.get("conjoint")))
    if _safe(client.get("conjoint_nom")):
        conjoint_nom = _safe(client.get("conjoint_nom"))
    if _safe(client.get("conjoint_prenom")):
        conjoint_prenom = _safe(client.get("conjoint_prenom"))
    if not conjoint_nom and not conjoint_prenom:
        return None
    return {
        "prenom": conjoint_prenom,
        "nom": conjoint_nom,
        "avs_number": _safe(
            client.get("conjoint_avs")
            or client.get("conjoint_avs_number")
            or client.get("avs_conjoint")
        ),
        "sexe": _safe(client.get("conjoint_sexe") or client.get("sexe_conjoint")),
        "date_naissance": client.get("conjoint_date_naissance"),
        "civilite": _safe(client.get("conjoint_civilite")),
    }


def lpp_profiles_by_person(
    client: Dict[str, Any],
    spouse: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Mappe Madame/Monsieur → identité CRM (client ou conjoint), sans défaut global."""
    client_label = (
        _civilite_from_sexe(client.get("sexe"))
        or _civilite_from_sexe(client.get("civilite"))
        or resolve_lpp_person(explicit=client.get("civilite"))
    )
    profiles: Dict[str, Dict[str, Any]] = {}
    if client_label:
        profiles[client_label] = {
            "prenom": _safe(client.get("prenom")),
            "nom": _safe(client.get("nom")),
            "avs_number": _safe(client.get("avs_number")),
            "sexe": _safe(client.get("sexe") or client_label),
            "date_naissance": client.get("date_naissance"),
            "civilite": client_label,
            "_source": "client",
        }

    spouse_id = _spouse_identity_from_client(client, spouse)
    if not spouse_id:
        return profiles

    spouse_label = (
        _civilite_from_sexe(spouse_id.get("sexe"))
        or _civilite_from_sexe(spouse_id.get("civilite"))
        or _opposite_lpp_person(client_label)
    )
    if not spouse_label:
        return profiles
    if spouse_label == client_label and client_label:
        # Même civilité stockée par erreur : basculer sur l'opposé du client.
        spouse_label = _opposite_lpp_person(client_label) or spouse_label
    profiles[spouse_label] = {
        **spouse_id,
        "sexe": _safe(spouse_id.get("sexe") or spouse_label),
        "civilite": spouse_label,
        "_source": "spouse",
    }
    return profiles


def resolve_lpp_assure_for_letter(
    client: Dict[str, Any],
    person: str,
    spouse: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Retourne un dict client dont nom/prénom/AVS/sexe sont ceux de l'assuré
    concerné par la caisse (Madame ou Monsieur détecté sur le PDF), jamais
    systématiquement le titulaire du dossier.
    """
    wanted = resolve_lpp_person(explicit=person)
    if wanted not in {"Madame", "Monsieur"}:
        raise ValueError(
            "Personne (Madame/Monsieur) manquante pour cette caisse — "
            "relancez l'analyse de la réponse LPP."
        )
    profiles = lpp_profiles_by_person(client, spouse)
    assure = profiles.get(wanted)
    if not assure or not (_safe(assure.get("prenom")) or _safe(assure.get("nom"))):
        raise ValueError(
            f"Identité {wanted} introuvable dans le dossier "
            "(fiche client / conjoint). Impossible de générer la lettre."
        )

    letter_client = dict(client)
    letter_client["prenom"] = _safe(assure.get("prenom"))
    letter_client["nom"] = _safe(assure.get("nom"))
    letter_client["avs_number"] = _safe(assure.get("avs_number"))
    letter_client["sexe"] = _safe(assure.get("sexe") or wanted)
    letter_client["civilite"] = wanted
    if assure.get("date_naissance") not in (None, ""):
        letter_client["date_naissance"] = assure.get("date_naissance")

    # Assertion stricte : la personne de la lettre == personne PDF/caisse
    letter_label = (
        _civilite_from_sexe(letter_client.get("sexe"))
        or _civilite_from_sexe(letter_client.get("civilite"))
        or wanted
    )
    if letter_label != wanted:
        raise ValueError(
            f"Incohérence lettre : caisse={wanted} mais assuré généré={letter_label} "
            f"({letter_client.get('prenom')} {letter_client.get('nom')})"
        )
    if not _safe(letter_client.get("nom")) or not _safe(letter_client.get("prenom")):
        raise ValueError(f"Nom/prénom incomplets pour {wanted}")
    return letter_client


def lpp_fund_merge_key(fund: Dict[str, Any]) -> str:
    person = _safe(fund.get("person")).casefold()
    name = _safe(fund.get("name") or fund.get("nom")).casefold()
    return f"{person}|{name}"


def tag_lpp_funds_with_person(
    funds: List[Dict[str, Any]],
    person: str,
    *,
    source_doc_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Attache la personne (et doc source) à chaque caisse détectée."""
    out: List[Dict[str, Any]] = []
    for fund in funds or []:
        if not isinstance(fund, dict):
            continue
        item = dict(fund)
        if person:
            item["person"] = person
        elif not item.get("person"):
            item["person"] = ""
        if source_doc_id:
            item["source_doc_id"] = source_doc_id
        out.append(item)
    return out


def merge_lpp_detected_funds(
    existing: Optional[List[Dict[str, Any]]],
    incoming: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Fusionne les caisses sans écraser Monsieur avec Madame (clé personne+nom)."""
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for fund in list(existing or []) + list(incoming or []):
        if not isinstance(fund, dict):
            continue
        name = _safe(fund.get("name") or fund.get("nom"))
        if not name:
            continue
        item = {**fund, "name": name}
        key = lpp_fund_merge_key(item)
        if key in merged:
            prev = merged[key]
            merged[key] = {
                **prev,
                **{k: v for k, v in item.items() if v not in (None, "")},
                "name": name,
                "person": item.get("person") or prev.get("person") or "",
            }
        else:
            merged[key] = item
            order.append(key)
    return [merged[k] for k in order]


def generate_decompte_letters(
    client: Dict[str, Any],
    funds: List[Dict[str, Any]],
    agent_name: str = "",
    spouse: Optional[Dict[str, Any]] = None,
) -> List[tuple[bytes, Dict[str, Any]]]:
    """Une lettre de décompte par caisse — identité = personne détectée pour CETTE caisse."""
    results: List[tuple[bytes, Dict[str, Any]]] = []
    for fund in funds:
        name = _safe(fund.get("name") or fund.get("nom") or "Caisse")
        # Uniquement la personne attachée à la caisse (PDF), jamais le titulaire global.
        person = resolve_lpp_person(explicit=fund.get("person"))
        if person not in {"Madame", "Monsieur"}:
            raise ValueError(
                f"Caisse « {name} » : personne Madame/Monsieur manquante. "
                "Relancez l'analyse de la réponse LPP avant de générer les lettres."
            )
        letter_client = resolve_lpp_assure_for_letter(client, person, spouse=spouse)
        # Assertion finale avant écriture du document
        assert_label = (
            _civilite_from_sexe(letter_client.get("sexe"))
            or _civilite_from_sexe(letter_client.get("civilite"))
        )
        if assert_label != person:
            raise ValueError(
                f"Refus génération : PDF/caisse={person} ≠ lettre={assert_label} "
                f"({letter_client.get('prenom')} {letter_client.get('nom')})"
            )

        person_slug = {"Madame": "Mme", "Monsieur": "Mr"}.get(person, "")
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:50] or "Caisse"
        fname = f"Demande_decompte_{person_slug}_{slug}.pdf" if person_slug else f"Demande_decompte_{slug}.pdf"
        pdf_bytes, meta = generate_document_pdf(
            "lettre_decompte_lpp",
            letter_client,
            agent_name=agent_name,
            custom_filename=fname,
            options={"fund": fund, "lpp_person": person},
        )
        meta["caisse_name"] = name
        meta["caisse_address"] = _safe(fund.get("address") or fund.get("adresse"))
        meta["caisse_reference"] = _safe(fund.get("reference") or fund.get("ref"))
        meta["lpp_person"] = person
        meta["assure_prenom"] = _safe(letter_client.get("prenom"))
        meta["assure_nom"] = _safe(letter_client.get("nom"))
        meta["assure_avs"] = _format_avs(letter_client.get("avs_number"))
        meta["lpp_tracking_id"] = _safe(fund.get("tracking_id") or fund.get("id"))
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
    """
    Extrait le texte de toutes les pages. Si le texte natif est trop pauvre,
    bascule sur OCR. Si le texte natif existe mais contient très peu de dates,
    fusionne avec l'OCR (cas PDF hybrides / tableaux scannés).
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    compact_len = len(re.sub(r"\s+", "", text))
    date_hits = len(re.findall(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", text or ""))

    if compact_len < 80:
        ocr_text = _ocr_pdf_text(pdf_bytes)
        return ocr_text if ocr_text.strip() else text

    # Texte présent mais peu de dates → tenter OCR en complément (tableaux AXA, etc.)
    if date_hits < 2:
        ocr_text = _ocr_pdf_text(pdf_bytes)
        if ocr_text and len(re.sub(r"\s+", "", ocr_text)) > compact_len * 0.5:
            return text + "\n" + ocr_text
    return text


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
    logging.getLogger("server").info(
        "LPP parse text_len=%s funds=%s names=%s",
        len(text),
        len(funds),
        [f.get("name") for f in funds],
    )
    return funds


def extract_pension_funds_from_pdf_with_text(pdf_bytes: bytes) -> tuple[List[Dict[str, str]], str]:
    """Comme extract_pension_funds_from_pdf, mais retourne aussi le texte OCR."""
    text = _extract_pdf_text(pdf_bytes)
    funds = _parse_funds_from_text(text)
    return funds, text


# Types de documents 3e pilier reconnus (ordre d'affichage UI).
DOCUMENT_TYPES_3P = [
    "Police 3a",
    "Police 3b",
    "Valeur de rachat",
    "Valeur de libération",
    "Résiliation",
    "Rachat",
    "Libre passage",
    "Ordre de paiement",
    "Autre document",
]

# Types pour lesquels on ne crée jamais d'échéance automatique.
_NO_EXPIRY_DOC_TYPES = frozenset({"Résiliation", "Rachat", "Libre passage"})


def _3p_date_to_iso(raw: str) -> Optional[str]:
    raw = (raw or "").strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            if dt.year < 1990 or dt.year > 2100:
                return None
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_3p_company_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    compact = re.sub(r"\s+", " ", name).strip()
    key = compact.casefold().replace("é", "e").replace("è", "e").replace("ê", "e")
    aliases = {
        "helvete": "Helvetia",
        "helvetia": "Helvetia",
        "axa winterthur": "AXA",
        "axa-winterthur": "AXA",
        "axa": "AXA",
        "swisslife": "Swiss Life",
        "swiss life": "Swiss Life",
        "la mobiliere": "Mobilière",
        "mobiliere": "Mobilière",
        "baloise": "Bâloise",
        "generali schweiz": "Generali",
        "generali switzerland": "Generali",
        "allianz suisse": "Allianz",
        "allianz switzerland": "Allianz",
        "zurich insurance": "Zurich",
        "zurich vie": "Zurich",
        "pax": "Pax",
        "vaudoise": "Vaudoise",
    }
    if key in aliases:
        return aliases[key]
    for alias_key, canonical in aliases.items():
        if alias_key in key:
            return canonical
    return compact


def classify_3p_document_type(text: str) -> str:
    """
    Identifie le type de document 3e pilier avant toute extraction d'échéance.
    """
    flat = re.sub(r"[ \t]+", " ", text or "")
    low = flat.casefold()

    scores = {t: 0 for t in DOCUMENT_TYPES_3P}

    def bump(doc_type: str, weight: int = 1) -> None:
        scores[doc_type] = scores.get(doc_type, 0) + weight

    # Libre passage (jamais une échéance 3a)
    if re.search(r"libre\s+passage|freiz[uü]gigkeit|freizuegigkeit|compte\s+de\s+libre\s+passage|fondation\s+de\s+libre\s+passage", low):
        bump("Libre passage", 12)
    if re.search(r"\bvested\s+benefits?\b|\bfreizügigkeitskonto\b", low):
        bump("Libre passage", 10)

    # Résiliation
    if re.search(r"r[ée]siliation|r[ée]silie|r[ée]silier|k[uü]ndigung|annulation\s+du\s+contrat", low):
        bump("Résiliation", 10)
    if re.search(r"contrat\s+(?:est\s+)?r[ée]sili[ée]|demande\s+de\s+r[ée]siliation", low):
        bump("Résiliation", 8)

    # Valeur de rachat (document d'information) vs Rachat (exécution)
    if re.search(r"valeur\s+de\s+rachat|r[uü]ckkaufswert|rueckkaufswert|surrender\s+value", low):
        bump("Valeur de rachat", 11)
    if re.search(r"valeur\s+de\s+lib[ée]ration|freigabewert", low):
        bump("Valeur de libération", 11)

    # Rachat (demande / exécution) — moins fort que « valeur de rachat »
    if re.search(r"demande\s+de\s+rachat|rachat\s+total|rachat\s+partiel|contrat\s+rachet[ée]|r[uü]ckkauf(?!\s*swert)", low):
        bump("Rachat", 9)
    elif "valeur de rachat" not in low and "rückkaufswert" not in low and "rueckkaufswert" not in low:
        if re.search(r"\brachat\b", low):
            bump("Rachat", 6)

    # Ordre de paiement
    if re.search(r"ordre\s+de\s+paiement|zahlungsauftrag|bulletin\s+de\s+versement|avis\s+de\s+paiement", low):
        bump("Ordre de paiement", 10)

    # Police 3a / 3b
    if re.search(r"\b3\s*a\b|pilier\s*3\s*a|3e?\s*pilier\s*a|pr[ée]voyance\s+li[ée]e|tied\s+pension|säule\s*3a|saeule\s*3a", low):
        bump("Police 3a", 8)
    if re.search(r"\b3\s*b\b|pilier\s*3\s*b|3e?\s*pilier\s*b|pr[ée]voyance\s+libre|säule\s*3b|saeule\s*3b", low):
        bump("Police 3b", 8)
    if re.search(r"\bpolice\b|police\s+d['’]?assurance|contrat\s+d['’]?assurance|versicherungspolice|versicherungsschein", low):
        if scores["Police 3b"] >= scores["Police 3a"]:
            bump("Police 3b" if scores["Police 3b"] > 0 else "Police 3a", 4)
        else:
            bump("Police 3a", 4)
    if re.search(r"conditions\s+(?:g[ée]n[ée]rales|particuli[eè]res)|capital\s+en\s+cas\s+de\s+vie|en\s+cas\s+de\s+vie\s+au", low):
        bump("Police 3a" if scores["Police 3a"] >= scores["Police 3b"] else "Police 3b", 3)

    best_type = "Autre document"
    best_score = 0
    for doc_type, score in scores.items():
        if score > best_score:
            best_score = score
            best_type = doc_type

    # Seuil minimal : sinon « Autre document »
    if best_score < 4:
        return "Autre document"
    return best_type


def _detect_3p_company(text: str) -> Optional[str]:
    company_patterns = [
        ("Swiss Life", r"Swiss\s*Life"),
        ("Helvetia", r"Helvetia|Helv[eè]te"),
        ("Generali", r"Generali"),
        ("AXA", r"\bAXA(?:\s*[- ]?\s*Winterthur)?\b"),
        ("Pax", r"\bPax\b"),
        ("Pictet", r"Pictet"),
        ("BCV", r"\bBCV\b|Banque\s+Cantonale\s+Vaudoise|Banque\s+Cantonale\s+de\s+Vaud"),
        ("Retraites Populaires", r"Retraites?\s*Populaires"),
        ("Zurich", r"\bZurich\b"),
        ("Vontobel", r"Vontobel"),
        ("Bâloise", r"B[aâ]loise"),
        ("Fortuna", r"Fortuna|3B\s*Fortuna"),
        ("Allianz", r"Allianz"),
        ("Mobilière", r"Mobili[eè]re|La\s+Mobili[eè]re"),
        ("Vaudoise", r"\bVaudoise\b"),
        ("Helvetia", r"Helvetia"),
    ]
    for company, pat in company_patterns:
        if re.search(pat, text or "", flags=re.IGNORECASE):
            return _normalize_3p_company_name(company)
    return None


def _detect_3p_policy(text: str) -> Optional[str]:
    policy_patterns = [
        r"(?:num(?:[ée]ro)?\s*(?:de\s*)?police|n[°ºo]?\s*(?:de\s*)?police|police\s*(?:n[°ºo]|num(?:[ée]ro)?)|pol\.\s*n[°ºo]?)\s*[:\-]?\s*([A-Z0-9\-/]{3,24})",
        r"(?:contract\s*(?:no\.?|number)|contrat\s*n[°ºo]?|policenummer|vertragsnummer)\s*[:\-]?\s*([A-Z0-9\-/]{3,24})",
        r"(?:n[°ºo]\s*(?:de\s*)?contrat|num(?:[ée]ro)?\s*(?:de\s*)?contrat)\s*[:\-]?\s*([A-Z0-9\-/]{3,24})",
    ]
    for pat in policy_patterns:
        m = re.search(pat, text or "", flags=re.IGNORECASE)
        if m:
            return (m.group(1) or "").strip().rstrip(".")
    m = re.search(r"(?:police|contrat|vertrag)[^\n]{0,40}?[:\-]?\s*([0-9]{5,20})", text or "", flags=re.IGNORECASE)
    if m:
        return (m.group(1) or "").strip()
    return None


_DATE_TOKEN_RE = re.compile(r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})")

# Libellés d'échéance (du plus spécifique au plus générique).
# Priorité basse = plus important.
_EXPIRY_LABEL_SPECS: List[tuple] = [
    (0, "Échéance du contrat de la prestation",
     r"(?:echeance|échéance)\s+du\s+contrat\s+de\s+la\s+prestation"),
    (1, "Échéance de la prestation",
     r"(?:echeance|échéance)\s+de\s+la\s+prestation"),
    (2, "Échéance de l'assurance",
     r"(?:echeance|échéance)\s+de\s+l['’]?\s*assurance"),
    (3, "Échéance du contrat",
     r"(?:echeance|échéance)\s+du\s+contrat"),
    (4, "Échéance de la police",
     r"(?:echeance|échéance)\s+(?:de\s+la\s+)?police"),
    (5, "Échéance police",
     r"(?:echeance|échéance)\s+police"),
    (6, "Date d'échéance",
     r"date\s+d['’]?(?:echeance|échéance)"),
    (7, "Fin du contrat",
     r"fin\s+du\s+contrat"),
    (8, "Date de fin",
     r"date\s+de\s+fin"),
    (9, "Contrat jusqu'au",
     r"contrat\s+jusqu['’]?\s*au"),
    (10, "Maturité",
     r"maturit[ée]|maturity(?:\s+date)?"),
    (11, "Terme",
     r"\bterme\b|vertragsende|ablauf(?:datum)?"),
    (12, "En cas de vie au",
     r"en\s+cas\s+de\s+vie\s+au"),
    (13, "Capital en cas de vie à l'échéance",
     r"capital\s+en\s+cas\s+de\s+vie\s+[àa]\s+l['’]?(?:echeance|échéance)"),
    (14, "Échéance",
     r"(?<![a-zàâäéèêëïîôöùûüç])(?:echeance|échéance)(?!\s+de\s+prime)(?!\s+annuelle)"),
    (15, "Expiry",
     r"expiry(?:\s+date)?|final\s+maturity"),
]

_EXCLUDE_DATE_CTX = re.compile(
    r"(?:naissance|n[ée]e?\s+le|geburtsdatum|date\s+de\s+naissance|"
    r"date\s+du\s+courrier|courrier\s+du|lettre\s+du|"
    r"imprim[ée]?|impression|date\s+d['’]?impression|druckdatum|printed|"
    r"date\s+d['’]?[ée]dition|[ée]dit[ée]\s+le|ausstellungsdatum|"
    r"signature|sign[ée]|date\s+d['’]?effet|effet\s+au|entr[ée]e\s+en\s+vigueur|"
    r"d[ée]but\s+(?:du\s+)?contrat|beginn|"
    r"[ée]ch[ée]ance\s+de\s+prime|prime\s+annuelle|"
    r"valable\s+(?:au|jusqu)|situation\s+au|au\s+\d{1,2}[./]\d{1,2}[./]\d{2,4}\s*$)",
    flags=re.IGNORECASE,
)

_TABLE_CTX_RE = re.compile(
    r"(?:echeance|échéance|contrat|prestation|valeur\s+de\s+rachat|"
    r"police|tarif|technique|capital|rachat|ablauf|maturity)",
    flags=re.IGNORECASE,
)


def _first_date_in_text(chunk: str) -> Optional[tuple]:
    """Retourne (iso, raw) de la première date valide dans chunk."""
    for m in _DATE_TOKEN_RE.finditer(chunk or ""):
        raw = m.group(1)
        iso = _3p_date_to_iso(raw)
        if iso:
            return iso, raw
    return None


def _iter_text_lines(text: str) -> List[str]:
    lines = []
    for ln in (text or "").splitlines():
        cleaned = re.sub(r"[ \t]+", " ", ln).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def _find_expiry_near_labels(text: str) -> Optional[tuple]:
    """
    Étape 1 : pour chaque libellé d'échéance, prendre la date sur la même ligne
    ou sur les 1–2 lignes suivantes (cas tableaux AXA).
    Retourne (iso, raw, label) ou None.
    """
    lines = _iter_text_lines(text)
    if not lines:
        # Texte aplati sans newlines
        lines = [re.sub(r"\s+", " ", text or "").strip()]

    best = None  # (priority, line_idx, iso, raw, label)

    for i, line in enumerate(lines):
        for priority, label, pat in _EXPIRY_LABEL_SPECS:
            m = re.search(pat, line, flags=re.IGNORECASE)
            if not m:
                continue
            # 1) Date après le libellé sur la même ligne
            after = line[m.end():]
            found = _first_date_in_text(after)
            # 2) Sinon date n'importe où sur la ligne (colonne à droite avant le libellé OCR)
            if not found:
                found = _first_date_in_text(line)
                # Si la seule date est clairement avant un contexte exclu, ignorer
                if found and _EXCLUDE_DATE_CTX.search(line[: max(0, m.start())]):
                    # date probablement liée à autre chose avant le libellé
                    after_found = _first_date_in_text(after)
                    found = after_found
            # 3) Sinon lignes suivantes (tableau : libellé / valeur)
            if not found:
                for j in range(1, 3):
                    if i + j >= len(lines):
                        break
                    nxt = lines[i + j]
                    # Ne pas sauter à une autre rubrique trop longue sans date
                    found = _first_date_in_text(nxt)
                    if found:
                        break
                    # Ligne suivante = suite du libellé + date (AXA wrap)
                    combined = line + " " + nxt
                    if re.search(pat, combined, flags=re.IGNORECASE):
                        found = _first_date_in_text(combined[m.start():] if m.start() < len(combined) else combined)
                        if found:
                            break

            if not found:
                continue
            iso, raw = found
            ctx = line
            if _EXCLUDE_DATE_CTX.search(ctx) and not re.search(
                r"(?:echeance|échéance)\s+(?:du\s+contrat|de\s+la\s+prestation|de\s+l['’]?assurance|police)|"
                r"fin\s+du\s+contrat|maturit",
                ctx,
                re.I,
            ):
                continue
            cand = (priority, i, iso, raw, label)
            if best is None or cand[0] < best[0] or (cand[0] == best[0] and cand[1] < best[1]):
                best = cand

    if best:
        return best[2], best[3], best[4]

    # Passe 2 : texte aplati — fenêtre large après chaque libellé (jusqu'à 160 car. / 1 date)
    flat = re.sub(r"\s+", " ", text or "")
    for priority, label, pat in _EXPIRY_LABEL_SPECS:
        for m in re.finditer(pat, flat, flags=re.IGNORECASE):
            window = flat[m.end(): m.end() + 160]
            found = _first_date_in_text(window)
            if not found:
                continue
            iso, raw = found
            ctx = flat[max(0, m.start() - 40): m.end() + 80]
            if _EXCLUDE_DATE_CTX.search(ctx) and priority > 5:
                continue
            return iso, raw, label

    return None


def _collect_all_dates_with_context(text: str) -> List[dict]:
    """Toutes les dates du document avec contexte local."""
    lines = _iter_text_lines(text)
    if not lines:
        lines = [re.sub(r"\s+", " ", text or "").strip()]

    results = []
    seen = set()
    for i, line in enumerate(lines):
        for m in _DATE_TOKEN_RE.finditer(line):
            raw = m.group(1)
            iso = _3p_date_to_iso(raw)
            if not iso:
                continue
            key = (iso, i, m.start())
            if key in seen:
                continue
            seen.add(key)
            prev_line = lines[i - 1] if i > 0 else ""
            next_line = lines[i + 1] if i + 1 < len(lines) else ""
            ctx = f"{prev_line} {line} {next_line}"
            results.append({
                "iso": iso,
                "raw": raw,
                "line_idx": i,
                "line": line,
                "ctx": ctx,
                "in_table": bool(_TABLE_CTX_RE.search(ctx)),
            })
    return results


def _fallback_expiry_from_all_dates(text: str) -> Optional[tuple]:
    """
    Stratégie de secours :
    1) toutes les dates
    2) exclure naissance / courrier / édition / effet
    3) privilégier dates dans un contexte tableau (Échéance, Contrat, Prestation…)
    4) sinon date future la plus éloignée
    """
    today = datetime.now().date()
    candidates = _collect_all_dates_with_context(text)
    if not candidates:
        return None

    kept = []
    for c in candidates:
        ctx = c["ctx"]
        if _EXCLUDE_DATE_CTX.search(ctx):
            # Garder si le contexte contient aussi un vrai libellé d'échéance fort
            if not re.search(
                r"(?:echeance|échéance)\s+(?:du\s+contrat|de\s+la\s+prestation|de\s+l['’]?assurance)|"
                r"fin\s+du\s+contrat|maturit",
                ctx,
                re.I,
            ):
                continue
        try:
            d = datetime.strptime(c["iso"], "%Y-%m-%d").date()
        except ValueError:
            continue
        # Dates de naissance typiques : plus de ~16 ans dans le passé et < aujourd'hui
        # déjà partiellement filtrées ; exclure aussi dates très anciennes (< 2000) hors table
        if d.year < 2000 and not c["in_table"]:
            continue
        c["date"] = d
        kept.append(c)

    if not kept:
        kept = []
        for c in candidates:
            try:
                c["date"] = datetime.strptime(c["iso"], "%Y-%m-%d").date()
            except ValueError:
                continue
            kept.append(c)
    if not kept:
        return None

    # 3) Dates en contexte tableau / mots-clés techniques
    table_hits = [c for c in kept if c["in_table"]]
    future_table = [c for c in table_hits if c["date"] >= today]
    if future_table:
        best = max(future_table, key=lambda c: c["date"])
        return best["iso"], best["raw"], "Secours tableau (date future la plus éloignée)"

    if table_hits:
        best = max(table_hits, key=lambda c: c["date"])
        return best["iso"], best["raw"], "Secours tableau"

    # 4) Date future la plus éloignée du document
    future = [c for c in kept if c["date"] >= today]
    if future:
        best = max(future, key=lambda c: c["date"])
        return best["iso"], best["raw"], "Secours date future la plus éloignée"

    # Aucune date future : ne pas inventer une échéance passée comme échéance contrat
    return None


def _extract_3p_expiry_from_text(flat: str, document_type: str) -> tuple:
    """
    Cherche une date d'échéance selon le type de document.
    Retourne (iso_date|None, raw_date|None, pattern_label|None).

    Parcourt tout le texte (libellés + secours), pas seulement la 1re date.
    """
    if document_type in _NO_EXPIRY_DOC_TYPES:
        return None, None, None

    # Étape 1 — libellés robustes (même ligne / lignes suivantes / fenêtre large)
    found = _find_expiry_near_labels(flat)
    if found:
        return found

    # Étape 2 — stratégies de secours sur toutes les dates
    fallback = _fallback_expiry_from_all_dates(flat)
    if fallback:
        return fallback

    return None, None, None


def extract_3p_expiry_from_pdf(pdf_bytes: bytes) -> Optional[str]:
    """
    Detecte la date d'echeance d'une police 3e pilier.
    Retourne YYYY-MM-DD ou None.
    """
    contracts = extract_3p_contracts_from_pdf(pdf_bytes)
    if not contracts:
        return None
    return contracts[0].get("expiry_date")


def extract_3p_contracts_from_pdf(pdf_bytes: bytes) -> List[dict]:
    """
    Analyse un PDF 3e pilier en 2 étapes :
    1) Identifier le type de document (police, valeur de rachat, résiliation, etc.)
    2) Extraire compagnie / n° de police / échéance selon le type

    Règles :
    - 1 PDF = 1 ligne (jamais plusieurs compagnies inventées)
    - Ne jamais inventer une date d'échéance
    - Toujours retourner une ligne (même sans échéance) pour saisie manuelle
    - Résiliation / Rachat / Libre passage → pas d'échéance automatique
    """
    text = _extract_pdf_text(pdf_bytes)
    if not text:
        return [{
            "company": None,
            "policy_number": None,
            "expiry_date": None,
            "detected": False,
            "raw_date": None,
            "document_type": "Autre document",
            "expiry_label": None,
        }]

    # Conserver les sauts de ligne (essentiel pour tableaux AXA) ;
    # n'aplatir que les espaces / tabs.
    structured = re.sub(r"[ \t]+", " ", text)
    document_type = classify_3p_document_type(structured)

    company = _detect_3p_company(structured)
    policy_number = _detect_3p_policy(structured)
    expiry_iso, raw_date, expiry_label = _extract_3p_expiry_from_text(structured, document_type)

    if expiry_iso and raw_date:
        m = re.search(re.escape(raw_date), structured)
        if m:
            window = structured[max(0, m.start() - 700): min(len(structured), m.start() + 250)]
            company = _detect_3p_company(window) or company
            policy_number = _detect_3p_policy(window) or policy_number

    return [{
        "company": company,
        "policy_number": policy_number,
        "expiry_date": expiry_iso,
        "detected": bool(expiry_iso),
        "raw_date": raw_date,
        "document_type": document_type,
        "expiry_label": expiry_label,
    }]
