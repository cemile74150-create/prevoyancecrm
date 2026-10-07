"""
Archive le HEAD courant du dépôt de production LeoSoft et l'envoie sur Infomaniak.

Destination unique : leosoft-code-backups/<fichier>.
N'appelle pas upload_backup() (préfixe crm-backups/).
N'efface aucune archive existante, ne prune pas, ne touche pas aux .crmbak ni aux .env.
Le préfixe BACKUP_S3_PREFIX de la sauvegarde CRM n'est pas utilisé.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
SCRIPT_REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPTS))

from backup_remote import _client, configured  # noqa: E402

GIT = r"C:\Program Files\Git\cmd\git.exe"
CODE_REPO = Path(
    os.environ.get(
        "LEOSOFT_CODE_REPO",
        r"C:\LeoSoftDeploy\leosoft-definitif-mail-note",
    )
)
PROD_BRANCH = os.environ.get("LEOSOFT_CODE_BRANCH", "definitif-mail-note-sans-commit")
FROZEN_SHA = "b160a568198381ce2d9368e8e13d83296f45a5a3"
EXPECTED_REMOTE = "github.com/cemile74150-create/prevoyancecrm"
S3_PREFIX = "leosoft-code-backups/"
LOG_PATH = BACKEND / "backups" / "backup_code_task.log"
MEMBERS_PATH = BACKEND / "backups" / "backup_code_last_members.txt"
ARCHIVE_PREFIX = "leosoft-code/"

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
    "railway.toml",
    "railway.json",
    "env.example",
    "env.backup.example",
}

PRIVATE_KEY_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN OPENSSH PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"-----BEGIN DSA PRIVATE KEY-----",
    b"-----BEGIN ENCRYPTED PRIVATE KEY-----",
)

_SECRET_ASSIGN = re.compile(
    r"(?i)(secret|password|passphrase|token|access_key)\s*=\s*\S{6,}"
)
_EMBEDDED_AUTH = re.compile(br"(?i)[\"']Authorization:\s+\S+")
_EMBEDDED_WEBHOOK = re.compile(br"(?i)WEBHOOK_CRON_SECRET\s*=\s*[\"'][^\"']+[\"']")


class Abort(Exception):
    def __init__(self, code: str, exit_code: int = 2) -> None:
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def load_dotenv_file(path: Path) -> None:
    """Même lecture que les scripts de backup : .env.backup, sans écraser l'environnement."""
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


def log_line(message: str) -> None:
    if _SECRET_ASSIGN.search(message):
        message = "REDACTED_LOG_LINE"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def _split(path: str) -> tuple[str, list[str]]:
    norm = path.replace("\\", "/").lstrip("./")
    if norm.startswith(ARCHIVE_PREFIX):
        norm = norm[len(ARCHIVE_PREFIX) :]
    elif norm.rstrip("/") == ARCHIVE_PREFIX.rstrip("/"):
        return "", []
    norm = norm.strip("/")
    if not norm:
        return "", []
    return norm, norm.split("/")


def is_sensitive_rel(path: str) -> bool:
    """Nom de fichier ou dossier d'identifiants. Ne lit pas le contenu."""
    _norm, parts = _split(path)
    if not parts:
        return False
    lower_parts = [part.lower() for part in parts]
    lower_name = lower_parts[-1]
    if any(
        part in {".env", "secrets", "credentials"} or part.startswith(".env.")
        for part in lower_parts
    ):
        return True
    if lower_name in SECRET_BASENAMES or lower_name.startswith("."):
        # .gitignore and similar dotfiles that are not secrets stay allowed,
        # except the credential names listed above and .env* handled below.
        if lower_name not in SECRET_BASENAMES and not _sensitive_basename(lower_name):
            return False
    return _sensitive_basename(lower_name)


def _sensitive_basename(lower_name: str) -> bool:
    if lower_name in SECRET_BASENAMES:
        return True
    if lower_name == ".env" or lower_name.startswith(".env.") or lower_name.endswith(".env"):
        return True
    if ".env." in lower_name or lower_name.endswith(".env.list"):
        return True
    if "credential" in lower_name or "secret" in lower_name:
        return True
    if lower_name.startswith(("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")):
        return True
    if lower_name.endswith((".pem", ".key", ".p12", ".pfx", ".ppk", ".kdbx")):
        return True
    if "token" in lower_name and lower_name.endswith((".json", ".txt", ".yml", ".yaml", ".env")):
        return True
    return False


def is_excluded(path: str) -> bool:
    """Fichiers omis de l'archive. *.log est omis, ce n'est pas un secret."""
    norm, parts = _split(path)
    if not parts:
        return False
    if is_sensitive_rel(norm):
        return True
    name = parts[-1]
    lower_name = name.lower()
    lower_parts = [part.lower() for part in parts]
    lower_norm = "/".join(lower_parts)

    if lower_name.endswith(".log"):
        return True
    if any(part in {"node_modules", "__pycache__", ".pytest_cache"} for part in lower_parts):
        return True
    if lower_norm == "frontend/build" or lower_norm.startswith("frontend/build/"):
        return True
    if lower_norm == "backend/backups" or lower_norm.startswith("backend/backups/"):
        return True
    if lower_name.endswith(".crmbak"):
        return True
    return False


def is_hard_abort(path: str) -> bool:
    """Arrêt sans upload si un fichier sensible ou *.crmbak reste dans l'archive."""
    norm, parts = _split(path)
    if not parts:
        return False
    if is_sensitive_rel(norm):
        return True
    return parts[-1].lower().endswith(".crmbak")


def git_out(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        [GIT, "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise Abort("GIT_FAILED", 2)
    return proc.stdout


def remote_slug(url: str) -> str:
    text = url.strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    text = text.replace(":", "/")
    if text.startswith("git@"):
        text = text[4:]
    if "github.com/" in text:
        return "github.com/" + text.split("github.com/", 1)[1]
    return text


def resolve_commit(repo: Path) -> tuple[str, str, str, bool]:
    toplevel = Path(git_out(repo, ["rev-parse", "--show-toplevel"]).strip()).resolve()
    if toplevel == SCRIPT_REPO.resolve():
        raise Abort("ABORT_DIRTY_WORKDIR", 2)
    slug = remote_slug(git_out(repo, ["remote", "get-url", "origin"]))
    if slug.lower() != EXPECTED_REMOTE:
        raise Abort("ABORT_UNEXPECTED_REMOTE", 2)
    branch = git_out(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    head = git_out(repo, ["rev-parse", "HEAD"]).strip()
    prod_tip = git_out(repo, ["rev-parse", f"refs/heads/{PROD_BRANCH}"]).strip()
    sha = head if branch == PROD_BRANCH else prod_tip
    git_out(repo, ["rev-parse", "--verify", f"{sha}^{{commit}}"])
    if sha == FROZEN_SHA or sha.startswith("b160a5681983"):
        raise Abort("ABORT_FROZEN_SHA", 2)
    dirty = bool(git_out(repo, ["status", "--porcelain"]).strip())
    return branch, head, sha, dirty


def list_tree_paths(repo: Path, sha: str) -> list[str]:
    text = git_out(repo, ["ls-tree", "-r", "--name-only", sha])
    return [line.strip().replace("\\", "/") for line in text.splitlines() if line.strip()]


def assert_s3_key(key: str) -> None:
    if not key.startswith(S3_PREFIX):
        raise Abort("ABORT_KEY_PREFIX", 2)
    if "crm-backups" in key or key.endswith(".crmbak"):
        raise Abort("ABORT_KEY_CRM_BACKUPS", 2)
    if ".." in key.split("/") or key.endswith("/"):
        raise Abort("ABORT_KEY_SHAPE", 2)


def clone_member(member: tarfile.TarInfo) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=member.name)
    info.size = member.size
    info.mtime = member.mtime
    info.mode = member.mode
    info.type = member.type
    info.uid = member.uid
    info.gid = member.gid
    info.uname = member.uname or ""
    info.gname = member.gname or ""
    info.linkname = member.linkname or ""
    info.pax_headers = dict(getattr(member, "pax_headers", {}) or {})
    return info


def build_archive(src_tar: Path, dest_gz: Path, kept: set[str], manifest: str, when: datetime) -> None:
    with tarfile.open(src_tar, "r") as tin, tarfile.open(dest_gz, "w:gz") as tout:
        for member in tin.getmembers():
            rel = _split(member.name)[0]
            if rel == "":
                tout.addfile(clone_member(member))
                continue
            if is_excluded(rel) or rel not in kept:
                if member.isdir() and any(path.startswith(rel + "/") for path in kept):
                    if not is_excluded(rel):
                        tout.addfile(clone_member(member))
                continue
            info = clone_member(member)
            if member.isreg() or member.isfile():
                extracted = tin.extractfile(member)
                if extracted is None:
                    raise Abort("ARCHIVE_MEMBER_UNREADABLE", 2)
                tout.addfile(info, extracted)
            else:
                tout.addfile(info)

        payload = manifest.encode("utf-8")
        info = tarfile.TarInfo(name=f"{ARCHIVE_PREFIX}CODE-SOURCE.txt")
        info.size = len(payload)
        info.mtime = int(when.timestamp())
        info.mode = 0o644
        info.type = tarfile.REGTYPE
        tout.addfile(info, io.BytesIO(payload))


def regular_rels(gz_path: Path) -> list[str]:
    rels: list[str] = []
    with tarfile.open(gz_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not (member.isreg() or member.isfile()):
                continue
            rels.append(_split(member.name)[0])
    return rels


def forbidden_members(gz_path: Path) -> list[str]:
    bad: list[str] = []
    with tarfile.open(gz_path, "r:gz") as tar:
        for member in tar.getmembers():
            rel = _split(member.name)[0]
            if not rel or rel == "CODE-SOURCE.txt":
                continue
            if is_excluded(rel) or is_hard_abort(rel):
                bad.append(rel)
    return bad


def _has_embedded_credential(data: bytes) -> bool:
    return bool(_EMBEDDED_AUTH.search(data) or _EMBEDDED_WEBHOOK.search(data))


def embedded_credential_rels(tar_path: Path, gzipped: bool = False) -> list[str]:
    found: list[str] = []
    mode = "r:gz" if gzipped else "r"
    with tarfile.open(tar_path, mode) as tar:
        for member in tar.getmembers():
            if not (member.isreg() or member.isfile()):
                continue
            rel = _split(member.name)[0]
            if not rel or rel == "CODE-SOURCE.txt":
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            if _has_embedded_credential(extracted.read()):
                found.append(rel)
    return found


def private_key_members(gz_path: Path) -> list[str]:
    found: list[str] = []
    with tarfile.open(gz_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not (member.isreg() or member.isfile()):
                continue
            rel = _split(member.name)[0]
            if not rel or rel == "CODE-SOURCE.txt":
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            data = extracted.read()
            if any(marker in data for marker in PRIVATE_KEY_MARKERS):
                found.append(rel)
    return found


def list_prefix_count(client, bucket: str) -> int:
    count = 0
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": S3_PREFIX, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        count += len(resp.get("Contents") or [])
        if not resp.get("IsTruncated"):
            return count
        token = resp.get("NextContinuationToken")
        if not token:
            return count


def s3_status(exc: Exception) -> str:
    response = getattr(exc, "response", None) or {}
    meta = response.get("ResponseMetadata") or {}
    err = response.get("Error") or {}
    http = meta.get("HTTPStatusCode", "")
    code = err.get("Code", type(exc).__name__)
    return f"http={http} code={code}"


def remote_is_absent(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        status = s3_status(exc)
        if any(token in status for token in ("code=404", "code=NoSuchKey", "code=NotFound", "http=404")):
            return True
        raise Abort(f"S3_ERROR {status}", 4) from exc
    return False


def discard_new_archive(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def write_member_list(rels: list[str]) -> None:
    MEMBERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    names = sorted(rel for rel in rels if rel and rel != "CODE-SOURCE.txt")
    MEMBERS_PATH.write_text("\n".join(names) + ("\n" if names else ""), encoding="utf-8")


def validate_archive(gz_path: Path, kept: set[str]) -> list[str]:
    bad = forbidden_members(gz_path)
    rels = regular_rels(gz_path)
    keys = private_key_members(gz_path)
    embedded = embedded_credential_rels(gz_path, gzipped=True)
    if bad or keys or embedded or any(is_excluded(rel) or is_hard_abort(rel) for rel in rels):
        discard_new_archive(gz_path)
        raise Abort("ABORT_FORBIDDEN_BEFORE_UPLOAD", 3)
    if any(rel.lower().endswith(".log") for rel in rels):
        discard_new_archive(gz_path)
        raise Abort("ABORT_LOG_IN_ARCHIVE", 3)
    extra = [rel for rel in rels if rel not in kept]
    missing = [path for path in kept if path not in set(rels)]
    if missing or set(extra) != {"CODE-SOURCE.txt"}:
        discard_new_archive(gz_path)
        raise Abort("ABORT_MEMBER_MISMATCH", 3)
    write_member_list(rels)
    return rels


def upload_archive(final_path: Path, key: str, sha: str, rels: list[str], excluded_count: int) -> dict:
    assert_s3_key(key)
    if FROZEN_SHA[:12] in final_path.name:
        raise Abort("ABORT_FROZEN_NAME", 2)
    if sha[:12] not in final_path.name:
        raise Abort("ABORT_NAME_COMMIT", 2)
    bad_final = forbidden_members(final_path)
    rels_final = regular_rels(final_path)
    if (
        bad_final
        or private_key_members(final_path)
        or embedded_credential_rels(final_path, gzipped=True)
        or any(rel.lower().endswith(".log") for rel in rels_final)
    ):
        raise Abort("ABORT_FORBIDDEN_FINAL", 3)
    if any(is_hard_abort(rel) for rel in rels_final):
        raise Abort("ABORT_ENV_OR_CRMBAK_FINAL", 3)

    client, bucket, ignored_prefix = _client()
    del ignored_prefix
    assert_s3_key(key)
    if not remote_is_absent(client, bucket, key):
        raise Abort("ABORT_REMOTE_EXISTS", 4)

    local_size = final_path.stat().st_size
    try:
        client.upload_file(
            str(final_path),
            bucket,
            key,
            ExtraArgs={"ContentType": "application/gzip"},
        )
        head = client.head_object(Bucket=bucket, Key=key)
    except Abort:
        raise
    except Exception as exc:
        raise Abort(f"S3_ERROR {s3_status(exc)}", 4) from exc

    http = int((head.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
    remote_size = int(head.get("ContentLength") or 0)
    if remote_size != local_size:
        raise Abort(f"HEAD_SIZE_MISMATCH local={local_size} remote={remote_size} http={http}", 4)

    report = {
        "local_path": str(final_path),
        "size_bytes": local_size,
        "git_sha": sha,
        "archived_files": len(rels_final),
        "bucket": bucket,
        "s3_key": key,
        "head_match": True,
        "head_http": http,
        "head_remote_size": remote_size,
        "members_listed": True,
        "forbidden_members": 0,
        "private_key_members": 0,
        "excluded_count": excluded_count,
        "object_count": list_prefix_count(client, bucket),
    }
    log_line(
        "status=ok"
        f" commit={sha}"
        f" archive={final_path.name}"
        f" size_bytes={local_size}"
        f" remote_size={remote_size}"
        f" key={key}"
    )
    print(json.dumps(report, ensure_ascii=True))
    return report


def build_code_archive(repo: Path) -> tuple[Path, str, list[str], int, list[str]]:
    global ARCHIVE_PREFIX

    branch, head, sha, dirty = resolve_commit(repo)
    short = sha[:12]
    ARCHIVE_PREFIX = f"leosoft-{short}/"
    paths = list_tree_paths(repo, sha)
    sensitive = [path for path in paths if is_sensitive_rel(path)]
    excluded = [path for path in paths if is_excluded(path)]
    kept_list = [path for path in paths if path not in set(excluded)]
    if any(is_hard_abort(path) for path in kept_list):
        raise Abort("ABORT_ENV_OR_CRMBAK", 2)
    if "debug-5656aa.log" in kept_list:
        raise Abort("ABORT_LOG_STILL_INCLUDED", 2)
    if any(is_sensitive_rel(path) for path in kept_list):
        raise Abort("ABORT_SENSITIVE_KEPT", 2)

    when = datetime.now().astimezone().replace(microsecond=0)
    stamp = when.strftime("%Y%m%d-%H%M%S")
    filename = f"leosoft-code-{stamp}-{short}.tar.gz"
    if FROZEN_SHA[:12] in filename or short not in filename:
        raise Abort("ABORT_NAME_COMMIT", 2)

    manifest = "\n".join(
        [
            f"full_sha={sha}",
            f"head={head}",
            f"checked_out_branch={branch}",
            f"prod_branch={PROD_BRANCH}",
            f"backup_local={when.isoformat(timespec='seconds')}",
            f"archive_filename={filename}",
            f"worktree_dirty={str(dirty).lower()}",
            "",
        ]
    )

    out_dir = BACKEND / "code_backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    final_path = out_dir / filename
    if final_path.exists():
        raise Abort("ABORT_ARCHIVE_EXISTS", 2)
    kept = set(kept_list)

    with tempfile.TemporaryDirectory(prefix="leosoft-code-src-") as tmp:
        tar_path = Path(tmp) / "source.tar"
        gz_tmp = Path(tmp) / filename
        proc = subprocess.run(
            [
                GIT,
                "-C",
                str(repo),
                "archive",
                "--format=tar",
                f"--prefix={ARCHIVE_PREFIX}",
                f"--output={tar_path}",
                sha,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise Abort("GIT_ARCHIVE_FAILED", 2)
        embedded = embedded_credential_rels(tar_path)
        for rel in embedded:
            kept.discard(rel)
        sensitive.extend(rel for rel in embedded if rel not in sensitive)
        build_archive(tar_path, gz_tmp, kept, manifest, when)
        rels = validate_archive(gz_tmp, kept)
        shutil.copy2(gz_tmp, final_path)

    rels_final = validate_archive(final_path, kept)
    log_line(
        "status=prepared"
        f" commit={sha}"
        f" head={head}"
        f" branch={branch}"
        f" prod_branch={PROD_BRANCH}"
        f" dirty={str(dirty).lower()}"
        f" archive={filename}"
        f" size_bytes={final_path.stat().st_size}"
        f" excluded_sensitive={len(sensitive)}"
    )
    return final_path, sha, rels_final, len(excluded), sensitive


def upload_prepared(path: Path) -> int:
    repo = CODE_REPO
    _branch, _head, sha, _dirty = resolve_commit(repo)
    global ARCHIVE_PREFIX
    ARCHIVE_PREFIX = f"leosoft-{sha[:12]}/"
    if path.name.startswith("leosoft-code-") and sha[:12] in path.name and FROZEN_SHA[:12] not in path.name:
        rels = regular_rels(path)
        key = f"{S3_PREFIX}{path.name}"
        upload_archive(path, key, sha, rels, excluded_count=0)
        return 0
    raise Abort("ABORT_NAME_COMMIT", 2)


def main() -> int:
    load_dotenv_file(BACKEND / ".env.backup")
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    if not configured():
        log_line("status=error code=S3_NOT_CONFIGURED")
        print("S3_NOT_CONFIGURED")
        return 1

    args = sys.argv[1:]
    no_upload = "--no-upload" in args
    try:
        if "--upload-prepared" in args:
            index = args.index("--upload-prepared")
            if index + 1 >= len(args):
                raise Abort("ABORT_UPLOAD_PATH", 2)
            return upload_prepared(Path(args[index + 1]))

        final_path, sha, rels, excluded_count, sensitive = build_code_archive(CODE_REPO)
        print(f"COMMIT {sha}")
        print(f"ARCHIVE {final_path.name}")
        print(f"SIZE {final_path.stat().st_size}")
        print(f"MEMBERS {len([rel for rel in rels if rel != 'CODE-SOURCE.txt'])}")
        for path in sensitive:
            print(f"EXCLUDED_SENSITIVE {path}")
        if no_upload:
            log_line(f"status=prepared_not_uploaded commit={sha} archive={final_path.name} size_bytes={final_path.stat().st_size}")
            print("UPLOAD skipped")
            return 0
        key = f"{S3_PREFIX}{final_path.name}"
        upload_archive(final_path, key, sha, rels, excluded_count)
        return 0
    except Abort as exc:
        log_line(f"status=error code={exc.code}")
        print(exc.code)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
