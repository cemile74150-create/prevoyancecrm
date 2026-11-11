"""Clôture dossiers + stats (Non renseigné exclu du taux)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dossier_cloture import (  # noqa: E402
    CLOTURE_MOTIF_ABOUTIE,
    CLOTURE_MOTIF_NON_ABOUTIE,
    aggregate_dossier_stats,
    cloture_motif_label,
    compute_taux_reussite,
    normalize_cloture_motif,
    resolve_period_bounds,
    validate_cloture_payload,
)


def test_normalize_et_label_motif():
    assert normalize_cloture_motif("affaire_aboutie") == CLOTURE_MOTIF_ABOUTIE
    assert normalize_cloture_motif("Affaire non aboutie") == CLOTURE_MOTIF_NON_ABOUTIE
    assert normalize_cloture_motif(None) is None
    assert cloture_motif_label(None) == "Non renseigné"
    assert cloture_motif_label("affaire_aboutie") == "Affaire aboutie"


def test_validate_cloture_exige_motif():
    try:
        validate_cloture_payload(statut="Clôturé", cloture_date="2026-03-01", cloture_motif=None)
        assert False, "attendu ValueError"
    except ValueError as exc:
        assert "Motif" in str(exc)

    date_iso, motif = validate_cloture_payload(
        statut="Clôturé",
        cloture_date="2026-03-01",
        cloture_motif="affaire_aboutie",
    )
    assert date_iso == "2026-03-01"
    assert motif == CLOTURE_MOTIF_ABOUTIE


def test_taux_exclut_non_renseigne():
    assert compute_taux_reussite(2, 2) == 50.0
    assert compute_taux_reussite(0, 0) is None

    dossiers = [
        {"statut": "Clôturé", "cloture_motif": CLOTURE_MOTIF_ABOUTIE, "created_at": "2026-01-10", "cloture_date": "2026-02-01", "conseiller": "A"},
        {"statut": "Clôturé", "cloture_motif": CLOTURE_MOTIF_NON_ABOUTIE, "created_at": "2026-01-11", "cloture_date": "2026-02-02", "conseiller": "A"},
        {"statut": "Clôturé", "cloture_motif": None, "created_at": "2026-01-12", "cloture_date": "2026-02-03", "conseiller": "B"},
        {"statut": "Nouveau", "created_at": "2026-02-05", "conseiller": "B"},
        {"statut": "Documents en attente", "created_at": "2026-02-06", "conseiller": "B"},
        {"statut": "Analyse en cours", "created_at": "2026-02-07", "conseiller": "A"},
    ]
    stats = aggregate_dossier_stats(dossiers, today=date(2026, 3, 1))
    assert stats["total"] == 6
    assert stats["nouveaux"] == 1
    assert stats["en_attente"] == 1
    assert stats["en_cours"] == 1
    assert stats["clotures"] == 3
    assert stats["affaires_abouties"] == 1
    assert stats["affaires_non_abouties"] == 1
    assert stats["clotures_non_renseignees"] == 1
    assert stats["taux_reussite"] == 50.0
    assert "exclus" in stats["taux_reussite_regle"]


def test_filtre_periode_et_statut():
    d_from, d_to = resolve_period_bounds("custom", "2026-02-01", "2026-02-28", today=date(2026, 3, 1))
    assert d_from == date(2026, 2, 1)
    assert d_to == date(2026, 2, 28)

    dossiers = [
        {"statut": "Clôturé", "cloture_motif": CLOTURE_MOTIF_ABOUTIE, "created_at": "2026-01-10", "cloture_date": "2026-02-10", "conseiller": "A"},
        {"statut": "Clôturé", "cloture_motif": CLOTURE_MOTIF_NON_ABOUTIE, "created_at": "2025-12-01", "cloture_date": "2025-12-15", "conseiller": "A"},
        {"statut": "Nouveau", "created_at": "2026-02-05", "conseiller": "A"},
    ]
    stats = aggregate_dossier_stats(
        dossiers,
        date_from=d_from,
        date_to=d_to,
        today=date(2026, 3, 1),
    )
    # Clôturé du 10/02 + Nouveau du 05/02 (réf = created pour Nouveau, cloture_date pour Clôturé)
    assert stats["total"] == 2
    assert stats["affaires_abouties"] == 1
    assert stats["nouveaux"] == 1

    only_clotures = aggregate_dossier_stats(
        dossiers,
        statut_filter="Clôturé",
        date_from=d_from,
        date_to=d_to,
        today=date(2026, 3, 1),
    )
    assert only_clotures["total"] == 1
    assert only_clotures["affaires_abouties"] == 1
