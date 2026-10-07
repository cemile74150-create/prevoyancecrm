"""Le prénom affiché suit la fiche CRM, pas la copie figée dans l'analyse."""

from analyses_prefill import apply_crm_display_prenoms, refresh_report_display_prenoms

SEP = " – "


def _helfer_record():
    return {
        "id": "helfer-analyse",
        "input": {
            "salaireClient1": 93925,
            "salaireConjoint": 72866,
            "fortune": 0,
            "client1": {
                "prenom": "Wiliam",
                "nom": "HELFER",
                "dateNaissance": "1961-12-13",
            },
            "conjoint": {
                "prenom": "Ariane",
                "nom": "HELFER",
                "dateNaissance": "1963-01-20",
            },
            "withdrawalScenarios": [
                {"items": [{"label": "LPP Wiliam", "kind": "lpp", "titulaire": "client1"}]}
            ],
        },
        "results": {
            "impotRevenuCouple1": 4188,
            "client1": {"capitalLppRetire65": 350359, "renteLpp65": 21024},
            "conjoint": {"capitalLppRetire65": 74339, "renteLpp65": 16057},
            "timeline": {
                "years": [2027, 2028],
                "events": [
                    {
                        "year": 2027,
                        "label": f"LPP{SEP}Wiliam{SEP}Capital",
                        "amount": 350359,
                        "kind": "lpp",
                        "person": "client1",
                    },
                    {
                        "year": 2028,
                        "label": f"LPP{SEP}Ariane{SEP}Capital + rente",
                        "amount": 74339,
                        "kind": "lpp",
                        "person": "conjoint",
                    },
                    {
                        "year": 2027,
                        "label": f"AVS{SEP}Wiliam",
                        "amount": 24570,
                        "kind": "avs",
                        "person": "client1",
                    },
                ],
                "byYear": {
                    "2027": [
                        {
                            "label": f"LPP{SEP}Wiliam{SEP}Capital",
                            "amount": 350359,
                            "kind": "lpp",
                            "person": "client1",
                        }
                    ],
                    "2028": [
                        {
                            "label": f"LPP{SEP}Ariane{SEP}Capital + rente",
                            "amount": 74339,
                            "kind": "lpp",
                            "person": "conjoint",
                        }
                    ],
                },
            },
        },
    }


def test_stale_prenom_replaced_before_engine_and_timeline_relabeled():
    stored = _helfer_record()
    client = {"prenom": "William", "nom": "HELFER"}
    spouse = {"prenom": "Ariane", "nom": "HELFER"}

    sent = refresh_report_display_prenoms(stored, client, spouse)

    assert sent["input"]["client1"]["prenom"] == "William"
    assert sent["input"]["conjoint"]["prenom"] == "Ariane"
    labels = [event["label"] for event in sent["results"]["timeline"]["events"]]
    assert f"LPP{SEP}William{SEP}Capital" in labels
    assert f"LPP{SEP}Ariane{SEP}Capital + rente" in labels
    assert f"AVS{SEP}William" in labels
    assert sent["results"]["timeline"]["byYear"]["2027"][0]["label"] == f"LPP{SEP}William{SEP}Capital"

    assert sent["input"]["salaireClient1"] == 93925
    assert sent["input"]["client1"]["nom"] == "HELFER"
    assert sent["input"]["client1"]["dateNaissance"] == "1961-12-13"
    assert sent["input"]["withdrawalScenarios"][0]["items"][0]["label"] == "LPP Wiliam"
    assert sent["results"]["impotRevenuCouple1"] == 4188
    assert sent["results"]["client1"]["capitalLppRetire65"] == 350359
    assert sent["results"]["conjoint"]["capitalLppRetire65"] == 74339
    assert sent["results"]["timeline"]["events"][0]["amount"] == 350359
    assert sent["results"]["timeline"]["events"][1]["amount"] == 74339

    assert stored["input"]["client1"]["prenom"] == "Wiliam"
    assert stored["results"]["timeline"]["events"][0]["label"] == f"LPP{SEP}Wiliam{SEP}Capital"


def test_empty_crm_prenom_keeps_analysis_then_assure_fallback():
    kept = apply_crm_display_prenoms(
        {"client1": {"prenom": "Wiliam"}, "conjoint": {"prenom": "Ariane"}},
        {"prenom": "  "},
        {"prenom": ""},
    )
    assert kept["client1"]["prenom"] == "Wiliam"
    assert kept["conjoint"]["prenom"] == "Ariane"

    blank = refresh_report_display_prenoms(
        {
            "input": {"client1": {"prenom": ""}, "conjoint": {"prenom": "   "}},
            "results": {
                "timeline": {
                    "events": [
                        {"label": f"LPP{SEP}Wiliam{SEP}Rente", "person": "client1", "amount": 6000, "kind": "lpp"},
                        {"label": f"AVS{SEP}Ariane", "person": "conjoint", "amount": 1, "kind": "avs"},
                    ],
                    "byYear": {},
                }
            },
        },
        {"prenom": None},
        None,
    )
    assert blank["input"]["client1"]["prenom"] == ""
    assert blank["input"]["conjoint"]["prenom"] == "   "
    assert blank["results"]["timeline"]["events"][0]["label"] == f"LPP{SEP}Assuré 1{SEP}Rente"
    assert blank["results"]["timeline"]["events"][1]["label"] == f"AVS{SEP}Assuré 2"
    assert blank["results"]["timeline"]["events"][0]["amount"] == 6000


def test_spouse_card_updates_conjoint_without_creating_one():
    updated = apply_crm_display_prenoms(
        {
            "client1": {"prenom": "William", "nom": "HELFER"},
            "conjoint": {"prenom": "Anne", "nom": "HELFER"},
            "etatCivil": "Marié(e)",
        },
        {"prenom": "William"},
        {"prenom": "Ariane"},
    )
    assert updated["conjoint"]["prenom"] == "Ariane"
    assert updated["etatCivil"] == "Marié(e)"

    single = apply_crm_display_prenoms(
        {"client1": {"prenom": "Wiliam"}, "conjoint": None, "salaireClient1": 100},
        {"prenom": "William"},
        {"prenom": "Ariane"},
    )
    assert single["client1"]["prenom"] == "William"
    assert single["conjoint"] is None
    assert single["salaireClient1"] == 100
