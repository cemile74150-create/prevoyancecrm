"""
Préremplit le form_payload d'une demande d'offre à partir du texte PDF.

Les clés sont celles du schéma Gravity Forms du type choisi (input_*),
les mêmes que le formulaire de création. Aucune valeur n'est inventée :
un champ sans correspondance dans le PDF reste à sa valeur vide / défaut de schéma.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from offre_form_types import (
    empty_form_payload,
    filter_form_payload_to_schema,
    load_form_schema,
)

_SKIP_TYPES = {"section", "html", "file", "honeypot", "captcha", "hidden", "list"}
_NON_VALUES = {"", "non indique", "non renseigne", "n a", "na", "none"}
_SECONDARY_HINTS = (
    "medecin",
    "veterinaire",
    "employeur",
    "enfant",
    "conjoint",
    "beneficiaire",
    "co assure",
    "co-assure",
)


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fold_keep_len(value: str) -> str:
    """Minuscules sans accents, un caractère de sortie par caractère d'entrée."""
    out: list[str] = []
    for ch in value or "":
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        if len(base) == 1:
            out.append(base.lower())
        else:
            out.append(ch.lower())
    return "".join(out)


def _is_agent_label(lab: str) -> bool:
    return (
        "agent" in lab
        or "conseiller" in lab
        or "votre adresse email" in lab
        or "votre numero finma" in lab
        or "finma" in lab
    )


def _is_secondary_label(lab: str) -> bool:
    return any(hint in lab for hint in _SECONDARY_HINTS)


def _role_for_label(lab: str, ftype: str) -> Optional[str]:
    """Rôle sémantique du libellé schéma. None = ne pas y injecter l'identité du preneur."""
    if not lab or _is_agent_label(lab) or _is_secondary_label(lab):
        return None
    if lab.startswith("civilite") or lab in {"titre", "civilite"}:
        return "civilite"
    if lab in {"prenom", "prenom :"} or "prenom du preneur" in lab or "prenom de l assure" in lab:
        return "prenom"
    if (
        lab in {"nom", "nom de famille", "nom :"}
        or "nom du preneur" in lab
        or "nom de l assure" in lab
    ) and "assureur" not in lab:
        return "nom"
    if lab in {"sexe"}:
        return "sexe"
    if "date de naissance" in lab and "permis" not in lab:
        return "date_naissance"
    if lab.startswith("nationalite"):
        return "nationalite"
    if lab in {"permis"} or lab.startswith("permis de sejour") or lab.startswith("permis"):
        if "date" in lab:
            return None
        return "permis"
    if lab in {"adresse", "rue", "adresse postale", "domicile"}:
        return "adresse"
    if lab in {"ville", "localite"}:
        return "ville"
    if lab in {"npa", "code postal", "cp"}:
        return "npa"
    if lab in {"pays", "pays de residence"}:
        return "pays"
    if ("email" in lab or lab in {"e mail", "courriel"}) and "recevrez" not in lab:
        return "email"
    if lab.startswith("telephone") or lab in {"telephone", "tel", "mobile", "natel"}:
        return "telephone"
    if lab in {"profession", "profession exercee"}:
        return "profession"
    if "date de debut" in lab or lab in {"debut du contrat", "entree en vigueur"}:
        return "date_debut"
    if "date de fin" in lab or "date d echeance" in lab or lab in {"echeance"}:
        return "date_fin"
    if ftype != "radio" and "exoneration" not in lab and "adaptation" not in lab and (
        ("montant" in lab and "prime" in lab)
        or lab in {"prime", "prime annuelle", "prime mensuelle", "cotisation", "cotisation annuelle"}
    ):
        return "montant_prime"
    if "periodicite" in lab and "prime" in lab:
        return "periodicite"
    if ("duree" in lab and "contrat" in lab) or lab == "duree":
        return "duree"
    if lab in {"montant de la rente", "rente mensuelle", "rente mensuelle garantie"} or (
        "rente" in lab and "montant" in lab and "invalidite" not in lab
    ):
        return "rente"
    if lab in {"montant investi", "capital investi"}:
        return "montant_investi"
    if "type de pilier" in lab:
        return "type_pilier"
    if ("police" in lab or lab in {"numero de contrat", "n de contrat", "reference"}) and "condition" not in lab:
        return "reference_police"
    if ("compagnie" in lab or lab in {"assureur", "assureur actuel"}) and "commentaire" not in lab:
        return "compagnie"
    if lab in {"fumeur"} or lab.startswith("fumeur"):
        return "fumeur"
    if "statut professionnel" in lab:
        return "statut_professionnel"
    return None


def _company_key(value: str) -> str:
    folded = _fold(value)
    folded = re.sub(r"\b(assurances?|assurance|vie|ag|sa)\b", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    aliases = (
        ("swiss life", "swiss life"),
        ("swisslife", "swiss life"),
        ("la mobiliere", "mobiliere"),
        ("mobiliere", "mobiliere"),
        ("retraites populaires", "retraites populaires"),
        ("groupe mutuel", "groupe mutuel"),
        ("rentes genevoises", "rentes genevoises"),
        ("liechtenstein life", "liechtenstein life"),
        ("vaudoise", "vaudoise"),
        ("helvetia", "helvetia"),
        ("generali", "generali"),
        ("allianz", "allianz"),
        ("zurich", "zurich"),
        ("baloise", "baloise"),
        ("axa", "axa"),
        ("pax", "pax"),
        ("swica", "swica"),
    )
    for needle, key in aliases:
        if needle in folded:
            return key
    return folded


def _match_company_options(company: str, options: list) -> list[str]:
    key = _company_key(company)
    if len(key) < 3:
        return []
    found: list[str] = []
    for opt in options:
        other = _company_key(str(opt))
        if not other:
            continue
        if other == key or key in other or other in key:
            if str(opt) not in found:
                found.append(str(opt))
    return found


def _match_choice(value: Any, options: list) -> Optional[str]:
    if value is None or not options:
        return None
    folded_value = _fold(str(value))
    if not folded_value:
        return None
    yn = None
    if folded_value in {"oui", "yes", "ja", "true"}:
        yn = "oui"
    elif folded_value in {"non", "no", "nein", "false"}:
        yn = "non"
    best: Optional[str] = None
    best_len = -1
    for opt in options:
        folded_opt = _fold(str(opt))
        if not folded_opt:
            continue
        if folded_opt == folded_value:
            return str(opt)
        if yn and (folded_opt == yn or folded_opt.startswith(yn + " ")):
            if folded_opt == yn or best is None:
                best = str(opt)
                best_len = 1000 if folded_opt == yn else len(folded_opt)
            continue
        if len(folded_opt) >= 4 and (folded_opt in folded_value or folded_value in folded_opt):
            if len(folded_opt) > best_len:
                best = str(opt)
                best_len = len(folded_opt)
    return best


def _as_swiss_date(raw: Any) -> Optional[str]:
    from offre_extract import _normalize_date

    text = str(raw or "").strip()
    if not text:
        return None
    norm = _normalize_date(text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else text)
    if not norm:
        found = re.search(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2}", text)
        if found:
            norm = _normalize_date(found.group(0))
    if not norm:
        return None
    year, month, day = norm.split("-")
    return f"{day}.{month}.{year}"


def _as_number_string(raw: Any) -> Optional[str]:
    from offre_extract import _compact_money_token

    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        num = float(raw)
    else:
        found = re.search(r"[0-9][0-9'’\s.,]*", str(raw))
        num = _compact_money_token(found.group(0)) if found else None
    if num is None:
        return None
    if abs(num - round(num)) < 0.001:
        return str(int(round(num)))
    text = f"{num:.2f}".rstrip("0").rstrip(".")
    return text


def _coerce(field: dict, raw: Any, *, role: Optional[str] = None) -> Any:
    if raw is None:
        return None
    ftype = field.get("type") or "text"
    if ftype in _SKIP_TYPES:
        return None
    options = [o for o in (field.get("options") or []) if o is not None and str(o).strip()]
    if role == "compagnie" and ftype == "checkbox":
        picked = _match_company_options(str(raw), options)
        return picked or None
    if role == "type_pilier":
        return _coerce_type_pilier(raw, options)
    if role == "duree" and ftype in {"select", "radio"} and options:
        text = str(raw).strip()
        return _match_choice(f"{text} ans", options) or _match_choice(text, options) or _match_choice(f"{text} annees", options)
    if ftype == "checkbox":
        chunks = raw if isinstance(raw, list) else re.split(r"[,;/]|\bet\b", str(raw))
        picked: list[str] = []
        for chunk in chunks:
            matched = _match_choice(chunk, options) if options else str(chunk).strip()
            if matched and matched not in picked:
                picked.append(matched)
        if not picked and options:
            blob = _fold(str(raw))
            for opt in options:
                folded_opt = _fold(str(opt))
                if len(folded_opt) >= 4 and folded_opt in blob:
                    picked.append(str(opt))
        return picked or None
    if ftype in {"radio", "select"}:
        if not options:
            text = str(raw).strip()
            return text or None
        return _match_choice(raw, options)
    if ftype == "date":
        return _as_swiss_date(raw)
    if ftype == "number":
        return _as_number_string(raw)
    if ftype == "email":
        found = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", str(raw))
        return found.group(0) if found else None
    text = re.sub(r"\s+", " ", str(raw)).strip(" \t:;,-")
    if not text or _fold(text) in _NON_VALUES:
        return None
    if _fold(text) == _fold(field.get("label") or ""):
        return None
    max_len = 600 if ftype == "textarea" else 160
    if len(text) > max_len:
        return None
    return text


def _coerce_type_pilier(raw: Any, options: list) -> Optional[str]:
    folded = _fold(str(raw))
    if not options:
        text = str(raw).strip()
        return text or None
    if re.search(r"\b3a\b", folded) or "lie" in folded:
        for opt in options:
            folded_opt = _fold(str(opt))
            if "3a" in folded_opt or "lie" in folded_opt:
                return str(opt)
    if re.search(r"\b3b\b", folded) or "libre" in folded:
        for opt in options:
            folded_opt = _fold(str(opt))
            if "3b" in folded_opt or "libre" in folded_opt:
                return str(opt)
    return _match_choice(raw, options)


def _canonical(extracted: dict) -> dict[str, Any]:
    civilite = extracted.get("civilite")
    sexe = extracted.get("sexe")
    if not sexe and civilite:
        folded = _fold(str(civilite))
        if "madame" in folded or folded in {"mme", "frau"}:
            sexe = "Féminin"
        elif "monsieur" in folded or folded in {"m", "herr", "mr"}:
            sexe = "Masculin"
    duree = extracted.get("duree")
    bag = {
        "civilite": civilite,
        "prenom": extracted.get("prenom"),
        "nom": extracted.get("nom"),
        "sexe": sexe,
        "date_naissance": extracted.get("date_naissance"),
        "nationalite": extracted.get("nationalite"),
        "permis": extracted.get("permis"),
        "adresse": extracted.get("adresse"),
        "ville": extracted.get("ville"),
        "npa": extracted.get("npa"),
        "pays": extracted.get("pays"),
        "email": extracted.get("email"),
        "telephone": extracted.get("telephone"),
        "profession": extracted.get("profession"),
        "date_debut": extracted.get("date_debut"),
        "date_fin": extracted.get("date_fin"),
        "montant_prime": extracted.get("montant_prime"),
        "periodicite": extracted.get("periodicite"),
        "duree": None if duree is None else str(duree),
        "rente": extracted.get("rente_mensuelle_garantie"),
        "montant_investi": extracted.get("montant_investi"),
        "type_pilier": extracted.get("type_pilier"),
        "reference_police": extracted.get("reference_police"),
        "compagnie": extracted.get("compagnie"),
        "fumeur": extracted.get("fumeur"),
        "statut_professionnel": extracted.get("statut_professionnel"),
    }
    return {k: v for k, v in bag.items() if v not in (None, "")}


def _label_occurrences(text: str, label: str) -> list[str]:
    """Valeurs qui suivent « libellé : » dans le texte PDF, dans l'ordre."""
    words = _fold(label).split()
    if len(" ".join(words)) < 8:
        return []
    folded_text = _fold_keep_len(text or "")
    if len(folded_text) != len(text or ""):
        return []
    # Apostrophes et traits d'union du PDF ne cassent pas le libellé (« l'assuré », « souhaitez-vous »).
    separator = r"(?:[\s\-–_/'’]+)"
    pattern = separator.join(re.escape(word) for word in words)
    regex = re.compile(rf"(?:^|[\n\r.;])\s*{pattern}\s*[:：]\s*([^\n\r]{{1,220}})", re.I)
    found: list[str] = []
    for match in regex.finditer(folded_text):
        raw = (text or "")[match.start(1) : match.end(1)].strip()
        raw = re.sub(r"\s+", " ", raw).strip(" \t:;,-")
        if raw:
            found.append(raw)
    return found


def fill_form_payload_from_pdf(
    form_type: str,
    extracted: Optional[dict],
    *,
    text: str = "",
) -> dict[str, Any]:
    """
    Retourne form_payload (clés du schéma) + filled_keys (champs réellement lus dans le PDF).
    """
    form_type = (form_type or "").strip()
    schema = load_form_schema(form_type) or {}
    fields = [f for f in (schema.get("fields") or []) if isinstance(f, dict)]
    if not fields:
        return {"form_payload": {}, "filled_keys": []}

    payload = empty_form_payload(form_type)
    known_labels = {_fold(f.get("label") or "") for f in fields if f.get("label")}
    values = _canonical(extracted or {})
    source = text or str((extracted or {}).get("_text") or "")
    pdf_set: set[str] = set()
    role_used: set[str] = set()

    def assign(field: dict, raw: Any, *, role: Optional[str] = None) -> bool:
        name = field.get("name") or field.get("id")
        if not name or name in pdf_set:
            return False
        coerced = _coerce(field, raw, role=role)
        if coerced in (None, "", []):
            return False
        payload[name] = coerced
        pdf_set.add(name)
        return True

    for field in fields:
        ftype = field.get("type") or "text"
        if ftype in _SKIP_TYPES:
            continue
        lab = _fold(field.get("label") or "")
        if _is_agent_label(lab):
            continue
        role = _role_for_label(lab, ftype)
        if not role or role in role_used:
            continue
        raw = values.get(role)
        if raw in (None, ""):
            continue
        if assign(field, raw, role=role):
            if role != "compagnie":
                role_used.add(role)

    label_index: dict[str, int] = {}
    for field in fields:
        ftype = field.get("type") or "text"
        label = (field.get("label") or "").strip()
        lab = _fold(label)
        idx = label_index.get(lab, 0)
        label_index[lab] = idx + 1
        name = field.get("name") or field.get("id")
        if not name or name in pdf_set or ftype in _SKIP_TYPES or not label:
            continue
        if _is_agent_label(lab) or len(lab) < 8:
            continue
        occurrences = _label_occurrences(source, label)
        if idx >= len(occurrences):
            continue
        candidate = occurrences[idx]
        if _fold(candidate) in known_labels:
            continue
        assign(field, candidate, role=_role_for_label(lab, ftype))

    cleaned = filter_form_payload_to_schema(form_type, payload)
    return {
        "form_payload": cleaned,
        "filled_keys": sorted(k for k in pdf_set if k in cleaned),
    }
