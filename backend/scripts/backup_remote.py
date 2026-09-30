"""Lecture des archives CRM (.crmbak) sur le bucket Infomaniak.

Les identifiants BACKUP_S3_* sont utilisés en priorité. À défaut, le client
retombe sur S3_* (déjà utilisé pour les documents) et le préfixe crm-backups/.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import boto3
from botocore.config import Config as BotoConfig


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _env_bool(name: str, default: str = "true") -> bool:
    raw = _env(name) or default
    return raw.lower() in ("1", "true", "yes", "y", "on")


def _settings() -> Dict[str, Any]:
    endpoint = _env("BACKUP_S3_ENDPOINT_URL") or _env("S3_ENDPOINT_URL")
    access_key = _env("BACKUP_S3_ACCESS_KEY") or _env("S3_ACCESS_KEY")
    secret_key = _env("BACKUP_S3_SECRET_KEY") or _env("S3_SECRET_KEY")
    bucket = _env("BACKUP_S3_BUCKET") or _env("S3_BUCKET")
    region = _env("BACKUP_S3_REGION") or _env("S3_REGION") or "us-east-1"
    prefix = _env("BACKUP_S3_PREFIX") or "crm-backups/"
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    force_path = _env_bool(
        "BACKUP_S3_FORCE_PATH_STYLE",
        _env("S3_FORCE_PATH_STYLE") or "true",
    )
    return {
        "endpoint_url": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "bucket": bucket,
        "region": region,
        "prefix": prefix,
        "force_path_style": force_path,
    }


def configured() -> bool:
    cfg = _settings()
    return all([cfg["endpoint_url"], cfg["access_key"], cfg["secret_key"], cfg["bucket"]])


def _client() -> Tuple[Any, str, str]:
    cfg = _settings()
    if not configured():
        raise RuntimeError(
            "Sauvegarde S3 non configurée (BACKUP_S3_* ou S3_ENDPOINT_URL / S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET)."
        )
    boto_cfg = BotoConfig(
        region_name=cfg["region"] or "us-east-1",
        s3={"addressing_style": "path" if cfg["force_path_style"] else "virtual"},
        signature_version="s3v4",
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        retries={"max_attempts": 3, "mode": "standard"},
    )
    client = boto3.client(
        "s3",
        endpoint_url=cfg["endpoint_url"],
        aws_access_key_id=cfg["access_key"],
        aws_secret_access_key=cfg["secret_key"],
        region_name=cfg["region"] or "us-east-1",
        config=boto_cfg,
    )
    return client, cfg["bucket"], cfg["prefix"]


def list_remote_backups(max_keys: int = 5000) -> List[dict]:
    client, bucket, prefix = _client()
    items: List[dict] = []
    token = None
    while len(items) < max_keys:
        kwargs: Dict[str, Any] = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": min(1000, max_keys - len(items))}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            items.append(
                {
                    "key": obj.get("Key") or "",
                    "size": int(obj.get("Size") or 0),
                    "last_modified": obj.get("LastModified"),
                }
            )
            if len(items) >= max_keys:
                break
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    return items
