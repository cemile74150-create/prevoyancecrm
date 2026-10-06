"""Contrôle technique quotidien (lecture seule, hors données métier clients)."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

EXPECTED_INDEX_SPECS: Dict[str, List[List[Tuple[str, int]]]] = {
    "clients": [
        [("user_id", 1), ("created_at", -1)],
        [("user_id", 1), ("statut", 1)],
        [("user_id", 1), ("conseiller", 1)],
        [("dossier_id", 1)],
    ],
    "documents": [
        [("user_id", 1), ("client_id", 1), ("is_deleted", 1), ("created_at", -1)],
        [("storage_path", 1)],
    ],
    "notes": [[("user_id", 1), ("client_id", 1), ("created_at", -1)]],
    "demandes": [[("user_id", 1), ("done", 1), ("created_at", -1)]],
    "actions": [[("user_id", 1), ("client_id", 1), ("created_at", -1)]],
    "appointments": [[("user_id", 1), ("date", 1)]],
    "tasks": [[("user_id", 1), ("done", 1), ("echeance", 1)]],
    "suivi_3p_clients": [[("user_id", 1), ("conseiller", 1)]],
    "suivi_3p_documents": [[("user_id", 1), ("suivi_3p_client_id", 1), ("is_deleted", 1)]],
    "users": [[("email", 1)]],
    "user_sessions": [[("session_token", 1)], [("user_id", 1)]],
}


async def _count_indexes(db) -> Tuple[int, int]:
    present = 0
    expected = sum(len(v) for v in EXPECTED_INDEX_SPECS.values())
    for coll, specs in EXPECTED_INDEX_SPECS.items():
        try:
            idx = await db[coll].index_information()
            keys_list = [tuple(v["key"]) for name, v in idx.items() if name != "_id_"]
            for spec in specs:
                if tuple(spec) in keys_list:
                    present += 1
        except Exception:
            pass
    return present, expected


TZ = ZoneInfo("Europe/Zurich")
STATE_ID = "snapshot"
COL_STATE = "tech_audit_state"
COL_HISTORY = "tech_audit_history"

STORAGE_COLLECTIONS = (
    "documents",
    "form_library",
    "suivi_3p_documents",
    "suivi_3p_pending_documents",
    "demandes_offres_3p_documents",
)

DATA_DIR = Path(__file__).resolve().parent / "data"
LEGACY_SNAPSHOT = DATA_DIR / "tech_audit_snapshot.json"

_audit_running = False
_audit_lock: Optional[asyncio.Lock] = None

MONGO_FREE_WARN_GIB = 1.0
MONGO_FREE_PROBLEM_GIB = 0.5
BACKUP_WARN_HOURS = 48
BACKUP_PROBLEM_HOURS = 168
_CRMBAK_STAMP_RE = re.compile(
    r"prevoyancecrm_backup_(\d{8})_(\d{6})\.tar\.gz\.crmbak$",
    re.IGNORECASE,
)

_SECRET_RE = re.compile(
    r"(password|passwd|token|secret|api[_-]?key|authorization|bearer|credential)",
    re.I,
)


def _env_bool(name: str, default: str = "true") -> bool:
    return (os.environ.get(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )


def _audit_hour() -> int:
    try:
        h = int((os.environ.get("TECH_AUDIT_HOUR") or "3").strip())
        return max(0, min(23, h))
    except ValueError:
        return 3


def is_production_runtime() -> bool:
    """True lorsque le code s'exécute sur Railway (variables d'environnement plateforme)."""
    return bool(
        (os.environ.get("RAILWAY_ENVIRONMENT") or "").strip()
        or (os.environ.get("RAILWAY_SERVICE_ID") or "").strip()
        or (os.environ.get("RAILWAY_PROJECT_ID") or "").strip()
    )


def is_audit_production(*, in_process: bool) -> bool:
    """
    Contexte production pour l'audit.
    in_process=True : le backend CRM déployé (API / cron) — toujours production réelle.
    """
    return bool(in_process or is_production_runtime())


def runtime_context(*, in_process: bool) -> dict:
    prod = is_audit_production(in_process=in_process)
    return {
        "in_process": in_process,
        "production": prod,
        "platform": "railway" if is_production_runtime() else ("server" if in_process else "external"),
    }


def _config_missing_status(*, in_process: bool) -> str:
    """Sur le serveur CRM (in-process) : config manquante = vraie panne, jamais « impossible »."""
    if in_process:
        return "problem"
    return "unavailable"


def sanitize_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if _SECRET_RE.search(text):
        return "Erreur technique (détail masqué)"
    text = re.sub(r"s3://[^\s]+", "s3://…", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.\w+", "…@…", text)
    text = re.sub(r"WinError\s+\d+", "erreur réseau", text, flags=re.I)
    text = re.sub(r"127\.0\.0\.1|localhost", "hôte local", text, flags=re.I)
    return text[:limit]


def classify_storage_path(path: str) -> str:
    sp = (path or "").strip()
    if not sp:
        return "empty"
    if sp.startswith("s3://"):
        return "s3"
    if sp.startswith("local://"):
        return "local"
    return "other"


def status_label(status: str) -> str:
    if status == "ok":
        return "Conforme"
    if status == "warning":
        return "Attention"
    if status == "unavailable":
        return "Contrôle impossible à effectuer"
    return "Problème"


def aggregate_global(*statuses: str, in_process: bool = False) -> str:
    """Statut global : les contrôles « unavailable » (hors serveur) ne bloquent pas le global in-process."""
    measured = [s for s in statuses if s != "unavailable"]
    pool = measured if measured else list(statuses)
    if any(s == "problem" for s in pool):
        return "problem"
    if any(s == "warning" for s in pool):
        return "warning"
    if not measured and any(s == "unavailable" for s in statuses):
        return "unavailable"
    return "ok"


def format_fr_datetime(dt: datetime) -> str:
    local = dt.astimezone(TZ)
    return local.strftime("%d/%m/%Y à %H:%M")


def next_control_label(from_dt: Optional[datetime] = None) -> str:
    now = (from_dt or datetime.now(TZ)).astimezone(TZ)
    if now.hour < _audit_hour():
        return f"aujourd'hui à {_audit_hour():02d}:00"
    return "demain"


def _load_backup_remote_module():
    try:
        from scripts import backup_remote

        return backup_remote
    except ImportError:
        path = Path(__file__).resolve().parent / "scripts" / "backup_remote.py"
        spec = importlib.util.spec_from_file_location("backup_remote", path)
        if not spec or not spec.loader:
            raise RuntimeError("Module backup_remote introuvable")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def audit_is_running() -> bool:
    return _audit_running


def mark_audit_started() -> None:
    global _audit_running
    _audit_running = True


def mark_audit_finished() -> None:
    global _audit_running
    _audit_running = False


def _audit_lock_instance() -> asyncio.Lock:
    global _audit_lock
    if _audit_lock is None:
        _audit_lock = asyncio.Lock()
    return _audit_lock


async def run_daily_audit_background(db, *, force: bool = False) -> None:
    """Lance l'audit in-process en tâche de fond (scan S3 long)."""
    global _audit_running
    lock = _audit_lock_instance()
    async with lock:
        if _audit_running:
            logger.info("Tech audit: déjà en cours — ignoré")
            return
        _audit_running = True
        try:
            result = await run_daily_audit(db, force=force, in_process=True)
            if result.get("skipped"):
                logger.info("Tech audit background skipped: %s", result.get("reason"))
            else:
                logger.info(
                    "Tech audit background finished day=%s status=%s",
                    result.get("audit_day"),
                    result.get("global_status"),
                )
        except Exception:
            logger.exception("Tech audit background failed")
        finally:
            _audit_running = False


async def launch_manual_audit(db, *, force: bool) -> dict:
    """
    Démarre un contrôle manuel in-process (même moteur que le cron).
    Retour immédiat ; l'audit s'exécute en arrière-plan.
    """
    if audit_is_running():
        payload = await build_tech_status_from_db(db)
        return {
            "ok": True,
            "started": False,
            "running": True,
            "reason": "in_progress",
            "message": "Un contrôle est déjà en cours",
            "status": payload,
        }

    now = datetime.now(TZ)
    audit_day = now.date().isoformat()
    snap = await load_snapshot(db)
    previous_at = snap.get("last_control_at")

    if not force:
        existing = await db[COL_HISTORY].find_one({"audit_day": audit_day}, {"_id": 0, "id": 1})
        if existing:
            payload = await build_tech_status_from_db(db)
            return {
                "ok": True,
                "started": False,
                "running": False,
                "skipped": True,
                "reason": "already_ran_today",
                "audit_day": audit_day,
                "message": "Un contrôle a déjà été enregistré aujourd'hui.",
                "status": payload,
            }

    mark_audit_started()
    logger.info("Tech audit manual launch force=%s previous_at=%s", force, previous_at)

    async def _worker() -> None:
        try:
            await run_daily_audit(db, force=force, in_process=True)
        except Exception:
            logger.exception("Tech audit manual worker failed")
        finally:
            mark_audit_finished()

    asyncio.create_task(_worker())

    return {
        "ok": True,
        "started": True,
        "running": True,
        "await_control_after": previous_at,
        "message": "Contrôle production en cours (MongoDB, S3 Infomaniak, sauvegardes)…",
    }


def _public_app_base_url() -> str:
    for key in (
        "PUBLIC_APP_URL",
        "REACT_APP_BACKEND_URL",
        "RAILWAY_PUBLIC_DOMAIN",
    ):
        raw = (os.environ.get(key) or "").strip().rstrip("/")
        if not raw:
            continue
        if key == "RAILWAY_PUBLIC_DOMAIN":
            return f"https://{raw}"
        return raw
    return ""


async def ensure_tech_audit_indexes(db) -> None:
    try:
        await db[COL_HISTORY].create_index(
            [("audit_day", 1)],
            unique=True,
            name="tech_audit_day_unique",
            background=True,
        )
    except Exception as exc:
        logger.warning("Index tech_audit_history: %s", exc)


async def migrate_legacy_json_if_needed(db) -> None:
    existing = await db[COL_STATE].find_one({"_id": STATE_ID})
    if existing:
        return
    snapshot = {}
    try:
        if LEGACY_SNAPSHOT.exists():
            snapshot = json.loads(LEGACY_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Migration snapshot JSON: %s", exc)
    if snapshot:
        await db[COL_STATE].replace_one(
            {"_id": STATE_ID},
            {"_id": STATE_ID, **snapshot, "migrated_from_json": True},
            upsert=True,
        )


async def load_snapshot(db) -> dict:
    await migrate_legacy_json_if_needed(db)
    doc = await db[COL_STATE].find_one({"_id": STATE_ID}, {"_id": 0})
    if doc:
        doc.pop("_id", None)
        return doc
    if LEGACY_SNAPSHOT.exists():
        try:
            return json.loads(LEGACY_SNAPSHOT.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


async def load_history(db, limit: int = 60) -> List[dict]:
    cursor = db[COL_HISTORY].find({}, {"_id": 0}).sort("checked_at", -1).limit(limit)
    return await cursor.to_list(limit)


def _check_health(*, in_process: bool) -> Tuple[str, dict, List[str]]:
    """
    In-process (API + cron interne) : le backend qui exécute l'audit EST l'application —
    pas de requête localhost / machine locale.
    CLI externe : ping l'URL publique du CRM si disponible.
    """
    if in_process:
        detail = {
            "status": "ok",
            "health_ok": True,
            "endpoint": "/health",
            "method": "in_process",
            "environment": "production",
        }
        return "ok", detail, []

    base = _public_app_base_url()
    if not base:
        detail = {
            "status": "unavailable",
            "health_ok": None,
            "method": "external",
            "message": "URL publique du CRM non configurée pour un contrôle externe",
        }
        return "unavailable", detail, [
            "Railway: contrôle externe impossible (PUBLIC_APP_URL / REACT_APP_BACKEND_URL absent)"
        ]

    url = f"{base}/health"
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ok = resp.status == 200 and '"ok"' in body
    except Exception as exc:
        ok = False
        detail = {
            "status": "problem",
            "health_ok": False,
            "endpoint": "/health",
            "method": "external",
            "url_host": sanitize_text(base.split("//")[-1].split("/")[0]),
        }
        return "problem", detail, [f"Health check production: {sanitize_text(exc)}"]

    detail = {
        "status": "ok" if ok else "problem",
        "health_ok": ok,
        "endpoint": "/health",
        "method": "external",
        "url_host": sanitize_text(base.split("//")[-1].split("/")[0]),
    }
    return detail["status"], detail, ([] if ok else ["Health check production: réponse invalide"])


async def _check_mongo(db, *, in_process: bool) -> Tuple[str, dict, List[str]]:
    anomalies: List[str] = []
    detail: dict = {
        "status": "problem",
        "accessible": False,
        "environment": "Production",
        "source": "production_runtime" if in_process else "external_connection",
    }
    if db is None:
        st = "problem" if in_process else "unavailable"
        anomalies.append("MongoDB: connexion indisponible")
        detail["status"] = st
        return st, detail, anomalies
    try:
        stats = await db.command("dbStats")
        fs_total = float(stats.get("fsTotalSize") or 0)
        fs_used = float(stats.get("fsUsedSize") or 0)
        fs_free = max(0.0, fs_total - fs_used)
        free_gib = fs_free / (1024**3)
        idx_present, idx_expected = await _count_indexes(db)
        missing_indexes: List[str] = []
        for coll, specs in EXPECTED_INDEX_SPECS.items():
            try:
                idx = await db[coll].index_information()
                keys_list = [tuple(v["key"]) for name, v in idx.items() if name != "_id_"]
                for spec in specs:
                    if tuple(spec) not in keys_list:
                        missing_indexes.append(f"{coll}:{spec}")
            except Exception:
                missing_indexes.append(f"{coll}:?")
        total_docs = 0
        names = await db.list_collection_names()
        for name in names:
            total_docs += await db[name].count_documents({})
        detail.update(
            {
                "accessible": True,
                "volume_gb": round(fs_total / (1024**3), 2) if fs_total else None,
                "free_space_gib": round(free_gib, 2),
                "free_space_label": f"~{free_gib:.2f} Go".replace(".", ","),
                "documents": total_docs,
                "collections": len(names),
                "indexes_present": idx_present,
                "indexes_expected": idx_expected,
                "missing_indexes": missing_indexes[:20],
                "out_of_disk_resolved": free_gib > MONGO_FREE_PROBLEM_GIB,
            }
        )
        status = "ok"
        if missing_indexes:
            status = "problem"
            anomalies.append(f"MongoDB: {len(missing_indexes)} index manquant(s)")
        if free_gib < MONGO_FREE_PROBLEM_GIB:
            status = "problem"
            anomalies.append(f"MongoDB: espace disque critique ({detail['free_space_label']})")
        elif free_gib < MONGO_FREE_WARN_GIB and status == "ok":
            status = "warning"
            anomalies.append(f"MongoDB: espace disque faible ({detail['free_space_label']})")
        detail["status"] = status
        return status, detail, anomalies
    except Exception as exc:
        st = "problem" if in_process else "unavailable"
        anomalies.append(f"MongoDB: {sanitize_text(exc)}")
        detail["status"] = st
        return st, detail, anomalies


async def _scan_storage_refs(db, *, s3_enabled: bool) -> dict:
    total_active_refs = 0
    s3_refs = 0
    non_s3_count = 0
    unique_s3_paths: set[str] = set()
    s3_read_failures = 0

    for coll in STORAGE_COLLECTIONS:
        names = await db.list_collection_names()
        if coll not in names:
            continue
        cursor = db[coll].find(
            {"is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "storage_path": 1, "docx_storage_path": 1},
        )
        async for doc in cursor:
            for field in ("storage_path", "docx_storage_path"):
                sp = (doc.get(field) or "").strip()
                if not sp:
                    continue
                total_active_refs += 1
                kind = classify_storage_path(sp)
                if kind == "s3":
                    s3_refs += 1
                    unique_s3_paths.add(sp)
                else:
                    non_s3_count += 1

    if unique_s3_paths and s3_enabled:

        def _read_s3_paths() -> int:
            from object_storage import get_object

            fails = 0
            for path in unique_s3_paths:
                try:
                    data, _ = get_object(path)
                    if len(data) < 1:
                        raise RuntimeError("fichier vide")
                except Exception:
                    fails += 1
            return fails

        s3_read_failures = await asyncio.to_thread(_read_s3_paths)

    missing_files = non_s3_count + s3_read_failures
    return {
        "total_active_refs": total_active_refs,
        "active_refs_on_s3": s3_refs,
        "active_docs_verified": max(0, total_active_refs - missing_files),
        "active_docs_total": total_active_refs,
        "unique_s3_paths_checked": len(unique_s3_paths) if s3_enabled else 0,
        "missing_docs": missing_files,
        "s3_read_failures": s3_read_failures,
        "non_s3_active_refs": non_s3_count,
    }


async def _check_s3(
    db,
    *,
    in_process: bool,
    scan: Optional[dict] = None,
) -> Tuple[str, dict, List[str]]:
    anomalies: List[str] = []
    detail: dict = {
        "status": "problem",
        "provider": "Infomaniak S3",
        "environment": "production" if in_process else "external",
    }
    try:
        from object_storage import configured, config

        if not configured():
            st = _config_missing_status(in_process=in_process)
            detail.update(
                {
                    "status": st,
                    "message": (
                        "Variables S3 absentes sur le serveur CRM"
                        if in_process
                        else "Variables S3 non disponibles dans cet environnement d'exécution"
                    ),
                }
            )
            msg = (
                "S3: configuration absente sur le serveur CRM"
                if in_process
                else "S3: contrôle impossible (configuration non chargée dans cet environnement)"
            )
            return st, detail, [msg] if st != "unavailable" else []

        def _probe_bucket() -> str:
            import boto3
            from botocore.config import Config as BotoConfig

            cfg = config()
            client = boto3.client(
                "s3",
                endpoint_url=cfg.endpoint_url,
                aws_access_key_id=cfg.access_key,
                aws_secret_access_key=cfg.secret_key,
                region_name=cfg.region or "us-east-1",
                config=BotoConfig(signature_version="s3v4"),
            )
            client.head_bucket(Bucket=cfg.bucket)
            return cfg.bucket

        bucket = await asyncio.to_thread(_probe_bucket)
        detail["bucket_display"] = bucket
        detail["endpoint_configured"] = True
        scan = scan or await _scan_storage_refs(db, s3_enabled=True)
        detail.update(scan)
        detail["last_verification"] = datetime.now(TZ).date().isoformat()
        status = "ok"
        if scan["missing_docs"] > 0 or scan["s3_read_failures"] > 0:
            status = "problem"
            anomalies.append(
                f"S3: {scan['missing_docs']} référence(s) active(s) manquante(s) ou illisible(s)"
            )
        elif scan["non_s3_active_refs"] > 0:
            status = "warning"
            anomalies.append(
                f"S3: {scan['non_s3_active_refs']} référence(s) active(s) hors S3"
            )
        detail["status"] = status
        return status, detail, anomalies
    except Exception as exc:
        anomalies.append(f"S3: {sanitize_text(exc)}")
        detail["status"] = "problem" if in_process else "unavailable"
        return detail["status"], detail, anomalies


def _crmbak_stamp_dt(key: str) -> Optional[datetime]:
    """Horodatage embarqué dans le nom de fichier (heure Europe/Zurich)."""
    name = str(key or "").rsplit("/", 1)[-1]
    m = _CRMBAK_STAMP_RE.search(name)
    if not m:
        return None
    try:
        naive = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=TZ)


def _crmbak_s3_dt(obj: dict) -> Optional[datetime]:
    lm = obj.get("last_modified")
    if lm is None:
        return None
    if getattr(lm, "tzinfo", None) is None:
        lm = lm.replace(tzinfo=timezone.utc)
    return lm.astimezone(timezone.utc)


def _crmbak_effective_dt(obj: dict) -> Optional[datetime]:
    """Date effective = max(LastModified S3, horodatage du nom). Jamais un snapshot historique."""
    candidates: List[datetime] = []
    s3_dt = _crmbak_s3_dt(obj)
    if s3_dt is not None:
        candidates.append(s3_dt)
    stamp = _crmbak_stamp_dt(str(obj.get("key") or ""))
    if stamp is not None:
        candidates.append(stamp.astimezone(timezone.utc))
    if not candidates:
        return None
    return max(candidates)


def _check_backup(*, in_process: bool) -> Tuple[str, dict, List[str]]:
    anomalies: List[str] = []
    detail: dict = {
        "status": "warning",
        "location": "Infomaniak S3",
        "environment": "production" if in_process else "external",
    }
    try:
        backup_remote = _load_backup_remote_module()
        if not backup_remote.configured():
            st = _config_missing_status(in_process=in_process)
            detail["status"] = st
            msg = (
                "Sauvegarde: bucket backup non configuré sur le serveur CRM"
                if in_process
                else "Sauvegarde: contrôle impossible (bucket backup non configuré ici)"
            )
            return st, detail, [msg] if st != "unavailable" else []

        # Lecture live Infomaniak uniquement (pas de snapshot historique).
        _, bucket_name, prefix = backup_remote._client()
        detail["bucket_display"] = bucket_name or ""
        detail["prefix"] = prefix or "crm-backups/"

        items = backup_remote.list_remote_backups(max_keys=5000)
        crmbaks = [o for o in items if str(o.get("key", "")).endswith(".crmbak")]
        crmbaks = [o for o in crmbaks if _crmbak_effective_dt(o) is not None]
        crmbaks.sort(key=lambda o: _crmbak_effective_dt(o) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        logger.info(
            "Tech audit backup scan bucket=%s prefix=%s objects=%s crmbak=%s",
            bucket_name,
            prefix,
            len(items),
            len(crmbaks),
        )
        if crmbaks:
            top = crmbaks[0]
            logger.info(
                "Tech audit backup latest key=%s size=%s effective=%s",
                top.get("key"),
                top.get("size"),
                (_crmbak_effective_dt(top) or datetime.min.replace(tzinfo=timezone.utc)).isoformat(),
            )

        if not crmbaks:
            anomalies.append("Sauvegarde: aucune archive .crmbak trouvée sur le bucket backup")
            detail["status"] = "problem"
            detail["archives_found"] = 0
            return "problem", detail, anomalies

        latest = crmbaks[0]
        effective = _crmbak_effective_dt(latest)
        if effective is None:
            anomalies.append("Sauvegarde: date de dernière archive inconnue")
            detail["status"] = "warning"
            return "warning", detail, anomalies

        age = datetime.now(timezone.utc) - effective.astimezone(timezone.utc)
        local_dt = effective.astimezone(TZ)
        size_bytes = int(latest.get("size") or 0)
        size_mb = size_bytes / (1024 * 1024)
        key = str(latest.get("key") or "")
        filename = key.split("/")[-1] if key else "—"
        detail.update(
            {
                "last_date": local_dt.date().isoformat(),
                "last_time": local_dt.strftime("%H:%M"),
                "filename": filename,
                "size_label": f"~{size_mb:.0f} Mo" if size_mb else "—",
                "size_bytes": size_bytes,
                "age_hours": round(age.total_seconds() / 3600, 1),
                "archives_found": len(crmbaks),
                "restorable": True,
            }
        )
        status = "ok"
        if age > timedelta(hours=BACKUP_PROBLEM_HOURS):
            status = "problem"
            anomalies.append(
                f"Sauvegarde: dernière archive datée de plus de {BACKUP_PROBLEM_HOURS // 24} jours"
            )
        elif age > timedelta(hours=BACKUP_WARN_HOURS):
            status = "warning"
            anomalies.append(
                f"Sauvegarde: dernière archive datée de plus de {BACKUP_WARN_HOURS} h"
            )
        detail["status"] = status
        return status, detail, anomalies
    except Exception as exc:
        st = "problem" if in_process else "unavailable"
        anomalies.append(f"Sauvegarde: {sanitize_text(exc)}")
        detail["status"] = st
        return st, detail, anomalies


async def run_daily_audit(db, *, force: bool = False, in_process: bool = False) -> dict:
    """Exécute le contrôle quotidien et enregistre le résultat (sans doublon journalier)."""
    await ensure_tech_audit_indexes(db)
    now = datetime.now(TZ)
    audit_day = now.date().isoformat()
    ctx = runtime_context(in_process=in_process)
    production = bool(ctx["production"])

    if not force:
        existing = await db[COL_HISTORY].find_one({"audit_day": audit_day}, {"_id": 0, "id": 1})
        if existing:
            return {"skipped": True, "reason": "already_ran_today", "audit_day": audit_day}

    from object_storage import configured as s3_configured

    logger.info(
        "Tech audit start day=%s in_process=%s s3=%s mongo=%s backup_env=%s",
        audit_day,
        in_process,
        s3_configured(),
        bool(os.environ.get("MONGO_URL")),
        bool(os.environ.get("BACKUP_S3_BUCKET") or os.environ.get("S3_BUCKET")),
    )

    railway_st, railway, an_r = _check_health(in_process=in_process)
    mongo_st, mongo, an_m = await _check_mongo(db, in_process=in_process)
    s3_ok = s3_configured()
    scan = await _scan_storage_refs(db, s3_enabled=s3_ok)
    s3_st, storage, an_s = await _check_s3(db, in_process=in_process, scan=scan)
    backup_st, backup, an_b = await asyncio.to_thread(_check_backup, in_process=in_process)

    anomalies = an_r + an_m + an_s + an_b
    global_status = aggregate_global(
        railway_st, mongo_st, s3_st, backup_st, in_process=in_process
    )
    result = status_label(global_status)

    entry = {
        "id": str(uuid.uuid4()),
        "audit_day": audit_day,
        "checked_at": now.isoformat(),
        "global_status": global_status,
        "result": result,
        "runtime": ctx,
        "railway": {**railway, "status": railway_st},
        "mongodb": {**mongo, "status": mongo_st},
        "storage": {**storage, "status": s3_st},
        "backup": {**backup, "status": backup_st},
        "crm": {"status": railway_st},
        "anomalies": anomalies,
    }

    if force:
        await db[COL_HISTORY].delete_one({"audit_day": audit_day})
    await db[COL_HISTORY].insert_one(entry)

    snapshot = {
        "_id": STATE_ID,
        "last_control_date": audit_day,
        "last_control_at": now.isoformat(),
        "last_control_label": format_fr_datetime(now),
        "next_control_label": next_control_label(now),
        "global_status": global_status,
        "global_status_label": result,
        "runtime": ctx,
        "storage": {
            "status": s3_st,
            "provider": storage.get("provider") or "Infomaniak S3",
            "bucket_display": storage.get("bucket_display") or "",
            "active_docs_verified": storage.get("active_docs_verified"),
            "active_docs_total": storage.get("active_docs_total"),
            "missing_docs": storage.get("missing_docs"),
            "s3_read_failures": storage.get("s3_read_failures"),
            "non_s3_active_refs": storage.get("non_s3_active_refs"),
            "last_verification": storage.get("last_verification"),
        },
        "backup": backup,
        "mongodb": mongo,
        "hosting": {
            "status": "operational" if railway_st == "ok" else ("unknown" if railway_st == "unavailable" else "degraded"),
            "platform": "Railway",
            "application": "LeoSoft",
            "storage_label": "Infomaniak S3",
            "database_label": "MongoDB",
            "health_ok": railway.get("health_ok"),
            "health_method": railway.get("method"),
            "last_deploy": audit_day,
        },
        "anomalies": anomalies,
        "functional_tests": (await load_snapshot(db)).get("functional_tests") or {},
    }
    await db[COL_STATE].replace_one({"_id": STATE_ID}, snapshot, upsert=True)

    logger.info(
        "Tech audit OK day=%s status=%s in_process=%s production=%s anomalies=%s",
        audit_day,
        global_status,
        in_process,
        production,
        len(anomalies),
    )
    return {
        "ok": True,
        "audit_day": audit_day,
        "global_status": global_status,
        "anomalies": anomalies,
        "runtime": ctx,
    }


async def maybe_run_scheduled_audit(db) -> Optional[dict]:
    if not _env_bool("TECH_AUDIT_ENABLED", "true"):
        logger.info("Tech audit: désactivé (TECH_AUDIT_ENABLED)")
        return None
    now = datetime.now(TZ)
    audit_day = now.date().isoformat()
    existing = await db[COL_HISTORY].find_one({"audit_day": audit_day}, {"_id": 0})
    if existing and not existing.get("migrated_from_json"):
        logger.info("Tech audit: déjà enregistré pour %s — aucun doublon", audit_day)
        return None
    if existing and existing.get("migrated_from_json"):
        await db[COL_HISTORY].delete_one({"audit_day": audit_day})
    if now.hour < _audit_hour():
        logger.debug("Tech audit: avant l'heure planifiée (%s:00)", _audit_hour())
        return None
    logger.info("Tech audit: démarrage planifié pour %s (in_process)", audit_day)
    if audit_is_running():
        return None
    asyncio.create_task(run_daily_audit_background(db, force=False))
    return {"started": True, "audit_day": audit_day}


async def build_tech_status_from_db(db) -> dict:
    snapshot = await load_snapshot(db)
    history = await load_history(db)
    _mongo_st, live_mongo, _ = await _check_mongo(db, in_process=True)

    last_at = snapshot.get("last_control_at") or snapshot.get("last_control_date")
    last_label = snapshot.get("last_control_label")
    if not last_label and last_at:
        try:
            dt = datetime.fromisoformat(str(last_at))
            last_label = format_fr_datetime(dt)
        except Exception:
            last_label = str(last_at)

    global_status = snapshot.get("global_status") or "ok"
    gs_label = snapshot.get("global_status_label") or status_label(global_status)
    anomalies = list(snapshot.get("anomalies") or [])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "last_control_date": snapshot.get("last_control_date"),
        "last_control_at": snapshot.get("last_control_at"),
        "last_control_label": last_label or "—",
        "next_control_label": snapshot.get("next_control_label") or next_control_label(),
        "global_status": global_status,
        "global_status_label": gs_label,
        "runtime": snapshot.get("runtime") or runtime_context(in_process=True),
        "storage": dict(snapshot.get("storage") or {}),
        "backup": dict(snapshot.get("backup") or {}),
        "mongodb": dict(snapshot.get("mongodb") or {}),
        "hosting": dict(snapshot.get("hosting") or {}),
        "functional_tests": dict(snapshot.get("functional_tests") or {}),
        "history": history,
        "anomalies": anomalies,
        "health_check_ok": bool((snapshot.get("hosting") or {}).get("health_ok", True)),
        "audit_running": audit_is_running(),
    }

    if live_mongo.get("accessible"):
        mongo = payload["mongodb"]
        mongo["free_space_label"] = live_mongo.get("free_space_label") or mongo.get("free_space_label")
        mongo["documents"] = live_mongo.get("documents", mongo.get("documents"))
        mongo["collections"] = live_mongo.get("collections", mongo.get("collections"))
        mongo["indexes_present"] = live_mongo.get("indexes_present", mongo.get("indexes_present"))
        mongo["indexes_expected"] = live_mongo.get("indexes_expected", mongo.get("indexes_expected"))
        mongo["live_read"] = True

    return payload
