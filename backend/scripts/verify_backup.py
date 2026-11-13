"""
Vérifie l'intégrité d'un dossier de backup ou d'une archive .crmbak.

Usage:
  python scripts/verify_backup.py path/to/backups_full_...
  python scripts/verify_backup.py path/to/file.tar.gz.crmbak
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
import tarfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_backup_dir(backup_dir: Path) -> dict:
    backup_dir = backup_dir.resolve()
    manifest = backup_dir / "manifest.csv"
    integrity_path = backup_dir / "integrity.json"
    cols = backup_dir / "collections_jsonl"

    errors = []
    checked = 0
    if not cols.exists():
        errors.append("collections_jsonl/ manquant")
    else:
        jsonl_files = list(cols.glob("*.jsonl"))
        if not jsonl_files:
            errors.append("aucun JSONL")
        for f in jsonl_files:
            if f.stat().st_size == 0 and f.name not in ("app_migrations.jsonl",):
                # empty collections possible; warn only for large expected ones
                pass

    if not manifest.exists():
        errors.append("manifest.csv manquant")
    else:
        with manifest.open(encoding="utf-8") as mf:
            for row in csv.DictReader(mf):
                status = str(row.get("ok", "")).strip().lower()
                if status.startswith("skipped"):
                    # Soft-deleted / volontairement omis: pas une erreur d'intégrité
                    continue
                if status != "true":
                    errors.append(f"fichier KO id={row.get('id')}: {row.get('error')}")
                    continue
                rel = row.get("local_path") or ""
                fp = backup_dir / rel
                expected = (row.get("sha256") or "").strip()
                if not fp.exists():
                    errors.append(f"manquant: {rel}")
                    continue
                actual = sha256_file(fp)
                checked += 1
                if expected and actual != expected:
                    errors.append(f"SHA256 mismatch {rel}")

    integrity = {}
    if integrity_path.exists():
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
        if integrity.get("files_fail", 0) and not errors:
            # déjà listé via manifest
            pass

    ok = len(errors) == 0
    # Tolérance optionnelle (même règle que backup_full) — skipped_deleted exclus
    max_fail_ratio = float(os.environ.get("BACKUP_MAX_FAIL_RATIO", "0"))
    if not ok and max_fail_ratio > 0 and manifest.exists():
        fail_n = 0
        ok_n = 0
        with manifest.open(encoding="utf-8") as mf:
            for row in csv.DictReader(mf):
                status = str(row.get("ok", "")).strip().lower()
                if status == "true":
                    ok_n += 1
                elif status.startswith("skipped"):
                    continue
                else:
                    fail_n += 1
        total = ok_n + fail_n
        if total > 0 and (fail_n / total) <= max_fail_ratio:
            ok = True
            errors = [f"TOLERE {fail_n}/{total} echecs (<= {max_fail_ratio})"] + errors[:10]

    return {
        "ok": ok,
        "backup_dir": str(backup_dir),
        "files_checked": checked,
        "error_count": len(errors),
        "errors": errors[:50],
        "integrity": integrity,
    }


def verify_encrypted_archive(archive: Path) -> dict:
    from backup_crypto import decrypt_file

    with tempfile.TemporaryDirectory(prefix="crmbak_") as tmp:
        tmp_path = Path(tmp)
        tar_path = tmp_path / "backup.tar.gz"
        decrypt_file(archive, tar_path)
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with tarfile.open(tar_path, "r:gz") as tar:
            try:
                tar.extractall(extract_dir, filter="data")
            except TypeError:
                tar.extractall(extract_dir)
        # le tar contient un sous-dossier backups_full_*
        subs = [p for p in extract_dir.iterdir() if p.is_dir()]
        if not subs:
            return {"ok": False, "errors": ["archive vide après déchiffrement"]}
        report = verify_backup_dir(subs[0])
        report["encrypted_archive"] = str(archive)
        report["encrypted_sha256"] = sha256_file(archive)
        return report


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: verify_backup.py <backup_dir|file.crmbak>")
        return 2
    target = Path(sys.argv[1]).resolve()
    if target.is_dir():
        report = verify_backup_dir(target)
    elif target.suffix == ".crmbak" or target.name.endswith(".crmbak"):
        # charge passphrase depuis .env.backup si besoin
        envf = Path(__file__).resolve().parents[1] / ".env.backup"
        if envf.exists():
            for raw in envf.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v and k not in os.environ:
                    os.environ[k] = v
        report = verify_encrypted_archive(target)
    else:
        print("Cible non reconnue (dossier backups_full_* ou .crmbak)")
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
