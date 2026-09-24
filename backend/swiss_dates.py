"""Dates suisses JJ.MM.AAAA pour e-mails / résumés d'offres.

Ne préfixe JAMAIS « 20 » (ou « 19 ») à une année déjà à 4 chiffres.
Répare le bug historique de saisie live : 201971 → 1971, 202026 → 2026.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_DMY_RE = re.compile(
    r"^(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,6})$"
)
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def repair_mangled_year(year: str) -> str:
    """Retire un préfixe erroné « 20 » devant une année déjà à 4 chiffres."""
    s = str(year or "").strip()
    if re.fullmatch(r"20\d{4}", s):
        rest = s[2:]
        try:
            n = int(rest)
        except ValueError:
            return s
        if 1000 <= n <= 2100:
            return rest
    return s


def expand_short_year(year: str) -> str:
    """yy → 19yy / 20yy (seuil 30). Ne touche pas aux années ≥ 3 chiffres."""
    s = repair_mangled_year(year)
    if len(s) != 2:
        return s
    try:
        n = int(s)
    except ValueError:
        return s
    return ("20" if n <= 30 else "19") + s


def format_swiss_date(value: Any) -> str:
    """
    Normalise vers JJ.MM.AAAA exact.
    - ISO → suisse
    - Suisse déjà correcte → inchangée (padding jj/mm)
    - Année mangled 6 chiffres → réparée
    - Année courte volontaire (2 chiffres) → expansion yy→19xx/20xx
    Chaîne vide si valeur absente ; brut trimé si non parseable.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if "T" in text:
        text = text.split("T", 1)[0].strip()

    iso = _ISO_RE.match(text)
    if iso:
        y, m, d = iso.group(1), iso.group(2), iso.group(3)
        return f"{d}.{m}.{y}"

    # D'abord DMY complet (y compris année mangled 6 chiffres) — avant strptime
    # qui tronquerait « 10.02.201971 »[:10] → « 10.02.2019 ».
    m = _DMY_RE.match(text)
    if m:
        day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), expand_short_year(m.group(3))
        if len(year) != 4:
            return f"{day}.{month}.{repair_mangled_year(m.group(3))}"
        try:
            yy = int(year)
            if not (1000 <= yy <= 9999):
                return text
            datetime(yy, int(month), int(day))
        except ValueError:
            return f"{day}.{month}.{year}"
        return f"{day}.{month}.{year}"

    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            # Uniquement sur 10 caractères exacts pour éviter la troncature mangled
            chunk = text[:10] if len(text) >= 10 else text
            if len(chunk) < 8:
                continue
            dt = datetime.strptime(chunk, fmt)
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            continue

    return text
