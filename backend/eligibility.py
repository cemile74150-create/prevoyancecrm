"""Listes d'éligibilité : règles, persistance et seed.

Les fiches clients restent la seule source des données client.
Une appartenance (eligibility_memberships) relie une liste à une fiche existante.
"""
from __future__ import annotations

import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

LISTS_COLLECTION = "eligibility_lists"
MEMBERSHIPS_COLLECTION = "eligibility_memberships"

MANAGER_ENV = "ELIGIBILITY_MANAGER_USER_ID"

LIST_NAME_MAX = 120

DEFAULT_LISTS = (
    "Placement à tranche",
    "Retraite populaire – rente viagère à taux réduit",
)

SEED_AUTHOR = "system:seed"

_DASHES = re.compile(r"[\u2010-\u2015\u2212-]+")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_list_name(raw: Any) -> str:
    """Nom affiché : espaces condensés. Lève ValueError si vide ou trop long."""
    name = " ".join(str(raw or "").split())
    if not name:
        raise ValueError("Indiquez le nom de la liste.")
    if len(name) > LIST_NAME_MAX:
        raise ValueError(f"Le nom de la liste ne doit pas dépasser {LIST_NAME_MAX} caractères.")
    return name


def normalize_list_name(raw: Any) -> str:
    """Clé d'unicité : casse, accents, tirets et espaces ignorés."""
    text = unicodedata.normalize("NFD", str(raw or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = _DASHES.sub("-", text.casefold())
    text = re.sub(r"\s*-\s*", " - ", text)
    return " ".join(text.split())


def manager_account_id() -> str:
    return (os.environ.get(MANAGER_ENV) or "").strip()


def can_create_lists(user: Any) -> bool:
    """Seul le compte désigné par ELIGIBILITY_MANAGER_USER_ID. Variable absente : personne."""
    expected = manager_account_id()
    account = str(getattr(user, "account_id", "") or "").strip()
    return bool(expected) and account == expected


def public_list(doc: dict, client_count: Optional[int] = None) -> dict:
    out = {
        "id": doc["_id"],
        "name": doc.get("name") or "",
        "is_active": doc.get("is_active", True) is not False,
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }
    if client_count is not None:
        out["client_count"] = client_count
    return out


def public_client_row(client: dict, normalize_statut) -> dict:
    return {
        "id": client.get("id"),
        "prenom": client.get("prenom") or "",
        "nom": client.get("nom") or "",
        "numero_dossier": client.get("numero_dossier") or "",
        "telephone": client.get("telephone") or "",
        "email": client.get("email") or "",
        "statut": normalize_statut(client.get("statut")),
        "dossier_id": client.get("dossier_id"),
    }


def client_matches(client: dict, folded_query: str, fold) -> bool:
    """Recherche sur nom, prénom et numéro de dossier."""
    if not folded_query:
        return True
    prenom = fold(client.get("prenom"))
    nom = fold(client.get("nom"))
    haystacks = (
        prenom,
        nom,
        f"{prenom} {nom}".strip(),
        f"{nom} {prenom}".strip(),
        fold(client.get("numero_dossier")),
    )
    return any(folded_query in h for h in haystacks if h)


def client_sort_key(client: dict, fold) -> tuple:
    return (fold(client.get("nom")), fold(client.get("prenom")), str(client.get("id") or ""))


def new_list_doc(name: str, created_by: str) -> dict:
    stamp = now_iso()
    return {
        "_id": uuid.uuid4().hex,
        "name": name,
        "normalized_name": normalize_list_name(name),
        "is_active": True,
        "created_by": created_by,
        "created_at": stamp,
        "updated_at": stamp,
    }


async def ensure_indexes(db) -> None:
    await db[LISTS_COLLECTION].create_index(
        [("normalized_name", 1)], unique=True, name="uniq_eligibility_list_name"
    )
    await db[MEMBERSHIPS_COLLECTION].create_index(
        [("list_id", 1), ("client_id", 1)], unique=True, name="uniq_eligibility_membership"
    )
    await db[MEMBERSHIPS_COLLECTION].create_index([("client_id", 1)], name="idx_eligibility_client")


async def seed_default_lists(db) -> int:
    """Crée les listes par défaut absentes. Idempotent : rien n'est dupliqué ni réactivé."""
    created = 0
    for name in DEFAULT_LISTS:
        doc = new_list_doc(name, SEED_AUTHOR)
        key = doc.pop("normalized_name")
        try:
            res = await db[LISTS_COLLECTION].update_one(
                {"normalized_name": key},
                {"$setOnInsert": doc},
                upsert=True,
            )
        except DuplicateKeyError:
            continue
        if getattr(res, "upserted_id", None) is not None:
            created += 1
    return created


async def ensure_setup(db) -> int:
    await ensure_indexes(db)
    return await seed_default_lists(db)


async def create_list(db, name: str, created_by: str) -> dict:
    """Lève ValueError (nom invalide) ou FileExistsError (nom déjà pris)."""
    doc = new_list_doc(clean_list_name(name), created_by)
    if await db[LISTS_COLLECTION].find_one({"normalized_name": doc["normalized_name"]}, {"_id": 1}):
        raise FileExistsError("Une liste porte déjà ce nom.")
    try:
        await db[LISTS_COLLECTION].insert_one(doc)
    except DuplicateKeyError as exc:
        raise FileExistsError("Une liste porte déjà ce nom.") from exc
    return doc


async def active_lists(db) -> list[dict]:
    rows = await db[LISTS_COLLECTION].find({"is_active": {"$ne": False}}).to_list(1000)
    return sorted(rows, key=lambda d: (str(d.get("created_at") or ""), d.get("name") or ""))


async def add_membership(db, list_id: str, client_id: str, added_by: str, added_by_name: str = "") -> bool:
    """True si l'association vient d'être créée, False si elle existait déjà."""
    try:
        res = await db[MEMBERSHIPS_COLLECTION].update_one(
            {"list_id": list_id, "client_id": client_id},
            {"$setOnInsert": {
                "_id": uuid.uuid4().hex,
                "added_by": added_by,
                "added_by_name": added_by_name or None,
                "added_at": now_iso(),
            }},
            upsert=True,
        )
    except DuplicateKeyError:
        return False
    return getattr(res, "upserted_id", None) is not None


async def remove_membership(db, list_id: str, client_id: str) -> bool:
    res = await db[MEMBERSHIPS_COLLECTION].delete_one({"list_id": list_id, "client_id": client_id})
    return bool(getattr(res, "deleted_count", 0))


async def remove_client_memberships(db, client_id: str) -> int:
    res = await db[MEMBERSHIPS_COLLECTION].delete_many({"client_id": client_id})
    return int(getattr(res, "deleted_count", 0) or 0)
