"""Dates JJ.MM.AAAA — pas de double-expansion, réparation années mangled."""
from swiss_dates import expand_short_year, format_swiss_date, repair_mangled_year


def test_repair_mangled_year():
    assert repair_mangled_year("201971") == "1971"
    assert repair_mangled_year("202026") == "2026"
    assert repair_mangled_year("202010") == "2010"
    assert repair_mangled_year("1971") == "1971"
    assert repair_mangled_year("2026") == "2026"
    assert repair_mangled_year("2020") == "2020"
    assert repair_mangled_year("20") == "20"


def test_expand_short_year_only_two_digits():
    assert expand_short_year("20") == "2020"
    assert expand_short_year("18") == "2018"
    assert expand_short_year("71") == "1971"
    assert expand_short_year("1971") == "1971"
    assert expand_short_year("2026") == "2026"
    assert expand_short_year("201971") == "1971"


def test_format_swiss_date_exact_examples():
    assert format_swiss_date("10.02.1971") == "10.02.1971"
    assert format_swiss_date("24.09.2026") == "24.09.2026"
    assert format_swiss_date("03.11.2010") == "03.11.2010"
    assert format_swiss_date("1971-02-10") == "10.02.1971"
    assert format_swiss_date("2026-09-24") == "24.09.2026"


def test_format_swiss_date_repairs_mangled():
    assert format_swiss_date("10.02.201971") == "10.02.1971"
    assert format_swiss_date("24.09.202026") == "24.09.2026"
    assert format_swiss_date("03.11.202010") == "03.11.2010"


def test_format_swiss_date_short_year_intentional():
    assert format_swiss_date("15.06.20") == "15.06.2020"
    assert format_swiss_date("15.06.18") == "15.06.2018"
    assert format_swiss_date("10.02.71") == "10.02.1971"


def test_format_demande_offre_email_dates_not_mangled(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    import email_service as es
    from offre_form_types import format_schema_field_value

    assert format_schema_field_value({"type": "date"}, "10.02.1971") == "10.02.1971"
    assert format_schema_field_value({"type": "date"}, "10.02.201971") == "10.02.1971"
    assert format_schema_field_value({"type": "date"}, "24.09.2026") == "24.09.2026"
    assert format_schema_field_value({"type": "date"}, "24.09.202026") == "24.09.2026"
    assert format_schema_field_value({"type": "date"}, "03.11.2010") == "03.11.2010"

    _, text, html = es.format_demande_offre_email(
        {
            "id": "d-dates",
            "numero": "OFF-2026-DATE",
            "form_type": "vehicule",
            "form_type_label": "Véhicule",
            "prenom": "Test",
            "nom": "Dates",
            "date_naissance": "10.02.201971",
            "form_payload": {
                "input_134": "Assurance véhicule",
                "input_3": "10.02.1971",
                "input_53": "24.09.202026",
            },
        }
    )
    assert "10.02.1971" in text
    assert "24.09.2026" in text
    assert "201971" not in text
    assert "202026" not in text
    assert "10.02.1971" in html
    assert "24.09.2026" in html
