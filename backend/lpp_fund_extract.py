"""
Nettoyage et parsing des caisses LPP (réponses Centrale du 2e pilier).

Objectif : nom + adresse postale utiles à l'envoi, sans parasites
(numéros de page, tableaux OCR, corps de courrier, références).
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ADRESSE_A_VERIFIER = "Adresse à vérifier"

_PAGE_HDR = re.compile(r"^Page\s+\d+\s+sur\s+\d+\s*$", re.I)
_TABLE_MARKER = re.compile(r"^\[(?:table|ocr-table-heuristics)", re.I)
_APPENDIX_SPLIT = re.compile(
    r"\n----- OCR_TABLE_APPENDIX -----\n|"
    r"\n\[ocr-table-heuristics\]\n|"
    r"\n\[table p\d+",
    re.I,
)
_PIPE_HEAVY = re.compile(r"\|")
_REF_LINE = re.compile(
    r"^(?:n[°o]\.?\s*(?:de\s*)?r[ée]f|r[ée]f(?:[ée]rence)?|votre\s+r[ée]f|notre\s+r[ée]f)\b",
    re.I,
)
_PARASITE_FRAG = re.compile(
    r"^(?:;?\s*N\.?|;|,|/|-|_|\.|\|)+$|"
    r"^page\s+\d+|"
    r"^\d+\s*/\s*\d+$|"
    r"^sur\s+\d+$",
    re.I,
)
_STREET_START = re.compile(
    r"^(?:c/o\b|postfach\b|case\s+postale\b|case\s+postal\b|p\.?\s*o\.?\s*box\b|"
    r"rue\b|route\b|avenue\b|av\.?\b|chemin\b|bd\.?\b|boulevard\b|quai\b|place\b|"
    r"strasse\b|weg\b|gasse\b|allee\b|allée\b|seestrasse\b|bahnhof\b|"
    r"general[- ]|mühlematt|weststrasse|malatrex)",
    re.I,
)
_NPA_LINE = re.compile(
    r"^(?:CH[-\s]?)?(?P<npa>\d{4})\s+(?P<city>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\- ]{1,60}?)(?:\s+\d{1,4})?\s*$"
)
_NPA_INLINE = re.compile(
    r"\b(?P<npa>\d{4})\s+(?P<city>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\- ]{1,40}?)\b(?:\s+\d{1,4})?"
)
_COUNTRY = re.compile(r"^(?:suisse|schweiz|switzerland|switzerland|liechtenstein)\s*$", re.I)
_HAS_DIGIT = re.compile(r"\d")

_BOILERPLATE_STARTS = (
    "nous attirons",
    "la comparaison",
    "nous esperons",
    "nous espérons",
    "nous vous",
    "afin d",
    "chaque annee",
    "chaque année",
    "madame monsieur",
    "agence mendes",
    "centrale du",
    "fonds de garantie",
    "en raison",
    "eu egard",
    "eu égard",
    "il existe",
    "depuis le",
    "vue d",
    "responsable de",
    "demande de recherche",
    "cordialement",
    "veuillez agreer",
    "veuillez agréer",
    "avec nos",
    "par la presente",
    "par la présente",
)

_ASSURE_HINTS = (
    "assuré",
    "assure",
    "preneur",
    "bénéficiaire",
    "beneficiaire",
    "date de naissance",
    "n° avs",
    "no avs",
    "avs",
    "numero avs",
    "numéro avs",
)


def _norm(s: str) -> str:
    import unicodedata

    raw = unicodedata.normalize("NFKD", str(s or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", raw).strip().lower()


def strip_lpp_parse_noise(text: str) -> str:
    """Retire en-têtes de page, annexes tableaux et lignes parasites avant parsing."""
    if not text:
        return ""
    # Couper toute annexe tableaux OCR / find_tables
    cut = _APPENDIX_SPLIT.search(text)
    if cut:
        text = text[: cut.start()]
    out: List[str] = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            continue
        if _PAGE_HDR.match(line):
            continue
        if _TABLE_MARKER.match(line):
            continue
        if line.count("|") >= 2:
            continue
        if _PARASITE_FRAG.match(line):
            continue
        # Cellules OCR restées avec pipes isolés
        if "|" in line:
            line = re.sub(r"\s*\|\s*", " ", line)
            line = re.sub(r"\s+", " ", line).strip(" |;,-")
            if not line or _PARASITE_FRAG.match(line):
                continue
        out.append(line)
    return "\n".join(out)


def is_boilerplate_line(line: str) -> bool:
    low = _norm(line)
    if not low:
        return True
    if any(low.startswith(s) for s in _BOILERPLATE_STARTS):
        return True
    if any(h in low for h in ("votre attention", "seul l", "competente", "compétente")):
        return True
    return False


def is_address_line(line: str) -> bool:
    low = line.lower().strip()
    if not low or is_boilerplate_line(line) or _PAGE_HDR.match(line):
        return False
    if _REF_LINE.match(line) or _PARASITE_FRAG.match(line):
        return False
    if _NPA_LINE.match(line.strip()):
        return True
    if _STREET_START.match(low):
        return True
    if re.search(r"\b(case\s+postale|postfach)\b", low) and _HAS_DIGIT.search(low):
        return True
    if re.match(r"^\d{1,4}\s+[A-Za-zÀ-ÿ]", line) and len(line) < 80:
        # « 14 Rue … » rare, mais accepter si NPA ailleurs dans le bloc
        return False
    # Rue + numéro en fin : « Malatrex 14 » sans mot-clé rue (OCR partiel)
    if re.search(r"\b\d{1,4}[a-zA-Z]?\s*$", line) and 4 <= len(line) <= 60 and _HAS_DIGIT.search(line):
        if not any(x in low for x in ("tel", "fax", "www", "http", "avs", "@")):
            # Ne pas traiter un nom d'institution contenant un chiffre comme adresse
            if any(x in low for x in ("fondation", "caisse", "stiftung", "prevoyance", "prévoyance", "pension", "lpp", "bvg")):
                return False
            return True
    if _COUNTRY.match(line.strip()):
        return True
    return False


def is_name_continuation(line: str) -> bool:
    if not line or is_boilerplate_line(line) or is_address_line(line):
        return False
    if _REF_LINE.match(line) or _PAGE_HDR.match(line) or _PARASITE_FRAG.match(line):
        return False
    if len(line) > 90:
        return False
    low = line.lower()
    if any(x in low for x in _ASSURE_HINTS):
        return False
    if any(x in low for x in ("nous ", "votre attention", "seul l", "competente", "compétente")):
        return False
    return True


def _clean_addr_token(line: str) -> str:
    s = re.sub(r"\s+", " ", str(line or "")).strip(" :\t•-|/;,")
    s = re.sub(r"\s*\|\s*", " ", s)
    s = re.sub(r"\s*;\s*N\.?\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+;\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" :;-|,")
    return s


def sanitize_address_lines(lines: Sequence[str]) -> List[str]:
    """Ne conserve que rue / CP / NPA+ville / pays."""
    cleaned: List[str] = []
    for raw in lines:
        line = _clean_addr_token(raw)
        if not line:
            continue
        if _PAGE_HDR.match(line) or _PARASITE_FRAG.match(line) or _REF_LINE.match(line):
            continue
        if is_boilerplate_line(line):
            break
        if line.count("|") >= 2:
            continue
        if any(h in line.lower() for h in _ASSURE_HINTS):
            # Adresse assuré / identité — stop
            break
        if is_address_line(line) or _NPA_LINE.match(line) or _COUNTRY.match(line):
            cleaned.append(line)
            continue
        # Ligne ambiguë après une rue déjà vue : accepter si courte et sans phrase
        if cleaned and len(line) <= 60 and not is_boilerplate_line(line):
            if _HAS_DIGIT.search(line) or _COUNTRY.match(line):
                cleaned.append(line)
        if len(cleaned) >= 5:
            break
    # Couper après la première ligne NPA+ville (sauf pays ensuite)
    result: List[str] = []
    saw_npa = False
    for line in cleaned:
        if saw_npa:
            if _COUNTRY.match(line):
                result.append(line)
            break
        result.append(line)
        if _NPA_LINE.match(line) or (_NPA_INLINE.search(line) and re.match(r"^\d{4}\b", line)):
            saw_npa = True
    return result[:5]


def address_looks_complete(address: str) -> bool:
    text = (address or "").strip()
    if not text or text == ADRESSE_A_VERIFIER:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    has_npa = any(_NPA_LINE.match(ln) or _NPA_INLINE.search(ln) for ln in lines)
    has_street = any(is_address_line(ln) and not _NPA_LINE.match(ln) for ln in lines) or (
        len(lines) >= 2 and has_npa
    )
    return bool(has_npa and has_street)


def format_caisse_address(address: str) -> Tuple[str, bool]:
    """
    Retourne (adresse_propre, incertaine).
    Si incomplet / bruité → (« Adresse à vérifier », True).
    """
    lines = sanitize_address_lines((address or "").splitlines())
    if not lines:
        return ADRESSE_A_VERIFIER, True
    joined = "\n".join(lines)
    if not address_looks_complete(joined):
        return ADRESSE_A_VERIFIER, True
    # Rejeter si trop de bruit résiduel
    low = joined.lower()
    if "page " in low or "|" in joined or "nous " in low:
        return ADRESSE_A_VERIFIER, True
    return joined, False


def build_recipient_block(name: str, address: str) -> str:
    name = re.sub(r"\s+", " ", str(name or "")).strip(" :.-")
    address = str(address or "").strip()
    if not name:
        return address
    if not address:
        return name
    if _norm(name) in _norm(address):
        return address
    return f"{name}\n{address}"


def sanitize_fund_record(fund: Dict[str, Any]) -> Dict[str, Any]:
    """Nettoie un enregistrement caisse déjà persisté (sans ré-OCR)."""
    if not isinstance(fund, dict):
        return fund
    out = dict(fund)
    name = re.sub(r"\s+", " ", str(out.get("name") or out.get("nom") or "")).strip(" :.-")
    # Retirer parasites éventuels collés au nom
    name = re.sub(r"\s*Page\s+\d+\s+sur\s+\d+\s*", " ", name, flags=re.I).strip()
    name = re.sub(r"\s+", " ", name).strip(" :.-|;")

    raw_addr = str(out.get("address") or out.get("adresse") or "")
    if out.get("address_override"):
        # Saisie manuelle : respectée telle quelle (légèrement normalisée)
        override = str(out.get("address_override")).strip()
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in override.splitlines() if ln.strip()]
        address = "\n".join(lines) if lines else ADRESSE_A_VERIFIER
        uncertain = address == ADRESSE_A_VERIFIER or not address_looks_complete(address)
    else:
        # Prefer address field; sinon extraire du recipient_block / raw
        if not raw_addr.strip():
            block = str(out.get("recipient_block") or out.get("raw") or "")
            block_lines = [ln.strip() for ln in strip_lpp_parse_noise(block).splitlines() if ln.strip()]
            if block_lines and _norm(block_lines[0]) == _norm(name):
                raw_addr = "\n".join(block_lines[1:])
            else:
                # Chercher à partir de la première ligne d'adresse
                start = 0
                for i, ln in enumerate(block_lines):
                    if is_address_line(ln):
                        start = i
                        break
                raw_addr = "\n".join(block_lines[start:])
        address, uncertain = format_caisse_address(raw_addr)

    out["name"] = name or str(out.get("name") or "Caisse")
    out["address"] = address
    out["adresse"] = address
    out["address_uncertain"] = bool(uncertain)
    out["recipient_block"] = build_recipient_block(out["name"], address)
    # raw conservé pour audit mais plus utilisé pour le courrier
    if "raw" in out and not out.get("raw_original"):
        out["raw_original"] = out.get("raw")
    out["raw"] = out["recipient_block"]
    return out


def sanitize_funds_list(funds: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for fund in funds or []:
        if not isinstance(fund, dict):
            continue
        cleaned = sanitize_fund_record(fund)
        key = (
            _norm(str(cleaned.get("person") or "")),
            _norm(str(cleaned.get("name") or "")),
        )
        if not key[1] or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def fund_address_is_ready(fund: Dict[str, Any]) -> bool:
    """True si l'adresse est complète et utilisable pour un courrier."""
    cleaned = sanitize_fund_record(fund if isinstance(fund, dict) else {})
    address = str(cleaned.get("address") or "").strip()
    if cleaned.get("address_uncertain"):
        return False
    if not address or address == ADRESSE_A_VERIFIER:
        return False
    return address_looks_complete(address)


def funds_blocking_generation(funds: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Caisses qui empêchent la génération (adresse à corriger)."""
    blocked: List[Dict[str, str]] = []
    for fund in funds or []:
        if not isinstance(fund, dict):
            continue
        cleaned = sanitize_fund_record(fund)
        if fund_address_is_ready(cleaned):
            continue
        blocked.append({
            "name": str(cleaned.get("name") or "Caisse"),
            "person": str(cleaned.get("person") or ""),
            "address": str(cleaned.get("address") or ADRESSE_A_VERIFIER),
        })
    return blocked


def collect_address_overrides(funds: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Index person|name → address_override pour survie après réanalyse."""
    out: Dict[str, str] = {}
    for fund in funds or []:
        if not isinstance(fund, dict):
            continue
        override = str(fund.get("address_override") or "").strip()
        if not override:
            continue
        person = _norm(str(fund.get("person") or ""))
        name = _norm(str(fund.get("name") or fund.get("nom") or ""))
        if not name:
            continue
        out[f"{person}|{name}"] = override
        # Clé sans personne : repli si la réanalyse change le tagging
        out[f"|{name}"] = override
    return out


def apply_address_overrides(
    funds: Iterable[Dict[str, Any]],
    overrides: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Réapplique les corrections manuelles sur des caisses fraîchement parsées."""
    if not overrides:
        return [dict(f) for f in (funds or []) if isinstance(f, dict)]
    out: List[Dict[str, Any]] = []
    for fund in funds or []:
        if not isinstance(fund, dict):
            continue
        row = dict(fund)
        person = _norm(str(row.get("person") or ""))
        name = _norm(str(row.get("name") or row.get("nom") or ""))
        override = overrides.get(f"{person}|{name}") or overrides.get(f"|{name}")
        if override:
            row["address_override"] = override
            row["address"] = override
            row["adresse"] = override
        out.append(sanitize_fund_record(row))
    return out


def parse_funds_from_clean_text(text: str) -> List[Dict[str, str]]:
    """
    Détection des institutions après nettoyage du texte.
    Même logique structurelle que l'ancien parser, avec adresses filtrées.
    """
    text = strip_lpp_parse_noise(text)
    reference = ""
    ref_m = re.search(
        r"(?:n[°o]\.?\s*de\s*r[ée]f[ée]rence|reference)\s*[:\s]\s*([0-9./-]+)",
        text,
        re.I,
    )
    if ref_m:
        reference = ref_m.group(1).strip()

    found: List[Dict[str, str]] = []
    seen = set()

    def _add_block(lines: List[str]) -> None:
        if not lines:
            return
        name_lines = [lines[0]]
        idx = 1
        while idx < len(lines) and is_name_continuation(lines[idx]):
            name_lines.append(lines[idx])
            idx += 1
        addr_lines = sanitize_address_lines(lines[idx:])
        name = re.sub(r"\s+", " ", " ".join(name_lines)).strip(" :.-")
        if len(name) < 5 or len(name) > 200:
            return
        low = _norm(name)
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
        address, uncertain = format_caisse_address("\n".join(addr_lines))
        key = low
        if key in seen:
            return
        seen.add(key)
        recipient = build_recipient_block(name, address)
        found.append({
            "name": name,
            "address": address,
            "reference": reference,
            "raw": recipient,
            "recipient_block": recipient,
            "address_uncertain": uncertain,
        })

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
        lines: List[str] = []
        for ln in body.splitlines():
            cleaned = re.sub(r"\s+", " ", ln).strip(" :\t•-")
            if not cleaned or cleaned in {":", "-", "•"}:
                continue
            if is_boilerplate_line(cleaned):
                break
            lines.append(cleaned)
        # Plusieurs caisses dans le même corps : découper dès qu'une nouvelle
        # institution commence après un bloc NPA.
        blocks: List[List[str]] = []
        current: List[str] = []
        for ln in lines:
            if (
                current
                and not is_address_line(ln)
                and is_name_continuation(ln)
                and any(_NPA_LINE.match(x) or _NPA_INLINE.search(x) for x in current)
            ):
                blocks.append(current)
                current = [ln]
            else:
                current.append(ln)
        if current:
            blocks.append(current)
        for block in blocks:
            _add_block(block)

    if found:
        return found[:40]

    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    i = 0
    while i < len(lines):
        if not _NPA_INLINE.search(lines[i]) and not re.match(r"^\d{4}\b", lines[i]):
            i += 1
            continue
        start = i
        for back in range(1, 7):
            j = i - back
            if j < 0:
                break
            if is_boilerplate_line(lines[j]):
                break
            start = j
        block = lines[start: i + 1]
        if block and not is_address_line(block[0]):
            head = block[0].lower()
            if not any(x in head for x in ("agence mendes", "centrale", "fonds de garantie", "route de saint")):
                _add_block(block)
        i += 1
    return found[:40]


def timed_parse_funds_from_text(text: str) -> Tuple[List[Dict[str, str]], Dict[str, float]]:
    """Parse + timings (ms) pour audit performance."""
    t0 = time.perf_counter()
    cleaned = strip_lpp_parse_noise(text)
    t1 = time.perf_counter()
    funds = parse_funds_from_clean_text(cleaned)
    t2 = time.perf_counter()
    return funds, {
        "strip_ms": round((t1 - t0) * 1000, 2),
        "parse_ms": round((t2 - t1) * 1000, 2),
        "total_ms": round((t2 - t0) * 1000, 2),
    }
