"""Tests chiffrement champs + documents."""

from __future__ import annotations

import os

import pytest

# Ensure keys before importing modules that may cache
os.environ["DATA_ENCRYPTION_PASSPHRASE"] = "test-passphrase-crm-encrypt-32c"


@pytest.fixture(autouse=True)
def _reset_keys(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_PASSPHRASE", "test-passphrase-crm-encrypt-32c")
    monkeypatch.delenv("DATA_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("DATA_ENCRYPTION_KEY_PREVIOUS", raising=False)
    monkeypatch.delenv("DATA_ENCRYPTION_PASSPHRASE_PREVIOUS", raising=False)
    import data_crypto_keys

    data_crypto_keys.clear_key_cache()
    yield
    data_crypto_keys.clear_key_cache()


def test_field_encrypt_decrypt_roundtrip():
    from field_crypto import decrypt_str, encrypt_str, is_encrypted_value

    plain = "756.1234.5678.90"
    enc = encrypt_str(plain)
    assert is_encrypted_value(enc)
    assert enc != plain
    assert decrypt_str(enc) == plain


def test_field_dual_read_plaintext():
    from field_crypto import decrypt_str

    assert decrypt_str("756.1111.2222.33") == "756.1111.2222.33"


def test_field_idempotent_encrypt():
    from field_crypto import encrypt_str

    enc = encrypt_str("hello")
    assert encrypt_str(enc) == enc


def test_client_fields_encrypt_decrypt():
    from field_crypto import decrypt_client_fields, encrypt_client_fields, is_encrypted_value

    doc = {
        "id": "c1",
        "prenom": "Ada",
        "nom": "Lovelace",
        "avs_number": "756.1234.5678.90",
        "email": "ada@example.com",
        "telephone": "+41 79 000 00 00",
        "adresse": "Rue du Lac 1",
        "npa": "1000",
        "ville": "Lausanne",
        "date_naissance": "1815-12-10",
    }
    enc = encrypt_client_fields(doc)
    assert enc["prenom"] == "Ada"
    assert is_encrypted_value(enc["avs_number"])
    assert is_encrypted_value(enc["email"])
    dec = decrypt_client_fields(enc)
    assert dec["avs_number"] == doc["avs_number"]
    assert dec["email"] == doc["email"]
    assert dec["adresse"] == doc["adresse"]


def test_storage_encrypt_decrypt_roundtrip():
    from storage_crypto import decrypt_blob, encrypt_blob, is_encrypted_blob

    raw = b"%PDF-1.4 fake content for test"
    enc = encrypt_blob(raw)
    assert is_encrypted_blob(enc)
    assert enc != raw
    assert decrypt_blob(enc) == raw


def test_storage_dual_read_legacy():
    from storage_crypto import decrypt_blob

    legacy = b"%PDF-1.4 legacy plaintext"
    assert decrypt_blob(legacy) == legacy


def test_storage_idempotent_encrypt():
    from storage_crypto import encrypt_blob

    enc = encrypt_blob(b"abc")
    assert encrypt_blob(enc) == enc


def test_rotation_with_previous_passphrase(monkeypatch):
    import data_crypto_keys
    from field_crypto import decrypt_str, encrypt_str
    from storage_crypto import decrypt_blob, encrypt_blob

    old_phrase = "old-passphrase-for-rotation-xx"
    new_phrase = "new-passphrase-for-rotation-yy"

    monkeypatch.setenv("DATA_ENCRYPTION_PASSPHRASE", old_phrase)
    data_crypto_keys.clear_key_cache()
    enc_field = encrypt_str("secret-avs")
    enc_blob = encrypt_blob(b"pdf-bytes")

    monkeypatch.setenv("DATA_ENCRYPTION_PASSPHRASE", new_phrase)
    monkeypatch.setenv("DATA_ENCRYPTION_PASSPHRASE_PREVIOUS", old_phrase)
    data_crypto_keys.clear_key_cache()

    assert decrypt_str(enc_field) == "secret-avs"
    assert decrypt_blob(enc_blob) == b"pdf-bytes"

    # Re-encrypt under new key
    re_field = encrypt_str(decrypt_str(enc_field))
    assert decrypt_str(re_field) == "secret-avs"


def test_needs_field_encryption_and_patch():
    from field_crypto import is_encrypted_value, needs_field_encryption, patch_encrypt_sensitive

    plain = {"avs_number": "756.1", "prenom": "Ada"}
    assert needs_field_encryption(plain) is True
    enc = patch_encrypt_sensitive({"avs_number": "756.1", "statut": "Nouveau"})
    assert is_encrypted_value(enc["avs_number"])
    assert enc["statut"] == "Nouveau"
    assert needs_field_encryption({"avs_number": enc["avs_number"]}) is False


def test_local_storage_encrypt_via_helpers(tmp_path, monkeypatch):
    """Round-trip write/read via storage_crypto (simule put/get)."""
    from storage_crypto import decrypt_blob, encrypt_blob

    raw = b"%PDF-1.4 storage roundtrip"
    enc = encrypt_blob(raw)
    path = tmp_path / "doc.bin"
    path.write_bytes(enc)
    assert decrypt_blob(path.read_bytes()) == raw
