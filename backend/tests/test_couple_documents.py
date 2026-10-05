"""Tests partage documents entre conjoints (couples)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from server import _documents_list_query, _is_couple_scope  # noqa: E402


def test_is_couple_scope_single():
    assert _is_couple_scope({"member_ids": ["c1"]}) is False
    assert _is_couple_scope({}) is False


def test_is_couple_scope_couple():
    assert _is_couple_scope({"member_ids": ["c1", "c2"]}) is True


def test_documents_list_query_single():
    scope = {"member_ids": ["c1"], "dossier_id": "d1", "dossier_ids": ["d1"]}
    q = _documents_list_query("user1", "c1", scope)
    assert q["user_id"] == "user1"
    assert q["is_deleted"] is False
    assert q["$or"] == [{"client_id": "c1"}]


def test_documents_list_query_couple():
    scope = {"member_ids": ["c1", "c2"], "dossier_id": "d1", "dossier_ids": ["d1", "d2"]}
    q = _documents_list_query("user1", "c1", scope)
    assert q["$or"] == [
        {"client_id": {"$in": ["c1", "c2"]}},
        {"dossier_id": {"$in": ["d1", "d2"]}},
    ]


def test_documents_list_query_couple_from_spouse_view():
    """Le conjoint voit les mêmes documents via member_ids."""
    scope = {"member_ids": ["wife", "husband"], "dossier_id": "fam-1", "dossier_ids": ["fam-1"]}
    q_wife = _documents_list_query("u", "wife", scope)
    q_husband = _documents_list_query("u", "husband", scope)
    assert q_wife["$or"] == q_husband["$or"]
    assert q_wife["$and"] != q_husband["$and"]


def test_documents_list_query_couple_lpp_stays_on_owner():
    """Réponse LPP de Monsieur ne doit pas matcher la requête de Madame."""
    scope = {"member_ids": ["c1", "c2"], "dossier_id": "d1", "dossier_ids": ["d1"]}
    q = _documents_list_query("user1", "c1", scope)
    assert "$and" in q
    person_clause = q["$and"][0]["$or"]
    assert {"client_id": "c1"} in person_clause
    own_or_not_lpp = person_clause[1]["$and"]
    cats = own_or_not_lpp[0]["category"]["$nin"]
    assert "Réponse recherche LPP" in cats
    items = own_or_not_lpp[1]["checklist_item"]["$nin"]
    assert "Demande LPP" in items
