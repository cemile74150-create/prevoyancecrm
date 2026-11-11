"""Contrôle d'accès par domaine e-mail (module Congés & absences).

Règle : e-mail normalisé (strip + minuscules) se termine par « @ » + domaine.
Miroir frontend : frontend/src/lib/emailDomainAccess.js — garder les deux alignés.
"""
from __future__ import annotations

from typing import Any, Optional

LEAVES_EMAIL_DOMAIN = "agencemendes.ch"


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def email_ends_with_domain(email: Any, domain: str = LEAVES_EMAIL_DOMAIN) -> bool:
    """True si l'e-mail (après normalisation) se termine par « @domain »."""
    normalized = normalize_email(email)
    domain_norm = str(domain or "").strip().lower().lstrip("@")
    if not normalized or not domain_norm:
        return False
    return normalized.endswith("@" + domain_norm)


def user_email(user: Any) -> str:
    if user is None:
        return ""
    if isinstance(user, dict):
        return normalize_email(user.get("email"))
    return normalize_email(getattr(user, "email", None))


def can_access_leaves_module(user: Any, domain: str = LEAVES_EMAIL_DOMAIN) -> bool:
    """Accès au module Congés : uniquement les comptes du domaine autorisé."""
    return email_ends_with_domain(user_email(user), domain)
