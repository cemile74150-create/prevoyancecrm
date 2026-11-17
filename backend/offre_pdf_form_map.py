"""
Mapping extraction structurée → champs exacts input_* des formulaires existants.

Sans modifier les JSON de formulaires. Adaptateurs par type de formulaire
(voyage / vehicule), indépendants de la compagnie ; golden ELVIA = tests.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from offre_extract_structured import (
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_TO_VERIFY,
    _value_or_none,
    map_objets_to_voyage_hints,
)
from offre_form_types import empty_form_payload, filter_form_payload_to_schema, load_form_schema
from offre_pdf_form_fill import _as_number_string, _as_swiss_date, _coerce, _fold

# ---------------------------------------------------------------------------
# Slots déclaratifs (clés schéma existantes — ne pas inventer de champs JSON)
# ---------------------------------------------------------------------------

# voyage = plaques interchangeables : 2 blocs distincts (ordre PDF = index 1, 2)
_VOYAGE_VEHICLE_SLOTS: List[Dict[str, Any]] = [
    {
        "index": 1,
        "info": {
            "marque": "input_48",
            "modele": "input_49",
            "no_matricule": "input_51",
            "canton": "input_87",
            "plaque": "input_52",
            "mise_en_circulation": "input_53",
            "prix_catalogue": "input_54",
            "prix_options": "input_55",
            "leasing": "input_56",
            "garage": "input_58",
            "emploi": "input_59",
            "km_annuel": "input_61",
        },
        "cover": {
            "rc": "input_66",
            "rc_protection_bonus": "input_67",
            "casco_integrale": "input_69",
            "franchise_collision": "input_70",
            "protection_bonus_collision": "input_73",
            "casco_partielle": "input_71",
            "assistance": "input_77",
        },
    },
    {
        "index": 2,
        "info": {
            "marque": "input_90",
            "modele": "input_91",
            "no_matricule": "input_93",
            "canton": "input_94",
            "plaque": "input_95",
            "mise_en_circulation": "input_96",
            "prix_catalogue": "input_97",
            "prix_options": "input_98",
            "leasing": "input_99",
            "garage": "input_101",
            "emploi": "input_102",
            "km_annuel": "input_104",
        },
        "cover": {
            "rc": "input_107",
            "rc_protection_bonus": "input_108",
            "casco_integrale": "input_110",
            "franchise_collision": "input_111",
            "protection_bonus_collision": "input_113",
            "casco_partielle": "input_114",
            "assistance": "input_118",
        },
    },
]

_VEHICULE_SLOT: Dict[str, Any] = {
    "index": 1,
    "info": {
        "marque": "input_48",
        "modele": "input_49",
        "no_matricule": "input_51",
        "canton": "input_87",
        "plaque": "input_52",
        "mise_en_circulation": "input_53",
        "prix_catalogue": "input_54",
        "prix_options": "input_55",
        "leasing": "input_56",
        "garage": "input_58",
        "emploi": "input_59",
        "km_annuel": "input_61",
    },
    "cover": {
        "rc": "input_66",
        "rc_protection_bonus": "input_67",
        "casco_integrale": "input_69",
        "franchise_collision": "input_70",
        "protection_bonus_collision": "input_73",
        "casco_partielle": "input_71",
        "assistance": "input_77",
    },
}

# Preneur / contrat : rôles → recherche par label (page 1 / fin), pas hardcode compagnie
_PERSON_ROLES = (
    ("civilite", "civilite"),
    ("prenom", "prenom"),
    ("nom", "nom"),
    ("adresse", "adresse"),
    ("ville", "ville"),
    ("npa", "npa"),
    ("pays", "pays"),
    ("date_naissance", "date_naissance"),
    ("nationalite", "nationalite"),
    ("permis", "permis"),
    ("email", "email"),
    ("telephone", "telephone"),
    ("date_debut", "date_debut"),
    ("montant_prime", "montant_prime"),
    ("periodicite", "periodicite"),
    ("compagnie", "compagnie"),
    ("reference_police", "reference_police"),
)


def _schema_fields_by_name(form_type: str) -> Dict[str, dict]:
    schema = load_form_schema(form_type) or {}
    out: Dict[str, dict] = {}
    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        name = field.get("name") or field.get("id")
        if name:
            out[str(name)] = field
    return out


def _canton_from_plaque(plaque: Any) -> Optional[str]:
    if not plaque:
        return None
    m = re.match(r"^\s*([A-Za-z]{1,2})\b", str(plaque))
    if not m:
        return None
    return m.group(1).upper()


def _map_emploi(utilisation: Any) -> Optional[str]:
    folded = _fold(str(utilisation or ""))
    if not folded:
        return None
    if "priv" in folded or "personnel" in folded:
        return "Trajets personnels"
    if "travail" in folded or "pendulaire" in folded:
        return "Trajet pour aller au travail"
    if "pro" in folded or "commerc" in folded:
        return "Trajets professionnels"
    return None


def _map_garage(disponibilite: Any) -> Tuple[Optional[str], str]:
    """
    Retourne (valeur_option, status).
    Preuve textuelle claire « Place de garage à disposition: Oui/Non » → found
    (mapping GF : Oui → Garage au domicile, Non → Place publique).
    Sans preuve → not_found (pas de faux to_verify).
    """
    folded = _fold(str(disponibilite or ""))
    if folded == "oui":
        return "Garage au domicile", STATUS_FOUND
    if folded == "non":
        return "Place publique", STATUS_FOUND
    return None, STATUS_NOT_FOUND


def _conducteur_detenteur_from_text(text: str) -> Tuple[Optional[str], str]:
    """
    Remplit « conducteur = détenteur » uniquement si le PDF l'affirme clairement.
    Sinon not_found (vide) — ne pas inventer un Oui en to_verify.
    """
    folded = _fold(text or "")
    if not folded:
        return None, STATUS_NOT_FOUND
    if re.search(
        r"conducteur\s+est[- ]?il\s+le\s+d[eé]tenteur\s*[:?]?\s*oui"
        r"|le\s+conducteur\s+(?:est|=)\s+(?:le\s+)?d[eé]tenteur"
        r"|conducteur\s*=\s*d[eé]tenteur"
        r"|fahrer\s*=\s*halter",
        folded,
    ):
        return "Oui", STATUS_FOUND
    if re.search(
        r"conducteur\s+est[- ]?il\s+le\s+d[eé]tenteur\s*[:?]?\s*non"
        r"|le\s+conducteur\s+n['’]?est\s+pas\s+(?:le\s+)?d[eé]tenteur",
        folded,
    ):
        return "Non", STATUS_FOUND
    return None, STATUS_NOT_FOUND


def _field_meta(name: str, value: Any, status: str, *, label: str = "", source: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "value": value,
        "status": status,
        "source": source,
    }


def _assign_named(
    *,
    payload: Dict[str, Any],
    statuses: Dict[str, Dict[str, Any]],
    filled: set,
    fields_by_name: Dict[str, dict],
    name: str,
    raw: Any,
    status: str = STATUS_FOUND,
    role: Optional[str] = None,
    source: str = "structured_map",
) -> bool:
    if name in filled:
        return False
    field = fields_by_name.get(name)
    if not field:
        return False
    if status == STATUS_NOT_FOUND or raw in (None, ""):
        statuses[name] = _field_meta(name, None, STATUS_NOT_FOUND, label=field.get("label") or "", source=source)
        return False
    if status == STATUS_TO_VERIFY:
        # Valeur proposée mais marquée à vérifier — on remplit tout de même pour revue humaine.
        coerced = _coerce(field, raw, role=role)
        if coerced in (None, "", []):
            statuses[name] = _field_meta(name, None, STATUS_TO_VERIFY, label=field.get("label") or "", source=source)
            return False
        payload[name] = coerced
        filled.add(name)
        statuses[name] = _field_meta(
            name, coerced, STATUS_TO_VERIFY, label=field.get("label") or "", source=source
        )
        return True
    coerced = _coerce(field, raw, role=role)
    if coerced in (None, "", []):
        statuses[name] = _field_meta(name, None, STATUS_NOT_FOUND, label=field.get("label") or "", source=source)
        return False
    payload[name] = coerced
    filled.add(name)
    statuses[name] = _field_meta(name, coerced, STATUS_FOUND, label=field.get("label") or "", source=source)
    return True


def _find_field_by_role(fields_by_name: Dict[str, dict], role: str, *, page: Optional[int] = None) -> Optional[dict]:
    from offre_pdf_form_fill import _role_for_label, _is_agent_label

    candidates = []
    for field in fields_by_name.values():
        ftype = field.get("type") or "text"
        lab = _fold(field.get("label") or "")
        if _is_agent_label(lab):
            continue
        if page is not None and int(field.get("page") or 0) != page:
            continue
        if _role_for_label(lab, ftype) == role:
            candidates.append(field)
    if not candidates:
        return None
    # Préférer page 1 pour identité
    candidates.sort(key=lambda f: (int(f.get("page") or 99), f.get("name") or ""))
    return candidates[0]


def _map_person_and_contract(
    *,
    form_type: str,
    extracted: dict,
    payload: Dict[str, Any],
    statuses: Dict[str, Dict[str, Any]],
    filled: set,
    fields_by_name: Dict[str, dict],
    text: str = "",
) -> None:
    from offre_pdf_form_fill import _canonical

    values = _canonical(extracted or {})
    # date permis conduire : rôle spécial (pas dans _canonical)
    if extracted.get("date_permis_conduire"):
        values["date_permis_conduire"] = extracted["date_permis_conduire"]

    role_pages = {
        "civilite": 1,
        "prenom": 1,
        "nom": 1,
        "adresse": 1,
        "ville": 1,
        "npa": 1,
        "pays": 1,
        "date_naissance": 1,
        "nationalite": 1,
        "permis": 1,
        "email": None,
        "telephone": None,
        "date_debut": None,
        "montant_prime": None,
        "periodicite": None,
        "compagnie": None,
        "reference_police": None,
    }

    for role, _ in _PERSON_ROLES:
        raw = values.get(role)
        if raw in (None, ""):
            continue
        field = _find_field_by_role(fields_by_name, role, page=role_pages.get(role))
        if not field and role_pages.get(role) is not None:
            field = _find_field_by_role(fields_by_name, role, page=None)
        if not field:
            continue
        name = field.get("name") or field.get("id")
        if not name or name in filled:
            continue
        _assign_named(
            payload=payload,
            statuses=statuses,
            filled=filled,
            fields_by_name=fields_by_name,
            name=str(name),
            raw=raw,
            status=STATUS_FOUND,
            role=role,
            source="person_contract",
        )

    # Date permis de conduire (libellé spécifique)
    dob_permis = extracted.get("date_permis_conduire")
    if dob_permis:
        for field in fields_by_name.values():
            lab = _fold(field.get("label") or "")
            if "date du permis de conduire" in lab or lab == "date du permis":
                name = field.get("name") or field.get("id")
                if name and name not in filled:
                    _assign_named(
                        payload=payload,
                        statuses=statuses,
                        filled=filled,
                        fields_by_name=fields_by_name,
                        name=str(name),
                        raw=dob_permis,
                        status=STATUS_FOUND,
                        source="permis_conduire",
                    )
                break

    # Assurance auto existante → Oui + compagnie (marque commerciale)
    marque = extracted.get("compagnie")
    structured = extracted.get("structured") if isinstance(extracted.get("structured"), dict) else {}
    assureur = _value_or_none((structured or {}).get("assureur")) if structured else None
    if marque and form_type in {"voyage", "vehicule", "motocycle"}:
        for field in fields_by_name.values():
            lab = _fold(field.get("label") or "")
            name = field.get("name") or field.get("id")
            if not name or name in filled:
                continue
            if "avez vous" in lab and "assurance automobile" in lab:
                _assign_named(
                    payload=payload,
                    statuses=statuses,
                    filled=filled,
                    fields_by_name=fields_by_name,
                    name=str(name),
                    raw="Oui",
                    status=STATUS_FOUND,
                    source="assurance_existante",
                )
            elif lab.startswith("quelle compagnie"):
                _assign_named(
                    payload=payload,
                    statuses=statuses,
                    filled=filled,
                    fields_by_name=fields_by_name,
                    name=str(name),
                    raw=marque,
                    status=STATUS_FOUND,
                    role="compagnie",
                    source="assurance_existante",
                )
            elif "compagnies suivantes" in lab or lab.startswith("la demande doit etre faite"):
                # Liste GF : souvent le porteur (Allianz) plutôt que la marque (ELVIA)
                company_for_list = assureur or marque
                _assign_named(
                    payload=payload,
                    statuses=statuses,
                    filled=filled,
                    fields_by_name=fields_by_name,
                    name=str(name),
                    raw=company_for_list,
                    status=STATUS_FOUND if assureur else STATUS_TO_VERIFY,
                    role="compagnie",
                    source="compagnies_demande",
                )

    # Conducteur = détenteur : uniquement preuve textuelle claire (sinon vide / not_found)
    det_val, det_status = _conducteur_detenteur_from_text(text or str(extracted.get("_text") or ""))
    for field in fields_by_name.values():
        lab = _fold(field.get("label") or "")
        if "conducteur est il le detenteur" in lab or "conducteur est-il le detenteur" in lab:
            name = field.get("name") or field.get("id")
            if not name or name in filled:
                break
            if det_val and det_status == STATUS_FOUND:
                _assign_named(
                    payload=payload,
                    statuses=statuses,
                    filled=filled,
                    fields_by_name=fields_by_name,
                    name=str(name),
                    raw=det_val,
                    status=STATUS_FOUND,
                    source="detenteur_explicite",
                )
            else:
                statuses[str(name)] = _field_meta(
                    str(name),
                    None,
                    STATUS_NOT_FOUND,
                    label=field.get("label") or "",
                    source="detenteur_sans_preuve",
                )
            break


def _apply_vehicle_slot(
    *,
    slot: Dict[str, Any],
    hints: Dict[str, Any],
    payload: Dict[str, Any],
    statuses: Dict[str, Dict[str, Any]],
    filled: set,
    fields_by_name: Dict[str, dict],
) -> None:
    idx = int(slot["index"])
    prefix = f"vehicule_{idx}"

    def hint(key: str) -> Any:
        return hints.get(f"{prefix}_{key}")

    info = slot.get("info") or {}
    cover = slot.get("cover") or {}

    def _normalize_vehicle_raw(key: str, raw: Any) -> Any:
        if raw in (None, ""):
            return raw
        if key == "mise_en_circulation":
            return _as_swiss_date(raw) or raw
        if key in {"prix_catalogue", "prix_options", "km_annuel", "franchise_collision"}:
            return _as_number_string(raw) or raw
        return raw

    mappings = [
        (info.get("marque"), "marque", hint("marque"), STATUS_FOUND, None),
        (info.get("modele"), "modele", hint("modele"), STATUS_FOUND, None),
        (info.get("no_matricule"), "no_matricule", hint("no_matricule"), STATUS_FOUND, None),
        (info.get("plaque"), "plaque", hint("plaque"), STATUS_FOUND, None),
        (info.get("mise_en_circulation"), "mise_en_circulation", hint("mise_en_circulation"), STATUS_FOUND, None),
        (info.get("prix_catalogue"), "prix_catalogue", hint("prix_catalogue"), STATUS_FOUND, None),
        (info.get("prix_options"), "prix_options", hint("prix_options"), STATUS_FOUND, None),
        (info.get("km_annuel"), "km_annuel", hint("km_annuel"), STATUS_FOUND, None),
        (info.get("leasing"), "leasing", hint("leasing"), STATUS_FOUND, None),
    ]
    for name, key, raw, status, role in mappings:
        if not name:
            continue
        raw = _normalize_vehicle_raw(key, raw)
        if raw in (None, ""):
            statuses.setdefault(
                name,
                _field_meta(name, None, STATUS_NOT_FOUND, label=(fields_by_name.get(name) or {}).get("label") or ""),
            )
            continue
        # Remplacer une valeur label-fill partielle (ex. date ISO sur champ text)
        if name in filled and key == "mise_en_circulation":
            filled.discard(name)
        if name in filled and key in {"prix_catalogue", "prix_options", "km_annuel"}:
            prev = payload.get(name)
            if isinstance(prev, str) and (" " in prev or prev.endswith(".0")):
                filled.discard(name)
        _assign_named(
            payload=payload,
            statuses=statuses,
            filled=filled,
            fields_by_name=fields_by_name,
            name=name,
            raw=raw,
            status=status,
            role=role,
            source=f"{prefix}_info",
        )

    canton_name = info.get("canton")
    if canton_name:
        canton = _canton_from_plaque(hint("plaque"))
        if canton:
            _assign_named(
                payload=payload,
                statuses=statuses,
                filled=filled,
                fields_by_name=fields_by_name,
                name=canton_name,
                raw=canton,
                status=STATUS_FOUND,
                source=f"{prefix}_canton",
            )

    emploi_name = info.get("emploi")
    if emploi_name:
        emploi = _map_emploi(hint("utilisation"))
        if emploi:
            _assign_named(
                payload=payload,
                statuses=statuses,
                filled=filled,
                fields_by_name=fields_by_name,
                name=emploi_name,
                raw=emploi,
                status=STATUS_FOUND,
                source=f"{prefix}_emploi",
            )

    garage_name = info.get("garage")
    if garage_name:
        garage_val, garage_status = _map_garage(hint("garage_disponibilite"))
        if garage_val:
            _assign_named(
                payload=payload,
                statuses=statuses,
                filled=filled,
                fields_by_name=fields_by_name,
                name=garage_name,
                raw=garage_val,
                status=garage_status,
                source=f"{prefix}_garage",
            )

    cover_keys = [
        ("rc", "rc"),
        ("rc_protection_bonus", "rc_protection_bonus"),
        ("casco_integrale", "casco_integrale"),
        ("casco_partielle", "casco_partielle"),
        ("assistance", "assistance"),
        ("protection_bonus_collision", "protection_bonus_collision"),
        ("franchise_collision", "franchise_collision"),
    ]
    for slot_key, hint_key in cover_keys:
        name = cover.get(slot_key)
        if not name:
            continue
        raw = hint(hint_key)
        if raw in (None, ""):
            statuses.setdefault(
                name,
                _field_meta(name, None, STATUS_NOT_FOUND, label=(fields_by_name.get(name) or {}).get("label") or ""),
            )
            continue
        if slot_key == "franchise_collision":
            raw = _as_number_string(raw) or raw
            if name in filled:
                filled.discard(name)
        _assign_named(
            payload=payload,
            statuses=statuses,
            filled=filled,
            fields_by_name=fields_by_name,
            name=name,
            raw=raw,
            status=STATUS_FOUND,
            source=f"{prefix}_cover",
        )


def merge_payload_preserve_existing(
    existing: Optional[Dict[str, Any]],
    incoming: Dict[str, Any],
    *,
    overwrite: bool = False,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Fusionne sans écraser les valeurs déjà renseignées, sauf overwrite=True.
    Retourne (merged, skipped_keys).
    """
    base = dict(existing or {})
    skipped: List[str] = []

    def _is_empty(val: Any) -> bool:
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        if isinstance(val, (list, dict)) and len(val) == 0:
            return True
        return False

    for key, val in (incoming or {}).items():
        if val is None:
            continue
        if overwrite or _is_empty(base.get(key)):
            base[key] = val
        else:
            skipped.append(key)
    return base, skipped


def map_structured_to_form_payload(
    form_type: str,
    extracted: Optional[dict],
    *,
    text: str = "",
    existing_payload: Optional[Dict[str, Any]] = None,
    overwrite_existing: bool = False,
) -> Dict[str, Any]:
    """
    Point d'entrée Phase 2–3 : payload schéma + filled_keys + field_statuses.
    Réutilise le fill générique (labels PDF) puis complète via slots structurés.
    """
    form_type = (form_type or "").strip()
    extracted = extracted or {}
    fields_by_name = _schema_fields_by_name(form_type)
    if not fields_by_name:
        return {
            "form_payload": {},
            "filled_keys": [],
            "field_statuses": {},
            "objet_hints": {},
            "skipped_existing_keys": [],
        }

    from offre_pdf_form_fill import fill_form_payload_from_pdf

    base_fill = fill_form_payload_from_pdf(form_type, extracted, text=text or str(extracted.get("_text") or ""))
    payload = dict(base_fill.get("form_payload") or empty_form_payload(form_type))
    filled: set = set(base_fill.get("filled_keys") or [])
    statuses: Dict[str, Dict[str, Any]] = {
        k: _field_meta(k, payload.get(k), STATUS_FOUND, label=(fields_by_name.get(k) or {}).get("label") or "", source="label_fill")
        for k in filled
        if k in fields_by_name
    }

    hints = map_objets_to_voyage_hints(list(extracted.get("objets") or []))
    structured = extracted.get("structured") if isinstance(extracted.get("structured"), dict) else None
    if structured and not hints:
        hints = map_objets_to_voyage_hints(list(structured.get("objets") or []))

    _map_person_and_contract(
        form_type=form_type,
        extracted=extracted,
        payload=payload,
        statuses=statuses,
        filled=filled,
        fields_by_name=fields_by_name,
        text=text or str(extracted.get("_text") or ""),
    )

    if form_type == "voyage":
        for slot in _VOYAGE_VEHICLE_SLOTS:
            _apply_vehicle_slot(
                slot=slot,
                hints=hints,
                payload=payload,
                statuses=statuses,
                filled=filled,
                fields_by_name=fields_by_name,
            )
    elif form_type in {"vehicule", "motocycle", "attestation_vehicule"}:
        _apply_vehicle_slot(
            slot=_VEHICULE_SLOT,
            hints=hints,
            payload=payload,
            statuses=statuses,
            filled=filled,
            fields_by_name=fields_by_name,
        )

    cleaned = filter_form_payload_to_schema(form_type, payload)
    filled_keys = sorted(k for k in filled if k in cleaned and cleaned.get(k) not in (None, "", []))

    # Marquer not_found pour slots véhicule attendus mais vides (revue UI)
    expected_names: List[str] = []
    if form_type == "voyage":
        for slot in _VOYAGE_VEHICLE_SLOTS:
            expected_names.extend((slot.get("info") or {}).values())
            expected_names.extend((slot.get("cover") or {}).values())
    elif form_type in {"vehicule", "motocycle"}:
        expected_names.extend((_VEHICULE_SLOT.get("info") or {}).values())
        expected_names.extend((_VEHICULE_SLOT.get("cover") or {}).values())
    for name in expected_names:
        if name not in statuses and name in fields_by_name:
            statuses[name] = _field_meta(
                name,
                None,
                STATUS_NOT_FOUND,
                label=(fields_by_name.get(name) or {}).get("label") or "",
                source="expected_slot",
            )

    merged, skipped = merge_payload_preserve_existing(
        existing_payload,
        cleaned,
        overwrite=overwrite_existing,
    )
    if existing_payload is not None and not overwrite_existing:
        # Recalculer filled_keys sur ce qui a réellement été écrit
        filled_keys = [
            k
            for k in filled_keys
            if k not in skipped and merged.get(k) not in (None, "", [])
        ]
        cleaned = filter_form_payload_to_schema(form_type, merged)
    else:
        cleaned = filter_form_payload_to_schema(form_type, cleaned)

    return {
        "form_payload": cleaned,
        "filled_keys": filled_keys,
        "field_statuses": statuses,
        "objet_hints": hints,
        "skipped_existing_keys": skipped,
    }
