from datetime import datetime, timedelta, timezone

from demandes_offres_3p import (
    compute_stats,
    count_variantes_sollicitees,
    filter_rows_by_period,
    period_bounds,
    STATUT_BROUILLON,
    STATUT_ENVOYEE,
)


def _row(**kwargs):
    base = {
        "id": "1",
        "statut": STATUT_ENVOYEE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agent_label": "Agent A",
        "form_type_label": "RC seule",
        "form_category": "RC / Ménage",
        "compagnies": ["Helvetia", "AXA"],
        "offres": [],
    }
    base.update(kwargs)
    return base


def test_count_variantes_one_demande_three_compagnies():
    row = _row(compagnies=["A", "B", "C"])
    assert count_variantes_sollicitees(row) == 3


def test_compute_stats_demandes_vs_variantes():
    rows = [
        _row(id="1", compagnies=["Helvetia", "AXA"]),
        _row(id="2", agent_label="Agent B", compagnies=["Zurich"]),
    ]
    s = compute_stats(rows)
    assert s["nb_demandes"] == 2
    assert s["nb_brouillons"] == 0
    assert s["nb_variantes_sollicitees"] == 3
    assert len(s["by_agent"]) == 2
    assert s["by_agent"][0]["nb_demandes"] >= 1


def test_compute_stats_separates_brouillons():
    rows = [
        _row(id="1", statut=STATUT_ENVOYEE, compagnies=["A"]),
        _row(id="2", statut=STATUT_BROUILLON, compagnies=["B", "C"]),
        _row(id="3", statut=STATUT_BROUILLON, compagnies=[]),
        _row(id="4", statut="Offre signée", compagnies=["D"]),
    ]
    s = compute_stats(rows)
    assert s["nb_brouillons"] == 2
    assert s["nb_demandes"] == 2
    assert s["total"] == 4
    # Variantes : brouillons exclus
    assert s["nb_variantes_sollicitees"] == 2
    agents = {a["agent"]: a for a in s["by_agent"]}
    assert agents["Agent A"]["nb_brouillons"] == 2
    assert agents["Agent A"]["nb_demandes"] == 2
    assert agents["Agent A"]["offres_signees"] == 1
    assert any(p["id"] == "brouillon" and p["count"] == 2 for p in s["pipeline"])


def test_compute_stats_separates_origine_conseiller_vs_attribuee():
    rows = [
        _row(id="1", demande_origine="conseiller"),
        _row(id="2", demande_origine="conseiller", statut=STATUT_BROUILLON),
        _row(id="3", demande_origine="attribuee", agent_label="Agent B"),
        _row(id="4", demande_origine="attribuee", statut="Demande annulée"),
    ]
    s = compute_stats(rows)
    assert s["nb_origine_conseiller"] == 2
    assert s["nb_origine_attribuee"] == 1
    assert s["nb_demandes_conseiller"] == 2
    assert s["nb_demandes_attribuees"] == 1
    assert s["by_origine"]["conseiller"] == 2
    assert s["by_origine"]["attribuee"] == 1


def test_compute_stats_offres_recues_kpi_counts_offre_recue_only():
    """KPI dashboard « Offres reçues » : statut « Offre reçue » uniquement."""
    from demandes_offres_3p import (
        STATUT_OFFRE_COMPLETE,
        STATUT_OFFRE_ENVOYEE_CLIENT,
        STATUT_OFFRE_RECUE,
    )

    rows = [
        _row(id="1", statut=STATUT_OFFRE_RECUE),
        _row(id="2", statut=STATUT_OFFRE_COMPLETE),
        _row(id="3", statut="Offre complète"),  # legacy → offres_completes
        _row(id="4", statut="Offre choisie"),
        _row(id="5", statut="Offre signée"),
        _row(id="6", statut=STATUT_ENVOYEE),
        _row(id="7", statut=STATUT_OFFRE_ENVOYEE_CLIENT),
        _row(id="8", statut=STATUT_OFFRE_RECUE),
    ]
    s = compute_stats(rows)
    assert s["offres_recues"] == 2
    assert s["offres_completes"] == 2
    assert s["offres_envoyees_client"] == 1


def test_filter_rows_by_period_month():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=400)).isoformat()
    rows = [_row(created_at=now.isoformat()), _row(id="2", created_at=old)]
    filtered, meta = filter_rows_by_period(rows, periode="year")
    assert len(filtered) == 1
    assert meta["periode"] == "year"
