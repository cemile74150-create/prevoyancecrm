"""Tests classification géographique Suivi 3P (Frontalier / Suisse)."""
from suivi_3p import classify_residence_suivi, filter_suivi_3p_rows, serialize_suivi_client


def test_classify_france_address_is_frontalier():
    assert (
        classify_residence_suivi(
            {
                "adresse": "Rue des Italiens, 12",
                "npa": "74200",
                "ville": "Thonon Les Bains",
                "pays": "France",
            }
        )
        == "Frontalier"
    )


def test_classify_swiss_address_is_suisse():
    assert (
        classify_residence_suivi(
            {
                "adresse": "Rue du Lac 12",
                "npa": "1202",
                "ville": "Genève",
                "pays": "Suisse",
            }
        )
        == "Suisse"
    )


def test_classify_from_address_text_france_without_pays():
    assert (
        classify_residence_suivi(
            {"adresse": "20 Place des Aviateurs - F 74580 VIRY", "npa": "", "ville": ""}
        )
        == "Frontalier"
    )


def test_classify_prefers_address_over_stored_flag_conflict():
    # Adresse Suisse clairement identifiable → Suisse même si flag oui erroné
    assert (
        classify_residence_suivi(
            {
                "adresse": "Rue de la Paix 1",
                "npa": "1201",
                "ville": "Genève",
                "pays": "Suisse",
                "frontalier": "oui",
            }
        )
        == "Suisse"
    )


def test_filter_frontaliers_and_suisses_do_not_mix():
    rows = [
        {"id": "1", "nom": "A", "prenom": "Fr", "residence_suivi": "Frontalier", "statut_suivi": "À analyser"},
        {"id": "2", "nom": "B", "prenom": "Ch", "residence_suivi": "Suisse", "statut_suivi": "À analyser"},
        {"id": "3", "nom": "C", "prenom": "?", "residence_suivi": None, "statut_suivi": "À analyser"},
    ]
    fr = filter_suivi_3p_rows(rows, geo="frontaliers")
    ch = filter_suivi_3p_rows(rows, geo="suisses")
    assert [r["id"] for r in fr] == ["1"]
    assert [r["id"] for r in ch] == ["2"]


def test_serialize_includes_residence_suivi():
    row = serialize_suivi_client(
        {
            "id": "x",
            "prenom": "Wahiba",
            "nom": "BOUGRINI",
            "adresse": "Rue des Italiens, 12",
            "npa": "74200",
            "ville": "Thonon Les Bains",
            "pays": "France",
            "frontalier": "oui",
            "statut": "À analyser",
            "conseiller": None,
        }
    )
    assert row["residence_suivi"] == "Frontalier"
    assert row["conseiller"] is None
    assert row["frontalier"] == "oui"
