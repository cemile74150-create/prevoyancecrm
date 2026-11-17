"""
Sauvegarde complète avant migration.

1) Dump de toutes les collections Mongo en JSONL
2) Téléchargement de tous les documents référencés via `storage_path`
   (supports: local://, s3://, pcloud:{fileid} si configuré)
3) Manifest CSV + SHA256 pour vérification / rollback
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from pymongo import MongoClient

ROOT_DIR = Path(__file__).resolve().parents[1]  # backend/

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

APP_NAME = "prevoyance-crm"

# Collections avec documents binaires référencés par storage_path (connu a priori).
# Toute collection supplémentaire contenant storage_path est aussi incluse à l'exécution.
STORAGE_COLLECTIONS: Tuple[str, ...] = (
    "documents",
    "form_library",
    "suivi_3p_documents",
    "suivi_3p_pending_documents",
)

# Collections métier attendues (toujours exportées, même si vides).
# À l'exécution on union avec list_collection_names() pour ne rien rater.
ALL_COLLECTIONS: Tuple[str, ...] = (
    "users",
    "user_sessions",
    "clients",
    "notes",
    "demandes",
    "actions",
    "documents",
    "form_library",
    "appointments",
    "tasks",
    "suivi_3p_clients",
    "suivi_3p_documents",
    "suivi_3p_pending_documents",
    "app_migrations",
)

# Préfixes système Mongo à ignorer lors du dump dynamique
_SKIP_COLLECTION_PREFIXES: Tuple[str, ...] = ("system.",)

logger = logging.getLogger("backup_full")


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def ensure_env() -> None:
    missing = [k for k, v in {"MONGO_URL": MONGO_URL, "DB_NAME": DB_NAME}.items() if not v]
    if missing:
        raise RuntimeError(f"Missing env: {', '.join(missing)}")


def mongo_client() -> MongoClient:
    ensure_env()
    return MongoClient(MONGO_URL)  # sync


def iter_docs(collection, query: Optional[dict] = None) -> Iterable[dict]:
    q = query or {}
    # Pas de projection: on sauvegarde tout
    cursor = collection.find(q)
    for d in cursor:
        # BSON -> JSON friendly
        d.pop("_id", None)
        yield d


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def storage_read_local(storage_path: str) -> bytes:
    if not storage_path.startswith("local://"):
        raise ValueError("Not a local:// storage_path")
    rel = storage_path.replace("local://", "", 1).lstrip("/").replace("\\", "/")
    if not rel or ".." in Path(rel).parts:
        raise FileNotFoundError(storage_path)
    root = ROOT_DIR.resolve()
    p = (ROOT_DIR / rel).resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise FileNotFoundError(storage_path) from e
    return p.read_bytes()


def storage_read_bytes(storage_path: str) -> Tuple[bytes, str]:
    """
    Retourne (bytes, content_type).

    storage_path possibles:
    - local://...
    - s3://bucket/key
    - pcloud:{fileid} (si pcloud_storage configuré)
    """
    storage_path = (storage_path or "").strip()
    if not storage_path:
        raise ValueError("empty storage_path")

    if storage_path.startswith("local://"):
        data = storage_read_local(storage_path)
        return data, "application/octet-stream"

    if storage_path.startswith("s3://"):
        import sys

        if str(ROOT_DIR) not in sys.path:
            sys.path.insert(0, str(ROOT_DIR))
        import object_storage  # type: ignore

        data, ctype = object_storage.get_object(storage_path)
        return data, ctype

    if storage_path.startswith("pcloud:"):
        import pcloud_storage  # type: ignore

        return pcloud_storage.download_storage_path(storage_path)

    raise FileNotFoundError(f"Chemin storage non supporté pour backup: {storage_path[:120]}")


def sanitize_filename(name: str) -> str:
    name = (name or "").strip() or "file"
    # Minimal: évite séparateurs Windows + caractères critiques
    bad = '<>:"/\\|?*'
    for ch in bad:
        name = name.replace(ch, "_")
    return name


def backup_local_filename(doc_id: str, original_filename: str, *, max_name_len: int = 100) -> str:
    """
    Nom de fichier local pour le dump.

    Windows limite souvent les chemins à ~260 caractères : avec le dossier
    backups_full_.../files/<collection>/<user>/, les longs noms de courriers
    dépassent la limite et font échouer write_bytes (Errno 2) alors que le
    binaire distant est parfaitement lisible.
    """
    doc_id = sanitize_filename(str(doc_id or "unknown")) or "unknown"
    original = sanitize_filename(original_filename)
    suffix = Path(original).suffix[:20]
    stem = Path(original).stem or "file"
    prefix = f"{doc_id}__"
    # Toujours garder l'id ; tronquer uniquement le libellé d'origine
    budget = max(8, int(max_name_len) - len(prefix) - len(suffix))
    if len(stem) > budget:
        stem = stem[:budget].rstrip(" ._")
    name = f"{prefix}{stem}{suffix}"
    if len(name) > max_name_len:
        # Ultime secours : id + extension seule
        name = f"{doc_id}{suffix}"[:max_name_len]
    return name


def list_backup_collections(db) -> Tuple[str, ...]:
    """Union des collections connues + toutes les collections live Mongo."""
    live = []
    for name in db.list_collection_names():
        if any(name.startswith(p) for p in _SKIP_COLLECTION_PREFIXES):
            continue
        live.append(name)
    ordered = list(ALL_COLLECTIONS)
    for name in sorted(live):
        if name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def list_storage_collections(db) -> Tuple[str, ...]:
    """Collections contenant au moins un storage_path non vide."""
    found = list(STORAGE_COLLECTIONS)
    for name in db.list_collection_names():
        if name in found:
            continue
        if any(name.startswith(p) for p in _SKIP_COLLECTION_PREFIXES):
            continue
        try:
            if db[name].find_one({"storage_path": {"$exists": True, "$nin": [None, ""]}}):
                found.append(name)
                logger.info("Storage collection découverte: %s", name)
        except Exception as e:
            logger.warning("Scan storage_path impossible sur %s: %s", name, e)
    return tuple(found)


def collect_storage_rows(db) -> Iterable[dict]:
    """Itère sur tous les documents binaires avec storage_path."""
    for coll_name in list_storage_collections(db):
        coll = db[coll_name]
        for d in iter_docs(coll):
            storage_path = d.get("storage_path")
            if not storage_path:
                continue
            yield {
                "collection": coll_name,
                "id": d.get("id"),
                "user_id": d.get("user_id"),
                "storage_path": storage_path,
                "original_filename": d.get("original_filename") or d.get("filename") or "",
                "content_type": d.get("content_type") or "",
                "size": d.get("size"),
                "is_deleted": bool(d.get("is_deleted")),
                "raw": d,
            }


def export_collections_as_jsonl(out_dir: Path, db, collections: Optional[Tuple[str, ...]] = None) -> Tuple[str, ...]:
    cols_dir = out_dir / "collections_jsonl"
    cols_dir.mkdir(parents=True, exist_ok=True)

    names = collections or list_backup_collections(db)
    for name in names:
        out = cols_dir / f"{name}.jsonl"
        coll = db[name]
        logger.info("Dump %s -> %s", name, out)
        with out.open("w", encoding="utf-8") as f:
            for d in iter_docs(coll):
                f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    return names


def export_files(out_dir: Path, db) -> Path:
    files_dir = out_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest.csv"
    fieldnames = [
        "collection",
        "id",
        "user_id",
        "storage_path",
        "original_filename",
        "content_type",
        "size",
        "sha256",
        "ok",
        "error",
        "local_path",
        "is_deleted",
    ]

    rows_done = 0
    with manifest_path.open("w", encoding="utf-8", newline="") as mf:
        writer = csv.DictWriter(mf, fieldnames=fieldnames)
        writer.writeheader()

        for row in collect_storage_rows(db):
            rows_done += 1
            collection = row["collection"]
            doc_id = row["id"] or "unknown"
            storage_path = row["storage_path"]
            original_filename = sanitize_filename(row["original_filename"])
            is_deleted = bool(row.get("is_deleted"))

            # Positionnement physique: files/{collection}/{user_id}/{id}__{name_tronqué}
            user_bucket = sanitize_filename(str(row.get("user_id") or "tenant"))
            dest_dir = files_dir / collection / user_bucket
            dest_dir.mkdir(parents=True, exist_ok=True)
            # Budget dynamique pour rester sous la limite Windows (~260)
            path_budget = max(48, 240 - len(str(dest_dir)) - 1)
            dest_path = dest_dir / backup_local_filename(
                doc_id, original_filename, max_name_len=path_budget
            )
            dest_path_write: Path = dest_path
            if os.name == "nt":
                dest_path_write = Path("\\\\?\\" + str(dest_path.resolve()))

            status = "false"
            err = ""
            sha = ""
            content_type = row.get("content_type") or ""
            local_rel = ""
            try:
                data, ctype = storage_read_bytes(storage_path)
                sha = sha256_bytes(data)
                content_type = content_type or ctype
                dest_path_write.write_bytes(data)
                status = "true"
                local_rel = str(dest_path.relative_to(out_dir))
            except Exception as e:
                err = str(e)
                # Soft-deleted + binaire déjà perdu en prod: métadonnées JSONL restent,
                # mais on ne bloque pas la sauvegarde (document déjà inaccessible).
                if is_deleted:
                    status = "skipped_deleted"
                    err = f"skipped_deleted: {err}"
                    logger.warning(
                        "Binaire soft-deleted introuvable id=%s path=%s (%s)",
                        doc_id,
                        storage_path,
                        e,
                    )
                else:
                    status = "false"

            writer.writerow(
                {
                    "collection": collection,
                    "id": doc_id,
                    "user_id": row.get("user_id"),
                    "storage_path": storage_path,
                    "original_filename": row.get("original_filename"),
                    "content_type": content_type,
                    "size": row.get("size"),
                    "sha256": sha,
                    "ok": status,
                    "error": err,
                    "local_path": local_rel,
                    "is_deleted": is_deleted,
                }
            )

            if rows_done % 200 == 0:
                logger.info("Export files: %d rows processed", rows_done)

    logger.info("Manifest: %s", manifest_path)
    return manifest_path


def _manifest_status_counts(manifest_path: Path) -> Dict[str, int]:
    ok_n = fail_n = skipped_n = 0
    if not manifest_path.exists():
        return {"ok": 0, "fail": 0, "skipped": 0, "total": 0}
    with manifest_path.open(encoding="utf-8") as mf:
        for row in csv.DictReader(mf):
            status = str(row.get("ok", "")).strip().lower()
            if status == "true":
                ok_n += 1
            elif status.startswith("skipped"):
                skipped_n += 1
            else:
                fail_n += 1
    return {"ok": ok_n, "fail": fail_n, "skipped": skipped_n, "total": ok_n + fail_n + skipped_n}


def write_integrity(out_dir: Path, db, collections: Optional[Tuple[str, ...]] = None) -> dict:
    manifest_path = out_dir / "manifest.csv"
    counts_status = _manifest_status_counts(manifest_path)
    ok_n = counts_status["ok"]
    fail_n = counts_status["fail"]
    skipped_n = counts_status["skipped"]
    names = collections or list_backup_collections(db)
    counts = {name: db[name].count_documents({}) for name in names}
    integrity = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "collection_counts": counts,
        "collections_exported": list(names),
        "files_ok": ok_n,
        "files_fail": fail_n,
        "files_skipped_deleted": skipped_n,
        "files_total": ok_n + fail_n + skipped_n,
    }
    (out_dir / "integrity.json").write_text(json.dumps(integrity, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Integrity: files_ok=%s files_fail=%s files_skipped_deleted=%s",
        ok_n,
        fail_n,
        skipped_n,
    )
    strict = str(os.environ.get("BACKUP_STRICT", "true")).strip().lower() in ("1", "true", "yes", "y")
    if strict and fail_n > 0:
        max_fail_ratio = float(os.environ.get("BACKUP_MAX_FAIL_RATIO", "0"))
        # Seuls les échecs sur documents ACTIFS comptent (skipped_deleted exclus).
        active_total = ok_n + fail_n
        if active_total == 0 or (fail_n / max(active_total, 1)) > max_fail_ratio:
            raise RuntimeError(
                f"Backup incomplet: {fail_n}/{active_total} fichiers actifs en échec "
                f"(skipped_deleted={skipped_n})"
            )
    return integrity


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )
    ensure_env()

    dry_run = str(os.environ.get("DRY_RUN", "")).strip().lower() in ("1", "true", "yes", "y")
    limit_files_raw = os.environ.get("LIMIT_FILES", "").strip()
    limit_files = int(limit_files_raw) if limit_files_raw.isdigit() else None

    backup_root = Path(os.environ.get("BACKUP_DIR") or (ROOT_DIR / "backups")).resolve()
    out_dir = backup_root / f"backups_full_{utc_now_stamp()}"

    # En DRY_RUN: on ne fait aucune écriture disque (utile pour valider rapidement)
    if dry_run:
        logger.info("DRY_RUN enabled: aucun fichier ne sera écrit.")

    db = mongo_client()[DB_NAME]
    collections = list_backup_collections(db)
    storage_collections = list_storage_collections(db)

    # Metadonnées backup
    meta = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mongo_url": (MONGO_URL or "").split("@")[-1],  # éviter d’inclure user/pass
        "db_name": DB_NAME,
        "collections": list(collections),
        "storage_collections": list(storage_collections),
    }

    if dry_run:
        counts = {name: db[name].count_documents({}) for name in collections}
        logger.info("DRY_RUN counts=%s", counts)

        storage_rows_count = 0
        for _ in collect_storage_rows(db):
            storage_rows_count += 1
            if limit_files is not None and storage_rows_count >= limit_files:
                break
        logger.info("DRY_RUN storage_rows_count=%s (limit=%s)", storage_rows_count, limit_files)
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "backup_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Backup output dir: %s", out_dir)

    export_collections_as_jsonl(out_dir, db, collections)
    export_files(out_dir, db)
    write_integrity(out_dir, db, collections)
    logger.info("Backup finished OK: %s", out_dir)
    print(out_dir)


if __name__ == "__main__":
    main()

