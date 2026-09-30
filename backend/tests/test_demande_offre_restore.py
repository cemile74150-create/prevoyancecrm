"""Annulation / restauration des demandes d'offre : statut, numéro, données, historique."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demandes_offres_3p import (  # noqa: E402
    ACTION_ANNULEE,
    ACTION_RESTAUREE,
    DEFAULT_RESTORE_STATUT,
    FIELD_STATUT_AVANT_ANNULATION,
    STATUT_ANNULEE,
    STATUT_DEMANDE_ANNULEE_CODE,
    STATUT_ATTENTE_INFOS,
    STATUT_BROUILLON,
    STATUT_ENVOYEE,
    STATUT_OFFRE_RECUE,
    history_entry,
    resolve_statut_avant_annulation,
    serialize_demande,
)


def test_default_restore_statut_is_brouillon():
    """Choix produit : restauration toujours en Brouillon."""
    assert DEFAULT_RESTORE_STATUT == STATUT_BROUILLON


def test_resolve_always_returns_brouillon_even_with_stored_status():
    """Ignore statut_avant_annulation (ex. Demande envoyée) → Brouillon."""
    doc = {
        "statut": STATUT_ANNULEE,
        FIELD_STATUT_AVANT_ANNULATION: STATUT_OFFRE_RECUE,
        "historique": [
            history_entry("Demande envoyée", statut=STATUT_ENVOYEE),
            history_entry(ACTION_ANNULEE, statut=STATUT_ANNULEE),
        ],
    }
    assert resolve_statut_avant_annulation(doc) == STATUT_BROUILLON


def test_resolve_never_restores_to_envoyee():
    doc = {
        "statut": STATUT_ANNULEE,
        FIELD_STATUT_AVANT_ANNULATION: STATUT_ENVOYEE,
        "historique": [
            history_entry("Envoyée", statut=STATUT_ENVOYEE),
            history_entry(ACTION_ANNULEE, statut=STATUT_ANNULEE),
        ],
    }
    assert resolve_statut_avant_annulation(doc) == STATUT_BROUILLON
    assert resolve_statut_avant_annulation(doc) != STATUT_ENVOYEE


def test_resolve_fallback_without_field_or_historique():
    assert resolve_statut_avant_annulation({"statut": STATUT_ANNULEE}) == DEFAULT_RESTORE_STATUT
    assert resolve_statut_avant_annulation({}) == DEFAULT_RESTORE_STATUT
    assert resolve_statut_avant_annulation(None) == DEFAULT_RESTORE_STATUT
    assert DEFAULT_RESTORE_STATUT == STATUT_BROUILLON


def test_resolve_legacy_cancelled_without_field_is_brouillon():
    """Anciennes annulations sans statut_avant_annulation : Brouillon (pas Offre reçue / envoyée)."""
    doc = {
        "statut": STATUT_ANNULEE,
        "historique": [
            history_entry("Créée", statut=STATUT_BROUILLON),
            history_entry("Envoyée", statut=STATUT_ENVOYEE),
            history_entry("Offre reçue", statut=STATUT_OFFRE_RECUE),
            history_entry(ACTION_ANNULEE, statut=STATUT_ANNULEE),
        ],
    }
    assert resolve_statut_avant_annulation(doc) == STATUT_BROUILLON


def test_resolve_ignores_attente_infos_stored_value():
    doc = {
        "statut": STATUT_ANNULEE,
        FIELD_STATUT_AVANT_ANNULATION: STATUT_ATTENTE_INFOS,
        "historique": [
            history_entry("En attente", statut=STATUT_ATTENTE_INFOS),
            history_entry(ACTION_ANNULEE, statut=STATUT_ANNULEE),
        ],
    }
    assert resolve_statut_avant_annulation(doc) == STATUT_BROUILLON


def test_serialize_exposes_statut_avant_annulation():
    doc = {
        "id": "d1",
        "numero": "OFF-2026-0042",
        "statut": STATUT_ANNULEE,
        FIELD_STATUT_AVANT_ANNULATION: STATUT_ENVOYEE,
        "compagnies": ["AXA"],
        "montant_prime": 1200,
        "historique": [],
    }
    out = serialize_demande(doc)
    # Le libellé historique « Demande annulée » est normalisé en code.
    assert out["statut"] == STATUT_DEMANDE_ANNULEE_CODE
    assert out[FIELD_STATUT_AVANT_ANNULATION] == STATUT_ENVOYEE
    assert out["numero"] == "OFF-2026-0042"
    assert out["compagnies"] == ["AXA"]
    assert out["montant_prime"] == 1200.0


def test_cancel_extra_shape_preserves_previous_status_contract():
    """
    Contrat d'annulation (sans DB) : le payload ``extra`` doit porter
    statut_avant_annulation + métadonnées, sans toucher aux champs métier.
    """
    previous = STATUT_ENVOYEE
    comment = "erreur de saisie"
    extra = {
        FIELD_STATUT_AVANT_ANNULATION: previous,
        "annulation": {
            "at": "2026-09-24T10:00:00+00:00",
            "by": "Alice",
            "commentaire": comment,
            "statut_avant": previous,
        },
    }
    # Champs métier qui doivent rester intacts après un $set de statut + extra
    preserved = {
        "numero": "OFF-2026-0099",
        "client_id": "c1",
        "compagnies": ["Helvetia", "Swiss Life"],
        "montant_prime": 500,
        "form_payload": {"prenom": "Jean"},
        "offres": [{"id": "o1"}],
        "documents": [{"id": "doc1"}],
    }
    merged = {**preserved, "statut": STATUT_ANNULEE, **extra}
    assert merged["numero"] == "OFF-2026-0099"
    assert merged["client_id"] == "c1"
    assert merged["compagnies"] == ["Helvetia", "Swiss Life"]
    assert merged["montant_prime"] == 500
    assert merged["form_payload"]["prenom"] == "Jean"
    assert merged["offres"]
    assert merged["documents"]
    assert merged[FIELD_STATUT_AVANT_ANNULATION] == previous
    assert merged["annulation"]["statut_avant"] == previous


def test_restore_extra_shape_clears_field_and_history_action():
    restored = STATUT_BROUILLON
    numero = "OFF-2026-0099"
    hist = [
        history_entry("Offre reçue", statut=STATUT_OFFRE_RECUE),
        history_entry(ACTION_ANNULEE, statut=STATUT_ANNULEE),
    ]
    restore_entry = history_entry(
        ACTION_RESTAUREE,
        by_name="Bob",
        by_id="b1",
        detail=f"Statut rétabli : {restored}",
        statut=restored,
        meta={"statut_avant_annulation": restored, "numero": numero},
    )
    hist.append(restore_entry)
    doc = {
        "numero": numero,
        "statut": restored,
        FIELD_STATUT_AVANT_ANNULATION: None,
        "historique": hist,
        "compagnies": ["AXA"],
    }
    assert doc["numero"] == numero
    assert doc["statut"] == STATUT_BROUILLON
    assert doc[FIELD_STATUT_AVANT_ANNULATION] is None
    assert hist[-1]["action"] == ACTION_RESTAUREE
    assert hist[-1]["by_name"] == "Bob"
    assert hist[-1]["statut"] == STATUT_BROUILLON
    assert "Demande restaurée" in hist[-1]["action"]
