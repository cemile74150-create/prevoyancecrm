"""
Matériel de clé pour le chiffrement applicatif (champs + documents).

Distinct de BACKUP_ENCRYPTION_PASSPHRASE (sauvegardes .crmbak).

Sources (priorité) :
  1. DATA_ENCRYPTION_KEY — 32 octets en base64
  2. DATA_ENCRYPTION_PASSPHRASE — phrase longue (scrypt → 32 octets)

Rotation :
  DATA_ENCRYPTION_KEY_PREVIOUS ou DATA_ENCRYPTION_PASSPHRASE_PREVIOUS
  pour déchiffrer l'ancien format pendant la ré-écriture.
"""

from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache
from typing import List, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

KEY_LEN = 32
# Sel fixe applicatif (pas un secret) — la passphrase / KEY porte le secret.
_SCRYPT_SALT = b"prevoyancecrm-data-encryption-v1"


class EncryptionNotConfigured(RuntimeError):
    pass


def encryption_configured() -> bool:
    return bool(
        (os.environ.get("DATA_ENCRYPTION_KEY") or "").strip()
        or (os.environ.get("DATA_ENCRYPTION_PASSPHRASE") or "").strip()
    )


def _decode_raw_key(value: str) -> bytes:
    raw = value.strip()
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as e:
        raise EncryptionNotConfigured(
            "DATA_ENCRYPTION_KEY invalide (base64 de 32 octets attendu)"
        ) from e
    if len(key) != KEY_LEN:
        raise EncryptionNotConfigured(
            f"DATA_ENCRYPTION_KEY doit décoder en {KEY_LEN} octets (reçu {len(key)})"
        )
    return key


def _derive_from_passphrase(passphrase: str) -> bytes:
    p = (passphrase or "").strip()
    if len(p) < 16:
        raise EncryptionNotConfigured(
            "DATA_ENCRYPTION_PASSPHRASE trop courte (min. 16 caractères)"
        )
    kdf = Scrypt(salt=_SCRYPT_SALT, length=KEY_LEN, n=2**14, r=8, p=1)
    return kdf.derive(p.encode("utf-8"))


def _master_key_from_env(
    key_var: str,
    passphrase_var: str,
    *,
    required: bool,
) -> Optional[bytes]:
    key_raw = (os.environ.get(key_var) or "").strip()
    if key_raw:
        return _decode_raw_key(key_raw)
    phrase = (os.environ.get(passphrase_var) or "").strip()
    if phrase:
        return _derive_from_passphrase(phrase)
    if required:
        raise EncryptionNotConfigured(
            "Chiffrement données non configuré : définissez DATA_ENCRYPTION_KEY "
            "(32 octets base64) ou DATA_ENCRYPTION_PASSPHRASE (min. 16 caractères)."
        )
    return None


@lru_cache(maxsize=1)
def master_key() -> bytes:
    key = _master_key_from_env(
        "DATA_ENCRYPTION_KEY",
        "DATA_ENCRYPTION_PASSPHRASE",
        required=True,
    )
    assert key is not None
    return key


@lru_cache(maxsize=1)
def previous_master_keys() -> tuple:
    keys: List[bytes] = []
    prev = _master_key_from_env(
        "DATA_ENCRYPTION_KEY_PREVIOUS",
        "DATA_ENCRYPTION_PASSPHRASE_PREVIOUS",
        required=False,
    )
    if prev:
        keys.append(prev)
    return tuple(keys)


def clear_key_cache() -> None:
    """Pour tests / rechargement env."""
    master_key.cache_clear()
    previous_master_keys.cache_clear()
    derive_context_key.cache_clear()


@lru_cache(maxsize=16)
def derive_context_key(context: str, master: Optional[bytes] = None) -> bytes:
    """
    HKDF pour séparer les contextes crypto (field vs storage).
    `master` optionnel pour rotation (clé précédente).
    """
    mk = master if master is not None else master_key()
    return HKDF(
        algorithm=hashes.SHA256(),
        length=KEY_LEN,
        salt=None,
        info=f"prevoyancecrm:{context}:v1".encode("utf-8"),
    ).derive(mk)


def fingerprint_key() -> str:
    """Identifiant non secret pour logs / migrations (pas la clé)."""
    return hashlib.sha256(master_key()).hexdigest()[:12]
