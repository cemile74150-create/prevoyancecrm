"""
Caisse AVS destinataire pour la lettre « Demande AVS ».

Le canton de résidence propose une caisse par défaut. L'utilisateur peut
toujours choisir une autre caisse (affiliation différente) ou la CSC.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent / "data"
CAISSES_PATH = DATA_DIR / "caisses_avs_cantonales.json"
NPA_PATH = DATA_DIR / "swiss_npa_canton.json"

CANTON_LABELS = {
    "AG": "Argovie",
    "AI": "Appenzell Rhodes-Intérieures",
    "AR": "Appenzell Rhodes-Extérieures",
    "BE": "Berne",
    "BL": "Bâle-Campagne",
    "BS": "Bâle-Ville",
    "FR": "Fribourg",
    "GE": "Genève",
    "GL": "Glaris",
    "GR": "Grisons",
    "JU": "Jura",
    "LU": "Lucerne",
    "NE": "Neuchâtel",
    "NW": "Nidwald",
    "OW": "Obwald",
    "SG": "Saint-Gall",
    "SH": "Schaffhouse",
    "SO": "Soleure",
    "SZ": "Schwyz",
    "TG": "Thurgovie",
    "TI": "Tessin",
    "UR": "Uri",
    "VD": "Vaud",
    "VS": "Valais",
    "ZG": "Zoug",
    "ZH": "Zürich",
}

FOREIGN_HINTS = (
    "france", "français", "francais", "italia", "italy", "deutschland",
    "germany", "allemagne", "espagne", "spain", "belgique", "belgium",
    "autriche", "austria", "portugal", "uk", "united kingdom", "usa",
    "états-unis", "etats-unis", "étranger", "etranger", "abroad",
)


def _fold(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _digits_npa(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 4:
        return digits[:4]
    return digits


@lru_cache(maxsize=1)
def load_caisses_catalog() -> dict:
    return json.loads(CAISSES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_npa_catalog() -> dict:
    return json.loads(NPA_PATH.read_text(encoding="utf-8"))


def list_caisses() -> List[dict]:
    catalog = load_caisses_catalog()
    items = []
    for row in catalog.get("caisses") or []:
        items.append(_public_caisse(row))
    items.append(_public_caisse(catalog["csc"]))
    return items


def get_caisse(caisse_id: Optional[str]) -> Optional[dict]:
    key = str(caisse_id or "").strip().upper()
    if not key:
        return None
    catalog = load_caisses_catalog()
    if key in {"CSC", "CH", "SUISSE"}:
        return _public_caisse(catalog["csc"])
    for row in catalog.get("caisses") or []:
        if str(row.get("id") or "").upper() == key:
            return _public_caisse(row)
    return None


def _public_caisse(row: dict) -> dict:
    lines = [str(x).strip() for x in (row.get("address_lines") or []) if str(x).strip()]
    street = str(row.get("street") or "").strip()
    po_box = str(row.get("po_box") or "").strip()
    npa = str(row.get("npa") or "").strip()
    locality = str(row.get("locality") or "").strip()
    short_address = ", ".join(
        part for part in (
            street or None,
            po_box or None,
            " ".join(p for p in (npa, locality) if p) or None,
        ) if part
    )
    return {
        "id": row.get("id"),
        "canton": row.get("canton"),
        "canton_label": row.get("canton_label") or CANTON_LABELS.get(str(row.get("canton") or ""), ""),
        "name": row.get("name"),
        "name_lines": list(row.get("name_lines") or ([row.get("name")] if row.get("name") else [])),
        "street": street,
        "po_box": po_box or None,
        "npa": npa,
        "locality": locality,
        "address_lines": lines,
        "address_short": short_address,
    }


def _is_foreign_residence(client: dict) -> bool:
    pays = _fold(client.get("pays") or client.get("pays_residence"))
    if not pays:
        return False
    if pays in {"ch", "suisse", "schweiz", "switzerland", "svizzera", "swiss"}:
        return False
    if any(hint in pays for hint in FOREIGN_HINTS):
        return True
    # Code pays ISO
    if len(pays) == 2 and pays != "ch":
        return True
    return True


def _locality_cantons(ville: str) -> List[str]:
    needle = _fold(ville)
    if not needle:
        return []
    catalog = load_npa_catalog()
    mapping = catalog.get("npa_to_canton") or {}
    localities = catalog.get("localities") or {}
    hits: Dict[str, int] = {}
    for npa, names in localities.items():
        canton = mapping.get(npa)
        if not canton:
            continue
        for name in names:
            folded = _fold(name)
            if not folded:
                continue
            if folded == needle or folded.startswith(needle) or needle.startswith(folded):
                hits[canton] = hits.get(canton, 0) + 1
            else:
                # « Genève 2 » → Genève
                core = re.sub(r"\s+\d+$", "", needle).strip()
                name_core = re.sub(r"\s+\d+$", "", folded).strip()
                if core and (core == name_core or name_core.startswith(core) or core.startswith(name_core)):
                    hits[canton] = hits.get(canton, 0) + 1
    return [c for c, _ in sorted(hits.items(), key=lambda item: (-item[1], item[0]))]


def detect_residence_canton(client: dict) -> dict:
    """
    Résout le canton de résidence depuis NPA + localité (référentiel swisstopo).
    Ne déduit jamais le canton des seuls premiers chiffres du NPA.
    """
    npa = _digits_npa(client.get("npa"))
    ville = str(client.get("ville") or "").strip()
    pays = str(client.get("pays") or client.get("pays_residence") or "").strip()

    if _is_foreign_residence(client):
        return {
            "canton": None,
            "canton_label": None,
            "source": "foreign",
            "confidence": "high",
            "npa": npa or None,
            "ville": ville or None,
            "pays": pays or None,
            "message": "Résidence à l'étranger — CSC proposée par défaut.",
            "needs_manual": False,
        }

    catalog = load_npa_catalog()
    mapping = catalog.get("npa_to_canton") or {}
    ambiguous = catalog.get("ambiguous_npa") or {}
    localities = catalog.get("localities") or {}

    if npa and npa in ambiguous:
        candidates = list(ambiguous[npa])
        by_ville = _locality_cantons(ville)
        chosen = next((c for c in by_ville if c in candidates), None)
        if chosen:
            return {
                "canton": chosen,
                "canton_label": CANTON_LABELS.get(chosen, chosen),
                "source": "npa_locality",
                "confidence": "high",
                "npa": npa,
                "ville": ville or None,
                "pays": pays or None,
                "message": None,
                "needs_manual": False,
            }
        return {
            "canton": None,
            "canton_label": None,
            "source": "ambiguous_npa",
            "confidence": "low",
            "npa": npa,
            "ville": ville or None,
            "pays": pays or None,
            "candidates": candidates,
            "message": "Ce code postal couvre plusieurs cantons — sélectionnez la caisse.",
            "needs_manual": True,
        }

    if npa and npa in mapping:
        canton = mapping[npa]
        return {
            "canton": canton,
            "canton_label": CANTON_LABELS.get(canton, canton),
            "source": "npa",
            "confidence": "high",
            "npa": npa,
            "ville": ville or None,
            "pays": pays or None,
            "localities": list(localities.get(npa) or []),
            "message": None,
            "needs_manual": False,
        }

    by_ville = _locality_cantons(ville)
    if len(by_ville) == 1:
        canton = by_ville[0]
        return {
            "canton": canton,
            "canton_label": CANTON_LABELS.get(canton, canton),
            "source": "locality",
            "confidence": "medium",
            "npa": npa or None,
            "ville": ville or None,
            "pays": pays or None,
            "message": None,
            "needs_manual": False,
        }
    if len(by_ville) > 1:
        return {
            "canton": None,
            "canton_label": None,
            "source": "ambiguous_locality",
            "confidence": "low",
            "npa": npa or None,
            "ville": ville or None,
            "pays": pays or None,
            "candidates": by_ville,
            "message": "Localité ambiguë — sélectionnez la caisse manuellement.",
            "needs_manual": True,
        }

    return {
        "canton": None,
        "canton_label": None,
        "source": "unknown",
        "confidence": "none",
        "npa": npa or None,
        "ville": ville or None,
        "pays": pays or None,
        "message": "Canton non identifiable — sélectionnez la caisse manuellement.",
        "needs_manual": True,
    }


def resolve_avs_caisse(
    client: dict,
    *,
    selected_id: Optional[str] = None,
) -> dict:
    """
    Choix effectif pour l'UI / la lettre.

    Priorité :
    1. sélection manuelle enregistrée ou demandée
    2. caisse du canton détecté
    3. CSC si étranger
    4. aucune caisse (sélection manuelle obligatoire)
    """
    detection = detect_residence_canton(client)
    catalog = load_caisses_catalog()
    stored = None
    if isinstance(client.get("avs_caisse"), dict):
        stored = client.get("avs_caisse")
    preferred = (
        selected_id
        or (stored or {}).get("id")
        or (stored or {}).get("caisse_id")
        or client.get("avs_caisse_id")
    )
    manual = bool(selected_id) or bool((stored or {}).get("manual"))

    caisse = get_caisse(preferred) if preferred else None
    if caisse is None and not detection.get("needs_manual"):
        if detection.get("canton"):
            caisse = get_caisse(detection["canton"])
        elif detection.get("source") == "foreign":
            caisse = _public_caisse(catalog["csc"])

    return {
        "detection": detection,
        "caisse": caisse,
        "manual": manual and caisse is not None,
        "needs_selection": caisse is None,
        "options": list_caisses(),
        "source_ref": {
            "caisses": catalog.get("source"),
            "npa": (load_npa_catalog() or {}).get("source"),
        },
    }


def caisse_storage_payload(caisse: dict, *, manual: bool = False, detection: Optional[dict] = None) -> dict:
    return {
        "id": caisse.get("id"),
        "canton": caisse.get("canton"),
        "canton_label": caisse.get("canton_label"),
        "name": caisse.get("name"),
        "address_lines": list(caisse.get("address_lines") or []),
        "address_short": caisse.get("address_short"),
        "manual": bool(manual),
        "detected_canton": (detection or {}).get("canton"),
        "detection_source": (detection or {}).get("source"),
    }
