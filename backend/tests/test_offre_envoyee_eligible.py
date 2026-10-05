from suivi_3p import is_offre_envoyee_eligible, is_analyse_pdf_doc


def test_eligible_needs_pdf_and_gain_over_250():
    docs = [{"category": "Analyse 3e Pilier", "original_filename": "x.pdf"}]
    assert is_analyse_pdf_doc(docs[0])
    assert not is_offre_envoyee_eligible({"gain_fiscal_estime": 200}, docs)
    assert is_offre_envoyee_eligible({"gain_fiscal_estime": 251}, docs)
    assert not is_offre_envoyee_eligible({"gain_fiscal_estime": 500}, [])
    assert not is_offre_envoyee_eligible(
        {"gain_fiscal_estime": 500},
        [{"kind": "courrier_optimisation_fiscale", "category": "Analyse 3e Pilier"}],
    )
