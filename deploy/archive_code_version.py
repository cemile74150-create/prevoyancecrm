#!/usr/bin/env python3
"""
Archive une version de code LeoSoft (arbre Git publié) — local et/ou Infomaniak S3.

Préfixe S3 dédié : leosoft-versions/  (distinct de crm-backups/ et leosoft-code-backups/)
Dossier local    : C:\\LeoSoft\\Versions\\YYYY-MM-DD_<shortSHA>\\

Ne supprime jamais d'archives existantes.
N'inclut jamais .env, secrets, données clients, backups Mongo/PDF, node_modules.

Modes :
  --dry-run           planifie seulement (aucun fichier écrit, aucun upload)
  --local-only        construit + copie locale + vérifie checksum (défaut sûr)
  --upload-s3         local + Infomaniak leosoft-versions/ + vérif SHA-256 re-téléchargée
  --ensure            crée si absent ; si déjà présent, vérifie et complète S3 manquant
  --upload-existing   upload S3 d'une archive locale déjà valide (pas de rebuild)

PC hors ligne / disque Versions indisponible :
  --allow-s3-without-local  autorise succès S3 seul + marque pending_local_sync

Usage typique (depuis la racine du dépôt) :
  python deploy/archive_code_version.py --dry-run
  python deploy/archive_code_version.py --local-only
  python deploy/archive_code_version.py --upload-s3
  python deploy/archive_code_version.py --ensure --upload-s3
  python deploy/archive_code_version.py --upload-existing --version-id 2026-11-20_c81daf185154
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
REPO_ROOT = DEPLOY_DIR.parent
BACKEND = REPO_ROOT / "backend"
SCRIPTS = BACKEND / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

S3_PREFIX = "leosoft-versions/"
LOCAL_ROOT = Path(os.environ.get("LEOSOFT_VERSIONS_DIR", r"C:\LeoSoft\Versions"))
EXPECTED_FOLDER = "leosoft-saisie-preneur"
EXPECTED_REMOTE_SLUG = "github.com/cemile74150-create/prevoyancecrm"
FORBIDDEN_S3_TOKENS = ("crm-backups", ".crmbak")

# Chemins / noms exclus de l'archive (données, secrets, artefacts reconstructibles).
EXCLUDE_DIR_NAMES = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    ".git",
    "coverage",
    "htmlcov",
    "dist",
    ".turbo",
    ".next",
    "uploads",
    "generated",
}
EXCLUDE_PATH_PREFIXES = (
    "backend/backups/",
    "backend/code_backups/",
    "frontend/build/",
    "prevoyancecrm/",
)
SECRET_BASENAMES = {
    "credentials.json",
    "token.json",
    "secrets.json",
    "secret.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "data_crypto_keys",
}
# Bloc PEM réel (BEGIN + corps + END). Les littéraux de détection dans les
# scripts (ex. backup_code_source.py) ne matchent pas seuls.
_PEM_PRIVATE_KEY = re.compile(
    br"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
    br"[A-Za-z0-9+/=\r\n]{64,}"
    br"-----END (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----",
    re.DOTALL,
)


class ArchiveError(Exception):
    pass


def _git(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise ArchiveError(f"git {' '.join(args)} a échoué: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _remote_slug(url: str) -> str:
    text = url.strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    text = text.replace(":", "/")
    if text.startswith("git@"):
        text = text[4:]
    if "github.com/" in text:
        return "github.com/" + text.split("github.com/", 1)[1]
    return text


def load_dotenv_backup() -> None:
    path = BACKEND / ".env.backup"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_sensitive_rel(rel: str) -> bool:
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if not parts:
        return False
    lower_parts = [p.lower() for p in parts]
    name = lower_parts[-1]
    if any(p == ".env" or p.startswith(".env.") for p in lower_parts):
        return True
    if any(p in {"secrets", "credentials"} for p in lower_parts):
        return True
    if name in SECRET_BASENAMES:
        return True
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return True
    if ".env." in name or name.endswith(".env.list"):
        return True
    if "credential" in name or ("secret" in name and not name.endswith(".md")):
        return True
    if name.startswith(("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")):
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx", ".ppk", ".kdbx")):
        return True
    if name.endswith((".crmbak", ".log")):
        return True
    return False


def is_excluded_rel(rel: str) -> bool:
    norm = rel.replace("\\", "/").lstrip("./")
    if not norm or is_sensitive_rel(norm):
        return True
    parts = norm.split("/")
    lower_parts = [p.lower() for p in parts]
    if any(p in EXCLUDE_DIR_NAMES for p in lower_parts):
        return True
    for prefix in EXCLUDE_PATH_PREFIXES:
        if norm == prefix.rstrip("/") or norm.startswith(prefix):
            return True
    name = parts[-1]
    if name.endswith((".pyc", ".pyo", ".crmbak", ".log")):
        return True
    return False


def resolve_git_context(commit: str | None) -> dict:
    if REPO_ROOT.name != EXPECTED_FOLDER:
        raise ArchiveError(
            f"Refus : dossier attendu {EXPECTED_FOLDER}, trouvé {REPO_ROOT.name}."
        )
    marker = REPO_ROOT / ".leosoft-release-source"
    if not marker.exists():
        raise ArchiveError("Refus : .leosoft-release-source absent.")
    slug = _remote_slug(_git("remote", "get-url", "origin"))
    if slug.lower() != EXPECTED_REMOTE_SLUG:
        raise ArchiveError(f"Refus : remote inattendu ({slug}).")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        raise ArchiveError("Refus : HEAD détaché.")
    head = _git("rev-parse", "HEAD")
    sha = _git("rev-parse", commit) if commit else head
    dirty = bool(_git("status", "--porcelain"))
    short = sha[:12]
    day = datetime.now().astimezone().strftime("%Y-%m-%d")
    version_id = f"{day}_{short}"
    return {
        "branch": branch,
        "head": head,
        "commit": sha,
        "short_sha": short,
        "dirty_worktree": dirty,
        "version_id": version_id,
        "remote": slug,
    }


def list_tree_paths(sha: str) -> list[str]:
    text = _git("ls-tree", "-r", "--name-only", sha)
    return [line.replace("\\", "/") for line in text.splitlines() if line.strip()]


def filter_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    excluded: list[str] = []
    for path in paths:
        if is_excluded_rel(path):
            excluded.append(path)
        else:
            kept.append(path)
    return kept, excluded


def build_tar_gz(sha: str, kept: set[str], archive_prefix: str, dest: Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="leosoft-ver-") as tmp:
        raw_tar = Path(tmp) / "source.tar"
        proc = subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                f"--prefix={archive_prefix}",
                f"--output={str(raw_tar)}",
                sha,
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise ArchiveError(f"git archive a échoué: {proc.stderr.strip()}")

        members_out: list[str] = []
        with tarfile.open(raw_tar, "r") as tin, tarfile.open(dest, "w:gz") as tout:
            for member in tin.getmembers():
                name = member.name.replace("\\", "/")
                if name.startswith(archive_prefix):
                    rel = name[len(archive_prefix) :]
                else:
                    rel = name
                rel = rel.lstrip("/")
                if rel and (is_excluded_rel(rel) or rel not in kept):
                    continue
                if member.isreg() or member.isfile():
                    extracted = tin.extractfile(member)
                    if extracted is None:
                        raise ArchiveError(f"Membre illisible: {name}")
                    data = extracted.read()
                    if _PEM_PRIVATE_KEY.search(data):
                        raise ArchiveError(f"Clé privée détectée dans {rel}")
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data)
                    info.mtime = member.mtime
                    info.mode = member.mode
                    info.type = tarfile.REGTYPE
                    tout.addfile(info, __import__("io").BytesIO(data))
                    members_out.append(rel)
                elif member.isdir():
                    # Ne garder les dossiers que s'ils contiennent un fichier conservé.
                    if rel and not any(k.startswith(rel.rstrip("/") + "/") for k in kept):
                        if rel not in kept:
                            continue
                    tout.addfile(member)
        return members_out


def assert_archive_clean(archive: Path, kept: set[str]) -> list[str]:
    found: list[str] = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not (member.isreg() or member.isfile()):
                continue
            name = member.name.replace("\\", "/")
            # strip first path component (version prefix)
            parts = name.split("/", 1)
            rel = parts[1] if len(parts) > 1 else ""
            if not rel:
                continue
            if is_excluded_rel(rel) or is_sensitive_rel(rel):
                raise ArchiveError(f"Fichier interdit dans l'archive: {rel}")
            if rel not in kept:
                raise ArchiveError(f"Fichier hors liste dans l'archive: {rel}")
            extracted = tar.extractfile(member)
            if extracted is not None:
                data = extracted.read()
                if _PEM_PRIVATE_KEY.search(data):
                    raise ArchiveError(f"Clé privée dans l'archive: {rel}")
            found.append(rel)
    missing = sorted(kept - set(found))
    if missing:
        # Dossiers vides / fichiers exclus après coup — tolérer seulement si vraiment exclus
        real_missing = [m for m in missing if not is_excluded_rel(m)]
        if real_missing:
            sample = ", ".join(real_missing[:8])
            raise ArchiveError(f"Fichiers manquants dans l'archive ({len(real_missing)}): {sample}")
    return found


def write_metadata(
    dest_dir: Path,
    ctx: dict,
    *,
    archive_name: str,
    checksum: str,
    size: int,
    members: int,
    excluded: int,
    railway_deployment_id: str | None,
    s3_key: str | None,
) -> Path:
    meta = {
        "scheme": "leosoft-version-v1",
        "version_id": ctx["version_id"],
        "version": ctx["version_id"],
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "github_commit": ctx["commit"],
        "github_short_sha": ctx["short_sha"],
        "github_branch": ctx["branch"],
        "github_head_at_archive": ctx["head"],
        "dirty_worktree": ctx["dirty_worktree"],
        "remote": ctx["remote"],
        "railway_deployment_id": railway_deployment_id or None,
        "archive_filename": archive_name,
        "archive_sha256": checksum,
        "archive_size_bytes": size,
        "member_count": members,
        "excluded_count": excluded,
        "s3_prefix": S3_PREFIX,
        "s3_key": s3_key,
        "local_dir": str(dest_dir),
        "includes": [
            "frontend/ (sources + lockfiles, sans node_modules ni build)",
            "backend/ (sources + requirements, sans backups/.env)",
            "deploy/ (scripts et docs non secrets)",
            "Dockerfile / configs non secrètes suivies par Git",
            ".leosoft-release-source",
        ],
        "excludes": [
            ".env* et secrets",
            "node_modules / __pycache__ / frontend/build",
            "backend/backups / *.crmbak / uploads / données clients",
            "prevoyancecrm/ (ancienne copie)",
        ],
        "notes": [
            "Archive = arbre Git du commit indiqué (pas les fichiers non commités).",
            "Ne jamais restaurer Mongo pour un rollback code.",
            "Aucune suppression automatique d'archives anciennes.",
        ],
    }
    path = dest_dir / "version.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dest_dir / "SHA256SUMS.txt").write_text(
        f"{checksum}  {archive_name}\n", encoding="utf-8"
    )
    return path


def copy_verified(src: Path, dest: Path, expected_sha: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    if not dest.is_file():
        raise ArchiveError(f"Copie locale manquante: {dest}")
    got = sha256_file(dest)
    if got != expected_sha:
        raise ArchiveError(f"Checksum local incohérent: {got} != {expected_sha}")
    if dest.stat().st_size != src.stat().st_size:
        raise ArchiveError("Taille locale incohérente après copie.")


def _s3_object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception as exc:
        err = getattr(exc, "response", None) or {}
        code = str((err.get("Error") or {}).get("Code", ""))
        http = (err.get("ResponseMetadata") or {}).get("HTTPStatusCode")
        if http == 404 or code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise ArchiveError(f"Erreur S3 head_object: {exc}") from exc


def upload_s3(
    local_archive: Path,
    key: str,
    expected_sha: str,
    *,
    skip_if_present: bool = False,
) -> dict:
    if not key.startswith(S3_PREFIX):
        raise ArchiveError(f"Refus : clé S3 hors préfixe {S3_PREFIX}")
    if any(tok in key for tok in FORBIDDEN_S3_TOKENS):
        raise ArchiveError("Refus : clé S3 ressemble à un backup CRM.")
    from backup_remote import configured, _client  # type: ignore

    if not configured():
        raise ArchiveError("S3 non configuré (BACKUP_S3_* dans backend/.env.backup).")
    client, bucket, _crm_prefix = _client()
    # Marqueur de dossier virtuel (best-effort) — n'efface / ne modifie aucun autre préfixe
    try:
        client.put_object(
            Bucket=bucket,
            Key=S3_PREFIX,
            Body=b"",
            ContentType="application/x-directory",
        )
    except Exception:
        pass

    already = _s3_object_exists(client, bucket, key)
    if already and not skip_if_present:
        raise ArchiveError(f"Objet S3 déjà présent (pas d'écrasement): {key}")

    if not already:
        try:
            client.upload_file(
                str(local_archive),
                bucket,
                key,
                ExtraArgs={
                    "ContentType": "application/gzip",
                    "Metadata": {"sha256": expected_sha, "source": "leosoft-versions"},
                },
            )
        except Exception:
            # Certains backends rejettent Metadata — retry sans métadonnées
            client.upload_file(
                str(local_archive),
                bucket,
                key,
                ExtraArgs={"ContentType": "application/gzip"},
            )

    head = client.head_object(Bucket=bucket, Key=key)
    remote_size = int(head.get("ContentLength") or 0)
    local_size = local_archive.stat().st_size
    if remote_size != local_size:
        raise ArchiveError(f"Taille S3 incohérente local={local_size} remote={remote_size}")
    meta_sha = (head.get("Metadata") or {}).get("sha256")
    if meta_sha and meta_sha != expected_sha:
        raise ArchiveError("Métadonnée sha256 S3 incohérente.")

    # Preuve d'intégrité : re-téléchargement + SHA-256 (jamais d'écrasement de l'objet source)
    with tempfile.TemporaryDirectory(prefix="leosoft-s3-verify-") as tmp:
        verify_path = Path(tmp) / local_archive.name
        client.download_file(bucket, key, str(verify_path))
        got = sha256_file(verify_path)
        if got != expected_sha:
            raise ArchiveError(
                f"SHA-256 S3 incohérent après téléchargement: {got} != {expected_sha}"
            )
        if verify_path.stat().st_size != local_size:
            raise ArchiveError("Taille S3 incohérente après re-téléchargement.")

    return {
        "bucket": bucket,
        "key": key,
        "uri": f"s3://{bucket}/{key}",
        "remote_size": remote_size,
        "sha256_verified": expected_sha,
        "already_present": already,
        "verified": True,
    }


def write_deploy_record(
    dest_dir: Path,
    *,
    phase: str,
    railway_deployment_id: str | None,
    commit: str,
    version_id: str,
) -> Path:
    records_path = dest_dir / "deploy-records.jsonl"
    entry = {
        "phase": phase,
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "version_id": version_id,
        "github_commit": commit,
        "railway_deployment_id": railway_deployment_id or None,
    }
    with records_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return records_path


def load_existing_version(version_id: str) -> tuple[Path, dict, Path, str]:
    dest_dir = LOCAL_ROOT / version_id
    meta_path = dest_dir / "version.json"
    if not meta_path.is_file():
        raise ArchiveError(f"version.json introuvable: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    archive_name = meta.get("archive_filename") or f"leosoft-{version_id}.tar.gz"
    archive = dest_dir / archive_name
    if not archive.is_file():
        raise ArchiveError(f"Archive locale manquante: {archive}")
    expected = (meta.get("archive_sha256") or "").strip().lower()
    if not expected:
        raise ArchiveError("archive_sha256 manquant dans version.json")
    got = sha256_file(archive)
    if got != expected:
        raise ArchiveError(f"Checksum local incohérent: {got} != {expected}")
    sums = dest_dir / "SHA256SUMS.txt"
    if sums.is_file():
        line = sums.read_text(encoding="utf-8").strip().splitlines()[0]
        listed = line.split()[0].strip().lower()
        if listed != expected:
            raise ArchiveError("SHA256SUMS.txt incohérent avec version.json")
    return dest_dir, meta, archive, expected


def update_metadata_s3(meta_path: Path, meta: dict, s3_key: str, s3_info: dict) -> None:
    meta["s3_key"] = s3_key
    meta["s3_prefix"] = S3_PREFIX
    meta["s3_uri"] = s3_info.get("uri")
    meta["s3_sha256_verified"] = s3_info.get("sha256_verified")
    meta["s3_verified_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def try_write_local_from_tmp(
    tmp_archive: Path,
    version_dir: Path,
    archive_name: str,
    checksum: str,
    *,
    allow_s3_without_local: bool,
) -> tuple[Path | None, str | None]:
    """Retourne (final_archive, local_error). final_archive None si local impossible."""
    try:
        if version_dir.exists() and any(version_dir.iterdir()):
            raise ArchiveError(
                f"Dossier version déjà présent (pas d'écrasement): {version_dir}"
            )
        version_dir.mkdir(parents=True, exist_ok=False)
        final_archive = version_dir / archive_name
        copy_verified(tmp_archive, final_archive, checksum)
        return final_archive, None
    except Exception as exc:
        if allow_s3_without_local:
            return None, str(exc)
        raise


def plan_report(ctx: dict, kept: list[str], excluded: list[str]) -> dict:
    return {
        "mode": "dry-run",
        "version_id": ctx["version_id"],
        "commit": ctx["commit"],
        "branch": ctx["branch"],
        "dirty_worktree": ctx["dirty_worktree"],
        "kept_files": len(kept),
        "excluded_files": len(excluded),
        "local_target": str(LOCAL_ROOT / ctx["version_id"]),
        "s3_prefix": S3_PREFIX,
        "s3_key_would_be": f"{S3_PREFIX}{ctx['version_id']}/leosoft-{ctx['version_id']}.tar.gz",
        "sample_kept": kept[:12],
        "sample_excluded_sensitive": [p for p in excluded if is_sensitive_rel(p)][:12],
        "will_delete_old_archives": False,
        "will_touch_production": False,
        "will_restore_mongo": False,
    }


def run_upload_existing(
    *,
    version_id: str,
    railway_deployment_id: str | None,
    phase: str | None,
) -> int:
    load_dotenv_backup()
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    dest_dir, meta, archive, checksum = load_existing_version(version_id)
    archive_name = archive.name
    s3_key = f"{S3_PREFIX}{version_id}/{archive_name}"
    s3_info = upload_s3(
        archive,
        s3_key,
        checksum,
        skip_if_present=True,
    )
    update_metadata_s3(dest_dir / "version.json", meta, s3_key, s3_info)
    if railway_deployment_id and not meta.get("railway_deployment_id"):
        meta["railway_deployment_id"] = railway_deployment_id
        (dest_dir / "version.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    records = None
    if phase:
        records = write_deploy_record(
            dest_dir,
            phase=phase,
            railway_deployment_id=railway_deployment_id,
            commit=str(meta.get("github_commit") or ""),
            version_id=version_id,
        )
    # Sidecar S3 metadata (jamais d'écrasement du tar)
    meta_key = f"{S3_PREFIX}{version_id}/version.json"
    from backup_remote import configured, _client  # type: ignore

    if configured():
        client, bucket, _ = _client()
        if not _s3_object_exists(client, bucket, meta_key):
            body = (dest_dir / "version.json").read_bytes()
            client.put_object(
                Bucket=bucket,
                Key=meta_key,
                Body=body,
                ContentType="application/json",
            )
    result = {
        "status": "ok",
        "mode": "upload-existing",
        "version_id": version_id,
        "local_dir": str(dest_dir),
        "archive": str(archive),
        "archive_sha256": checksum,
        "s3": s3_info,
        "uploaded": True,
        "deploy_records": str(records) if records else None,
        "deleted_old_archives": False,
        "pending_local_sync": False,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def run_ensure_or_build(
    *,
    dry_run: bool,
    upload_s3_flag: bool,
    ensure: bool,
    commit: str | None,
    railway_deployment_id: str | None,
    phase: str | None,
    allow_s3_without_local: bool,
) -> int:
    ctx = resolve_git_context(commit)
    paths = list_tree_paths(ctx["commit"])
    kept, excluded = filter_paths(paths)
    if not kept:
        raise ArchiveError("Aucun fichier à archiver.")

    version_dir = LOCAL_ROOT / ctx["version_id"]
    archive_name = f"leosoft-{ctx['version_id']}.tar.gz"
    archive_prefix = f"leosoft-{ctx['short_sha']}/"
    s3_key = f"{S3_PREFIX}{ctx['version_id']}/{archive_name}"

    # --ensure : archive locale déjà valide → compléter S3 / records sans rebuild
    if ensure and not dry_run and (version_dir / "version.json").is_file():
        dest_dir, meta, archive, checksum = load_existing_version(ctx["version_id"])
        s3_info = None
        if upload_s3_flag:
            load_dotenv_backup()
            os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
            s3_info = upload_s3(archive, s3_key, checksum, skip_if_present=True)
            update_metadata_s3(dest_dir / "version.json", meta, s3_key, s3_info)
        if phase:
            write_deploy_record(
                dest_dir,
                phase=phase,
                railway_deployment_id=railway_deployment_id,
                commit=ctx["commit"],
                version_id=ctx["version_id"],
            )
        result = {
            "status": "ok",
            "mode": "ensure-existing",
            "version_id": ctx["version_id"],
            "commit": ctx["commit"],
            "branch": ctx["branch"],
            "local_dir": str(dest_dir),
            "archive": str(archive),
            "archive_sha256": checksum,
            "s3": s3_info,
            "uploaded": bool(s3_info),
            "rebuilt": False,
            "deleted_old_archives": False,
            "pending_local_sync": False,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    with tempfile.TemporaryDirectory(prefix="leosoft-ver-build-") as tmp:
        tmp_archive = Path(tmp) / archive_name
        members = build_tar_gz(ctx["commit"], set(kept), archive_prefix, tmp_archive)
        assert_archive_clean(tmp_archive, set(kept))
        checksum = sha256_file(tmp_archive)
        size = tmp_archive.stat().st_size

        if dry_run:
            report = plan_report(ctx, kept, excluded)
            report.update(
                {
                    "built_tmp_archive": True,
                    "archive_sha256": checksum,
                    "archive_size_bytes": size,
                    "member_count": len(members),
                    "discarded_tmp": True,
                }
            )
            print(json.dumps(report, indent=2, ensure_ascii=False))
            print("DRY-RUN OK — archive temporaire vérifiée puis jetée.")
            return 0

        if not dry_run and version_dir.exists() and any(version_dir.iterdir()) and not ensure:
            raise ArchiveError(
                f"Dossier version déjà présent (pas d'écrasement): {version_dir}"
            )

        final_archive, local_error = try_write_local_from_tmp(
            tmp_archive,
            version_dir,
            archive_name,
            checksum,
            allow_s3_without_local=allow_s3_without_local and upload_s3_flag,
        )
        pending_local_sync = final_archive is None
        s3_info = None
        meta_path = None

        if upload_s3_flag:
            load_dotenv_backup()
            os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
            source_for_s3 = final_archive if final_archive is not None else tmp_archive
            s3_info = upload_s3(source_for_s3, s3_key, checksum, skip_if_present=False)
        elif pending_local_sync:
            raise ArchiveError(
                f"Écriture locale impossible et S3 non demandé: {local_error}"
            )

        if final_archive is not None:
            meta_path = write_metadata(
                version_dir,
                ctx,
                archive_name=archive_name,
                checksum=checksum,
                size=size,
                members=len(members),
                excluded=len(excluded),
                railway_deployment_id=railway_deployment_id,
                s3_key=s3_key if s3_info else None,
            )
            if s3_info:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                update_metadata_s3(meta_path, meta, s3_key, s3_info)
            if phase:
                write_deploy_record(
                    version_dir,
                    phase=phase,
                    railway_deployment_id=railway_deployment_id,
                    commit=ctx["commit"],
                    version_id=ctx["version_id"],
                )
            if not final_archive.is_file():
                raise ArchiveError("Échec : archive locale manquante après écriture.")
            if sha256_file(final_archive) != checksum:
                raise ArchiveError("Échec : checksum local après métadonnées.")
        else:
            # S3 seul : consignes de resync local
            print(
                "ATTENTION: archive S3 OK mais copie locale absente "
                f"(pending_local_sync). Cause: {local_error}. "
                "Quand le PC Versions est de nouveau disponible: "
                "retélécharger depuis S3 (préfixe leosoft-versions/) "
                f"vers C:\\LeoSoft\\Versions\\{ctx['version_id']}\\ "
                "puis vérifier SHA-256 (voir deploy/VERSIONS.md § Sync local).",
                file=sys.stderr,
            )

        if upload_s3_flag and not s3_info:
            raise ArchiveError("Échec : upload S3 requis mais non réalisé.")
        if not upload_s3_flag and final_archive is None:
            raise ArchiveError("Échec : ni local ni S3.")

    result = {
        "status": "ok",
        "mode": "build",
        "version_id": ctx["version_id"],
        "commit": ctx["commit"],
        "branch": ctx["branch"],
        "dirty_worktree": ctx["dirty_worktree"],
        "local_dir": str(version_dir) if final_archive else None,
        "archive": str(final_archive) if final_archive else None,
        "archive_sha256": checksum,
        "archive_size_bytes": size,
        "member_count": len(members),
        "excluded_count": len(excluded),
        "metadata": str(meta_path) if meta_path else None,
        "s3": s3_info,
        "uploaded": bool(s3_info),
        "deleted_old_archives": False,
        "pending_local_sync": pending_local_sync,
        "local_error": local_error,
        "s3_key": s3_key if s3_info else None,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def run(
    *,
    dry_run: bool,
    local_only: bool,
    upload_s3_flag: bool,
    ensure: bool,
    upload_existing: bool,
    version_id: str | None,
    commit: str | None,
    railway_deployment_id: str | None,
    phase: str | None,
    allow_s3_without_local: bool,
) -> int:
    _ = local_only  # mode explicite côté CLI ; logique portée par upload_s3_flag
    if upload_existing:
        if not version_id:
            # Déduire depuis HEAD si non fourni
            ctx = resolve_git_context(commit)
            version_id = ctx["version_id"]
        return run_upload_existing(
            version_id=version_id,
            railway_deployment_id=railway_deployment_id,
            phase=phase,
        )
    return run_ensure_or_build(
        dry_run=dry_run,
        upload_s3_flag=upload_s3_flag,
        ensure=ensure,
        commit=commit,
        railway_deployment_id=railway_deployment_id,
        phase=phase,
        allow_s3_without_local=allow_s3_without_local,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive une version code LeoSoft")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Planifie / construit en temp puis jette — aucun écriture durable",
    )
    mode.add_argument(
        "--local-only",
        action="store_true",
        help="Écrit sous C:\\LeoSoft\\Versions uniquement (pas S3)",
    )
    mode.add_argument(
        "--upload-s3",
        action="store_true",
        help="Local + upload Infomaniak préfixe leosoft-versions/ (GO requis)",
    )
    mode.add_argument(
        "--upload-existing",
        action="store_true",
        help="Upload S3 d'une archive locale déjà présente (vérif SHA puis transfer)",
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="Ne pas écraser : réutilise l'archive locale si valide, complète S3",
    )
    parser.add_argument(
        "--allow-s3-without-local",
        action="store_true",
        help="Si C:\\LeoSoft\\Versions indisponible, réussir via S3 seul (resync plus tard)",
    )
    parser.add_argument("--commit", default=None, help="SHA Git à archiver (défaut: HEAD)")
    parser.add_argument(
        "--version-id",
        default=None,
        help="Identifiant version (pour --upload-existing)",
    )
    parser.add_argument(
        "--railway-deployment-id",
        default=None,
        help="ID déploiement Railway à consigneren métadonnées (optionnel)",
    )
    parser.add_argument(
        "--phase",
        default=None,
        choices=["before-deploy", "after-deploy", "manual"],
        help="Phase consignées dans deploy-records.jsonl",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Tests unitaires d'exclusion (sans I/O réseau)",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        assert is_sensitive_rel("backend/.env")
        assert is_sensitive_rel("backend/.env.backup")
        assert is_excluded_rel("frontend/node_modules/x/y.js")
        assert is_excluded_rel("backend/backups/x.crmbak")
        assert not is_excluded_rel("frontend/src/App.js")
        assert not is_excluded_rel("deploy/leosoft-up.ps1")
        assert S3_PREFIX == "leosoft-versions/"
        assert "crm-backups" not in S3_PREFIX
        print("SELF-TEST OK")
        return 0

    if not (
        args.dry_run
        or args.local_only
        or args.upload_s3
        or args.upload_existing
    ):
        # Défaut sûr : dry-run
        args.dry_run = True

    try:
        return run(
            dry_run=args.dry_run,
            local_only=args.local_only,
            upload_s3_flag=args.upload_s3 or args.upload_existing,
            ensure=args.ensure,
            upload_existing=args.upload_existing,
            version_id=args.version_id,
            commit=args.commit,
            railway_deployment_id=args.railway_deployment_id,
            phase=args.phase,
            allow_s3_without_local=args.allow_s3_without_local,
        )
    except ArchiveError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
