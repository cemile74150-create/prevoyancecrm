"""
Chiffrement AES-256-GCM des blobs documents (PDF, etc.) avant object storage.

Format fichier :
  magic (8) = b'CRMDOC01'
  nonce (12)
  ciphertext + tag (AESGCM)

Dual-read : sans magic → octets traités comme clair legacy.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from data_crypto_keys import (
    EncryptionNotConfigured,
    derive_context_key,
    encryption_configured,
    master_key,
    previous_master_keys,
)

MAGIC = b"CRMDOC01"
NONCE_LEN = 12
CONTEXT = "storage"


def is_encrypted_blob(data: bytes) -> bool:
    return isinstance(data, (bytes, bytearray)) and bytes(data[:8]) == MAGIC


def _as_bytes(value, *, label: str) -> bytes:
    """Refuse les coroutines / types non-bytes avant AESGCM / fitz."""
    import inspect

    if value is None:
        raise TypeError(f"{label}: None")
    if inspect.isawaitable(value):
        raise TypeError(
            f"{label}: coroutine non awaitée — un await manque avant l'usage des bytes"
        )
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, bytearray):
        return bytes(value)
    if not isinstance(value, bytes):
        raise TypeError(f"{label}: bytes attendus, reçu {type(value).__name__}")
    return value


def encrypt_blob(plaintext: bytes, *, key: Optional[bytes] = None) -> bytes:
    raw = _as_bytes(plaintext, label="encrypt_blob")
    if is_encrypted_blob(raw):
        return raw
    if not encryption_configured():
        raise EncryptionNotConfigured(
            "DATA_ENCRYPTION_KEY / DATA_ENCRYPTION_PASSPHRASE requis pour chiffrer les documents"
        )
    aes_key = key or derive_context_key(CONTEXT)
    # Touch master to fail early if misconfigured
    if key is None:
        master_key()
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(aes_key).encrypt(nonce, raw, MAGIC)
    return MAGIC + nonce + ct


def decrypt_blob(data: bytes, *, keys: Optional[Iterable[bytes]] = None) -> bytes:
    """Déchiffre un blob ; laisse passer le clair legacy sans magic."""
    raw = _as_bytes(data, label="decrypt_blob")
    if not is_encrypted_blob(raw):
        return raw
    if not encryption_configured():
        raise EncryptionNotConfigured(
            "Document chiffré présent mais DATA_ENCRYPTION_* manquant"
        )
    nonce = raw[8 : 8 + NONCE_LEN]
    ct = raw[8 + NONCE_LEN :]
    candidates: List[bytes] = []
    if keys is not None:
        candidates.extend(keys)
    else:
        candidates.append(derive_context_key(CONTEXT))
        for mk in previous_master_keys():
            candidates.append(derive_context_key(CONTEXT, mk))

    last_err: Optional[Exception] = None
    for k in candidates:
        try:
            return AESGCM(k).decrypt(nonce, ct, MAGIC)
        except Exception as e:
            last_err = e
            continue
    raise ValueError("Impossible de déchiffrer le document (clé incorrecte ?)") from last_err
