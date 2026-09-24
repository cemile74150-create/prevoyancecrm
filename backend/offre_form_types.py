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
    return out


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

    crm_by_role = {
        "civilite": _crm_val("civilite"),
        "prenom": _crm_val("prenom"),
        "nom": _crm_val("nom"),
        "sexe": _crm_val("sexe"),
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
        cur = next_payload.get(name)
        empty = cur is None or cur == "" or (isinstance(cur, list) and len(cur) == 0)
        if empty or overwrite:
            next_payload[name] = val

    return next_payload


def _field_visible(field: dict, payload: dict) -> bool:
    sw = field.get("show_when") or {}
    rules = sw.get("rules") or []
    if not rules:
        return True
    results = []
    for rule in rules:
        raw = payload.get(rule.get("field"))
        expected = rule.get("value")
        if isinstance(raw, list):
            ok = expected in raw
        else:
            actual = "" if raw is None else str(raw)
            if rule.get("op") == "isnot":
                ok = actual != expected
            else:
                ok = actual == expected
        results.append(ok)
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
