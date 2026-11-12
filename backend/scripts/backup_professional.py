"""
Pipeline de sauvegarde professionnelle (indépendant de Railway runtime) :

1) Dump Mongo (JSONL) + tous les PDF/documents (via S3 / local)
2) Vérification d'intégrité (manifest SHA256 + integrity.json)
3) Archive .tar.gz
4) Chiffrement AES-256-GCM (.crmbak)
5) Upload Object Storage Infomaniak (si BACKUP_S3_* / S3_* configurés)
6) Conservation locale optionnelle du .crmbak

Usage:
  cd backend
  # charger .env.backup puis :
  python scripts/backup_professional.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPTS))

from backup_crypto import encrypt_file  # noqa: E402
from backup_full import main as run_backup_full  # noqa: E402
from backup_remote import configured as remote_configured  # noqa: E402
from backup_remote import prune_local_backups  # noqa: E402
from backup_remote import prune_remote_backups  # noqa: E402
from backup_remote import sha256_file  # noqa: E402
from backup_remote import upload_backup  # noqa: E402
from verify_backup import verify_backup_dir  # noqa: E402

logger = logging.getLogger("backup_professional")


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
    # object_storage lit S3_* ; l'upload utilise BACKUP_S3_*.
    # Si seuls BACKUP_S3_* sont définis, les propager pour la lecture des documents.
    for src, dst in (
        ("BACKUP_S3_ENDPOINT_URL", "S3_ENDPOINT_URL"),
        ("BACKUP_S3_ACCESS_KEY", "S3_ACCESS_KEY"),
        ("BACKUP_S3_SECRET_KEY", "S3_SECRET_KEY"),
        ("BACKUP_S3_BUCKET", "S3_BUCKET"),
        ("BACKUP_S3_REGION", "S3_REGION"),
        ("BACKUP_S3_FORCE_PATH_STYLE", "S3_FORCE_PATH_STYLE"),
    ):
        if (os.environ.get(src) or "").strip() and not (os.environ.get(dst) or "").strip():
            os.environ[dst] = os.environ[src].strip()


def latest_backup_dir(root: Path) -> Path:
    dirs = sorted(root.glob("backups_full_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not dirs:
        raise RuntimeError(f"Aucun dossier backups_full_* dans {root}")
    return dirs[0]


def make_tar_gz(src_dir: Path, dest_tar: Path) -> Path:
    dest_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest_tar, "w:gz") as tar:
        tar.add(src_dir, arcname=src_dir.name)
    return dest_tar


def main() -> int:
    # stdout only: évite que PowerShell traite les logs INFO comme NativeCommandError
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )
    load_dotenv_file(BACKEND / ".env.backup")

    backup_root = Path(os.environ.get("BACKUP_DIR") or (BACKEND / "backups")).resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    os.environ["BACKUP_DIR"] = str(backup_root)

    require_remote = str(os.environ.get("BACKUP_REQUIRE_REMOTE", "true")).lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    logger.info("=== 1/5 Dump Mongo + fichiers ===")
    run_backup_full()
    out_dir = latest_backup_dir(backup_root)

    logger.info("=== 2/5 Vérification intégrité dossier ===")
    verify_report = verify_backup_dir(out_dir)
    if not verify_report.get("ok"):
        raise RuntimeError(f"Vérification échouée: {verify_report}")

    stamp = out_dir.name.replace("backups_full_", "")
    tar_path = backup_root / f"prevoyancecrm_backup_{stamp}.tar.gz"
    enc_path = backup_root / f"prevoyancecrm_backup_{stamp}.tar.gz.crmbak"

    logger.info("=== 3/5 Archive tar.gz ===")
    make_tar_gz(out_dir, tar_path)
    tar_sha = sha256_file(tar_path)

    logger.info("=== 4/5 Chiffrement AES-GCM ===")
    enc_meta = encrypt_file(tar_path, enc_path)
    enc_sha = sha256_file(enc_path)

    remote_meta = None
    if remote_configured():
        logger.info("=== 5/5 Upload Infomaniak Object Storage + vérification ===")
        remote_meta = upload_backup(enc_path)
        if not remote_meta.get("verified") or remote_meta.get("remote_size") != enc_path.stat().st_size:
            raise RuntimeError(f"Upload Infomaniak non vérifié: {remote_meta}")
        logger.info(
            "Upload vérifié: %s size=%s sha256=%s",
            remote_meta.get("uri"),
            remote_meta.get("remote_size"),
            remote_meta.get("sha256"),
        )
    else:
        msg = (
            "Object Storage non configuré (BACKUP_S3_* absents). "
            f"Archive locale: {enc_path}"
        )
        if require_remote:
            raise RuntimeError(msg + " — BACKUP_REQUIRE_REMOTE=true, échec.")
        logger.warning("=== 5/5 SKIP upload distant — %s ===", msg)

    keep_plain = str(os.environ.get("BACKUP_KEEP_PLAIN_TAR", "false")).lower() in ("1", "true", "yes")
    if not keep_plain and tar_path.exists():
        tar_path.unlink()

    # Rapport non secret à côté de l'archive chiffrée (avant suppression du dossier clair)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "encrypted_archive": str(enc_path),
        "encrypted_sha256": enc_sha,
        "tar_sha256_before_encrypt": tar_sha,
        "encryption": enc_meta,
        "verify": verify_report,
        "remote": remote_meta,
        "railway_independent": True,
        "plaintext_dir_removed": False,
    }
    (backup_root / f"prevoyancecrm_backup_{stamp}.report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    keep_plain_dir = str(os.environ.get("BACKUP_KEEP_PLAIN_DIR", "false")).lower() in ("1", "true", "yes")
    if keep_plain_dir:
        report["backup_dir"] = str(out_dir)
        (out_dir / "professional_backup_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        # Ne jamais laisser Mongo JSONL + PDF en clair après chiffrement réussi
        try:
            shutil.rmtree(out_dir)
            report["plaintext_dir_removed"] = True
            report["backup_dir"] = None
            (backup_root / f"prevoyancecrm_backup_{stamp}.report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("Dossier clair supprimé: %s", out_dir)
        except Exception as e:
            logger.error("Impossible de supprimer le dossier clair %s: %s", out_dir, e)
            report["backup_dir"] = str(out_dir)
            report["plaintext_dir_removed"] = False

    # Prune off par défaut : 1 copie PC + 1 copie Infomaniak, sans supprimer l'existant.
    # Suppression uniquement si BACKUP_ALLOW_PRUNE=true et BACKUP_NO_PRUNE n'est pas vrai.
    no_prune = str(os.environ.get("BACKUP_NO_PRUNE", "")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    allow_prune = str(os.environ.get("BACKUP_ALLOW_PRUNE", "")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if no_prune or not allow_prune:
        logger.info(
            "=== Retention désactivée (prune off; BACKUP_ALLOW_PRUNE requis pour supprimer) ==="
        )
        keep_remote = 0
        keep_local = 0
        local_prune = {"deleted": 0, "skipped": True, "reason": "prune_disabled"}
        remote_prune = {"deleted": 0, "skipped": True, "reason": "prune_disabled"}
    else:
        keep_remote = int(
            os.environ.get("BACKUP_RETENTION_REMOTE")
            or os.environ.get("BACKUP_RETENTION_COUNT", "9999")
            or "9999"
        )
        keep_local = int(
            os.environ.get("BACKUP_RETENTION_LOCAL")
            or os.environ.get("BACKUP_RETENTION_COUNT", "9999")
            or "9999"
        )
        logger.info("=== Retention explicite: Infomaniak=%s local=%s ===", keep_remote, keep_local)
        local_prune = prune_local_backups(backup_root, keep=keep_local)
        remote_prune = prune_remote_backups(keep=keep_remote) if remote_configured() else {"skipped": True}
    report["retention"] = {
        "keep_remote": keep_remote,
        "keep_local": keep_local,
        "local": local_prune,
        "remote": remote_prune,
    }
    (backup_root / f"prevoyancecrm_backup_{stamp}.report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Retention local=%s remote=%s", local_prune, remote_prune)

    logger.info("PROFESSIONAL_BACKUP_OK %s", enc_path)
    print(
        json.dumps(
            {
                "ok": True,
                "encrypted": str(enc_path),
                "remote": remote_meta,
                "retention": report["retention"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
            force=True,
        )
        logging.getLogger("backup_professional").exception("BACKUP FAILED: %s", e)
        raise SystemExit(1)
