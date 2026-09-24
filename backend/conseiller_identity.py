"""Normalisation des libellés conseiller pour comparaison / agrégation.

Comparaisons internes : toujours via ``normalize_conseiller_key``.
Affichage : ``display_conseiller_name`` (forme lisible, canonique si fusion).
Ne modifie pas les valeurs stockées en base.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Optional

_WS = re.compile(r"\s+")


def normalize_conseiller_key(name: Any) -> str:
    """Clé stable : trim, espaces collapsés, accents retirés (NFD), casefold."""
    s = _WS.sub(" ", str(name or "").strip())
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.casefold()


def cleanup_conseiller_display(name: Any) -> str:
    """Nettoyage léger pour affichage (conserve accents et casse)."""
    return _WS.sub(" ", str(name or "").strip())


def _letter_case_flags(s: str) -> tuple[bool, bool]:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False, False
    return all(c.isupper() for c in letters), all(c.islower() for c in letters)


def _display_score(s: str) -> tuple:
    """Plus bas = préféré. Évite les mots en TOUT MAJUSCULES ; favorise Title Case."""
    words = [w for w in s.split(" ") if w]
    all_caps_words = sum(
        1 for w in words if any(c.isalpha() for c in w) and w.isupper() and len(w) > 1
    )
    title_like = sum(
        1
        for w in words
        if len(w) > 1 and w[0].isupper() and w[1:].islower()
    )
    all_lower_words = sum(
        1 for w in words if any(c.isalpha() for c in w) and w.islower()
    )
    return (all_caps_words, -title_like, all_lower_words, -len(s))


def _title_words(s: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() if w else w for w in s.split(" "))


def display_conseiller_name(*candidates: Any, fallback: str = "Non attribué") -> str:
    """Choisit un libellé lisible parmi des variantes (même personne)."""
    cleaned = [cleanup_conseiller_display(c) for c in candidates]
    cleaned = [c for c in cleaned if c]
    if not cleaned:
        return fallback
    best = min(cleaned, key=_display_score)
    all_upper, all_lower = _letter_case_flags(best)
    if all_upper or all_lower:
        return _title_words(best)
    return best


def merge_conseiller_display(current: Optional[str], incoming: Any) -> str:
    return display_conseiller_name(current, incoming)


def unique_conseiller_displays(names: Iterable[Any]) -> list[str]:
    """Déduplique une liste de noms via la clé normalisée."""
    by_key: dict[str, str] = {}
    for raw in names:
        cleaned = cleanup_conseiller_display(raw)
        if not cleaned:
            continue
        key = normalize_conseiller_key(cleaned)
        if not key:
            continue
        prev = by_key.get(key)
        by_key[key] = (
            display_conseiller_name(prev, cleaned) if prev else display_conseiller_name(cleaned)
        )
    return sorted(by_key.values(), key=lambda n: n.casefold())
