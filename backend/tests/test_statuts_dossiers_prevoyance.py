"""Statuts du Kanban Dossiers Prévoyance."""

from __future__ import annotations

from server import STATUT_PRESENTE_EN_COURS, STATUTS, normalize_statut


def test_presente_en_cours_entre_a_presenter_et_cloture():
    assert STATUT_PRESENTE_EN_COURS == "Dossier présenté — en cours"
    idx = STATUTS.index(STATUT_PRESENTE_EN_COURS)
    assert STATUTS[idx - 1] == "À présenter"
    assert STATUTS[idx + 1] == "Clôturé"


def test_statuts_existants_inchanges():
    assert STATUTS == [
        "Nouveau",
        "Documents en attente",
        "Analyse en cours",
        "Stand-by",
        "À présenter",
        STATUT_PRESENTE_EN_COURS,
        "Clôturé",
    ]


def test_normalize_statut_garde_les_anciens_et_le_nouveau():
    assert normalize_statut(STATUT_PRESENTE_EN_COURS) == STATUT_PRESENTE_EN_COURS
    assert normalize_statut("À présenter au client") == "À présenter"
    assert normalize_statut("Clôturé") == "Clôturé"
    assert normalize_statut(None) == "Nouveau"
