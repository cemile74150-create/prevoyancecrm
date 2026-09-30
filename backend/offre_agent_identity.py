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


def _empty_identity() -> dict[str, str]:
    return {"prenom": "", "nom": "", "email": "", "finma": "", "label": ""}


def agent_identity_from_user(user: Any) -> dict[str, str]:
    """Extrait prénom / nom / e-mail / FINMA depuis un User ou un dict users."""
    if user is None:
        return _empty_identity()

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


def agent_identity_from_doc(doc: Optional[dict]) -> dict[str, str]:
    """Identité agent déjà enregistrée sur la demande (pas le viewer)."""
    if not isinstance(doc, dict):
        return _empty_identity()
    prenom = str(doc.get("agent_prenom") or "").strip()
    nom = str(doc.get("agent_nom") or "").strip()
    email = str(doc.get("agent_email") or "").strip()
    finma = str(doc.get("agent_finma") or "").strip()
    label = str(doc.get("agent_label") or "").strip() or f"{prenom} {nom}".strip()
    if not prenom and not nom and label:
        parts = label.split(None, 1)
        prenom = parts[0] if parts else ""
        nom = parts[1] if len(parts) > 1 else ""
    return {
        "prenom": prenom,
        "nom": nom,
        "email": email,
        "finma": finma,
        "label": label,
    }


def _account_id_of(user: Any) -> str:
    if user is None:
        return ""
    if isinstance(user, dict):
        return str(user.get("account_id") or user.get("user_id") or "").strip()
    return str(
        getattr(user, "account_id", None) or getattr(user, "user_id", None) or ""
    ).strip()


def viewer_is_demande_creator(doc: Optional[dict], user: Any) -> bool:
    """True uniquement si le compte connecté est le créateur de la demande."""
    if not isinstance(doc, dict) or user is None:
        return False
    created = str(doc.get("created_by_account_id") or doc.get("created_by") or "").strip()
    viewer_id = _account_id_of(user)
    if created and viewer_id:
        return created == viewer_id
    viewer = agent_identity_from_user(user)
    bound = agent_identity_from_doc(doc)
    v_email = (viewer.get("email") or "").strip().lower()
    a_email = (bound.get("email") or "").strip().lower()
    if v_email and a_email:
        return v_email == a_email
    return False


def _identity_is_populated(identity: Optional[dict]) -> bool:
    if not identity:
        return False
    return bool(
        (identity.get("prenom") or "").strip()
        or (identity.get("nom") or "").strip()
        or (identity.get("email") or "").strip()
        or (identity.get("label") or "").strip()
    )


def identities_match(left: Optional[dict], right: Optional[dict]) -> bool:
    """True si deux identités agent désignent la même personne (e-mail, sinon prénom+nom)."""
    if not left or not right:
        return False
    left_email = (left.get("email") or "").strip().lower()
    right_email = (right.get("email") or "").strip().lower()
    if left_email and right_email:
        return left_email == right_email
    left_prenom = (left.get("prenom") or "").strip().lower()
    left_nom = (left.get("nom") or "").strip().lower()
    right_prenom = (right.get("prenom") or "").strip().lower()
    right_nom = (right.get("nom") or "").strip().lower()
    if not (left_prenom or left_nom) or not (right_prenom or right_nom):
        return False
    return left_prenom == right_prenom and left_nom == right_nom


def _normalize_identity(identity: Optional[dict]) -> dict[str, str]:
    ident = {
        "prenom": (identity.get("prenom") or "").strip() if identity else "",
        "nom": (identity.get("nom") or "").strip() if identity else "",
        "email": (identity.get("email") or "").strip() if identity else "",
        "finma": (identity.get("finma") or "").strip() if identity else "",
        "label": (identity.get("label") or "").strip() if identity else "",
    }
    if not ident["label"]:
        ident["label"] = f"{ident['prenom']} {ident['nom']}".strip()
    return ident


def resolve_agent_identity_for_write(
    doc: Optional[dict],
    user: Any,
    *,
    creator_identity: Optional[dict] = None,
) -> dict[str, str]:
    """
    Identité AGENT DEMANDEUR à afficher / persister.

    - Créateur : profil session (anti-spoof).
    - Autre viewer : identité déjà enregistrée (Sophie, ou agent réassigné par admin).
    - Si l'identité stockée = le viewer (vol à l'ouverture) : restaurer le créateur.
    """
    if viewer_is_demande_creator(doc, user) or not isinstance(doc, dict):
        return agent_identity_from_user(user)

    bound = agent_identity_from_doc(doc)
    viewer_ident = agent_identity_from_user(user)
    stolen = _identity_is_populated(bound) and identities_match(bound, viewer_ident)

    if _identity_is_populated(bound) and not stolen:
        return bound

    if stolen or not _identity_is_populated(bound):
        if _identity_is_populated(creator_identity):
            return _normalize_identity(creator_identity)

    if _identity_is_populated(bound):
        return bound
    return _empty_identity()


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
