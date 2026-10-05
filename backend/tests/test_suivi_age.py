"""Âge Suivi 3P : années révolues, tranches, date extraite sans réimport."""
from datetime import date

from suivi_3p import (
    age_filter_bounds,
    age_matches,
    attach_computed_age,
    birth_date_to_store,
    completed_age,
    filter_suivi_3p_rows,
    parse_date_naissance_from_analyse_text,
    resolve_birth_date,
)


def test_completed_age_birthday_today_is_that_age():
    assert completed_age("1976-10-05", today=date(2026, 10, 5)) == 50


def test_completed_age_day_before_birthday():
    assert completed_age("1976-10-05", today=date(2026, 10, 4)) == 49


def test_completed_age_missing_or_invalid_is_empty():
    assert completed_age(None, today=date(2026, 10, 5)) is None
    assert completed_age("", today=date(2026, 10, 5)) is None
    assert completed_age("pas-une-date", today=date(2026, 10, 5)) is None
    assert completed_age("32.13.1970", today=date(2026, 10, 5)) is None
    assert completed_age("2027-01-01", today=date(2026, 10, 5)) is None


def test_brackets_and_custom_range_overrides_preset():
    assert age_matches(49, age_filter_bounds("lt50", None, None))
    assert not age_matches(50, age_filter_bounds("lt50", None, None))
    assert age_matches(50, age_filter_bounds("50-54", None, None))
    assert age_matches(54, age_filter_bounds("50-54", None, None))
    assert not age_matches(55, age_filter_bounds("50-54", None, None))
    assert age_matches(55, age_filter_bounds("55-59", None, None))
    assert age_matches(60, age_filter_bounds("60-64", None, None))
    assert age_matches(64, age_filter_bounds("60-64", None, None))
    assert not age_matches(65, age_filter_bounds("60-64", None, None))
    assert age_matches(65, age_filter_bounds("65plus", None, None))
    assert not age_matches(64, age_filter_bounds("65plus", None, None))

    # min/max (ex. 55 à 62) remplace la tranche « moins de 50 »
    bounds = age_filter_bounds("lt50", 55, 62)
    assert age_matches(55, bounds)
    assert age_matches(62, bounds)
    assert not age_matches(49, bounds)
    assert not age_matches(63, bounds)
    assert age_matches(None, None)
    assert not age_matches(None, bounds)


def test_filter_hides_missing_age_only_when_age_filter_is_active():
    rows = [
        {"id": "1", "nom": "A", "prenom": "Anne", "statut_suivi": "À analyser", "age": None},
        {"id": "2", "nom": "B", "prenom": "Bob", "statut_suivi": "À analyser", "age": 61},
        {"id": "3", "nom": "C", "prenom": "Celine", "statut_suivi": "À analyser", "age": 48},
    ]
    assert [r["id"] for r in filter_suivi_3p_rows(rows)] == ["1", "2", "3"]
    assert [r["id"] for r in filter_suivi_3p_rows(rows, age_bracket="60-64")] == ["2"]
    assert [r["id"] for r in filter_suivi_3p_rows(rows, age_bracket="lt50", age_min=55, age_max=62)] == ["2"]


def test_parse_birth_date_on_following_line():
    text = "Etat civil : \nCelibataire\n\nDate de naissance : \n04.10.1976\n\nRevenu imposable"
    assert parse_date_naissance_from_analyse_text(text) == "1976-10-04"
    assert completed_age("1976-10-04", today=date(2026, 10, 5)) == 50


def test_already_imported_uses_extracted_date_without_client_field():
    row = {"id": "c1", "prenom": "Jean", "nom": "Martin", "date_naissance": None}
    docs = {
        "c1": [
            {
                "is_deleted": False,
                "created_at": "2024-01-01",
                "extracted_date_naissance": "12.05.1968",
            }
        ]
    }
    assert resolve_birth_date(row, docs["c1"]) == "1968-05-12"
    enriched = attach_computed_age([row], docs, today=date(2026, 10, 5))
    assert enriched[0]["age"] == 58
    assert enriched[0]["date_naissance"] is None


def test_client_birth_date_wins_over_extracted_alias():
    row = {"date_naissance": "1980-01-15"}
    docs = [{"dateNaissance": "1970-01-01", "extracted": {"geburtsdatum": "1960-01-01"}}]
    assert resolve_birth_date(row, docs) == "1980-01-15"


def test_birth_date_saved_only_when_empty():
    assert birth_date_to_store(None, "04.10.1976") == "1976-10-04"
    assert birth_date_to_store("", "1976-10-04") == "1976-10-04"
    assert birth_date_to_store("1980-01-01", "1976-10-04") is None
    assert birth_date_to_store("enc:v1:abc", "1976-10-04") is None
