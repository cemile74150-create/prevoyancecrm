"""Entreprises (cabinets) — FINMA et domaines e-mail partagés entre utilisateurs."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

COLLECTION = "entreprises"

AGENCE_MENDES_NOM = "Agence Mendes"
AGENCE_MENDES_FINMA = "F01101452"
AGENCE_MENDES_DOMAIN = "agencemendes.ch"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_domain(raw: Optional[str]) -> str:
    d = (raw or "").strip().lower()
    if d.startswith("@"):
        d = d[1:]
    d = d.strip().strip(".")
    return d


def normalize_domains(domains: Optional[list[str]]) -> list[str]:
    out: list[str] = []
    seen = set()
    for raw in domains or []:
        d = normalize_domain(raw)
        if not d or d in seen:
            continue
        if not re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$", d):
            continue
        seen.add(d)
        out.append(d)
    return out


def email_domain(email: Optional[str]) -> str:
    e = (email or "").strip().lower()
    if "@" not in e:
        return ""
    return normalize_domain(e.split("@", 1)[1])


class EntrepriseCreate(BaseModel):
    nom: str
    finma_number: str
    email_domains: list[str] = Field(default_factory=list)
    active: bool = True


class EntrepriseUpdate(BaseModel):
    nom: Optional[str] = None
    finma_number: Optional[str] = None
    email_domains: Optional[list[str]] = None
    active: Optional[bool] = None


def new_entreprise_doc(
    *,
    nom: str,
    finma_number: str,
    email_domains: Optional[list[str]] = None,
    active: bool = True,
    entreprise_id: Optional[str] = None,
) -> dict[str, Any]:
    now = _now()
    return {
        "id": entreprise_id or f"ent_{uuid.uuid4().hex[:12]}",
        "nom": (nom or "").strip(),
        "finma_number": (finma_number or "").strip(),
        "email_domains": normalize_domains(email_domains),
        "active": bool(active),
        "created_at": now,
        "updated_at": now,
    }


def public_entreprise(doc: Optional[dict]) -> Optional[dict]:
    if not isinstance(doc, dict):
        return None
    return {
        "id": doc.get("id"),
        "nom": doc.get("nom") or "",
        "finma_number": doc.get("finma_number") or "",
        "email_domains": list(doc.get("email_domains") or []),
        "active": doc.get("active", True) is not False,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


def match_entreprise_by_name(entreprises: list[dict], nom: str) -> Optional[dict]:
    key = (nom or "").strip().casefold()
    if not key:
        return None
    for e in entreprises:
        if (e.get("nom") or "").strip().casefold() == key:
            return e
    return None


def match_entreprise_by_email_domain(entreprises: list[dict], email: str) -> Optional[dict]:
    dom = email_domain(email)
    if not dom:
        return None
    for e in entreprises:
        if e.get("active") is False:
            continue
        for d in e.get("email_domains") or []:
            if normalize_domain(d) == dom:
                return e
    return None


async def ensure_agence_mendes(db) -> dict:
    """Crée Agence Mendes si absente (idempotent). Ne rattache aucun utilisateur."""
    existing = await db[COLLECTION].find_one(
        {"nom": {"$regex": r"^Agence\s+Mendes$", "$options": "i"}},
        {"_id": 0},
    )
    if existing:
        # Complète FINMA / domaine si manquants
        updates = {}
        if not (existing.get("finma_number") or "").strip():
            updates["finma_number"] = AGENCE_MENDES_FINMA
        domains = normalize_domains(existing.get("email_domains") or [])
        if AGENCE_MENDES_DOMAIN not in domains:
            domains.append(AGENCE_MENDES_DOMAIN)
            updates["email_domains"] = domains
        if updates:
            updates["updated_at"] = _now()
            await db[COLLECTION].update_one({"id": existing["id"]}, {"$set": updates})
            existing = {**existing, **updates}
        return existing
    doc = new_entreprise_doc(
        nom=AGENCE_MENDES_NOM,
        finma_number=AGENCE_MENDES_FINMA,
        email_domains=[AGENCE_MENDES_DOMAIN],
    )
    await db[COLLECTION].insert_one(doc)
    return doc


async def get_entreprise(db, entreprise_id: Optional[str]) -> Optional[dict]:
    eid = (entreprise_id or "").strip()
    if not eid:
        return None
    return await db[COLLECTION].find_one({"id": eid}, {"_id": 0})


async def list_entreprises_map(db) -> dict[str, dict]:
    rows = await db[COLLECTION].find({}, {"_id": 0}).to_list(500)
    return {str(r.get("id")): r for r in rows if r.get("id")}


def attach_entreprise_fields(user_doc: dict, entreprise: Optional[dict]) -> dict:
    """Champs publics dérivés (FINMA entreprise jamais dupliquée comme source)."""
    out = dict(user_doc)
    if entreprise:
        out["entreprise_id"] = entreprise.get("id")
        out["entreprise_nom"] = entreprise.get("nom") or ""
        out["entreprise_finma"] = entreprise.get("finma_number") or ""
    else:
        out["entreprise_id"] = (user_doc.get("entreprise_id") or "").strip() or None
        out["entreprise_nom"] = None
        out["entreprise_finma"] = None
    return out


def propose_mendes_attachments(users: list[dict], mendes: dict) -> list[dict]:
    """Utilisateurs @agencemendes.ch non encore rattachés (aperçu, sans écriture)."""
    mendes_id = mendes.get("id")
    proposals = []
    for u in users:
        email = (u.get("email") or "").strip().lower()
        if email_domain(email) != AGENCE_MENDES_DOMAIN:
            continue
        current = (u.get("entreprise_id") or "").strip()
        if current == mendes_id:
            continue
        proposals.append(
            {
                "user_id": u.get("user_id"),
                "email": email,
                "name": u.get("name") or f"{u.get('prenom') or ''} {u.get('nom') or ''}".strip(),
                "role": u.get("role"),
                "current_entreprise_id": current or None,
                "proposed_entreprise_id": mendes_id,
                "proposed_entreprise_nom": mendes.get("nom"),
                "proposed_entreprise_finma": mendes.get("finma_number"),
            }
        )
    return proposals
