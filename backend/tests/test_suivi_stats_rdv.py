from datetime import date, timedelta

from suivi_3p import compute_stats


def test_compute_stats_commercial_and_upcoming_rdv():
    today = date.today()
    past = (today - timedelta(days=3)).isoformat()
    future = (today + timedelta(days=5)).isoformat()
    rows = [
        {
            "id": "1",
            "prenom": "Alice",
            "nom": "A",
            "statut_suivi": "Offre envoyée",
            "client_contacte": True,
            "rdv_pris": True,
            "date_rdv": future,
            "conseiller": "MENDES Alberto",
            "gain_fiscal_estime": 500,
        },
        {
            "id": "2",
            "prenom": "Bob",
            "nom": "B",
            "statut_suivi": "À analyser",
            "client_contacte": False,
            "rdv_pris": False,
            "date_rdv": None,
            "conseiller": "X",
            "gain_fiscal_estime": None,
        },
        {
            "id": "3",
            "prenom": "Carla",
            "nom": "C",
            "statut_suivi": "Analyse en cours",
            "client_contacte": True,
            "rdv_pris": True,
            "date_rdv": past,
            "conseiller": "Y",
            "gain_fiscal_estime": 100,
        },
    ]
    s = compute_stats(rows)
    assert s["rdv_pris"] == 2
    assert s["clients_contactes"] == 2
    assert s["a_contacter"] == 1
    assert len(s["upcoming_rdvs"]) == 1
    assert s["upcoming_rdvs"][0]["id"] == "1"
    assert s["upcoming_rdvs"][0]["date_rdv"] == future
