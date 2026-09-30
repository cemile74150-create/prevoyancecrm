"""
Upload / download des archives de sauvegarde vers Object Storage Infomaniak (S3 privé).

Variables (priorité BACKUP_S3_* puis S3_*) :
  BACKUP_S3_ENDPOINT_URL / S3_ENDPOINT_URL
  BACKUP_S3_ACCESS_KEY / S3_ACCESS_KEY
  BACKUP_S3_SECRET_KEY / S3_SECRET_KEY
  BACKUP_S3_BUCKET / S3_BUCKET
  BACKUP_S3_REGION / S3_REGION
  BACKUP_S3_PREFIX  (défaut: crm-backups/)
  BACKUP_S3_FORCE_PATH_STYLE (défaut: true)
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return default


def configured() -> bool:
    return bool(
        _env("BACKUP_S3_ENDPOINT_URL", "S3_ENDPOINT_URL")
        and _env("BACKUP_S3_ACCESS_KEY", "S3_ACCESS_KEY")
        and _env("BACKUP_S3_SECRET_KEY", "S3_SECRET_KEY")
        and _env("BACKUP_S3_BUCKET", "S3_BUCKET")
    )


def _client():
    endpoint = _env("BACKUP_S3_ENDPOINT_URL", "S3_ENDPOINT_URL")
    access = _env("BACKUP_S3_ACCESS_KEY", "S3_ACCESS_KEY")
    secret = _env("BACKUP_S3_SECRET_KEY", "S3_SECRET_KEY")
    # Infomaniak S3 exige us-east-1 dans la signature (meme si le projet OpenStack est dc4-a)
    region = _env("BACKUP_S3_REGION", "S3_REGION", default="us-east-1") or "us-east-1"
    force_path = _env("BACKUP_S3_FORCE_PATH_STYLE", "S3_FORCE_PATH_STYLE", default="true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    cfg = BotoConfig(
        region_name=region,
        s3={"addressing_style": "path" if force_path else "virtual"},
        signature_version="s3v4",
        # Infomaniak ne supporte pas aws-chunked / flexible checksums boto3 recent
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        retries={"max_attempts": 5, "mode": "standard"},
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=region,
        config=cfg,
    ), _env("BACKUP_S3_BUCKET", "S3_BUCKET"), _env("BACKUP_S3_PREFIX", default="crm-backups/").lstrip("/")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_backup(local_path: Path, remote_name: Optional[str] = None) -> dict:
    if not configured():
        raise RuntimeError(
            "Object Storage backup non configuré. "
            "Renseignez BACKUP_S3_* (ou S3_*) dans backend/.env.backup"
        )
    client, bucket, prefix = _client()
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    # Certains interfaces (type Horizon) ne créent/affichent pas toujours les "dossiers virtuels"
    # si aucun marqueur n'existe. On met donc un marqueur vide pour le préfixe.
    if prefix:
        folder_key = prefix.rstrip("/") + "/"
        try:
            client.put_object(
                Bucket=bucket,
                Key=folder_key,
                Body=b"",
                ContentType="application/x-directory",
            )
        except Exception:
            # Le marqueur est best-effort : on ne bloque pas l'upload de l'archive.
            pass

    key = f"{prefix}{remote_name or local_path.name}"
    local_size = local_path.stat().st_size
    digest = sha256_file(local_path)
    try:
        client.upload_file(
            str(local_path),
            bucket,
            key,
            ExtraArgs={
                "ContentType": "application/octet-stream",
                "Metadata": {"sha256": digest, "source": "prevoyance-crm-backup"},
            },
        )
    except Exception:
        # Certains backends S3 rejectent Metadata — retry simple
        client.upload_file(str(local_path), bucket, key, ExtraArgs={"ContentType": "application/octet-stream"})

    # Preuve : l'objet distant doit exister avec une taille cohérente
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise RuntimeError(f"Upload S3 non vérifiable (head_object échoué) s3://{bucket}/{key}: {e}") from e

    remote_size = int(head.get("ContentLength") or 0)
    if remote_size != local_size:
        raise RuntimeError(
            f"Taille distante incohérente pour s3://{bucket}/{key}: "
            f"local={local_size} remote={remote_size}"
        )

    return {
        "bucket": bucket,
        "key": key,
        "uri": f"s3://{bucket}/{key}",
        "sha256": digest,
        "size": local_size,
        "remote_size": remote_size,
        "verified": True,
        "etag": (head.get("ETag") or "").strip('"') or None,
    }


def download_backup(key: str, dest: Path) -> dict:
    if not configured():
        raise RuntimeError("Object Storage backup non configuré")
    client, bucket, prefix = _client()
    full_key = key
    if not key.startswith(prefix) and not key.startswith("crm-backups"):
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        full_key = f"{prefix}{key.lstrip('/')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(bucket, full_key, str(dest))
    return {"bucket": bucket, "key": full_key, "path": str(dest), "sha256": sha256_file(dest)}


def list_remote_backups(max_keys: int = 1000) -> list:
    if not configured():
        return []
    client, bucket, prefix = _client()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    out = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": min(max_keys, 1000)}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            out.append(
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj.get("LastModified"),
                }
            )
            if len(out) >= max_keys:
                return out
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return out


def select_crmbak_for_retention(items: list, keep: int) -> tuple[list, list]:
    """
    Sépare les archives .crmbak : (à conserver, à supprimer).
    Les plus récentes (last_modified desc) sont conservées ; keep<=0 → rien à faire.
    """
    if keep <= 0:
        return [], []
    crmbaks = [o for o in items if str(o.get("key", "")).endswith(".crmbak")]

    def _sort_key(o: dict):
        lm = o.get("last_modified")
        if lm is None:
            return ""
        if hasattr(lm, "isoformat"):
            return lm.isoformat()
        return str(lm)

    crmbaks.sort(key=_sort_key, reverse=True)
    return crmbaks[:keep], crmbaks[keep:]


def prune_remote_backups(keep: int = 7, *, dry_run: bool = False) -> dict:
    """
    Conserve les `keep` archives .crmbak Infomaniak les plus récentes, supprime le reste.

    - Ne touche qu'aux objets `*.crmbak` (jamais Mongo / CRM / autres clés).
    - Ne supprime jamais les `keep` plus récentes (dont la sauvegarde venant d'être uploadée).
    - dry_run=True : calcule would_delete sans appeler delete_object.
    """
    if not configured() or keep <= 0:
        return {"deleted": 0, "kept": 0, "skipped": True, "dry_run": dry_run}
    client, bucket, _prefix = _client()
    all_items = list_remote_backups(max_keys=5000)
    keep_items, delete_items = select_crmbak_for_retention(all_items, keep)
    # Garde-fou : ne jamais effacer une clé encore dans keep_items
    keep_keys = {str(o.get("key")) for o in keep_items}
    delete_items = [o for o in delete_items if str(o.get("key")) not in keep_keys]

    deleted = 0
    would_delete = [str(o.get("key")) for o in delete_items]
    if not dry_run:
        for obj in delete_items:
            key = str(obj.get("key") or "")
            if not key.endswith(".crmbak"):
                continue
            client.delete_object(Bucket=bucket, Key=key)
            deleted += 1
    return {
        "deleted": deleted if not dry_run else 0,
        "would_delete": would_delete,
        "would_delete_count": len(would_delete),
        "kept": len(keep_items),
        "kept_keys": [str(o.get("key")) for o in keep_items],
        "total": len(keep_items) + len(delete_items),
        "dry_run": dry_run,
        "keep": keep,
    }


def prune_local_backups(backup_root: Path, keep: int = 7) -> dict:
    """Conserve les `keep` fichiers .crmbak locaux (+ rapports associes)."""
    if keep <= 0:
        return {"deleted": 0, "kept": 0, "skipped": True}
    archives = sorted(
        backup_root.glob("prevoyancecrm_backup_*.tar.gz.crmbak"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    keep_set = set(archives[:keep])
    deleted = 0
    for path in archives[keep:]:
        try:
            path.unlink(missing_ok=True)
            deleted += 1
        except Exception:
            pass
        # prevoyancecrm_backup_STAMP.tar.gz.crmbak -> prevoyancecrm_backup_STAMP.report.json
        stamp = path.name
        if stamp.endswith(".tar.gz.crmbak"):
            report = backup_root / (stamp[: -len(".tar.gz.crmbak")] + ".report.json")
            try:
                report.unlink(missing_ok=True)
            except Exception:
                pass
    for report in backup_root.glob("prevoyancecrm_backup_*.report.json"):
        stamp = report.name[: -len(".report.json")]
        arch = backup_root / f"{stamp}.tar.gz.crmbak"
        if not arch.exists():
            try:
                report.unlink(missing_ok=True)
            except Exception:
                pass
    return {"deleted": deleted, "kept": len(keep_set), "total": len(archives)}
