"""Offre signée : documents complémentaires et commentaire de l'agent."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    PERM_DEMANDES_OFFRES_EDIT,
    permission_for_request,
)
from demandes_offres_3p import (  # noqa: E402
    DOC_CATEGORY_DOCUMENT_SIGNATURE,
    DOC_CATEGORY_PROPOSITION_SIGNEE,
    STATUT_OFFRE_SIGNEE,
    build_signature_complement,
    serialize_demande,
    signature_document_ref,
    signature_history_detail,
)
from demandes_offres_routes import gestion_write_target  # noqa: E402


def test_complement_route_is_agent_route_not_gestion():
    path = "/api/demandes-offres/abc/signature/complements"
    assert permission_for_request("POST", path) == PERM_DEMANDES_OFFRES_EDIT
    assert gestion_write_target("POST", path) is None
    assert gestion_write_target("POST", "/api/demandes-offres/abc/signature") is None


def test_signature_document_ref_hides_storage():
    ref = signature_document_ref(
        {
            "id": "doc-1",
            "original_filename": "id.pdf",
            "content_type": "application/pdf",
            "size": 12,
            "storage_path": "secret/path",
            "category": DOC_CATEGORY_DOCUMENT_SIGNATURE,
            "created_at": "2026-11-10T10:00:00+00:00",
        },
        category=DOC_CATEGORY_DOCUMENT_SIGNATURE,
    )
    assert ref["id"] == "doc-1"
    assert ref["category"] == DOC_CATEGORY_DOCUMENT_SIGNATURE
    assert "storage_path" not in ref


def test_history_detail_combines_comment_and_count():
    docs = [{"id": "a"}, {"id": "b"}]
    assert signature_history_detail("Client OK", docs) == "Client OK · 2 documents"
    assert signature_history_detail("", [{"id": "a"}]) == "1 document"
    assert signature_history_detail("  Note  ", []) == "Note"
    assert signature_history_detail(None, None) == ""


def test_build_complement_keeps_author_and_valid_docs():
    entry = build_signature_complement(
        commentaire="  Mandat ajouté ",
        documents=[{"id": "d1", "original_filename": "m.pdf"}, {"original_filename": "sans id"}],
        by_name="Emeric Laugerette",
        by_id="agent-1",
        at="2026-11-10T10:00:00+00:00",
    )
    assert entry["id"]
    assert entry["commentaire"] == "Mandat ajouté"
    assert [d["id"] for d in entry["documents"]] == ["d1"]
    assert entry["by"] == "Emeric Laugerette"
    assert entry["by_id"] == "agent-1"
    assert entry["at"] == "2026-11-10T10:00:00+00:00"


def test_serialize_exposes_signature_documents_and_complements():
    doc = {
        "id": "d1",
        "statut": STATUT_OFFRE_SIGNEE,
        "signature": {
            "signee": True,
            "commentaire": "Signé en agence",
            "document_id": "p1",
            "document_category": DOC_CATEGORY_PROPOSITION_SIGNEE,
            "documents": [
                {"id": "p1", "category": DOC_CATEGORY_PROPOSITION_SIGNEE},
                {"id": "x1", "category": DOC_CATEGORY_DOCUMENT_SIGNATURE},
            ],
            "complements": [
                {"id": "c1", "commentaire": "IBAN", "documents": [{"id": "x2"}]},
            ],
        },
    }
    out = serialize_demande(doc)
    assert out["signature"]["commentaire"] == "Signé en agence"
    assert [d["id"] for d in out["signature"]["documents"]] == ["p1", "x1"]
    assert out["signature"]["complements"][0]["documents"][0]["id"] == "x2"
    assert out["client_signe"] is True
