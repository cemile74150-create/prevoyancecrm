"""
Identité AGENT DEMANDEUR pour les demandes d'offres.

Les champs agent (prénom, nom, e-mail, FINMA) sont dérivés du profil
utilisateur authentifié — jamais de la saisie client (anti-spoofing).
"""
from __future__ import annotations

import unicodedata
from typing import Any, Optional

from offre_form_types import load_form_schema


def fold_label(label: Optional[str]) -> str:
    """Accent-fold + lowercase + apostrophes → espaces (aligné frontend)."""
    text = unicodedata.normalize("NFD", str(label or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    for apo in ("'", "'", "`", "´"):
        text = text.replace(apo, " ")
    return " ".join(text.lower().split())


def agent_identity_from_user(user: Any) -> dict[str, str]:
    """Extrait prénom / nom / e-mail / FINMA depuis un User ou un dict users."""
    if user is None:
        return {"prenom": "", "nom": "", "email": "", "finma": "", "label": ""}

    def _g(*names: str) -> str:
        for name in names:
            if isinstance(user, dict):
                raw = user.get(name)
            else:
                raw = getattr(user, name, None)
            if raw is None:
                continue
            text = str(raw).strip()
            if text:
                return text
        return ""

    prenom = _g("prenom")
    nom = _g("nom")
    name = _g("name", "conseiller")
    if not prenom and not nom and name:
        parts = name.split(None, 1)
        prenom = parts[0] if parts else ""
        nom = parts[1] if len(parts) > 1 else ""
    email = _g("email")
    finma = _g("finma_number", "agent_finma", "finma")
    label = f"{prenom} {nom}".strip() or name
    return {
        "prenom": prenom,
        "nom": nom,
        "email": email,
        "finma": finma,
        "label": label,
    }


def classify_agent_field(label: Optional[str]) -> Optional[str]:
    """
    Rôle d'un champ schéma GF pour l'identité agent.
    Retourne: prenom | nom | email | finma | full_name | None
    """
    lab = fold_label(label)
    if not lab:
        return None
    # Sections / titres seuls
    if lab in {"agent demandeur", "agent demandeur :", "informations sur l agent"}:
        return None
    if "formulaire reserve" in lab:
        return None

    # FINMA (avec ou sans « Votre »)
    if "finma" in lab:
        return "finma"

    # E-mail agent (pas l'e-mail de réception « Vous recevrez… »)
    if "recevrez" in lab:
        return None
    if "email" in lab or "e-mail" in lab or "courriel" in lab:
        if "agent" in lab or lab.startswith("votre adresse email") or "votre adresse email" in lab:
            return "email"
        return None

    # ID agent (pilier3_autre) — hors scope autofill profil
    if lab.startswith("id de l agent") or "id de l'agent" in lab:
        return None

    # Prénom / nom agent
    if "prenom de l agent" in lab:
        return "prenom"
    if "nom de l agent" in lab and "prenom" not in lab:
        return "nom"
    if "prenom et nom" in lab and "agent" in lab:
        return "full_name"

    return None


def is_agent_identity_field(field: Optional[dict]) -> bool:
    if not isinstance(field, dict):
        return False
    if field.get("type") in {"section", "html", "file", "honeypot", "captcha", "hidden"}:
        return False
    return classify_agent_field(field.get("label")) is not None


def iter_agent_fields(schema: Optional[dict]) -> list[tuple[str, str, dict]]:
    """Liste (name, role, field) des champs agent d'un schéma."""
    out: list[tuple[str, str, dict]] = []
    for field in (schema or {}).get("fields") or []:
        if not isinstance(field, dict):
            continue
        if field.get("type") in {"section", "html", "file", "honeypot", "captcha", "hidden"}:
            continue
        role = classify_agent_field(field.get("label"))
        if not role:
            continue
        name = field.get("name") or field.get("id")
        if not name:
            continue
        out.append((str(name), role, field))
    return out


def schema_requires_finma(form_type_id: Optional[str]) -> bool:
    """True si le schéma a un champ FINMA marqué required (ou présent et visible)."""
    fid = (form_type_id or "").strip()
    if not fid or fid == "pilier3_legacy":
        # Legacy : FINMA souhaité mais pas dans REQUIRED_FOR_VALIDATE historique —
        # on exige tout de même un FINMA profil pour envoyer une offre.
        return True
    schema = load_form_schema(fid) or {}
    for _name, role, field in iter_agent_fields(schema):
        if role == "finma" and field.get("required"):
            return True
    # Champ FINMA présent sans required explicite → quand même requis métier
    for _name, role, _field in iter_agent_fields(schema):
        if role == "finma":
            return True
    return False


def apply_agent_identity_to_payload(
    form_type_id: Optional[str],
    payload: Optional[dict],
    identity: dict[str, str],
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Injecte l'identité agent dans form_payload (clés schéma uniquement)."""
    next_payload: dict[str, Any] = dict(payload or {})
    fid = (form_type_id or "").strip()
    if not fid or fid == "pilier3_legacy":
        return next_payload
    schema = load_form_schema(fid) or {}
    prenom = (identity.get("prenom") or "").strip()
    nom = (identity.get("nom") or "").strip()
    email = (identity.get("email") or "").strip()
    finma = (identity.get("finma") or "").strip()
    full_name = (identity.get("label") or f"{prenom} {nom}".strip()).strip()

    role_values = {
        "prenom": prenom,
        "nom": nom,
        "email": email,
        "finma": finma,
        "full_name": full_name,
    }

    for name, role, _field in iter_agent_fields(schema):
        val = role_values.get(role) or ""
        if not val and role != "finma":
            # Toujours écraser spoof même si vide (sauf on garde finma vide pour bloquer)
            if overwrite:
                next_payload[name] = val
            continue
        cur = next_payload.get(name)
        empty = cur is None or cur == "" or (isinstance(cur, list) and len(cur) == 0)
        if overwrite or empty:
            next_payload[name] = val

    # E-mail de réception GF (« Vous recevrez les offres… ») — autofill, pas spoof agent
    if email:
        for field in schema.get("fields") or []:
            if not isinstance(field, dict):
                continue
            if field.get("type") in {"section", "html", "hidden"}:
                continue
            lab = fold_label(field.get("label"))
            if "recevrez" in lab and ("email" in lab or "e-mail" in lab or "offre" in lab):
                name = field.get("name") or field.get("id")
                if not name:
                    continue
                cur = next_payload.get(name)
                empty = cur is None or str(cur).strip() == ""
                if overwrite or empty:
                    next_payload[name] = email

    return next_payload


def apply_agent_identity_to_doc(
    doc: dict,
    identity: dict[str, str],
    *,
    overwrite_payload: bool = True,
) -> dict:
    """
    Force agent_* CRM + form_payload agent fields depuis identity.
    Mutates and returns doc.
    """
    prenom = (identity.get("prenom") or "").strip()
    nom = (identity.get("nom") or "").strip()
    email = (identity.get("email") or "").strip()
    finma = (identity.get("finma") or "").strip()
    label = (identity.get("label") or f"{prenom} {nom}".strip()).strip()

    doc["agent_prenom"] = prenom
    doc["agent_nom"] = nom
    doc["agent_email"] = email
    doc["agent_finma"] = finma
    doc["agent_label"] = label or doc.get("agent_label") or ""

    form_type = (doc.get("form_type") or "").strip()
    if form_type and form_type != "pilier3_legacy":
        payload = doc.get("form_payload") if isinstance(doc.get("form_payload"), dict) else {}
        doc["form_payload"] = apply_agent_identity_to_payload(
            form_type, payload, identity, overwrite=overwrite_payload
        )
    return doc


_MISSING_FINMA_MSG = (
    "Votre numéro FINMA n'est pas renseigné sur votre profil utilisateur. "
    "Complétez-le dans Utilisateurs (ou demandez à un administrateur) avant d'envoyer une demande d'offre."
)


def missing_agent_finma_message(doc: Optional[dict], identity: Optional[dict] = None) -> Optional[str]:
    """Message bloquant si FINMA requis et absent du profil / doc."""
    form_type = ((doc or {}).get("form_type") or "pilier3_legacy").strip()
    if not schema_requires_finma(form_type):
        return None
    finma = ""
    if identity:
        finma = (identity.get("finma") or "").strip()
    if not finma:
        finma = str((doc or {}).get("agent_finma") or "").strip()
    if finma:
        return None
    return _MISSING_FINMA_MSG
