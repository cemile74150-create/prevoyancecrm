"""Historique demandes d'offre : événements métier uniquement, pas de spam Enregistrer."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demandes_offres_3p import (  # noqa: E402
    ACTION_CREEE,
    ACTION_ENVOYEE,
    ACTION_MODIFIEE,
    ACTION_RENVOYEE,
    ACTION_VALIDEE,
    STATUT_BROUILLON,
    STATUT_ENVOYEE,
    STATUT_VALIDEE,
    apply_modification_to_historique,
    collapse_demande_historique,
    demande_was_already_sent,
    history_entry,
    serialize_demande,
    should_track_demande_modification,
)


def _e(action: str, at: str = "2026-01-01T10:00:00+00:00", **kw):
    return {"id": f"id-{action}-{at}", "action": action, "at": at, **kw}


def test_collapse_keeps_single_modifiee_between_milestones():
    hist = [
        _e(ACTION_CREEE, "t1"),
        _e(ACTION_VALIDEE, "t2"),
        _e(ACTION_ENVOYEE, "t3"),
        _e(ACTION_MODIFIEE, "t4", by_name="A"),
        _e(ACTION_MODIFIEE, "t5", by_name="B"),
        _e(ACTION_MODIFIEE, "t6", by_name="C"),
    ]
    out = collapse_demande_historique(hist)
    actions = [e["action"] for e in out]
    assert actions == [ACTION_CREEE, ACTION_VALIDEE, ACTION_ENVOYEE, ACTION_MODIFIEE]
    assert out[-1]["by_name"] == "C"
    assert out[-1]["at"] == "t6"
    # Même id que la première modifiée de la fenêtre
    assert out[-1]["id"] == hist[3]["id"]


def test_collapse_allows_new_modifiee_after_renvoyee():
    hist = [
        _e(ACTION_ENVOYEE, "t1"),
        _e(ACTION_MODIFIEE, "t2"),
        _e(ACTION_MODIFIEE, "t3"),
        _e(ACTION_RENVOYEE, "t4"),
        _e(ACTION_MODIFIEE, "t5"),
        _e(ACTION_MODIFIEE, "t6"),
    ]
    out = collapse_demande_historique(hist)
    assert [e["action"] for e in out] == [
        ACTION_ENVOYEE,
        ACTION_MODIFIEE,
        ACTION_RENVOYEE,
        ACTION_MODIFIEE,
    ]
    assert out[1]["at"] == "t3"
    assert out[3]["at"] == "t6"


def test_apply_modification_refreshes_same_entry():
    hist = [
        _e(ACTION_ENVOYEE, "t1"),
        history_entry(ACTION_MODIFIEE, by_name="Alice", by_id="a1"),
    ]
    hist[1]["at"] = "t2"
    hist[1]["id"] = "mod-1"
    refreshed = history_entry(ACTION_MODIFIEE, by_name="Bob", by_id="b2")
    out = apply_modification_to_historique(hist, refreshed)
    assert len(out) == 2
    assert out[1]["action"] == ACTION_MODIFIEE
    assert out[1]["id"] == "mod-1"
    assert out[1]["by_name"] == "Bob"
    assert out[1]["by_id"] == "b2"


def test_apply_modification_appends_when_none_in_window():
    hist = [_e(ACTION_ENVOYEE, "t1")]
    entry = history_entry(ACTION_MODIFIEE, by_name="Alice")
    out = apply_modification_to_historique(hist, entry)
    assert [e["action"] for e in out] == [ACTION_ENVOYEE, ACTION_MODIFIEE]


def test_apply_modification_after_renvoyee_starts_new_window():
    hist = [
        _e(ACTION_ENVOYEE, "t1"),
        _e(ACTION_MODIFIEE, "t2", id="old-mod"),
        _e(ACTION_RENVOYEE, "t3"),
    ]
    entry = history_entry(ACTION_MODIFIEE, by_name="Alice")
    out = apply_modification_to_historique(hist, entry)
    assert [e["action"] for e in out] == [
        ACTION_ENVOYEE,
        ACTION_MODIFIEE,
        ACTION_RENVOYEE,
        ACTION_MODIFIEE,
    ]
    assert out[1]["id"] == "old-mod"
    assert out[3]["by_name"] == "Alice"
    assert out[3]["id"] != "old-mod"


def test_should_not_track_brouillon():
    assert should_track_demande_modification({"statut": STATUT_BROUILLON}) is False
    assert should_track_demande_modification({"statut": STATUT_ENVOYEE}) is True
    assert should_track_demande_modification({"statut": STATUT_VALIDEE}) is True


def test_demande_was_already_sent():
    assert demande_was_already_sent({"date_envoi": "2026-01-01"}) is True
    assert demande_was_already_sent({"historique": [_e(ACTION_ENVOYEE)]}) is True
    assert demande_was_already_sent({"historique": [_e(ACTION_RENVOYEE)]}) is True
    assert demande_was_already_sent({"historique": [_e(ACTION_CREEE)]}) is False
    assert demande_was_already_sent({}) is False


def test_serialize_collapses_noisy_historique():
    doc = {
        "id": "d1",
        "statut": STATUT_ENVOYEE,
        "historique": [
            _e(ACTION_CREEE, "t1"),
            _e(ACTION_ENVOYEE, "t2"),
            _e(ACTION_MODIFIEE, "t3"),
            _e(ACTION_MODIFIEE, "t4"),
            _e(ACTION_MODIFIEE, "t5"),
            {"action": "Note interne", "at": "t6"},
        ],
        "notes_internes": [{"note": "x"}],
    }
    from access_control import user_from_doc

    viewer = user_from_doc({
        "user_id": "u1",
        "email": "c@test.ch",
        "role": "conseiller",
        "active": True,
        "name": "C",
    })
    out = serialize_demande(doc, docs=[], viewer=viewer)
    actions = [e["action"] for e in out["historique"]]
    assert actions == [ACTION_CREEE, ACTION_ENVOYEE, ACTION_MODIFIEE]
    assert out["notes_internes"] == []


def test_ten_saves_still_one_modifiee():
    hist = [_e(ACTION_ENVOYEE, "t0")]
    for i in range(10):
        hist = apply_modification_to_historique(
            hist,
            history_entry(ACTION_MODIFIEE, by_name=f"User{i}"),
        )
    assert [e["action"] for e in hist] == [ACTION_ENVOYEE, ACTION_MODIFIEE]
    assert hist[-1]["by_name"] == "User9"
