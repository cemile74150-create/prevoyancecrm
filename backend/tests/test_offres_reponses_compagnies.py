"""Tests réponses multi-compagnies / multi-documents demandes d'offres."""
from demandes_offres_3p import (
    STATUT_COMPAGNIE_EN_ATTENTE,
    STATUT_COMPAGNIE_RECUE,
    STATUT_ENVOYEE,
    STATUT_OFFRE_RECUE,
    STATUT_OFFRE_SIGNEE,
    all_solicited_companies_have_offer,
    append_documents_to_offre,
    build_reponses_compagnies,
    normalize_offre_documents,
    normalize_offres_list,
    offer_has_received_payload,
    resolve_statut_apres_reception_offre,
    serialize_demande,
    upsert_company_offre,
)


def test_normalize_migrates_legacy_document_id():
    offer = {
        "id": "o1",
        "compagnie": "AXA",
        "document_id": "doc-1",
        "document_filename": "offre-axa.pdf",
        "statut": "Reçue",
    }
    docs = normalize_offre_documents(offer)
    assert len(docs) == 1
    assert docs[0]["id"] == "doc-1"
    assert docs[0]["original_filename"] == "offre-axa.pdf"


def test_append_documents_never_replaces():
    offer = {
        "id": "o1",
        "compagnie": "AXA",
        "documents": [{"id": "d1", "original_filename": "a.pdf"}],
        "statut": "Offre reçue",
    }
    updated = append_documents_to_offre(
        offer,
        [{"id": "d2", "original_filename": "b.pdf", "content_type": "application/pdf"}],
    )
    ids = [d["id"] for d in updated["documents"]]
    assert ids == ["d1", "d2"]


def test_upsert_keeps_one_card_per_company():
    offres = [
        {"id": "o1", "compagnie": "AXA", "statut": "Offre reçue", "date_reception": "2026-01-01", "documents": [{"id": "d1"}]},
    ]
    merged = upsert_company_offre(
        offres,
        {
            "id": "o-new",
            "compagnie": "AXA",
            "statut": "Offre reçue",
            "date_reception": "2026-01-02",
            "documents": [{"id": "d2", "original_filename": "suite.pdf"}],
        },
    )
    assert len(merged) == 1
    assert merged[0]["id"] == "o1"
    assert {d["id"] for d in merged[0]["documents"]} == {"d1", "d2"}


def test_partial_response_does_not_mark_demande_offre_recue():
    doc = {
        "statut": STATUT_ENVOYEE,
        "compagnies": ["AXA", "Helvetia"],
        "date_envoi": "2026-01-01T00:00:00+00:00",
        "offres": [
            {"id": "o1", "compagnie": "AXA", "statut": "Offre reçue", "date_reception": "2026-01-05"},
        ],
    }
    offres = normalize_offres_list(doc)
    assert all_solicited_companies_have_offer(doc, offres) is False
    assert resolve_statut_apres_reception_offre(doc, offres) == STATUT_ENVOYEE


def test_all_companies_received_sets_offre_recue():
    doc = {
        "statut": STATUT_ENVOYEE,
        "compagnies": ["AXA", "Helvetia"],
        "date_envoi": "2026-01-01T00:00:00+00:00",
        "offres": [
            {"id": "o1", "compagnie": "AXA", "statut": "Offre reçue", "date_reception": "2026-01-05"},
            {"id": "o2", "compagnie": "Helvetia", "statut": "Offre reçue", "date_reception": "2026-01-06"},
        ],
    }
    offres = normalize_offres_list(doc)
    assert all_solicited_companies_have_offer(doc, offres) is True
    assert resolve_statut_apres_reception_offre(doc, offres) == STATUT_OFFRE_RECUE


def test_reponses_compagnies_independent_status():
    doc = {
        "statut": STATUT_ENVOYEE,
        "compagnies": ["AXA", "Helvetia", "Vaudoise"],
        "offres": [
            {
                "id": "o1",
                "compagnie": "AXA",
                "statut": "Reçue",
                "date_reception": "2026-01-05",
                "document_id": "d1",
            },
        ],
    }
    cards = build_reponses_compagnies(doc)
    assert len(cards) == 3
    by_name = {c["compagnie"]: c for c in cards}
    assert by_name["AXA"]["statut"] == STATUT_COMPAGNIE_RECUE
    assert by_name["AXA"]["has_offre"] is True
    assert len(by_name["AXA"]["documents"]) == 1
    assert by_name["Helvetia"]["statut"] == STATUT_COMPAGNIE_EN_ATTENTE
    assert by_name["Helvetia"]["has_offre"] is False
    assert by_name["Vaudoise"]["has_offre"] is False


def test_serialize_exposes_reponses_and_client_signe():
    doc = {
        "id": "d1",
        "numero": "2026-0009",
        "statut": STATUT_OFFRE_SIGNEE,
        "compagnies": ["AXA"],
        "offres": [{"id": "o1", "compagnie": "AXA", "statut": "Offre reçue", "date_reception": "2026-01-01"}],
        "signature": {"signee": True, "date_signature": "2026-02-01"},
        "historique": [],
    }
    out = serialize_demande(doc)
    assert out["client_signe"] is True
    assert len(out["reponses_compagnies"]) == 1
    assert offer_has_received_payload(out["offres"][0]) is True


def test_legacy_retenue_normalizes_to_offre_recue():
    """Ancienne sélection « Offre retenue » → affichée comme Offre reçue, sans flag retenue."""
    from demandes_offres_3p import normalize_company_offer_statut, normalize_offre_entry

    assert normalize_company_offer_statut("Offre retenue", retenue=True) == STATUT_COMPAGNIE_RECUE
    assert normalize_company_offer_statut("Choisie") == STATUT_COMPAGNIE_RECUE
    entry = normalize_offre_entry({
        "id": "o1",
        "compagnie": "AXA",
        "statut": "Offre retenue",
        "retenue": True,
        "date_reception": "2026-01-01",
    })
    assert entry["statut"] == STATUT_COMPAGNIE_RECUE
    assert entry["retenue"] is False

    doc = {
        "statut": STATUT_OFFRE_SIGNEE,
        "compagnies": ["AXA"],
        "offre_choisie_id": "o1",
        "offre_retenue": {"offre_id": "o1", "compagnie": "AXA"},
        "offres": [{
            "id": "o1",
            "compagnie": "AXA",
            "statut": "Offre retenue",
            "retenue": True,
            "date_reception": "2026-01-01",
        }],
        "signature": {"signee": True},
        "historique": [],
    }
    cards = build_reponses_compagnies(doc)
    assert len(cards) == 1
    assert cards[0]["statut"] == STATUT_COMPAGNIE_RECUE
    assert cards[0]["retenue"] is False
    out = serialize_demande(doc)
    assert out["offre_retenue"] is None
    assert out["offre_choisie_id"] is None
    assert out["reponses_compagnies"][0]["statut"] == STATUT_COMPAGNIE_RECUE
