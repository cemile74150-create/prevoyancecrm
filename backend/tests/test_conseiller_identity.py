"""Tests normalisation identité conseiller."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from conseiller_identity import (  # noqa: E402
    display_conseiller_name,
    normalize_conseiller_key,
    unique_conseiller_displays,
)
from demandes_offres_3p import (  # noqa: E402
    STATUT_ENVOYEE,
    STATUT_INCOMPLETE,
    compute_agent_stats,
    compute_erreur_stats,
)


def test_normalize_conseiller_key_case_and_spaces():
    assert normalize_conseiller_key("Valentin Lugnier") == "valentin lugnier"
    assert normalize_conseiller_key("Valentin LUGNIER") == "valentin lugnier"
    assert normalize_conseiller_key("VALENTIN lugnier") == "valentin lugnier"
    assert normalize_conseiller_key("  Valentin   Lugnier  ") == "valentin lugnier"
    assert normalize_conseiller_key("") == ""
    assert normalize_conseiller_key(None) == ""


def test_normalize_conseiller_key_accents():
    assert normalize_conseiller_key("José García") == "jose garcia"
    assert normalize_conseiller_key("JOSE GARCIA") == normalize_conseiller_key("José García")
    assert normalize_conseiller_key("Éléonore") == "eleonore"


def test_display_conseiller_name_prefers_mixed_case():
    assert display_conseiller_name("Valentin LUGNIER", "Valentin Lugnier") == "Valentin Lugnier"
    assert display_conseiller_name("VALENTIN LUGNIER") == "Valentin Lugnier"
    assert display_conseiller_name("valentin lugnier") == "Valentin Lugnier"
    assert display_conseiller_name("", None) == "Non attribué"


def test_unique_conseiller_displays_merges():
    names = unique_conseiller_displays([
        "Valentin Lugnier",
        "Valentin LUGNIER",
        "VALENTIN lugnier",
        "Alberto Mendes",
    ])
    assert len(names) == 2
    assert "Valentin Lugnier" in names
    assert "Alberto Mendes" in names


def test_compute_erreur_stats_merges_case_variants():
    rows = [
        {
            "id": "1",
            "statut": STATUT_INCOMPLETE,
            "agent_label": "Valentin Lugnier",
            "incomplete_at": "2026-01-01",
            "erreurs_agent": [{"field": "a", "field_label": "A", "demande_id": "1"}],
            "prenom": "A",
            "nom": "B",
        },
        {
            "id": "2",
            "statut": STATUT_ENVOYEE,
            "agent_label": "Valentin LUGNIER",
            "erreurs_incomplete": [],
            "prenom": "C",
            "nom": "D",
        },
    ]
    stats = compute_erreur_stats(rows)
    assert len(stats["by_agent"]) == 1
    agent = stats["by_agent"][0]
    assert agent["agent"] == "Valentin Lugnier"
    assert agent["demandes"] == 2
    assert agent["incompletes"] == 1
    assert agent["taux_erreur"] == 50.0


def test_compute_agent_stats_merges_case_variants():
    rows = [
        {"id": "1", "statut": STATUT_ENVOYEE, "agent_label": "Valentin Lugnier", "compagnies": ["A"]},
        {"id": "2", "statut": STATUT_ENVOYEE, "agent_label": "VALENTIN lugnier", "compagnies": ["B"]},
    ]
    stats = compute_agent_stats(rows)
    assert len(stats["by_agent"]) == 1
    assert stats["by_agent"][0]["agent"] == "Valentin Lugnier"
    assert stats["by_agent"][0]["nb_demandes"] == 2
