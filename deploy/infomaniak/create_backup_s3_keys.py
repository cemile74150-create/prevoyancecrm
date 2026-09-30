# Complete BACKUP_S3_* in backend/.env.backup after creating EC2 credentials.
# Usage (PowerShell):
#   $env:OS_PASSWORD = "votre_mot_de_passe_openstack"
#   python deploy/infomaniak/create_backup_s3_keys.py
#
# Or pass: python deploy/infomaniak/create_backup_s3_keys.py --password "..."

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_BACKUP = ROOT / "backend" / ".env.backup"
OPENSTACK = Path.home() / "AppData/Roaming/Python/Python314/Scripts/openstack.exe"

# From PCP-UZDP8X4-openrc
OS_ENV = {
    "OS_AUTH_URL": "https://api.pub1.infomaniak.cloud/identity",
    "OS_PROJECT_ID": "9f9c85d0aa4445edbe8bbb54b8f0fc96",
    "OS_PROJECT_NAME": "PCP-UZDP8X4",
    "OS_USER_DOMAIN_NAME": "Default",
    "OS_PROJECT_DOMAIN_ID": "default",
    "OS_USERNAME": "PCU-UZDP8X4",
    "OS_REGION_NAME": "dc4-a",
    "OS_INTERFACE": "public",
    "OS_IDENTITY_API_VERSION": "3",
}

BUCKET = "prevoyancecrm-backups"
ENDPOINT = "https://s3.pub2.infomaniak.cloud"
REGION = "us-east-1"
PREFIX = "crm-backups/"


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    keys_seen = set()
    out: list[str] = []
    for line in lines:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if m and m.group(1) in updates:
            k = m.group(1)
            out.append(f"{k}={updates[k]}")
            keys_seen.add(k)
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in keys_seen:
            out.append(f"{k}={v}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", default="", help="OpenStack password for PCU-UZDP8X4")
    parser.add_argument("--list-only", action="store_true", help="List existing EC2 credentials")
    args = parser.parse_args()

    import os

    password = (args.password or os.environ.get("OS_PASSWORD") or "").strip()
    if not password:
        print(
            "Mot de passe OpenStack manquant.\n"
            "1) Manager Infomaniak > Public Cloud > projet PCP-UZDP8X4\n"
            "2) Utilisateur API PCU-UZDP8X4 (mot de passe du compte OpenStack)\n"
            "Puis:  $env:OS_PASSWORD='...'; python deploy/infomaniak/create_backup_s3_keys.py",
            file=sys.stderr,
        )
        return 2

    if not OPENSTACK.exists():
        print(f"openstack CLI introuvable: {OPENSTACK}", file=sys.stderr)
        return 2

    env = {**os.environ, **OS_ENV, "OS_PASSWORD": password}

    if args.list_only:
        r = subprocess.run(
            [str(OPENSTACK), "ec2", "credentials", "list", "-f", "json"],
            env=env,
            capture_output=True,
            text=True,
        )
        print(r.stdout or r.stderr)
        return r.returncode

    print("Creation des credentials EC2 (Access Key / Secret Key)...")
    r = subprocess.run(
        [str(OPENSTACK), "ec2", "credentials", "create", "-f", "json"],
        env=env,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stderr or r.stdout, file=sys.stderr)
        return r.returncode

    import json

    data = json.loads(r.stdout)
    access = data.get("access") or data.get("Access")
    secret = data.get("secret") or data.get("Secret")
    if not access or not secret:
        print("Reponse inattendue:", r.stdout, file=sys.stderr)
        return 1

    updates = {
        "BACKUP_S3_ENDPOINT_URL": ENDPOINT,
        "BACKUP_S3_ACCESS_KEY": access,
        "BACKUP_S3_SECRET_KEY": secret,
        "BACKUP_S3_BUCKET": BUCKET,
        "BACKUP_S3_REGION": REGION,
        "BACKUP_S3_FORCE_PATH_STYLE": "true",
        "BACKUP_S3_PREFIX": PREFIX,
    }
    upsert_env(ENV_BACKUP, updates)
    print(f"OK: cles ecrites dans {ENV_BACKUP}")
    print(f"  ACCESS_KEY={access}")
    print(f"  BUCKET={BUCKET} REGION={REGION}")
    print("Test de connexion S3...")

    # Quick list-bucket test via boto3
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        client = boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name=REGION,
            config=BotoConfig(
                s3={"addressing_style": "path"},
                signature_version="s3v4",
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        client.head_bucket(Bucket=BUCKET)
        print(f"OK: bucket '{BUCKET}' accessible")
        # write a tiny probe object then delete
        key = f"{PREFIX.rstrip('/')}/.crm-backup-probe"
        client.put_object(Bucket=BUCKET, Key=key, Body=b"ok")
        client.delete_object(Bucket=BUCKET, Key=key)
        print("OK: ecriture/suppression test reussie")
    except Exception as e:
        print(f"ATTENTION: cles creees mais test S3 echoue: {e}", file=sys.stderr)
        print("Verifiez le nom exact du bucket et les droits SwiftOperator.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
