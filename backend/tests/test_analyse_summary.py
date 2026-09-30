from suivi_3p import analyse_summary_from_docs, is_analyse_fortune_doc, is_analyse_3p_classic_doc


def test_classic_only():
    docs = [
        {
            "id": "a1",
            "category": "Analyse 3e Pilier",
            "original_filename": "DUPONT_Jean.pdf",
            "created_at": "2026-01-01",
        }
    ]
    s = analyse_summary_from_docs(docs)
    assert s["has_analyse_3p"] is True
    assert s["has_analyse_fortune"] is False
    assert s["analyse_fortune_doc_id"] is None


def test_fortune_badge_and_doc_id():
    docs = [
        {
            "id": "a1",
            "category": "Analyse 3e Pilier",
            "original_filename": "DUPONT_Jean.pdf",
            "created_at": "2026-01-01",
        },
        {
            "id": "f1",
            "category": "Analyse 3e Pilier",
            "display_label": "Analyse optimisation fiscale",
            "source_folder": "PDF - Analyse Fortune",
            "original_filename": "DUPONT Jean.pdf",
            "created_at": "2026-02-01",
        },
    ]
    assert is_analyse_3p_classic_doc(docs[0])
    assert is_analyse_fortune_doc(docs[1])
    s = analyse_summary_from_docs(docs)
    assert s["has_analyse_3p"] is True
    assert s["has_analyse_fortune"] is True
    assert s["analyse_fortune_doc_id"] == "f1"


def test_frontaliers_pdf_is_3p_not_fortune():
    docs = [
        {
            "id": "fr1",
            "category": "Analyse 3e Pilier",
            "display_label": "Analyse 3e Pilier",
            "source_folder": "PDF Frontaliers",
            "analyse_kind": "3p",
            "original_filename": "BEAUFRERE_Jean-Philippe.pdf",
            "created_at": "2026-09-18",
        }
    ]
    assert is_analyse_fortune_doc(docs[0]) is False
    assert is_analyse_3p_classic_doc(docs[0]) is True
    s = analyse_summary_from_docs(docs)
    assert s["has_analyse_3p"] is True
    assert s["has_analyse_fortune"] is False


def test_optimisation_label_without_fortune_folder_is_3p():
    """Ancien label « optimisation fiscale » hors dossier Fortune = 3e pilier."""
    doc = {
        "id": "x",
        "category": "Analyse 3e Pilier",
        "display_label": "Analyse optimisation fiscale",
        "source_folder": "PDF Frontaliers",
        "original_filename": "POULY_Quentin.pdf",
    }
    assert is_analyse_fortune_doc(doc) is False
    assert is_analyse_3p_classic_doc(doc) is True


def test_courrier_ignored():
    docs = [
        {
            "id": "c1",
            "category": "Analyse 3e Pilier",
            "kind": "courrier_optimisation_fiscale",
            "display_label": "Courrier optimisation fiscale – 01.01.2026",
            "created_at": "2026-03-01",
        }
    ]
    s = analyse_summary_from_docs(docs)
    assert s["has_analyse_3p"] is False
    assert s["has_analyse_fortune"] is False
