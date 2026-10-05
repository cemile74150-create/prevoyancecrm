"""Validation prénom/nom sur fiche Suivi 3P."""
from suivi_3p import serialize_suivi_client


def test_serialize_includes_prenom_nom():
    row = serialize_suivi_client({
        "id": "x",
        "prenom": "Raymond",
        "nom": "BAUD",
        "statut": "À analyser",
    })
    assert row["prenom"] == "Raymond"
    assert row["nom"] == "BAUD"
