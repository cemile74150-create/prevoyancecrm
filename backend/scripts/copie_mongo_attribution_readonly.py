"""Copie isolée pour le rapport d'attribution (source lecture seule → Mongo local).

- SOURCE : MONGO_PUBLIC_URL / COPY_SOURCE_MONGO_URL (Railway proxy) — find() uniquement
- CIBLE  : mongodb://127.0.0.1:27017/<--target-db> — seule destination d'écriture
- Projections minimales : pas d'e-mail / téléphone / adresse / AVS client
- Ne touche jamais aux permissions ni à la production en écriture

    # Variables injectées hors chat (jamais echo) :
    #   $env:COPY_SOURCE_MONGO_URL = ...
    #   $env:COPY_SOURCE_DB_NAME = prevoyancecrm
    python backend/scripts/copie_mongo_attribution_readonly.py --target-db leosoft_mendes_attribution_copy
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

from pymongo import MongoClient
from pymongo.errors import OperationFailure
from pymongo.read_preferences import ReadPreference

COLLECTIONS = (
    ("users", {
        "user_id": 1, "email": 1, "prenom": 1, "nom": 1, "name": 1, "role": 1,
        "conseiller": 1, "active": 1, "see_all_dossiers": 1, "permissions": 1,
    }),
    ("clients", {
        "id": 1, "numero_dossier": 1, "dossier_label": 1, "conseiller": 1,
        "agent_label": 1, "agent_email": 1, "conseiller_email": 1,
        "conseiller_account_id": 1, "agent_account_id": 1, "created_by_account_id": 1,
        "linked_spouse_id": 1, "source_import": 1, "in_dossiers": 1,
        # pas de prenom/nom/email/telephone/adresse client
    }),
    ("suivi_3p_clients", {
        "id": 1, "conseiller": 1, "agent_label": 1, "agent_email": 1,
        "conseiller_email": 1, "conseiller_account_id": 1, "agent_account_id": 1,
        "created_by_account_id": 1, "linked_spouse_id": 1,
    }),
    ("demandes_offres_3p", {
        "id": 1, "numero": 1, "agent_label": 1, "agent_email": 1,
        "conseiller_email": 1, "conseiller": 1, "agent_account_id": 1,
        "created_by_account_id": 1, "is_deleted": 1,
    }),
)


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant"


def _args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target-db", required=True, help="Nom de la base locale de copie")
    p.add_argument("--target-url", default="mongodb://127.0.0.1:27017", help="URI Mongo locale")
    p.add_argument("--drop-target", action="store_true", help="Supprime la base cible avant copie")
    return p.parse_args(argv)


def _assert_source_readonly_ops(client: MongoClient, db_name: str) -> None:
    """Vérifie qu'on ne s'appuie que sur find ; tente une écriture jetable et exige l'échec si possible."""
    db = client[db_name]
    probe = f"_attribution_readonly_probe_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    try:
        db[probe].insert_one({"probe": True})
    except OperationFailure:
        print("Source : écriture refusée par Mongo (idéal).")
        return
    except Exception as exc:
        print(f"Source : écriture bloquée ({type(exc).__name__}).")
        return
    # Si l'écriture a réussi (compte admin), on nettoie immédiatement et on continue
    # en s'engageant à n'utiliser que find() ensuite.
    try:
        db.drop_collection(probe)
    except Exception:
        pass
    print(
        "Avertissement : le compte source peut écrire. "
        "Ce script n'exécutera que des find() sur la source.",
        file=sys.stderr,
    )


def main(argv=None) -> int:
    args = _args(argv)
    source_url = (os.environ.get("COPY_SOURCE_MONGO_URL") or os.environ.get("MONGO_PUBLIC_URL") or "").strip()
    source_db = (os.environ.get("COPY_SOURCE_DB_NAME") or os.environ.get("DB_NAME") or "prevoyancecrm").strip()
    if not source_url:
        print("COPY_SOURCE_MONGO_URL ou MONGO_PUBLIC_URL manquant.", file=sys.stderr)
        return 2
    if _hote(args.target_url) != "local":
        print("Abort : la cible doit être localhost.", file=sys.stderr)
        return 3
    if _hote(source_url) == "local":
        print("Abort : la source ne doit pas être la même machine locale cible.", file=sys.stderr)
        return 4
    if args.target_db in {"prevoyancecrm", "admin", "local"}:
        print("Abort : nom de base cible réservé / trop risqué.", file=sys.stderr)
        return 5

    print(f"Source : {_hote(source_url)} / db={source_db} (lecture find uniquement)")
    print(f"Cible  : local / db={args.target_db} (seule écriture)")

    src = MongoClient(
        source_url,
        serverSelectionTimeoutMS=30000,
        read_preference=ReadPreference.PRIMARY,
    )
    src.admin.command("ping")
    _assert_source_readonly_ops(src, source_db)

    dst = MongoClient(args.target_url, serverSelectionTimeoutMS=10000)
    dst.admin.command("ping")
    if args.drop_target:
        dst.drop_database(args.target_db)
    target = dst[args.target_db]

    meta = {
        "copied_at": datetime.now(timezone.utc).isoformat(),
        "source_host_kind": _hote(source_url),
        "source_db": source_db,
        "purpose": "attribution_report_readonly",
        "collections": {},
    }

    src_db = src[source_db]
    for name, projection in COLLECTIONS:
        if name not in src_db.list_collection_names():
            print(f"  skip {name} (absente)")
            meta["collections"][name] = 0
            continue
        query: dict = {}
        if name == "clients":
            query = {"source_import": {"$ne": "suivi_3p_excel"}}
        if name == "demandes_offres_3p":
            query = {"is_deleted": {"$ne": True}}
        cursor = src_db[name].find(query, projection)
        batch = []
        count = 0
        target[name].delete_many({})
        for doc in cursor:
            doc.pop("_id", None)
            batch.append(doc)
            if len(batch) >= 500:
                target[name].insert_many(batch)
                count += len(batch)
                batch = []
        if batch:
            target[name].insert_many(batch)
            count += len(batch)
        meta["collections"][name] = count
        print(f"  copied {name}: {count}")

    target["_attribution_copy_meta"].delete_many({})
    target["_attribution_copy_meta"].insert_one(meta)
    src.close()
    dst.close()
    print("Copie terminée. Lancez le rapport avec --local --db", args.target_db, "--require-local-host")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
