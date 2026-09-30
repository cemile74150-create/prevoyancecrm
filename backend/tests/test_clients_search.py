"""Tests recherche hub Clients (suggestions Demande d'offre)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import helpers via server module after path setup
from server import _client_matches_q, _fold_search, _rank_client_match  # noqa: E402


def test_fold_and_partial_name_match():
    assert _fold_search("Wahlen") == "wahlen"
    assert _fold_search("Éléonore") == "eleonore"

    c = {"prenom": "Marc", "nom": "Wahlen", "email": "", "telephone": "", "numero_dossier": "DOS-0012"}
    assert _client_matches_q(c, "wah")
    assert _client_matches_q(c, "wahlen")
    assert _client_matches_q(c, "marc")
    assert _client_matches_q(c, "marc wah")
    assert not _client_matches_q(c, "dupont")


def test_rank_prefers_prefix():
    a = {"prenom": "Jean", "nom": "Dupont"}
    b = {"prenom": "Marie", "nom": "Dupré"}
    ql = "dup"
    assert _rank_client_match(a, ql)[0] <= _rank_client_match(b, ql)[0]
