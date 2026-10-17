"""Persistance isolée du module LAMal. Ne modifie pas les fiches clients."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

COLLECTIONS = {
    "datasets": "lamal_premium_datasets",
    "premiums": "lamal_premiums",
    "regions": "lamal_regions",
    "profiles": "lamal_client_profiles",
    "comparisons": "lamal_comparisons",
    "campaigns": "lamal_campaigns",
    "emails": "lamal_email_logs",
    "audit": "lamal_audit_logs",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


async def ensure_indexes(db) -> None:
    await db[COLLECTIONS["datasets"]].create_index([("year", 1), ("active", 1)])
    await db[COLLECTIONS["datasets"]].create_index([("sha256", 1)])
    await db[COLLECTIONS["premiums"]].create_index(
        [("dataset_id", 1), ("canton", 1), ("region", 1), ("age_class", 1), ("accident", 1), ("franchise_chf", 1)]
    )
    await db[COLLECTIONS["premiums"]].create_index(
        [("dataset_id", 1), ("insurer_id", 1), ("tariftyp", 1), ("tarif_id", 1)]
    )
    await db[COLLECTIONS["regions"]].create_index([("dataset_id", 1), ("bfs", 1)])
    await db[COLLECTIONS["regions"]].create_index([("dataset_id", 1), ("plz", 1)])
    await db[COLLECTIONS["profiles"]].create_index([("client_id", 1)], unique=True)
    await db[COLLECTIONS["comparisons"]].create_index([("client_id", 1), ("created_at", -1)])
    await db[COLLECTIONS["campaigns"]].create_index([("year", 1), ("created_at", -1)])
    await db[COLLECTIONS["emails"]].create_index([("campaign_id", 1), ("client_id", 1)], unique=True)
    await db[COLLECTIONS["audit"]].create_index([("created_at", -1)])


async def audit(db, actor: str, action: str, detail: Optional[dict] = None) -> None:
    await db[COLLECTIONS["audit"]].insert_one({
        "id": new_id(),
        "actor": actor,
        "action": action,
        "detail": detail or {},
        "created_at": now_iso(),
    })


async def active_dataset(db, year: int = 2027) -> Optional[dict]:
    return await db[COLLECTIONS["datasets"]].find_one({"year": year, "active": True}, {"_id": 0})
