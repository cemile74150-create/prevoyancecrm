"""Download Content-Disposition must use the registered original filename."""

from __future__ import annotations

import re
import uuid
from urllib.parse import unquote

from server import (
    _content_disposition,
    _resolve_download_filename,
    _sanitize_download_filename,
)


def _filename_star(header: str) -> str:
    m = re.search(r"filename\*=UTF-8''([^;]+)", header, re.I)
    assert m, header
    return unquote(m.group(1))


def test_sanitize_keeps_registered_name_and_extension():
    assert _sanitize_download_filename("Contrat Swiss Life.pdf") == "Contrat Swiss Life.pdf"


def test_sanitize_strips_path_and_forbidden_chars_only():
    assert _sanitize_download_filename(r"uploads\foo/Contrat<>Swiss|Life?.pdf") == "ContratSwissLife.pdf"


def test_resolve_prefers_original_filename_not_storage_uuid():
    storage_uuid = f"{uuid.uuid4()}.pdf"
    record = {
        "original_filename": "Contrat Swiss Life.pdf",
        "storage_path": f"prevoyance-crm/uploads/u/{storage_uuid}",
        "title": "Autre titre",
    }
    assert _resolve_download_filename(record) == "Contrat Swiss Life.pdf"


def test_resolve_skips_uuid_original_filename():
    storage_uuid = f"{uuid.uuid4()}.pdf"
    record = {
        "original_filename": storage_uuid,
        "title": "Mandat client.pdf",
    }
    assert _resolve_download_filename(record) == "Mandat client.pdf"


def test_content_disposition_utf8_preserves_exact_name():
    header = _content_disposition("attachment", "Contrat Swiss Life.pdf")
    assert 'filename="Contrat Swiss Life.pdf"' in header
    assert _filename_star(header) == "Contrat Swiss Life.pdf"


def test_content_disposition_preserves_accents_in_filename_star():
    header = _content_disposition("inline", "Décompte LPP Mme.pdf")
    assert _filename_star(header) == "Décompte LPP Mme.pdf"
