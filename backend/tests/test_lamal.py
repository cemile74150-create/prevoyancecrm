"""Comparateur LAMal : sécurité, primes OFSP, économies, e-mails sans envoi."""
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    LAMAL_OWNER_EMAIL,
    PERM_LAMAL_MODULE_ACCESS,
    ROLE_ADMIN,
    default_permissions,
    has_perm,
    permission_for_request,
    resolve_permissions,
    user_from_doc,
)
from lamal.engine import (  # noqa: E402
    Catalog,
    age_class_for_birth_year,
    commit_delivery,
    quote,
    render_email,
    resolve_residence,
    scan_premium_csv,
)
from lamal.people import client_view, is_opted_out, swiss_residence  # noqa: E402

FIXTURES = ROOT / "lamal" / "fixtures"
OFFICIAL = ROOT / "data" / "ofsp" / "Praemien_CH.csv"


def _catalog():
    report, offers = scan_premium_csv(FIXTURES / "premiums_2027_sample.csv", tariff_year=2027)
    assert report.ok, report.errors
    localities = json.loads((FIXTURES / "localities_sample.json").read_text(encoding="utf-8"))
    regions = {}
    for item in json.loads((FIXTURES / "regions_2027_sample.json").read_text(encoding="utf-8")):
        regions[item["bfs"]] = {**item, "region": f"PR_REG_{item['region']}"}
    return Catalog(year=2027, offers=offers, localities=localities, regions_by_bfs=regions)


def _profile(**kwargs):
    base = {
        "year": 2027,
        "birth_year": 1980,
        "with_accident": True,
        "franchise_chf": 300,
        "model_type": "BASE",
        "insurer_id": "8",
    }
    base.update(kwargs)
    return base


def test_lamal_permission_is_not_granted_to_other_admins():
    other = user_from_doc({
        "user_id": "user_other_admin",
        "email": "autre.admin@agencemendes.ch",
        "prenom": "Autre",
        "nom": "Admin",
        "role": ROLE_ADMIN,
        "permissions": {PERM_LAMAL_MODULE_ACCESS: True},
    })
    owner = user_from_doc({
        "user_id": "user_cemile",
        "email": LAMAL_OWNER_EMAIL,
        "prenom": "Cemile",
        "nom": "Demirtas",
        "role": ROLE_ADMIN,
    })
    assert default_permissions(ROLE_ADMIN)[PERM_LAMAL_MODULE_ACCESS] is False
    assert resolve_permissions({"role": ROLE_ADMIN, "email": "autre.admin@agencemendes.ch"})[PERM_LAMAL_MODULE_ACCESS] is False
    assert has_perm(other, PERM_LAMAL_MODULE_ACCESS) is False
    assert has_perm(owner, PERM_LAMAL_MODULE_ACCESS) is True
    assert permission_for_request("GET", "/api/lamal/dashboard") == PERM_LAMAL_MODULE_ACCESS
    assert permission_for_request("POST", "/api/lamal/emails/abc/send") == PERM_LAMAL_MODULE_ACCESS


def test_age_classes_follow_tariff_year():
    assert age_class_for_birth_year(2009, 2027) == "AKA_01_KIN"
    assert age_class_for_birth_year(2008, 2027) == "AKA_02_JUG"
    assert age_class_for_birth_year(2002, 2027) == "AKA_02_JUG"
    assert age_class_for_birth_year(2001, 2027) == "AKA_03_ERW"


def test_geneve_vaud_and_bern_regions_match_official_vectors():
    catalog = _catalog()
    geneve = resolve_residence(catalog, plz="1201", commune="Genève")
    assert geneve["ok"] and geneve["canton"] == "GE" and geneve["region"] == "PR_REG_0"
    lausanne = resolve_residence(catalog, plz="1003", commune="Lausanne")
    assert lausanne["region"] == "PR_REG_1" and lausanne["canton"] == "VD"
    aigle = resolve_residence(catalog, plz="1860", commune="Aigle")
    assert aigle["region"] == "PR_REG_2"
    bern = resolve_residence(catalog, plz="3004", commune="Bern")
    assert bern["region"] == "PR_REG_1"
    aarwangen = resolve_residence(catalog, plz="4912", commune="Aarwangen")
    assert aarwangen["region"] == "PR_REG_3"
    ambiguous = resolve_residence(catalog, plz="1860")
    assert ambiguous["ok"] and ambiguous["region"] == "PR_REG_2" and ambiguous["commune"] is None

    def premium(residence, insurer="8"):
        result = quote(catalog, _profile(residence=residence, insurer_id=insurer))
        reference = result["reference"]
        assert reference is not None
        return Decimal(reference["premium_month"])

    assert premium(geneve) == Decimal("791.00")
    assert premium(lausanne) == Decimal("748.00")
    assert premium(aigle) == Decimal("710.00")
    assert premium(bern) == Decimal("718.00")
    assert premium(aarwangen) == Decimal("605.00")
    without = quote(catalog, _profile(residence=geneve, with_accident=False))
    assert Decimal(without["reference"]["premium_month"]) == Decimal("735.60")


def test_savings_use_2027_official_premium_only():
    catalog = _catalog()
    residence = resolve_residence(catalog, plz="1201", commune="Genève")
    result = quote(catalog, _profile(
        residence=residence,
        known_premium="600",
        known_premium_year=2026,
    ))
    assert result["savings_reliable"] is True
    assert result["known_premium_ignored"]
    assert Decimal(result["reference"]["premium_month"]) == Decimal("791.00")
    offer = next(row for row in result["comparison_a"] if row["insurer_id"] == "312")
    assert Decimal(offer["premium_month"]) == Decimal("732.50")
    assert Decimal(offer["savings_month"]) == Decimal("58.50")
    assert Decimal(offer["savings_year"]) == Decimal("702.00")
    assert result["medical_recommendation"] is False
    assert result["subsidies_included"] is False
    higher = quote(catalog, _profile(residence=residence, franchise_chf=2500))
    assert Decimal(higher["reference"]["premium_month"]) == Decimal("662.70")
    assert all(row["franchise_chf"] == 2500 for row in higher["comparison_a"])
    note = higher["comparison_b"][0]["participation_note"]
    assert "n'est pas une prévision" in note


def test_incomplete_profile_blocks_savings_and_email_claims():
    catalog = _catalog()
    residence = resolve_residence(catalog, plz="1201", commune="Genève")
    blocked = quote(catalog, _profile(residence=residence, franchise_chf=None, insurer_id=None, model_type=None))
    assert blocked["ok"] is False
    assert blocked["savings_reliable"] is False
    unknown = quote(catalog, _profile(residence=residence, insurer_id=None, model_type=None))
    assert unknown["savings_reliable"] is False
    message = render_email({"nom": "Martin", "sexe": "Homme"}, unknown)
    assert message["kind"] == "sans_reference"
    assert "Économie mensuelle potentielle" not in message["body"]
    reliable = quote(catalog, _profile(residence=residence))
    claimed = render_email({"nom": "Martin", "sexe": "Homme"}, reliable)
    assert claimed["savings_claimed"] is True
    assert "58.50 CHF" in claimed["body"] or "58,50" in claimed["body"]
    assert "Martin" in claimed["body"]
    no_gain = dict(reliable)
    no_gain["savings_reliable"] = False
    no_gain["best_equivalent_alternative"] = None
    quiet = render_email({"nom": "Martin"}, no_gain)
    assert "Économie mensuelle potentielle" not in quiet["body"]


def test_send_is_blocked_without_real_transport(monkeypatch):
    monkeypatch.delenv("LAMAL_ALLOW_REAL_SEND", raising=False)
    called = {}

    def transport(payload):
        called["yes"] = payload

    blocked = commit_delivery({"to": "a@b.ch"}, confirm="ENVOYER-LAMAL", transport=transport)
    assert blocked["status"] == "envoi_bloque"
    assert "yes" not in called
    monkeypatch.setenv("LAMAL_ALLOW_REAL_SEND", "true")
    still = commit_delivery({"to": "a@b.ch"}, confirm="ENVOYER-LAMAL", transport=None)
    assert still["ok"] is False
    assert "yes" not in called


def test_french_residents_are_excluded_and_opt_out_is_respected():
    france = {"nom": "Durand", "npa": "74000", "ville": "Annecy", "pays": "France"}
    suisse = {"nom": "Martin", "npa": "1201", "ville": "Genève", "pays": "Suisse", "email": "martin@example.ch"}
    assert swiss_residence(france) is False
    assert swiss_residence(suisse) is True
    assert swiss_residence({"nom": "Inconnu"}) is None
    assert is_opted_out({"opposition_prospection": "oui"}) is True
    view = client_view(france, {}, None)
    assert view["swiss"] is False


def test_official_2027_file_when_present():
    if not OFFICIAL.exists():
        pytest.skip("Fichier officiel non téléchargé dans cet environnement")
    from lamal.engine import ACCIDENT_WITH

    report, offers = scan_premium_csv(OFFICIAL, tariff_year=2027)
    assert report.ok, report.errors
    assert {"GE", "VD", "BE"} <= report.cantons
    assert "ZE" not in report.cantons
    offer = offers[("8", "GE", "PR_REG_0", "AKA_03_ERW", "E1", ACCIDENT_WITH, "FRA_01_E_0300", "BASE")]
    assert offer.premium_month == Decimal("791.00")
