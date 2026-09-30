"""
Restauration d'une archive .crmbak vers un MongoDB cible (+ fichiers S3 optionnel).

Usage:
  set MONGO_URL=...
  set DB_NAME=prevoyancecrm
  set BACKUP_ENCRYPTION_PASSPHRASE=...
  python scripts/restore_from_backup.py path/to/file.tar.gz.crmbak
  python scripts/restore_from_backup.py path/to/file.tar.gz.crmbak --files-to-s3
  python scripts/restore_from_backup.py path/to/file.tar.gz.crmbak --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import tempfile
import tarfile
from pathlib import Path
from typing import Any, Dict

from pymongo import MongoClient

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPTS))

from backup_crypto import decrypt_file  # noqa: E402
from verify_backup import verify_backup_dir  # noqa: E402

logger = logging.getLogger("restore_backup")

PK_BY_COLLECTION = {
    "users": "user_id",
    "user_sessions": "session_token",
    "clients": "id",
    "notes": "id",
    "demandes": "id",
    "actions": "id",
    "documents": "id",
    "form_library": "id",
    "appointments": "id",
    "tasks": "id",
    "suivi_3p_clients": "id",
    "suivi_3p_documents": "id",
    "suivi_3p_pending_documents": "id",
    "app_migrations": "id",
}


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


def restore_collections(db, cols_dir: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for path in sorted(cols_dir.glob("*.jsonl")):
        name = path.stem
        pk = PK_BY_COLLECTION.get(name, "id")
        n = 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                doc = json.loads(line)
                key = doc.get(pk)
                if key is None:
                    db[name].insert_one(doc)
                else:
                    db[name].replace_one({pk: key}, doc, upsert=True)
                n += 1
        counts[name] = n
        logger.info("Restored %s=%s", name, n)
    return counts


def logical_for_row(row: dict) -> str:
    old = (row.get("storage_path") or "").strip()
    coll = row.get("collection") or "documents"
    doc_id = row.get("id") or "unknown"
    if old.startswith("s3://"):
        return old
    if old.startswith("local://"):
        return f"prevoyance-crm/{old.replace('local://', '', 1).lstrip('/')}"
    if old.startswith("prevoyance-crm/"):
        return old
    return f"prevoyance-crm/restored/{coll}/{doc_id}"


def restore_files_to_s3(db, backup_dir: Path) -> Dict[str, int]:
    import object_storage

    if not object_storage.configured():
        raise RuntimeError("S3_* requis pour --files-to-s3")

    uploaded = skipped = failed = 0
    with (backup_dir / "manifest.csv").open(encoding="utf-8") as mf:
        for row in csv.DictReader(mf):
            status = str(row.get("ok", "")).strip().lower()
            if status.startswith("skipped"):
                skipped += 1
                continue
            if status != "true":
                skipped += 1
                continue
            local = backup_dir / (row.get("local_path") or "")
            if not local.exists():
                failed += 1
                continue
            data = local.read_bytes()
            ctype = row.get("content_type") or "application/octet-stream"
            logical = logical_for_row(row)
            try:
                new_path = object_storage.put_object(logical, data, ctype)["path"]
                coll = row.get("collection")
                doc_id = row.get("id")
                if coll and doc_id:
                    db[coll].update_one({"id": doc_id}, {"$set": {"storage_path": new_path}})
                uploaded += 1
            except Exception as e:
                failed += 1
                logger.error("Upload fail %s: %s", row.get("id"), e)
    return {"uploaded": uploaded, "skipped": skipped, "failed": failed}


def extract_archive(archive: Path, dest: Path) -> Path:
    tar_path = dest / "backup.tar.gz"
    decrypt_file(archive, tar_path)
    extract_dir = dest / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tar:
        try:
            tar.extractall(extract_dir, filter="data")
        except TypeError:
            tar.extractall(extract_dir)
    subs = [p for p in extract_dir.iterdir() if p.is_dir()]
    if not subs:
        raise RuntimeError("Archive sans dossier de backup")
    return subs[0]


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    load_dotenv_file(BACKEND / ".env.backup")

    parser = argparse.ArgumentParser(description="Restaure un backup CRM chiffré")
    parser.add_argument("archive", help="Fichier .tar.gz.crmbak")
    parser.add_argument("--files-to-s3", action="store_true", help="Ré-upload les PDF vers S3 Infomaniak")
    parser.add_argument("--dry-run", action="store_true", help="Vérifie seulement, n'écrit pas Mongo")
    args = parser.parse_args()

    archive = Path(args.archive).resolve()
    if not archive.exists():
        raise SystemExit(f"Archive introuvable: {archive}")

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME") or "prevoyancecrm"
    if not args.dry_run and not mongo_url:
        raise SystemExit("MONGO_URL requis pour restaurer (sauf --dry-run)")

    with tempfile.TemporaryDirectory(prefix="crm_restore_") as tmp:
        backup_dir = extract_archive(archive, Path(tmp))
        report = verify_backup_dir(backup_dir)
        print(json.dumps({"verify": report}, ensure_ascii=False, indent=2))
        if not report.get("ok"):
            raise SystemExit("Intégrité KO — restauration annulée")

        if args.dry_run:
            print("DRY_RUN_OK")
            return 0

        client = MongoClient(mongo_url)
        db = client[db_name]
        counts = restore_collections(db, backup_dir / "collections_jsonl")
        files_report = restore_files_to_s3(db, backup_dir) if args.files_to_s3 else None
        print(json.dumps({"ok": True, "collections": counts, "files": files_report}, ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
