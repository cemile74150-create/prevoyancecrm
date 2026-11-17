"""Copie élargie lecture seule → Mongo local pour tests modules.

Source : COPY_SOURCE_MONGO_URL / MONGO_PUBLIC_URL (find uniquement)
Cible  : localhost uniquement

Inclut métadonnées documents/notes/historiques/offres/analyses — pas les binaires S3.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

from pymongo import MongoClient
from pymongo.read_preferences import ReadPreference

SPECS = {
    "users": {"user_id": 1, "email": 1, "prenom": 1, "nom": 1, "name": 1, "role": 1,
              "conseiller": 1, "active": 1, "see_all_dossiers": 1, "permissions": 1},
    "clients": {"id": 1, "numero_dossier": 1, "dossier_label": 1, "conseiller": 1,
                "agent_label": 1, "agent_email": 1, "conseiller_email": 1,
                "conseiller_account_id": 1, "linked_spouse_id": 1, "source_import": 1,
                "in_dossiers": 1, "statut": 1, "created_at": 1, "updated_at": 1},
    "documents": {"id": 1, "client_id": 1, "dossier_id": 1, "user_id": 1, "category": 1,
                  "is_deleted": 1, "storage_path": 1, "original_filename": 1, "created_at": 1},
    "notes": {"id": 1, "client_id": 1, "dossier_id": 1, "user_id": 1, "created_at": 1},
    "actions": {"id": 1, "client_id": 1, "dossier_id": 1, "user_id": 1, "description": 1, "created_at": 1},
    "journal_actions": {"id": 1, "client_id": 1, "user_id": 1, "created_at": 1},
    "demandes": {"id": 1, "client_id": 1, "user_id": 1, "done": 1, "date": 1, "created_at": 1},
    "appointments": {"id": 1, "client_id": 1, "user_id": 1, "date": 1},
    "tasks": {"id": 1, "client_id": 1, "user_id": 1, "done": 1},
    "suivi_3p_clients": {"id": 1, "conseiller": 1, "client_id": 1, "statut": 1},
    "suivi_3p_documents": {"id": 1, "suivi_3p_client_id": 1, "is_deleted": 1, "storage_path": 1},
    "demandes_offres_3p": {"id": 1, "numero": 1, "agent_label": 1, "agent_email": 1,
                           "agent_account_id": 1, "created_by_account_id": 1, "is_deleted": 1,
                           "statut": 1, "client_id": 1},
    "analyses": {"id": 1, "client_id": 1, "user_id": 1, "status": 1, "updated_at": 1},
}


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant"


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--target-db", required=True)
    p.add_argument("--drop-target", action="store_true")
    args = p.parse_args(argv)
    src_url = (os.environ.get("COPY_SOURCE_MONGO_URL") or os.environ.get("MONGO_PUBLIC_URL") or "").strip()
    src_db = (os.environ.get("COPY_SOURCE_DB_NAME") or "prevoyancecrm").strip()
    if not src_url or _hote(src_url) == "local":
        print("Source distante requise", file=sys.stderr)
        return 2
    if _hote("mongodb://127.0.0.1:27017") != "local":
        return 3
    if args.target_db in {"prevoyancecrm", "admin", "local"}:
        return 4

    src = MongoClient(src_url, serverSelectionTimeoutMS=30000, read_preference=ReadPreference.PRIMARY)
    src.admin.command("ping")
    dst = MongoClient("mongodb://127.0.0.1:27017")
    if args.drop_target:
        dst.drop_database(args.target_db)
    sdb, ddb = src[src_db], dst[args.target_db]
    names = set(sdb.list_collection_names())
    meta = {"copied_at": datetime.now(timezone.utc).isoformat(), "collections": {}, "purpose": "full_module_test"}
    for coll, proj in SPECS.items():
        if coll not in names:
            print("skip", coll)
            meta["collections"][coll] = 0
            continue
        q = {}
        if coll == "clients":
            q = {"source_import": {"$ne": "suivi_3p_excel"}}
        if coll == "demandes_offres_3p":
            q = {"is_deleted": {"$ne": True}}
        if coll in {"documents", "suivi_3p_documents"}:
            q = {"is_deleted": {"$ne": True}}
        batch, n = [], 0
        ddb[coll].delete_many({})
        for doc in sdb[coll].find(q, proj):
            doc.pop("_id", None)
            batch.append(doc)
            if len(batch) >= 500:
                ddb[coll].insert_many(batch)
                n += len(batch)
                batch = []
        if batch:
            ddb[coll].insert_many(batch)
            n += len(batch)
        meta["collections"][coll] = n
        print(coll, n)
    ddb["_full_copy_meta"].delete_many({})
    ddb["_full_copy_meta"].insert_one(meta)
    src.close()
    dst.close()
    print("OK", args.target_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
