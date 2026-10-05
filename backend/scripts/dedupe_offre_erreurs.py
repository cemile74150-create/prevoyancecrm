"""Retire les erreurs d'offre en double (une par demande + champ).

Ne supprime jamais une demande, un client ou un document.
"""
from __future__ import annotations

import os
import sys

from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demandes_offres_3p import (  # noqa: E402
    COLLECTION,
    COLLECTION_ERREURS,
    dedupe_erreur_records,
)


def main() -> int:
    url = (os.environ.get("MONGO_URL") or "").strip()
    name = (os.environ.get("DB_NAME") or "prevoyancecrm").strip()
    if not url:
        print("MONGO_URL manquant", file=sys.stderr)
        return 1
    client = MongoClient(url, serverSelectionTimeoutMS=15000)
    db = client[name]
    demandes_before = db[COLLECTION].count_documents({})
    rows = list(db[COLLECTION_ERREURS].find({}))
    kept, removed = dedupe_erreur_records(rows)
    removed_ids = []
    for rec in removed:
        rid = rec.get("_id")
        if rid is not None:
            removed_ids.append(rid)
            continue
        if rec.get("id"):
            removed_ids.append(rec.get("id"))
    deleted = 0
    if removed_ids:
        object_ids = [rid for rid in removed_ids if not isinstance(rid, str)]
        string_ids = [rid for rid in removed_ids if isinstance(rid, str)]
        if object_ids:
            deleted += db[COLLECTION_ERREURS].delete_many({"_id": {"$in": object_ids}}).deleted_count
        if string_ids:
            deleted += db[COLLECTION_ERREURS].delete_many({"id": {"$in": string_ids}}).deleted_count
    embedded_removed = 0
    demandes_touched = 0
    for doc in db[COLLECTION].find({}, {"id": 1, "erreurs_agent": 1, "agent_label": 1}):
        current = list(doc.get("erreurs_agent") or [])
        if not current:
            continue
        slim, extras = dedupe_erreur_records(current, demande_id=doc.get("id"))
        if not extras:
            continue
        db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"erreurs_agent": slim}})
        embedded_removed += len(extras)
        demandes_touched += 1
        agent = (doc.get("agent_label") or "").strip() or "—"
        fields = sorted({str(e.get("field_label") or e.get("field") or "") for e in extras})
        print(f"embarque agent={agent} champs={', '.join(fields)} retires={len(extras)}")
    demandes_after = db[COLLECTION].count_documents({})
    print(
        f"erreurs_documents_retires={deleted} "
        f"erreurs_embarquees_retirees={embedded_removed} "
        f"demandes_maj={demandes_touched} "
        f"demandes_avant={demandes_before} demandes_apres={demandes_after}"
    )
    if demandes_after != demandes_before:
        print("ANOMALIE: le nombre de demandes a change", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
