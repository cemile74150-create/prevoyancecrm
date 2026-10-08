from datetime import date

from fiscal_reference import (
    FISCAL_ALERT_TEXT,
    apply_validation,
    apply_year_change,
    default_config,
    fiscal_alert,
    public_status,
)


def test_alerte_absente_avant_2027():
    config = default_config()
    assert fiscal_alert(date(2026, 12, 31), config["referenceYear"], None) is None
    assert public_status(config, date(2026, 12, 31))["alert"] is None
    assert public_status(config, date(2026, 12, 31))["referenceYear"] == 2025


def test_alerte_presente_le_1er_janvier_2027():
    config = default_config()
    text = fiscal_alert(date(2027, 1, 1), 2025, None)
    assert text == FISCAL_ALERT_TEXT
    assert "2025" in text
    assert public_status(config, date(2027, 1, 1))["alert"] == FISCAL_ALERT_TEXT


def test_changer_lannee_ne_valide_pas_les_baremes():
    config = apply_year_change(default_config(), 2027)
    assert config["referenceYear"] == 2027
    assert config["validatedReferenceYear"] is None
    assert fiscal_alert(date(2027, 1, 1), config["referenceYear"], config["validatedReferenceYear"]) == FISCAL_ALERT_TEXT


def test_alerte_disparait_seulement_apres_validation():
    config = apply_validation(default_config(), "2027-01-02T00:00:00")
    assert config["referenceYear"] == 2025
    assert config["validatedReferenceYear"] == 2025
    assert fiscal_alert(date(2027, 1, 2), config["referenceYear"], config["validatedReferenceYear"]) is None

    changed = apply_year_change(config, 2026)
    assert fiscal_alert(date(2027, 6, 1), changed["referenceYear"], changed["validatedReferenceYear"]) == FISCAL_ALERT_TEXT
    validated = apply_validation(changed, "2027-06-02T00:00:00")
    assert validated["validatedReferenceYear"] == 2026
    assert fiscal_alert(date(2027, 6, 2), validated["referenceYear"], validated["validatedReferenceYear"]) is None
