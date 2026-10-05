from analyses_prefill import civilite_from_client, is_married, prefill_from_clients, to_iso_date


def test_iso_and_swiss_dates():
    assert to_iso_date("1961-12-13") == "1961-12-13"
    assert to_iso_date("13.12.1961") == "1961-12-13"
    assert to_iso_date("") == ""


def test_prefill_married_with_spouse():
    client = {
        "prenom": "Wiliam",
        "nom": "HELFER",
        "date_naissance": "13.12.1961",
        "sexe": "Homme",
        "etat_civil": "Marié",
        "npa": "1700",
        "ville": "Fribourg",
        "salaire_annuel": 90000,
        "conseiller": "Cemile",
    }
    spouse = {
        "prenom": "Anne",
        "nom": "HELFER",
        "date_naissance": "1964-04-02",
        "sexe": "Femme",
        "salaire_annuel": 40000,
    }
    data = prefill_from_clients(client, spouse, conseiller_nom="Autre")
    assert data["etatCivil"] == "Marié(e)"
    assert data["client1"]["nom"] == "HELFER"
    assert data["client1"]["dateNaissance"] == "1961-12-13"
    assert data["client1"]["civilite"] == "Monsieur"
    assert data["client1"]["lppPctDeblocable"] == 100
    assert data["salaireClient1"] == 90000
    assert data["villeRecherche"] == "1700 Fribourg"
    assert data["conjoint"]["prenom"] == "Anne"
    assert data["conjoint"]["civilite"] == "Madame"
    assert data["salaireConjoint"] == 40000
    assert data["libresPassages"] == []
    assert data["withdrawalScenarios"] == []
    assert data["conseillerNom"] == "Cemile"
    assert "telephone" not in data
    assert "email" not in data
    assert "adresse" not in data
    assert is_married(client) is True
    assert is_married({"etat_civil": "Partenariat enregistré"}) is True
    assert civilite_from_client({"sexe": "Femme"}) == "Madame"


def test_prefill_single_client_keeps_existing_fields_only():
    client = {
        "prenom": "Jean",
        "nom": "Ferreyres",
        "date_naissance": "1971-05-04",
        "sexe": "Homme",
        "etat_civil": "Célibataire",
        "adresse": "Rue du Test 1",
        "npa": "1003",
        "ville": "Lausanne",
        "pays_residence": "Suisse",
        "telephone": "0210000000",
        "email": "jean@example.test",
        "salaire_annuel": 120000,
        "conseiller": "Cemile Demirtas",
    }
    data = prefill_from_clients(client, conseiller_nom="Autre")
    assert data["etatCivil"] == "Personne vivant seule"
    assert data["conjoint"] is None
    assert data["client1"]["prenom"] == "Jean"
    assert data["client1"]["nom"] == "Ferreyres"
    assert data["client1"]["dateNaissance"] == "1971-05-04"
    assert data["salaireClient1"] == 120000
    assert data["villeRecherche"] == "1003 Lausanne"
    assert data["conseillerNom"] == "Cemile Demirtas"
    assert "telephone" not in data and "email" not in data


def test_prefill_married_label_without_spouse_fiche():
    data = prefill_from_clients({
        "prenom": "Jean",
        "nom": "Martin",
        "sexe": "Homme",
        "etat_civil": "Marié(e)",
        "conjoint": "Anne Martin",
    })
    assert data["etatCivil"] == "Marié(e)"
    assert data["conjoint"]["prenom"] == "Anne"
    assert data["conjoint"]["nom"] == "Martin"
    assert data["conjoint"]["civilite"] == "Madame"
