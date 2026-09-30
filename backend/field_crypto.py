"""
Chiffrement AES-256-GCM des champs sensibles (PII) en base.

Format stocké (str) :
  enc:v1:<base64url(nonce || ciphertext+tag)>

Dual-read : une valeur sans préfixe enc:v1: est traitée comme clair legacy.
"""

from __future__ import annotations

import base64
import copy
import os
from typing import Any, Dict, Iterable, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from data_crypto_keys import (
    EncryptionNotConfigured,
    derive_context_key,
    encryption_configured,
    master_key,
    previous_master_keys,
)

PREFIX = "enc:v1:"
NONCE_LEN = 12
CONTEXT = "field"

# Champs PII chiffrés (CRM clients + Suivi 3P)
SENSITIVE_FIELDS: tuple[str, ...] = (
    "avs_number",
    "email",
    "telephone",
    "adresse",
    "adresse_complement",
    "npa",
    "ville",
    "date_naissance",
    "conjoint_date_naissance",
    "pays_residence",
    "pays",
    "notes",  # Suivi 3P free-text
)


def is_encrypted_value(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def encrypt_str(plaintext: str, *, key: Optional[bytes] = None) -> str:
    if plaintext is None:
        raise TypeError("encrypt_str: plaintext None")
    text = str(plaintext)
    if is_encrypted_value(text):
        return text  # déjà chiffré
    if not text:
        return text
    aes_key = key or derive_context_key(CONTEXT)
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(aes_key).encrypt(nonce, text.encode("utf-8"), PREFIX.encode("utf-8"))
    return PREFIX + _b64e(nonce + ct)


def decrypt_str(value: str, *, keys: Optional[Iterable[bytes]] = None) -> str:
    if value is None:
        return value
    text = str(value)
    if not is_encrypted_value(text):
        return text  # clair legacy
    blob = _b64d(text[len(PREFIX) :])
    if len(blob) < NONCE_LEN + 16:
        raise ValueError("ciphertext champ trop court")
    nonce, ct = blob[:NONCE_LEN], blob[NONCE_LEN:]
    aad = PREFIX.encode("utf-8")

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
            return AESGCM(k).decrypt(nonce, ct, aad).decode("utf-8")
        except Exception as e:
            last_err = e
            continue
    raise ValueError("Impossible de déchiffrer le champ (clé incorrecte ?)") from last_err


def encrypt_client_fields(doc: Optional[dict], *, fields: Iterable[str] = SENSITIVE_FIELDS) -> dict:
    """Retourne une copie du document avec champs sensibles chiffrés."""
    if not doc:
        return doc or {}
    if not encryption_configured():
        raise EncryptionNotConfigured(
            "DATA_ENCRYPTION_KEY / DATA_ENCRYPTION_PASSPHRASE requis pour écrire des PII"
        )
    # Force résolution clé (fail early)
    master_key()
    out = copy.deepcopy(doc)
    for field in fields:
        if field not in out or out[field] is None:
            continue
        val = out[field]
        if not isinstance(val, str):
            val = str(val)
        if not val:
            continue
        out[field] = encrypt_str(val)
    return out


def decrypt_client_fields(doc: Optional[dict], *, fields: Iterable[str] = SENSITIVE_FIELDS) -> dict:
    """Retourne une copie du document avec champs sensibles déchiffrés (dual-read)."""
    if not doc:
        return doc or {}
    out = copy.deepcopy(doc)
    needs = any(is_encrypted_value(out.get(f)) for f in fields)
    if needs and not encryption_configured():
        raise EncryptionNotConfigured(
            "Données chiffrées présentes mais DATA_ENCRYPTION_* manquant"
        )
    if not needs and not encryption_configured():
        return out
    for field in fields:
        if field not in out or out[field] is None:
            continue
        val = out[field]
        if not isinstance(val, str):
            continue
        if not val:
            continue
        out[field] = decrypt_str(val)
    return out


def encrypt_fields_inplace(doc: dict, *, fields: Iterable[str] = SENSITIVE_FIELDS) -> dict:
    encrypted = encrypt_client_fields(doc, fields=fields)
    doc.clear()
    doc.update(encrypted)
    return doc


def decrypt_fields_inplace(doc: dict, *, fields: Iterable[str] = SENSITIVE_FIELDS) -> dict:
    decrypted = decrypt_client_fields(doc, fields=fields)
    doc.clear()
    doc.update(decrypted)
    return doc


def needs_field_encryption(doc: Optional[dict], *, fields: Iterable[str] = SENSITIVE_FIELDS) -> bool:
    """True si au moins un champ sensible est encore en clair (non vide)."""
    if not doc:
        return False
    for field in fields:
        val = doc.get(field)
        if isinstance(val, str) and val and not is_encrypted_value(val):
            return True
    return False


def patch_encrypt_sensitive(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Chiffre les clés sensibles présentes dans un dict $set / payload partiel."""
    if not updates:
        return updates
    out = dict(updates)
    touched = {k: v for k, v in out.items() if k in SENSITIVE_FIELDS}
    if not touched:
        return out
    enc = encrypt_client_fields(touched)
    out.update(enc)
    return out
