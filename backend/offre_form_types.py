"""
Catalogue des formulaires Demandes d'offres (schémas extraits de l'intranet GF).

Chaque type de formulaire a un id stable + un schéma de champs JSON.
Le formulaire legacy CRM (`pilier3_legacy`) conserve l'ancien wizard 3P.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

SCHEMAS_DIR = Path(__file__).resolve().parent / "offre_form_schemas"

# Toujours proposé en premier : wizard CRM historique (déjà en prod)
LEGACY_FORM = {
    "id": "pilier3_legacy",
    "label": "3ème pilier (formulaire CRM actuel)",
    "category": "3ème pilier",
    "gravity_form_id": None,
    "fields_count": 0,
    "schema_file": None,
    "active": True,
    "renderer": "legacy_wizard",
}


@lru_cache(maxsize=1)
def _index_raw() -> list[dict[str, Any]]:
    path = SCHEMAS_DIR / "index.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


@lru_cache(maxsize=1)
def load_form_menu() -> dict[str, Any]:
    """Structure exacte du menu intranet Offres (Particulier / Professionnelles)."""
    path = SCHEMAS_DIR / "menu.json"
    if not path.exists():
        return {"title": "Offres", "families": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"title": "Offres", "families": []}
    except Exception:
        return {"title": "Offres", "families": []}


def _menu_label_map() -> dict[str, str]:
    """form_type id → libellé affiché dans le menu intranet."""
    out: dict[str, str] = {}
    menu = load_form_menu()
    for family in menu.get("families") or []:
        for section in family.get("sections") or []:
            for item in section.get("items") or []:
                fid = item.get("form_type")
                if fid and fid not in out:
                    out[fid] = item.get("label") or fid
    for item in menu.get("extra_items") or []:
        fid = item.get("form_type")
        if fid and fid not in out:
            out[fid] = item.get("label") or fid
    return out


def list_form_types(*, active_only: bool = True) -> list[dict[str, Any]]:
    labels = _menu_label_map()
    items = [dict(LEGACY_FORM)]
    for row in _index_raw():
        if active_only and not row.get("active", True):
            continue
        if not row.get("fields_count"):
            continue
        fid = row.get("id")
        items.append(
            {
                "id": fid,
                "label": labels.get(fid) or row.get("label") or fid,
                "category": row.get("category") or "Autre",
                "gravity_form_id": row.get("gravity_form_id"),
                "fields_count": row.get("fields_count") or 0,
                "schema_file": row.get("schema_file"),
                "active": True,
                "renderer": "schema",
            }
        )
    # Dédupliquer par id
    seen = set()
    out = []
    for it in items:
        iid = it.get("id")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        # Prefer menu label
        if iid in labels:
            it["label"] = labels[iid]
        out.append(it)
    return out


def get_form_type(form_type_id: Optional[str]) -> Optional[dict[str, Any]]:
    fid = (form_type_id or "").strip() or LEGACY_FORM["id"]
    for it in list_form_types(active_only=False):
        if it.get("id") == fid:
            return it
    # Aussi chercher dans l'index même si fields_count=0
    for row in _index_raw():
        if row.get("id") == fid:
            return {
                "id": row.get("id"),
                "label": row.get("label") or row.get("id"),
                "category": row.get("category") or "Autre",
                "gravity_form_id": row.get("gravity_form_id"),
                "fields_count": row.get("fields_count") or 0,
                "schema_file": row.get("schema_file"),
                "active": bool(row.get("fields_count")),
                "renderer": "schema",
            }
    return None


@lru_cache(maxsize=1)
def professional_form_type_ids() -> frozenset[str]:
    """Ids des formulaires du menu « Assurances professionnelles »."""
    ids: set[str] = set()
    menu = load_form_menu()
    for family in menu.get("families") or []:
        if (family.get("id") or "").strip().lower() != "professionnelles":
            continue
        for section in family.get("sections") or []:
            for item in section.get("items") or []:
                fid = (item.get("form_type") or "").strip()
                if fid:
                    ids.add(fid)
    return frozenset(ids)


def is_professionnelle_form(
    form_type_id: Optional[str] = None,
    *,
    form_category: Optional[str] = None,
) -> bool:
    """True si le formulaire appartient à Assurances professionnelles (pas particulier)."""
    fid = (form_type_id or "").strip()
    if fid and fid in professional_form_type_ids():
        return True
    cat = (form_category or "").strip().lower()
    if "professionnelle" in cat or cat == "entreprise":
        return True
    return False


def _fold_label(label: str) -> str:
    s = unicodedata.normalize("NFKD", label or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


_CIVILITY_OPTS = {
    "monsieur",
    "madame",
    "non renseigne",
    "mr",
    "mme",
    "m.",
    "mme.",
    "homme",
    "femme",
    "masculin",
    "feminin",
}


def _sanitize_schema_identity_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure Prénom/Nom never carry civilité options that the UI would render as selects."""
    fields = data.get("fields")
    if not isinstance(fields, list):
        return data
    for field in fields:
        if not isinstance(field, dict):
            continue
        lab = _fold_label(field.get("label") or "")
        ftype = field.get("type") or "text"
        if ftype == "section" or "prenom et nom" in lab:
            continue
        opts = field.get("options") or []
        is_prenom = "prenom" in lab
        is_nom = (
            (lab in {"nom", "nom :"} or lab.startswith("nom "))
            and "assureur" not in lab
            and "veterinaire" not in lab
            and "prenom" not in lab
        )
        if not (is_prenom or is_nom):
            continue
        folded_opts = [_fold_label(str(o)) for o in opts if o is not None and str(o).strip()]
        civ_like = bool(folded_opts) and all(o in _CIVILITY_OPTS for o in folded_opts)
        country_like = len(opts) >= 20 and any(
            o in {"afghanistan", "albanie", "algerie", "allemagne", "suisse"} for o in folded_opts[:5]
        )
        if is_prenom or civ_like or (is_nom and (civ_like or (ftype == "select" and country_like))):
            field["type"] = "text"
            field["options"] = []
            default = field.get("default")
            if default is not None and _fold_label(str(default)) in _CIVILITY_OPTS:
                field.pop("default", None)
    return data


@lru_cache(maxsize=64)
def load_form_schema(form_type_id: str) -> Optional[dict[str, Any]]:
    meta = get_form_type(form_type_id)
    if not meta:
        return None
    if meta.get("renderer") == "legacy_wizard":
        return {
            **meta,
            "fields": [],
            "title": meta.get("label"),
        }
    schema_file = meta.get("schema_file")
    if not schema_file:
        return {**meta, "fields": []}
    path = SCHEMAS_DIR / schema_file
    if not path.exists():
        return {**meta, "fields": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {**meta, "fields": []}
    data["renderer"] = "schema"
    return _sanitize_schema_identity_fields(data)


def empty_form_payload(form_type_id: str) -> dict[str, Any]:
    schema = load_form_schema(form_type_id) or {}
    payload: dict[str, Any] = {}
    for field in schema.get("fields") or []:
        if field.get("type") in {"section", "html"}:
            continue
        name = field.get("name") or field.get("id")
        if not name:
            continue
        ftype = field.get("type")
        if ftype == "checkbox":
            payload[name] = []
        elif ftype == "list":
            cols = field.get("columns") or ["Valeur"]
            payload[name] = [{c: "" for c in cols}]
        elif field.get("default") not in (None, ""):
            payload[name] = field.get("default")
        else:
            payload[name] = ""
    return payload


def schema_field_names(form_type_id: str) -> set[str]:
    """Ensemble des noms de champs autorisés pour ce form_type (isolation stricte)."""
    return set(schema_fields_by_name(form_type_id).keys())


FIELD_COMMENT_SUFFIX = "__comment"

# Libellés / motifs pour lesquels une précision conseiller est utile au service Offres
_COMMENT_LABEL_HINTS = (
    "sinistre",
    "resiliation",
    "résiliation",
    "franchise",
    "garantie",
    "couverture",
    "motif",
    "pourquoi",
    "precision",
    "précision",
    "autre",
    "exclusion",
    "antecedent",
    "antécédent",
    "permis",
    "nationalite",
    "nationalité",
)


def field_comment_key(name: str) -> str:
    return f"{name}{FIELD_COMMENT_SUFFIX}"


def is_field_comment_key(key: str) -> bool:
    return str(key or "").endswith(FIELD_COMMENT_SUFFIX)


def base_field_name_from_comment_key(key: str) -> str:
    k = str(key or "")
    if k.endswith(FIELD_COMMENT_SUFFIX):
        return k[: -len(FIELD_COMMENT_SUFFIX)]
    return k


def field_allows_comment(field: Optional[dict]) -> bool:
    """
    Certains champs (choix / situations) acceptent une précision libre.
    Pas sur les zones « commentaires » déjà dédiées, ni sur sections/fichiers.
    """
    if not isinstance(field, dict):
        return False
    if field.get("allow_comment") is True:
        return True
    if field.get("allow_comment") is False:
        return False
    ftype = field.get("type") or "text"
    if ftype in {"section", "html", "file", "honeypot", "captcha", "hidden", "list", "textarea"}:
        return False
    lab = _norm_label(field.get("label") or "")
    if not lab:
        return False
    if "commentaire" in lab or "renseignement complementaire" in lab or "informations complementaires" in lab:
        return False
    if ftype in {"radio", "select", "checkbox"} and any(h in lab for h in _COMMENT_LABEL_HINTS):
        return True
    return False


def filter_form_payload_to_schema(
    form_type_id: str,
    form_payload: Optional[dict],
) -> dict[str, Any]:
    """
    Ne conserve que les clés appartenant au schéma du form_type demandé.
    Empêche le mélange de réponses entre formulaires (ex. champs 3a dans véhicule).
    Les précisions champ (`input_X__comment`) sont conservées si le champ parent est autorisé.
    """
    if not isinstance(form_payload, dict):
        return {}
    fid = (form_type_id or "").strip()
    if not fid or fid == LEGACY_FORM["id"]:
        return dict(form_payload)
    allowed = schema_field_names(fid)
    if not allowed:
        return dict(form_payload)
    out: dict[str, Any] = {}
    for k, v in form_payload.items():
        if k in allowed:
            out[k] = v
        elif is_field_comment_key(k) and base_field_name_from_comment_key(k) in allowed:
            out[k] = v
    return blank_hidden_fields_when_invisible(fid, out)


def _gender_key(value: Any) -> Optional[str]:
    """Normalize CRM / form tokens to M or F."""
    raw = str(value or "").strip()
    if not raw:
        return None
    folded = _norm_label(raw).replace(".", "").replace(" ", "")
    male = {"monsieur", "mr", "m", "homme", "masculin", "male", "h"}
    female = {"madame", "mme", "mlle", "mademoiselle", "femme", "feminin", "female", "f"}
    if folded in male or "masculin" in folded or folded.startswith("monsieur"):
        return "M"
    if folded in female or "feminin" in folded or folded.startswith("madame") or folded.startswith("mme"):
        return "F"
    return None


def _match_gender_option(value: Any, field: Optional[dict], *, kind: str) -> str:
    gender = _gender_key(value)
    if not gender:
        return ""
    options = [
        str(o) for o in ((field or {}).get("options") or [])
        if o is not None and str(o).strip()
    ]
    prefs = (
        (["Monsieur", "M.", "Mr"] if gender == "M" else ["Madame", "Mme", "Mlle"])
        if kind == "civilite"
        else (["Masculin", "Homme", "M", "Male"] if gender == "M" else ["Féminin", "Femme", "F", "Female"])
    )
    pool = options or prefs
    for pref in prefs:
        for opt in pool:
            if _norm_label(opt) == _norm_label(pref):
                return opt
    for opt in pool:
        if _gender_key(opt) == gender:
            return opt
    return pool[0] if pool else ""


def _sync_civilite_sexe_payload(schema: dict, payload: dict[str, Any], *, fill_missing_only: bool = True) -> dict[str, Any]:
    """Fill empty Civilité/Sexe from the other when both fields exist as a pair."""
    pending = None
    pairs: list[tuple[dict, dict]] = []
    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        if field.get("type") in {"section", "html"}:
            continue
        lab = _norm_label(field.get("label") or "")
        if lab.startswith("civilite") or lab == "titre":
            pending = field
            continue
        if pending is not None and lab == "sexe":
            pairs.append((pending, field))
            pending = None
    if not pairs:
        return payload
    next_payload = dict(payload)
    changed = False
    for civ_field, sex_field in pairs:
        civ_name = civ_field.get("name") or civ_field.get("id")
        sex_name = sex_field.get("name") or sex_field.get("id")
        if not civ_name or not sex_name:
            continue
        civ_val = next_payload.get(civ_name)
        sex_val = next_payload.get(sex_name)
        civ_empty = civ_val is None or str(civ_val).strip() == ""
        sex_empty = sex_val is None or str(sex_val).strip() == ""
        civ_g = _gender_key(civ_val)
        sex_g = _gender_key(sex_val)
        if civ_g and (sex_empty or (not fill_missing_only and sex_g != civ_g)):
            desired = _match_gender_option(civ_val, sex_field, kind="sexe")
            if desired and str(next_payload.get(sex_name) or "") != desired:
                next_payload[sex_name] = desired
                changed = True
        elif sex_g and civ_empty:
            desired = _match_gender_option(sex_val, civ_field, kind="civilite")
            if desired and str(next_payload.get(civ_name) or "") != desired:
                next_payload[civ_name] = desired
                changed = True
    return next_payload if changed else payload


def prefill_form_payload_from_crm(
    form_type_id: str,
    payload: Optional[dict],
    crm: Optional[dict],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Préremplit identité / adresse du schéma depuis les colonnes CRM (hub client).
    N'écrase pas une valeur déjà saisie sauf si overwrite=True.
    Civilité/sexe CRM (Homme/Femme) sont normalisés sur les options du schéma
    (Monsieur/Madame, Masculin/Féminin) puis synchronisés.
    """
    schema = load_form_schema(form_type_id) or {}
    next_payload: dict[str, Any] = dict(payload or {})
    src = crm if isinstance(crm, dict) else {}

    def _crm_val(*keys: str) -> str:
        for key in keys:
            raw = src.get(key)
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                return text
        return ""

    gender = _gender_key(_crm_val("civilite")) or _gender_key(_crm_val("sexe"))
    crm_by_role = {
        "civilite": _crm_val("civilite") or _crm_val("sexe"),
        "prenom": _crm_val("prenom"),
        "nom": _crm_val("nom"),
        "sexe": _crm_val("sexe") or _crm_val("civilite"),
        "date_naissance": _crm_val("date_naissance"),
        "nationalite": _crm_val("nationalite"),
        "permis": _crm_val("permis"),
        "adresse": _crm_val("adresse"),
        "adresse_ligne_2": _crm_val("adresse_complement", "adresse_ligne_2"),
        "ville": _crm_val("ville"),
        "npa": _crm_val("npa"),
        "pays": _crm_val("pays", "pays_residence") or "Suisse",
        "email": _crm_val("email"),
        "telephone": _crm_val("telephone"),
    }

    def _role_for_label(lab: str, *, is_agent: bool) -> Optional[str]:
        if is_agent:
            return None
        if lab.startswith("civilite") or lab == "titre":
            return "civilite"
        if lab in {"prenom", "prenom :"} or "prenom du preneur" in lab or "prenom de l'assure" in lab or "prenom de l assure" in lab:
            return "prenom"
        if lab in {"nom", "nom de famille", "nom :"} or "nom du preneur" in lab or "nom de l'assure" in lab or "nom de l assure" in lab:
            return "nom"
        if lab in {"sexe"}:
            return "sexe"
        if "date de naissance" in lab and "permis" not in lab:
            return "date_naissance"
        if lab.startswith("nationalite"):
            return "nationalite"
        if lab in {"permis"} or lab.startswith("permis de sejour") or lab.startswith("permis de séjour"):
            return "permis"
        if lab in {"adresse", "rue", "adresse postale"}:
            return "adresse"
        if "adresse ligne 2" in lab or lab in {"complement", "complement d adresse", "complément d'adresse"}:
            return "adresse_ligne_2"
        if lab in {"ville", "localite", "localité"}:
            return "ville"
        if lab in {"npa", "code postal", "cp"}:
            return "npa"
        if lab in {"pays", "pays de residence", "pays de résidence"}:
            return "pays"
        if lab in {"telephone", "tel", "mobile"} or lab.startswith("telephone"):
            return "telephone"
        if lab in {"email", "e-mail", "courriel"} and "agent" not in lab and "recevrez" not in lab:
            return "email"
        return None

    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        if field.get("type") in {"section", "html", "file", "honeypot", "captcha", "hidden"}:
            continue
        name = field.get("name") or field.get("id")
        if not name:
            continue
        lab = _norm_label(field.get("label") or "")
        is_agent = (
            "agent" in lab
            or "conseiller" in lab
            or "votre adresse email" in lab
            or "votre numero finma" in lab
        )
        role = _role_for_label(lab, is_agent=is_agent)
        if not role:
            continue
        val = crm_by_role.get(role) or ""
        if not val:
            continue
        if role in {"civilite", "sexe"}:
            matched = _match_gender_option(val if gender is None else ("Homme" if gender == "M" else "Femme"), field, kind=role)
            if matched:
                val = matched
            elif _gender_key(val) is None:
                continue
        cur = next_payload.get(name)
        empty = cur is None or cur == "" or (isinstance(cur, list) and len(cur) == 0)
        if empty or overwrite:
            next_payload[name] = val

    return _sync_civilite_sexe_payload(schema, next_payload, fill_missing_only=not overwrite)


# Suivi de « Toutes les personnes assurées sont-elles en pleine capacité de travail ? »
# Oui = pleine capacité : le champ est masqué. Non = il est affiché et obligatoire.
INCAPACITE_GAIN_LABEL = "Nature de l'incapacité de gain et depuis quand ?"


def _rule_parent_answered(raw: Any) -> bool:
    if isinstance(raw, list):
        return len(raw) > 0
    return raw is not None and str(raw).strip() != ""


def _parse_rule_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace("'", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rule_matches(rule: dict, payload: dict) -> bool:
    raw = payload.get(rule.get("field"))
    expected = rule.get("value")
    op = rule.get("op") or "is"
    if op in {">", "<", ">=", "<="}:
        left_raw = raw[0] if isinstance(raw, list) and raw else raw
        left = _parse_rule_number(left_raw)
        right = _parse_rule_number(expected)
        if left is None or right is None:
            return False
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        return left <= right
    if isinstance(raw, list):
        return expected in raw
    actual = "" if raw is None else str(raw)
    if op == "isnot":
        return actual != expected
    return actual == expected


def _show_when_parents_answered(field: dict, payload: dict) -> bool:
    """True only when every parent referenced by show_when has an explicit answer."""
    rules = (field.get("show_when") or {}).get("rules") or []
    if not rules:
        return False
    return all(_rule_parent_answered(payload.get(rule.get("field"))) for rule in rules)


def blank_hidden_fields_when_invisible(form_type_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Efface les valeurs masquées seulement si le parent a une réponse explicite.

    Si le parent est vide (dossier partiellement rempli / réouverture), on conserve
    la valeur déjà enregistrée pour ne pas détruire des données client.
    """
    if not isinstance(payload, dict):
        return {}
    schema = load_form_schema(form_type_id) or {}
    out = dict(payload)
    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        ftype = field.get("type") or "text"
        if ftype in {"section", "html", "hidden", "file"}:
            continue
        if _field_visible(field, payload):
            continue
        if not _show_when_parents_answered(field, payload):
            continue
        name = field.get("name") or field.get("id")
        if not name:
            continue
        cur = out.get(name)
        if isinstance(cur, list):
            if cur:
                out[name] = []
        elif str(cur or "").strip():
            out[name] = ""
        comment = field_comment_key(str(name))
        if str(out.get(comment) or "").strip():
            out[comment] = ""
    return out


def blank_incapacite_gain_when_hidden(form_type_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Compat : délégué au nettoyage générique des champs masqués."""
    return blank_hidden_fields_when_invisible(form_type_id, payload)


def _field_visible(field: dict, payload: dict) -> bool:
    sw = field.get("show_when") or {}
    rules = sw.get("rules") or []
    if not rules:
        return True
    results = [_rule_matches(rule, payload) for rule in rules]
    if (sw.get("logic") or "all") == "any":
        return any(results)
    return all(results)


def _value_empty(val: Any, ftype: str) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    if isinstance(val, list):
        if not val:
            return True
        if ftype == "list":
            return not any(
                str(v).strip()
                for row in val
                for v in (row.values() if isinstance(row, dict) else [row])
            )
        return False
    return False


def missing_schema_required(form_type_id: str, form_payload: Optional[dict]) -> list[str]:
    schema = load_form_schema(form_type_id) or {}
    payload = form_payload or {}
    missing = []
    for field in schema.get("fields") or []:
        if not field.get("required"):
            continue
        if field.get("type") in {"section", "html", "file"}:
            continue
        if not _field_visible(field, payload):
            continue
        name = field.get("name") or field.get("id")
        label = field.get("label") or name
        val = payload.get(name)
        if _value_empty(val, field.get("type") or "text"):
            missing.append(label)
    return missing


def _norm_label(label: str) -> str:
    return " ".join((label or "").lower().replace("é", "e").replace("è", "e").replace("ê", "e").split())


_INPUT_ID_RE = re.compile(r"^input[_\s.]?\d", re.IGNORECASE)


@lru_cache(maxsize=64)
def schema_fields_by_name(form_type_id: str) -> dict[str, dict[str, Any]]:
    """Index name → métadonnées champ pour un formulaire donné (isolé par form_type)."""
    schema = load_form_schema(form_type_id) or {}
    out: dict[str, dict[str, Any]] = {}
    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name = field.get("name") or field.get("id")
        if name:
            out[str(name)] = field
    return out


def resolve_field_label(form_type_id: Optional[str], field_name: str) -> Optional[str]:
    """
    Résout le libellé humain d'un champ (input_id → label) via le schéma du formulaire.
    Retourne None si le champ est inconnu pour ce form_type (pas de fallback technique).
    """
    fid = (form_type_id or "").strip()
    name = (field_name or "").strip()
    if not fid or not name:
        return None
    field = schema_fields_by_name(fid).get(name)
    if not field:
        return None
    label = (field.get("label") or "").strip()
    return label or None


def is_technical_input_id(key: str) -> bool:
    """True pour des clés techniques type input_124 / input 127.3."""
    return bool(_INPUT_ID_RE.match((key or "").strip()))


def format_schema_field_value(field: Optional[dict], value: Any) -> str:
    """Formate une valeur de payload pour affichage e-mail (listes, booléens, dates…)."""
    if value is None:
        return ""
    ftype = (field or {}).get("type") or "text"
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if ftype == "date":
        from swiss_dates import format_swiss_date

        return format_swiss_date(value)
    if ftype == "list" and isinstance(value, list):
        cols = (field or {}).get("columns") or []
        lines: list[str] = []
        for row in value:
            if isinstance(row, dict):
                parts = []
                for col in cols or row.keys():
                    cell = row.get(col)
                    if cell is None or not str(cell).strip():
                        continue
                    parts.append(f"{col}: {str(cell).strip()}")
                if parts:
                    lines.append(" · ".join(parts))
            else:
                text = str(row).strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        return ", ".join(parts)
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            fv = format_schema_field_value(None, v)
            if fv:
                parts.append(f"{k}: {fv}")
        return "; ".join(parts)
    return str(value).strip()


def iter_schema_filled_fields(
    form_type_id: str,
    payload: Optional[dict],
    *,
    include_empty: bool = False,
    empty_label: str = "Non renseigné",
) -> list[tuple[str, Optional[str]]]:
    """
    Parcourt le schéma dans l'ordre et produit (label, value) pour les champs.
    value=None marque un titre de section (pages / section fields).
    N'utilise que les champs du form_type demandé (pas de mélange entre formulaires).

    include_empty=True : affiche aussi les champs vides avec empty_label
    (récap complet e-mail « Offre reçue »). Sinon seuls les champs renseignés.
    """
    schema = load_form_schema(form_type_id) or {}
    fields = schema.get("fields") or []
    if not fields:
        return []
    data = payload if isinstance(payload, dict) else {}
    pages = {
        int(p.get("page")): (p.get("label") or "").strip()
        for p in (schema.get("pages") or [])
        if isinstance(p, dict) and p.get("page") is not None
    }

    rows: list[tuple[str, Optional[str]]] = []
    pending_page: Optional[str] = None
    pending_section: Optional[str] = None
    last_page: Optional[int] = None
    empty_text = (empty_label or "Non renseigné").strip() or "Non renseigné"

    for field in fields:
        if not isinstance(field, dict):
            continue
        ftype = field.get("type") or "text"
        if ftype in {"html", "file", "honeypot", "captcha", "hidden"}:
            continue

        page_no = field.get("page")
        try:
            page_int = int(page_no) if page_no is not None else None
        except (TypeError, ValueError):
            page_int = None
        if page_int is not None and page_int != last_page:
            last_page = page_int
            page_label = pages.get(page_int)
            if page_label:
                pending_page = page_label
            pending_section = None

        if ftype == "section":
            pending_section = (field.get("label") or "").strip() or None
            continue

        name = field.get("name") or field.get("id")
        if not name:
            continue
        if not _field_visible(field, data):
            continue
        raw = data.get(name)
        is_empty = _value_empty(raw, ftype)
        if is_empty and not include_empty:
            continue
        if is_empty:
            formatted = empty_text
        else:
            formatted = format_schema_field_value(field, raw)
            if not formatted or formatted in {"—", "-", "None"}:
                if not include_empty:
                    continue
                formatted = empty_text

        label = (field.get("label") or "").strip() or str(name)
        # Jamais exposer un id technique comme libellé
        if is_technical_input_id(label):
            continue

        if pending_page:
            rows.append((pending_page, None))
            pending_page = None
        if pending_section:
            rows.append((pending_section, None))
            pending_section = None
        rows.append((label, formatted))

        # Précision / commentaire associé au champ (si renseigné)
        comment_raw = data.get(field_comment_key(str(name)))
        if isinstance(comment_raw, str) and comment_raw.strip():
            rows.append((f"{label} — précision", comment_raw.strip()))

    return rows


_NON_COMPAGNIE = "envoi du formulaire"


def compagnie_key(name: Any) -> str:
    """Clé de comparaison : casse et espaces, sans fusionner des noms différents."""
    return " ".join(str(name or "").strip().casefold().split())


def is_mode_traitement(value: Any) -> bool:
    """« Envoi du formulaire » est un mode d'envoi, pas une compagnie."""
    return _fold_label(str(value or "")) == _NON_COMPAGNIE


def is_champ_compagnies_sollicitees(field: dict) -> bool:
    """Champ du formulaire où le conseiller choisit les compagnies à consulter."""
    if not isinstance(field, dict):
        return False
    ftype = field.get("type") or ""
    options = [str(opt).strip() for opt in (field.get("options") or []) if str(opt).strip()]
    if ftype not in {"checkbox", "radio", "select"} or not options:
        return False
    label = _fold_label(field.get("label") or "")
    if "compagnies suivantes" in label or "compagnie suivante" in label:
        return True
    if label.startswith("quelles compagnies"):
        return True
    if "compagnie" in label and "obtenir une offre" in label:
        return True
    if label.rstrip(" :") == "compagnies":
        return True
    return False


def champs_compagnies_sollicitees(form_type_id: Optional[str]) -> list[dict[str, Any]]:
    schema = load_form_schema(form_type_id or "") or {}
    return [
        field
        for field in (schema.get("fields") or [])
        if is_champ_compagnies_sollicitees(field)
    ]


def _dedupe_compagnies(names: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        text = str(raw or "").strip()
        if not text or is_mode_traitement(text):
            continue
        key = compagnie_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _valeurs_payload(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    return [text] if text else []


def options_compagnies_formulaire(form_type_id: Optional[str]) -> list[str]:
    """Compagnies proposées par ce formulaire, lues dans son schéma."""
    names: list[str] = []
    for field in champs_compagnies_sollicitees(form_type_id):
        for opt in field.get("options") or []:
            text = str(opt).strip()
            if text:
                names.append(text)
    return _dedupe_compagnies(names)


def compagnies_selectionnees(
    form_type_id: Optional[str],
    payload: Optional[dict],
    *,
    visible_only: bool = True,
) -> list[str]:
    """Compagnies cochées dans la demande, avec le libellé exact du formulaire."""
    data = payload if isinstance(payload, dict) else {}
    selected: list[str] = []
    for field in champs_compagnies_sollicitees(form_type_id):
        if visible_only and not _field_visible(field, data):
            continue
        name = field.get("name") or field.get("id")
        if not name:
            continue
        by_key = {
            compagnie_key(opt): str(opt).strip()
            for opt in (field.get("options") or [])
            if str(opt).strip() and not is_mode_traitement(opt)
        }
        for raw in _valeurs_payload(data.get(name)):
            if is_mode_traitement(raw):
                continue
            canonical = by_key.get(compagnie_key(raw))
            if canonical:
                selected.append(canonical)
    return _dedupe_compagnies(selected)


def sync_compagnies_from_payload(target: dict, form_type_id: str, payload: dict[str, Any]) -> None:
    """Recopie les compagnies cochées vers la colonne CRM, sans toucher aux offres."""
    fields = champs_compagnies_sollicitees(form_type_id)
    if not fields or not isinstance(payload, dict):
        return
    present = False
    for field in fields:
        name = field.get("name") or field.get("id")
        if name and name in payload:
            present = True
            break
    if not present:
        return
    target["compagnies"] = compagnies_selectionnees(form_type_id, payload)


def referentiel_compagnies(legacy: Optional[list[str]] = None) -> list[str]:
    """
    Union du wizard historique et de tous les formulaires actifs.
    Sert au filtre ; le wizard 3e pilier conserve sa propre liste.
    """
    names = [str(item).strip() for item in (legacy or []) if str(item).strip()]
    for form in list_form_types(active_only=True):
        names.extend(options_compagnies_formulaire(form.get("id")))
    return _dedupe_compagnies(names)


def sync_crm_fields_from_payload(target: dict, form_type_id: str, payload: dict[str, Any]) -> None:
    """Mappe quelques champs schéma → colonnes CRM (client / agent / prime) pour la liste."""
    schema = load_form_schema(form_type_id) or {}
    for field in schema.get("fields") or []:
        if field.get("type") in {"section", "html", "file"}:
            continue
        name = field.get("name") or field.get("id")
        if not name:
            continue
        raw = payload.get(name)
        if raw is None:
            continue
        if isinstance(raw, list):
            val = ", ".join(str(x) for x in raw if str(x).strip())
        else:
            val = str(raw).strip()
        if not val:
            continue
        lab = _norm_label(field.get("label") or "")
        is_agent = "agent" in lab or "conseiller" in lab or "votre adresse email" in lab or "votre numero finma" in lab
        if "nom de l'entreprise" in lab or lab == "nom de l entreprise":
            target["nom"] = val
            target["client_label"] = val
        elif lab in {"nom", "nom de famille", "nom :"} and not is_agent:
            target["nom"] = val
        elif lab in {"prenom", "prenom :"} and not is_agent:
            target["prenom"] = val
        elif ("prenom du preneur" in lab or "prenom de l'assure" in lab or "prenom de l assure" in lab) and not is_agent:
            target["prenom"] = val
        elif ("nom du preneur" in lab or "nom de l'assure" in lab or "nom de l assure" in lab) and not is_agent:
            target["nom"] = val
        elif ("prenom de l'employeur" in lab or "prenom de l employeur" in lab) and not target.get("prenom"):
            target["prenom"] = val
        elif ("nom de l'employeur" in lab or "nom de l employeur" in lab) and not target.get("nom"):
            target["nom"] = val
        elif ("prenom de l'agent" in lab or lab.endswith("— prenom") or "prenom de l agent" in lab) and is_agent:
            target["agent_prenom"] = val
        elif ("nom de l'agent" in lab or lab.endswith("— nom")) and is_agent:
            target["agent_nom"] = val
        elif "date de naissance" in lab and "permis" not in lab:
            target["date_naissance"] = val
        elif lab in {"adresse", "rue", "adresse postale"}:
            target["adresse"] = val
        elif lab in {"ville", "localite"}:
            target["ville"] = val
        elif lab in {"npa", "code postal", "cp"}:
            target["npa"] = val
        elif "email" in lab and ("votre" in lab or is_agent or "recevrez les offres" in lab):
            target["agent_email"] = val
        elif "finma" in lab:
            target["agent_finma"] = val
        elif "montant" in lab and "prime" in lab:
            try:
                target["montant_prime"] = float(str(val).replace("'", "").replace(" ", "").replace(",", "."))
            except Exception:
                pass
        elif lab.startswith("civilite") or lab == "titre":
            target["civilite"] = val
        elif "langue" in lab and "offre" in lab:
            target["langue_offre"] = val


_RDV_SKIP_TYPES = {
    "section", "html", "file", "checkbox", "radio", "select", "list",
    "number", "email", "tel", "hidden", "honeypot", "captcha", "consent",
    "name", "address",
}
_EMPTY_RDV_MARKERS = {"", "—", "-", "–", "aucun", "none", "null"}


def _rdv_label_key(label: str) -> str:
    """Libellé plié : accents, ponctuation et espaces ignorés."""
    return re.sub(r"[^a-z0-9]+", " ", _fold_label(label or "")).strip()


def _is_rdv_client_label(label: str) -> bool:
    key = _rdv_label_key(label)
    return bool(key) and "client" in key.split() and "rendez vous" in key


def _is_date_rdv_field(field: dict) -> bool:
    if not isinstance(field, dict):
        return False
    if (field.get("type") or "text") in _RDV_SKIP_TYPES:
        return False
    return _is_rdv_client_label(field.get("label") or "")


def _is_heure_rdv_field(field: dict) -> bool:
    if not isinstance(field, dict):
        return False
    if (field.get("type") or "text") in _RDV_SKIP_TYPES:
        return False
    key = _rdv_label_key(field.get("label") or "")
    if "heure" not in key.split():
        return False
    return "rendez vous" in key or "rdv" in key.split() or "client" in key.split()


def _payload_blank(value: Any) -> bool:
    if value is None or value is False:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _EMPTY_RDV_MARKERS
    if isinstance(value, (list, tuple)):
        return all(_payload_blank(item) for item in value)
    if isinstance(value, dict):
        return all(_payload_blank(item) for item in value.values())
    return False


def _field_keys(field: dict) -> list[str]:
    keys: list[str] = []
    for raw in (field.get("name"), field.get("id")):
        if raw is None:
            continue
        text = str(raw).strip()
        if text and text not in keys:
            keys.append(text)
    gf = field.get("gf_field_id")
    if gf is not None and str(gf).strip():
        alias = f"input_{str(gf).strip()}"
        if alias not in keys:
            keys.append(alias)
    label = str(field.get("label") or "").strip()
    if label and label not in keys:
        keys.append(label)
    return keys


def _lookup_field_value(payload: dict, field: dict) -> Any:
    keys = _field_keys(field)
    for key in keys:
        if key in payload and not _payload_blank(payload.get(key)):
            return payload.get(key)
    targets = {key for key in (_rdv_label_key(item) for item in keys) if key}
    if targets:
        for key, val in payload.items():
            if _payload_blank(val):
                continue
            if _rdv_label_key(str(key)) in targets:
                return val
    name = str(field.get("name") or field.get("id") or "").strip()
    if not name:
        return None
    parts: list[str] = []
    found_sub = False
    for index in (1, 2, 3):
        piece = ""
        for sep in (".", "_"):
            raw = payload.get(f"{name}{sep}{index}")
            if not _payload_blank(raw):
                piece = str(raw).strip()
                found_sub = True
                break
        parts.append(piece)
    return parts if found_sub else None


def _normalize_heure(value: Any) -> str:
    match = re.search(r"(\d{1,2})\s*[:hH]\s*(\d{2})", str(value or ""))
    if not match:
        return ""
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return f"{hour:02d}:{minute:02d}"


def _iso_ymd(year: Any, month: Any, day: Any) -> str:
    from datetime import datetime

    from swiss_dates import expand_short_year

    try:
        y_text = expand_short_year(str(year).strip())
        y, m, d = int(y_text), int(str(month).strip()), int(str(day).strip())
        datetime(y, m, d)
    except (TypeError, ValueError):
        return ""
    if not (1000 <= y <= 9999):
        return ""
    return f"{y:04d}-{m:02d}-{d:02d}"


def _iso_from_text(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if iso:
        return _iso_ymd(iso.group(1), iso.group(2), iso.group(3))
    ymd = re.match(r"^(\d{4})[./](\d{1,2})[./](\d{1,2})$", raw)
    if ymd:
        return _iso_ymd(ymd.group(1), ymd.group(2), ymd.group(3))
    dmy = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,6})$", raw)
    if dmy:
        return _iso_ymd(dmy.group(3), dmy.group(2), dmy.group(1))
    return ""


def _split_date_heure(value: Any) -> tuple[str, str]:
    """Date ISO + heure, sans interpréter une date de création ou d'envoi."""
    if value is None or isinstance(value, bool):
        return "", ""
    if isinstance(value, dict):
        year = value.get("year") or value.get("annee") or value.get("Y")
        month = value.get("month") or value.get("mois") or value.get("m")
        day = value.get("day") or value.get("jour") or value.get("d")
        heure = _normalize_heure(value.get("heure") or value.get("time") or "")
        if year and month and day:
            return _iso_ymd(year, month, day), heure
        for key in ("date", "value"):
            if not _payload_blank(value.get(key)):
                iso, embedded = _split_date_heure(value.get(key))
                return iso, heure or embedded
        return "", ""
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        if len(parts) >= 3 and all(re.fullmatch(r"\d{1,6}", part) for part in parts[:3]):
            first, second, third = parts[:3]
            heure = _normalize_heure(" ".join(parts[3:]))
            if len(first) == 4:
                return _iso_ymd(first, second, third), heure
            return _iso_ymd(third, second, first), heure
        return _split_date_heure(" ".join(parts))
    text = str(value).strip()
    if text.lower() in _EMPTY_RDV_MARKERS:
        return "", ""
    heure = ""
    match = re.search(r"(?:T|\s+)(\d{1,2})\s*[:hH]\s*(\d{2})", text)
    if match:
        heure = _normalize_heure(match.group(0))
        text = text[: match.start()].strip()
    iso = _iso_from_text(text)
    return (iso, heure) if iso else ("", "")


def rdv_client_depuis_formulaire(
    form_type_id: Optional[str],
    payload: Optional[dict],
) -> tuple[str, str]:
    """Date (ISO) et heure du rendez-vous client saisies dans le formulaire.

    Les schémas ne partagent pas la même clé (`input_35`, `input_60`, …).
    Le libellé « rendez-vous avec le client » est la source, pas la date
    d'envoi ni la date de création.
    """
    data = payload if isinstance(payload, dict) else {}
    if not data:
        return "", ""
    schema = load_form_schema((form_type_id or "").strip()) or {}
    date_iso, heure = "", ""
    for field in schema.get("fields") or []:
        if not _is_date_rdv_field(field):
            continue
        iso, embedded = _split_date_heure(_lookup_field_value(data, field))
        if iso:
            date_iso, heure = iso, embedded
            break
    if date_iso and not heure:
        for field in schema.get("fields") or []:
            if not _is_heure_rdv_field(field):
                continue
            found = _normalize_heure(_lookup_field_value(data, field))
            if found:
                heure = found
                break
    if date_iso:
        return date_iso, heure
    for key, val in data.items():
        if not _is_rdv_client_label(str(key)):
            continue
        iso, embedded = _split_date_heure(val)
        if iso:
            return iso, embedded
    return "", ""


def rdv_client_effectif(doc: Optional[dict]) -> tuple[str, str]:
    """Date affichée : `date_prochain_rdv` si elle est déjà la source, sinon le formulaire."""
    data = doc if isinstance(doc, dict) else {}
    stored_iso, stored_embedded = _split_date_heure(data.get("date_prochain_rdv"))
    if stored_iso:
        heure = _normalize_heure(data.get("heure_rdv")) or stored_embedded
        return stored_iso, heure
    return rdv_client_depuis_formulaire(data.get("form_type"), data.get("form_payload"))
