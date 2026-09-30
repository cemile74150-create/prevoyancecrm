"""Tests identité client unique (normalisation + clusters + payload 409)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from client_identity import (
    DUPLICATE_CODE,
    DUPLICATE_MESSAGE,
    client_identity_key,
    cluster_duplicates,
    duplicate_conflict_detail,
    identity_fields_for_storage,
    identity_key_complete,
    normalize_client_name,
    normalize_date_naissance,
)


def test_normalize_client_name_accents_spaces_case():
    assert normalize_client_name("  Sylvie  Eben ") == "sylvie eben"
    assert normalize_client_name("SYLVIE") == normalize_client_name("sylvie")
    assert normalize_client_name("Béatrice") == normalize_client_name("Beatrice")
    assert normalize_client_name("François") == "francois"


def test_normalize_date_naissance_formats():
    assert normalize_date_naissance("1990-05-01") == "1990-05-01"
    assert normalize_date_naissance("1990-05-01T12:00:00Z") == "1990-05-01"
    assert normalize_date_naissance("01.05.1990") == "1990-05-01"
    assert normalize_date_naissance("") == ""
    assert normalize_date_naissance("enc:v1:xxx") == ""


def test_identity_key_stable_and_complete():
    k1 = client_identity_key("Sylvie", "Eben", "1985-03-12")
    k2 = client_identity_key(" sylvie ", "EBEN", "1985-03-12T00:00:00")
    assert k1 == k2 == "sylvie|eben|1985-03-12"
    assert identity_key_complete(k1) is True
    assert identity_key_complete(client_identity_key("Sylvie", "Eben", None)) is False
    assert identity_fields_for_storage("Sylvie", "Eben", "1985-03-12")["identity_key"] == k1
    assert identity_fields_for_storage("Sylvie", "Eben", None)["identity_key"] == ""


def test_cluster_duplicates_groups_variants():
    clients = [
        {"id": "1", "prenom": "Sylvie", "nom": "Eben", "date_naissance": "1985-03-12", "numero_dossier": "DOS-0220"},
        {"id": "2", "prenom": "sylvie", "nom": "EBEN", "date_naissance": "1985-03-12T00:00:00", "numero_dossier": "DOS-0219"},
        {"id": "3", "prenom": "Jean", "nom": "Dupont", "date_naissance": "1970-01-01", "numero_dossier": "DOS-0001"},
        {"id": "4", "prenom": "  Sylvie  ", "nom": "Eben", "date_naissance": "1985-03-12", "numero_dossier": "DOS-0218"},
    ]
    clusters = cluster_duplicates(clients)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 3
    nums = {d["numero_dossier"] for d in clusters[0]["dossiers"]}
    assert nums == {"DOS-0220", "DOS-0219", "DOS-0218"}


def test_duplicate_conflict_payload():
    existing = {
        "id": "abc",
        "prenom": "Sylvie",
        "nom": "Eben",
        "numero_dossier": "DOS-0220",
        "conseiller": "Ada",
    }
    detail = duplicate_conflict_detail(existing)
    assert detail["code"] == DUPLICATE_CODE
    assert detail["message"] == DUPLICATE_MESSAGE
    assert detail["existing"]["id"] == "abc"
    assert detail["existing"]["numero_dossier"] == "DOS-0220"
    assert "Sylvie" in detail["existing"]["name"]


def test_require_unique_identity_raises_409():
    import asyncio

    from client_identity import require_unique_identity

    class FakeCursor:
        def __init__(self, docs):
            self._docs = docs

        async def to_list(self, n):
            return self._docs[:n]

    class FakeColl:
        def find(self, query, projection=None):
            return FakeCursor([
                {
                    "id": "exist-1",
                    "prenom": "Sylvie",
                    "nom": "Eben",
                    "date_naissance": "1985-03-12",
                    "numero_dossier": "DOS-0220",
                    "conseiller": "Ada",
                    "user_id": "tenant",
                    "created_at": "2024-01-01",
                }
            ])

    class FakeDb:
        clients = FakeColl()

    async def _run():
        await require_unique_identity(
            FakeDb(),
            prenom="sylvie",
            nom="eben",
            date_naissance="1985-03-12",
            user_id="tenant",
        )

    with pytest.raises(HTTPException) as ei:
        asyncio.run(_run())
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == DUPLICATE_CODE
    assert ei.value.detail["existing"]["numero_dossier"] == "DOS-0220"
