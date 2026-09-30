"""Tests N° FINMA associé au conseiller."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from server import _conseiller_name_key  # noqa: E402


def test_conseiller_name_key_normalizes():
    assert _conseiller_name_key(" Alberto  Mendes ") == "alberto mendes"
    assert _conseiller_name_key("ALBERTO MENDES") == _conseiller_name_key("alberto mendes")
    assert _conseiller_name_key("José García") == "jose garcia"
    assert _conseiller_name_key("Valentin LUGNIER") == _conseiller_name_key("Valentin Lugnier")
    assert _conseiller_name_key("") == ""
    assert _conseiller_name_key(None) == ""
