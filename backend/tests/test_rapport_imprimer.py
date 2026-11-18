"""Rapport à imprimer : tri, sélection, fusion PDF, documents manquants."""

import io

from pypdf import PdfWriter

from rapport_imprimer import (
    document_sort_rank,
    is_pdf_document,
    merge_pdf_bytes,
    normalize_document_ids,
    rapport_filename,
    resolve_ordered_documents,
    sort_documents_for_rapport,
)


def _one_page_pdf(text: str = "x") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    # text unused — blank pages suffice for merge count
    _ = text
    return buf.getvalue()


def test_is_pdf_document_accepts_filename_and_content_type():
    assert is_pdf_document({"original_filename": "Plan.pdf"})
    assert is_pdf_document({"content_type": "application/pdf"})
    assert not is_pdf_document({"original_filename": "note.docx", "content_type": "application/vnd.openxmlformats"})


def test_sort_puts_planification_before_other_categories():
    docs = [
        {"id": "1", "original_filename": "offre.pdf", "category": "Offre", "created_at": "2026-01-03"},
        {"id": "2", "original_filename": "plan.pdf", "category": "Analyse de prévoyance", "created_at": "2026-01-01"},
        {"id": "3", "original_filename": "lpp.pdf", "category": "Certificat LPP", "created_at": "2026-01-02"},
        {"id": "4", "original_filename": "reponse.pdf", "category": "Réponse recherche LPP", "created_at": "2026-01-02"},
    ]
    ordered = sort_documents_for_rapport(docs)
    assert [d["id"] for d in ordered] == ["2", "4", "3", "1"]
    assert document_sort_rank(docs[1])[0] < document_sort_rank(docs[0])[0]


def test_normalize_and_resolve_detects_missing_ids():
    ids = normalize_document_ids(["a", "a", "", "b", None])
    assert ids == ["a", "b"]
    available = {"a": {"id": "a", "original_filename": "a.pdf"}}
    found, missing = resolve_ordered_documents(["b", "a"], available)
    assert [d["id"] for d in found] == ["a"]
    assert missing == ["b"]


def test_merge_pdf_bytes_keeps_all_pages_without_mutating_inputs():
    p1 = _one_page_pdf("one")
    p2 = _one_page_pdf("two")
    original_p1 = bytes(p1)
    merged = merge_pdf_bytes([p1, p2])
    assert merged[:4] == b"%PDF"
    assert p1 == original_p1
    from pypdf import PdfReader

    assert len(PdfReader(io.BytesIO(merged)).pages) == 2


def test_merge_rejects_empty_selection():
    try:
        merge_pdf_bytes([])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_rapport_filename_slug():
    assert rapport_filename("DUBOIS", "Anne") == "Rapport_Planification_DUBOIS_Anne.pdf"
    assert "Rapport_Planification_" in rapport_filename("", "")


def test_saved_planification_and_all_document_families_are_eligible():
    """Critères 1–2 : planification enregistrée + tous PDF Documents listables."""
    families = [
        {"id": "plan", "original_filename": "Planif.pdf", "category": "Analyse de prévoyance"},
        {"id": "impot", "original_filename": "Impot.pdf", "category": "Déclaration fiscale"},
        {"id": "avs", "original_filename": "AVS.pdf", "category": "Formulaire AVS"},
        {"id": "rep", "original_filename": "RechercheLPP.pdf", "category": "Réponse recherche LPP"},
        {"id": "cert", "original_filename": "Certificat.pdf", "category": "Certificat LPP"},
        {"id": "3p", "original_filename": "Police3a.pdf", "category": "Police 3e pilier"},
        {"id": "offre", "original_filename": "Offre.pdf", "category": "Offre"},
        {"id": "autre", "original_filename": "Divers.pdf", "category": "Autre"},
    ]
    assert all(is_pdf_document(d) for d in families)
    ordered = sort_documents_for_rapport(families)
    assert ordered[0]["id"] == "plan"
    ids = {d["id"] for d in ordered}
    assert ids == {d["id"] for d in families}


def test_merge_respects_user_order_not_category_rank():
    """Critère 3 : l'ordre choisi (ids) prime sur le tri d'affichage."""
    # 1 page puis 2 pages : le PDF fusionné doit commencer par le doc 2 pages
    # si l'utilisateur le place en premier.
    one = _one_page_pdf("a")
    two_writer = PdfWriter()
    two_writer.add_blank_page(width=200, height=200)
    two_writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    two_writer.write(buf)
    two = buf.getvalue()

    available = {
        "small": {"id": "small", "original_filename": "plan.pdf", "category": "Analyse de prévoyance"},
        "big": {"id": "big", "original_filename": "offre.pdf", "category": "Offre"},
    }
    found, missing = resolve_ordered_documents(["big", "small"], available)
    assert missing == []
    assert [d["id"] for d in found] == ["big", "small"]

    # Simule la fusion dans cet ordre
    merged = merge_pdf_bytes([two, one])
    from pypdf import PdfReader

    pages = PdfReader(io.BytesIO(merged)).pages
    assert len(pages) == 3
