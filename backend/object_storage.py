"""
Object Storage (S3-compatible) pour documents CRM.

Objectif:
- stocker les documents dans un bucket privé Infomaniak
- ne jamais exposer de lien public ni d'URL présignée permanente
- le CRM sert les fichiers uniquement via ses routes authentifiées (proxy serveur)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import boto3
from botocore.config import Config as BotoConfig


S3_PREFIX = "s3://"
APP_NAME = "prevoyance-crm"


@dataclass(frozen=True)
class S3Config:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket: str
    region: str
    force_path_style: bool


def _env_bool(name: str, default: str = "true") -> bool:
    v = os.environ.get(name, default).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def config() -> S3Config:
    endpoint_url = os.environ.get("S3_ENDPOINT_URL", "").strip()
    access_key = os.environ.get("S3_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("S3_SECRET_KEY", "").strip()
    bucket = os.environ.get("S3_BUCKET", "").strip()
    region = os.environ.get("S3_REGION", "us-east-1").strip()
    force_path_style = _env_bool("S3_FORCE_PATH_STYLE", "true")

    if not (endpoint_url and access_key and secret_key and bucket):
        raise RuntimeError("S3 non configuré (S3_ENDPOINT_URL / S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET).")

    return S3Config(
        endpoint_url=endpoint_url,
        access_key=access_key,
        secret_key=secret_key,
        bucket=bucket,
        region=region,
        force_path_style=force_path_style,
    )


def configured() -> bool:
    return all(
        [
            (os.environ.get("S3_ENDPOINT_URL") or "").strip(),
            (os.environ.get("S3_ACCESS_KEY") or "").strip(),
            (os.environ.get("S3_SECRET_KEY") or "").strip(),
            (os.environ.get("S3_BUCKET") or "").strip(),
        ]
    )


def client():
    cfg = config()
    boto_cfg = BotoConfig(
        region_name=cfg.region or "us-east-1",
        s3={
            "addressing_style": "path" if cfg.force_path_style else "virtual",
        },
        signature_version="s3v4",
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint_url,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        region_name=cfg.region or "us-east-1",
        config=boto_cfg,
    )


def _logical_path_to_key(logical_path: str) -> str:
    """
    Le backend appelle put_object avec des paths du style:
      prevoyance-crm/uploads/{user_id}/{uuid}.{ext}
      prevoyance-crm/generated/{user_id}/{uuid}.pdf

    On stocke dans S3 avec les clés:
      uploads/{user_id}/{uuid}.{ext}
      generated/{user_id}/{uuid}.pdf
    """
    p = (logical_path or "").replace("\\", "/").lstrip("/")
    if p.startswith(APP_NAME + "/"):
        p = p[len(APP_NAME) + 1 :]
    return p


def _parse_s3_storage_path(storage_path: str) -> Tuple[str, str]:
    """
    Retourne (bucket, key).
    storage_path attendu:
      s3://bucket/key
    """
    sp = (storage_path or "").strip()
    if not sp.startswith(S3_PREFIX):
        raise ValueError(f"Not an S3 storage_path: {storage_path}")

    rest = sp[len(S3_PREFIX) :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid s3:// path: {storage_path}")
    return bucket, key


def get_object(storage_path: str) -> Tuple[bytes, str]:
    if not configured():
        raise RuntimeError("S3 non configuré")

    cfg = config()
    bucket, key = _parse_s3_storage_path(storage_path)
    if bucket != cfg.bucket:
        # Refuse cross-bucket reads (évite toute fuite via chemin Mongo compromis)
        raise ValueError(f"Bucket S3 non autorisé: {bucket}")

    c = client()
    obj = c.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read()
    if not isinstance(body, (bytes, bytearray)):
        raise TypeError(
            f"S3 Body.read() a renvoyé {type(body).__name__} au lieu de bytes "
            "(client S3 sync requis, pas de coroutine)"
        )
    ctype = obj.get("ContentType") or "application/octet-stream"
    return bytes(body), ctype


def put_object(logical_path: str, data: bytes, content_type: str) -> dict:
    if not configured():
        raise RuntimeError("S3 non configuré")
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(
            f"put_object attend des bytes, reçu {type(data).__name__}"
        )
    data = bytes(data)

    cfg = config()
    if logical_path.startswith(S3_PREFIX):
        _bucket, key = _parse_s3_storage_path(logical_path)
    else:
        key = _logical_path_to_key(logical_path)

    c = client()
    c.put_object(
        Bucket=cfg.bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    size = len(data)
    storage_path = f"{S3_PREFIX}{cfg.bucket}/{key}"
    return {"path": storage_path, "size": size}


def delete_object(storage_path: str) -> None:
    """Suppression serveur-side uniquement (pas d'URL publique)."""
    if not configured():
        raise RuntimeError("S3 non configuré")
    cfg = config()
    bucket, key = _parse_s3_storage_path(storage_path)
    if bucket != cfg.bucket:
        raise ValueError(f"Bucket S3 non autorisé: {bucket}")
    client().delete_object(Bucket=cfg.bucket, Key=key)
