"""
Chiffrement AES-256-GCM des archives de sauvegarde CRM.

Format fichier .crmbak :
  magic (8) = b'CRMBK001'
  salt (16)
  nonce (12)
  ciphertext + tag (AESGCM)

Clé dérivée de BACKUP_ENCRYPTION_PASSPHRASE via scrypt.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"CRMBK001"
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32


def _passphrase() -> bytes:
    p = (os.environ.get("BACKUP_ENCRYPTION_PASSPHRASE") or "").strip()
    if not p:
        raise RuntimeError(
            "BACKUP_ENCRYPTION_PASSPHRASE manquant — définissez une phrase secrète longue "
            "(stockée hors Railway, ex. coffre local / gestionnaire de mots de passe)."
        )
    if len(p) < 16:
        raise RuntimeError("BACKUP_ENCRYPTION_PASSPHRASE trop courte (min. 16 caractères)")
    return p.encode("utf-8")


def derive_key(passphrase: bytes, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_LEN, n=2**14, r=8, p=1)
    return kdf.derive(passphrase)


def encrypt_file(src: Path, dest: Path) -> dict:
    raw = src.read_bytes()
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(_passphrase(), salt)
    ct = AESGCM(key).encrypt(nonce, raw, MAGIC)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(MAGIC + salt + nonce + ct)
    return {
        "encrypted_path": str(dest),
        "source_bytes": len(raw),
        "encrypted_bytes": dest.stat().st_size,
    }


def decrypt_file(src: Path, dest: Path) -> dict:
    blob = src.read_bytes()
    if not blob.startswith(MAGIC):
        raise ValueError(f"Format inconnu (magic manquant): {src}")
    salt = blob[8 : 8 + SALT_LEN]
    nonce = blob[8 + SALT_LEN : 8 + SALT_LEN + NONCE_LEN]
    ct = blob[8 + SALT_LEN + NONCE_LEN :]
    key = derive_key(_passphrase(), salt)
    plain = AESGCM(key).decrypt(nonce, ct, MAGIC)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(plain)
    return {"decrypted_path": str(dest), "bytes": len(plain)}
