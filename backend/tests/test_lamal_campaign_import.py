"""Import des listes Excel de campagne LAMal : colonnes, primes OFSP, brouillon."""
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import re

from lamal.campaign_lists import (  # noqa: E402
    CALENDLY_LAMAL_URL,
    EMAIL_SUBJECT,
    MAIL_NAVY,
    MAIL_TURQUOISE,
    PRIMEINFO_URL_MISSING,
    apply_identity_edit,
    calculation_payload,
    plan_prepare,
    present_person,
    primeinfo_url,
    refuse_campaign_delivery,
    reimport_decisions,
    render_contact_email,
    save_draft_text,
    summarize,
    build_premium_index,
    load_ofsp_catalog,
    parse_workbook,
)
from lamal.engine import Catalog, scan_premium_csv  # noqa: E402

FIXTURES = ROOT / "lamal" / "fixtures"


def _catalog():
    report, offers = scan_premium_csv(FIXTURES / "premiums_2027_sample.csv", tariff_year=2027)
    assert report.ok, report.errors
    localities = json.loads((FIXTURES / "localities_sample.json").read_text(encoding="utf-8"))
    regions = {}
    for item in json.loads((FIXTURES / "regions_2027_sample.json").read_text(encoding="utf-8")):
        regions[item["bfs"]] = {**item, "region": f"PR_REG_{item['region']}"}
    return Catalog(
        year=2027,
        offers=offers,
        localities=localities,
        regions_by_bfs=regions,
        tariff_names={
            ("8", "01_016"): "Assurance Cabinets de santé",
            ("8", "01_046"): "Assurance du médecin de famille Profit",
            ("8", "01_131"): "Callmed",
            ("8", "01_170"): "Multimed",
        },
    )


def _workbook(sheets):
    book = openpyxl.Workbook()
    first = True
    for name, rows in sheets:
        sheet = book.active if first else book.create_sheet(name)
        first = False
        sheet.title = name
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_parse_skips_empty_rows_and_duplicate_people(tmp_path):
    payload = _workbook([
        ("Liste", [
            ["Prénom", "Nom de famille", "Date de naissance", "Âge", "NPA", "Lieu", "Email", "Compagnie d'assurances"],
            ["Ada", "Martin", datetime(1980, 5, 2), 46, 1201, "Genève", "ada@example.ch", "ASSURA"],
            [None, None, None, None, None, None, None, None],
            ["Ada", "Martin", datetime(1980, 5, 2), 46, 1201, "Genève", "ada@example.ch", "ASSURA"],
            ["Lina", "Martin", datetime(2018, 3, 1), 8, 1201, "Genève", "lina@example.ch", "CSS"],
        ]),
        ("Alias", [
            ["Prenom", "Nom", "Date de naissance", "Code postal", "Commune", "E-mail"],
            ["Paul", "Roch", datetime(1990, 1, 1), 1003, "Lausanne", "paul@example.ch"],
        ]),
        ("Vide", [["Foo", "Bar"], ["x", "y"]]),
    ])
    parsed = parse_workbook(payload)
    assert parsed["skipped_empty"] == 1
    assert parsed["duplicates_skipped"] == 1
    assert [row["prenom"] for row in parsed["contacts"]] == ["Ada", "Lina", "Paul"]
    ada = parsed["contacts"][0]
    assert ada["nom"] == "Martin"
    assert ada["npa"] == "1201"
    assert ada["naissance"] == "1980-05-02"
    assert ada["assureur"] == "ASSURA"
    assert ada["lieu"] == "Genève"
    assert "Prénom" in parsed["headers"]
    assert load_ofsp_catalog(tmp_path) is None


def _hrefs(body: str) -> list[str]:
    return re.findall(r"""href=["']([^"']+)["']""", body)


def test_email_keeps_only_the_cheapest_offer_per_model():
    catalog = _catalog()
    index = build_premium_index(catalog)
    message = render_contact_email(
        {"prenom": "Ada", "nom": "Martin", "npa": "1201", "lieu": "Genève", "naissance": "1980-05-02", "assureur": "HELSANA"},
        catalog,
        index,
    )
    body = message["body"]
    assert message["subject"] == EMAIL_SUBJECT
    assert "Bonjour Ada," in body
    assert "VOTRE COMPARATIF PERSONNALISÉ" in body
    assert "Primes d'assurance-maladie" in body
    assert "pour l'année 2027" in body
    assert body.count("Comparaison des primes mensuelles") == 2
    assert "Franchise de 300 CHF" in body
    assert "Franchise de 2’500 CHF" in body
    assert "Et vos assurances complémentaires ?" in body
    assert "L'équipe Agence Mendes" in body
    assert "avec couverture accidents" in body
    assert "non disponible" not in body
    assert "[—]" not in body
    assert body.count("Médecin de famille") == 2
    assert body.count("Télémédecine") == 2
    assert body.count("Flexible") == 2
    assert "Assurance du médecin de famille Profit" in body
    assert "640.70 CHF" in body
    assert "512.40 CHF" in body
    assert "SmartCare" in body
    assert "644.60 CHF" in body
    assert "516.30 CHF" in body
    assert "Multimed" in body
    assert "688.20 CHF" in body
    assert "Callmed" not in body
    assert "707.90" not in body
    assert "680.30" not in body
    assert "556.00" not in body
    assert "Assurance Cabinets de santé" not in body
    assert MAIL_NAVY in body
    assert MAIL_TURQUOISE in body
    assert "#800000" not in body
    assert "#002FA7" not in body
    assert _hrefs(body) == ["https://www.agencemendes.ch"]
    assert "priminfo" not in body.lower()
    assert primeinfo_url("8") is None
    assert "numéro OFSP" in PRIMEINFO_URL_MISSING
    assert CALENDLY_LAMAL_URL == ""
    assert "Prendre rendez-vous" not in body
    assert "calendly" not in body.lower()
    assert "Route de Saint-Julien 277, 1258 Perly – Genève" in body
    assert "+41 22 339 30 10" in body
    assert "[Compagnie]" not in body
    assert "À compléter" not in body
    assert "HELSANA" not in body
    assert message["calculated"]["premiums_found"] == 6
    assert message["calculated"]["accident"] == "avec"
    for franchise in (300, 2500):
        for code in ("PRAXIS", "TEL_DIG", "FLEX"):
            assert len(message["calculated"]["table"][franchise][code]) == 1


def test_unknown_cells_stay_dash_without_inventing_a_child_franchise():
    catalog = _catalog()
    index = build_premium_index(catalog)
    child = render_contact_email(
        {"prenom": "Lina", "nom": "Martin", "npa": "1201", "lieu": "Genève", "naissance": "2018-03-01"},
        catalog,
        index,
    )
    body = child["body"]
    assert "Bonjour Lina," in body
    assert "Franchise de 300 CHF" in body
    assert "Franchise de 2’500 CHF" in body
    assert "plafond officiel 600" in body
    assert body.count("non disponible") == 6
    assert "[Compagnie]" not in body
    assert "[—]" not in body
    assert "— CHF" not in body
    assert child["brouillon_statut"] == "a_verifier"
    assert MAIL_NAVY in body
    assert "#800000" not in body
    assert "640.70" not in body
    assert "163.30" not in body
    assert child["calculated"]["age_class"] == "AKA_01_KIN"
    assert child["calculated"]["premiums_found"] == 0
    assert _hrefs(body) == ["https://www.agencemendes.ch"]

    missing = render_contact_email(
        {"prenom": "Noe", "nom": "Blanc", "naissance": "1980-05-02"},
        catalog,
        index,
    )
    assert missing["calculated"]["residence"]["ok"] is False
    assert "640.70" not in missing["body"]
    assert missing["calculated"]["premiums_found"] == 0


def test_workbook_without_known_columns_is_rejected():
    payload = _workbook([("Feuille", [["Foo", "Bar"], ["1", "2"]])])
    try:
        parse_workbook(payload)
    except ValueError as exc:
        assert "Colonnes non reconnues" in str(exc)
    else:
        raise AssertionError("le classeur sans colonnes client aurait dû être refusé")


def test_import_keeps_people_without_email_or_premium_and_preserves_npa():
    payload = _workbook([
        ("Liste", [
            ["Prénom", "Nom de famille", "Date de naissance", "Âge", "NPA", "Lieu", "Email", "Remarque"],
            ["Ada", "Martin", datetime(1980, 5, 2), 99, "0123", "Genève", "", "dossier 4"],
            ["Noe", "Blanc", datetime(1981, 1, 2), 45, None, "Genève", "noe@example.ch", ""],
            [None, None, None, None, None, None, None, None],
        ]),
    ])
    parsed = parse_workbook(payload)
    assert parsed["skipped_empty"] == 1
    assert len(parsed["contacts"]) == 2
    ada = parsed["contacts"][0]
    assert ada["email"] == ""
    assert ada["npa"] == "0123"
    assert ada["age_fichier"] == "99"
    assert ada["extras"]["Remarque"] == "dossier 4"
    assert ada["ligne"] == 2
    assert parsed["contacts"][1]["npa"] == ""
    assert parsed["contacts"][1]["prenom"] == "Noe"


def test_categories_do_not_share_premiums():
    catalog = _catalog()
    index = build_premium_index(catalog)
    adult = render_contact_email(
        {"prenom": "Ada", "nom": "Martin", "npa": "1201", "lieu": "Genève", "naissance": "1980-05-02", "email": "ada@example.ch", "age_fichier": "8"},
        catalog,
        index,
    )
    child = render_contact_email(
        {"prenom": "Lina", "nom": "Martin", "npa": "1201", "lieu": "Genève", "naissance": "2018-03-01", "email": "lina@example.ch", "age_fichier": "46"},
        catalog,
        index,
    )
    youth = render_contact_email(
        {"prenom": "Paul", "nom": "Roch", "npa": "1201", "lieu": "Genève", "naissance": "2002-06-01", "email": "paul@example.ch"},
        catalog,
        index,
    )
    assert adult["body"] != child["body"]
    assert "Bonjour Ada," in adult["body"]
    assert "Bonjour Lina," in child["body"]
    assert "Bonjour Paul," in youth["body"]
    assert adult["calculated"]["age_class"] == "AKA_03_ERW"
    assert adult["calculated"]["categorie"] == "adulte"
    assert adult["calculated"]["age"] == 47
    assert child["calculated"]["categorie"] == "enfant"
    assert child["calculated"]["age"] == 9
    assert youth["calculated"]["age_class"] == "AKA_02_JUG"
    assert youth["calculated"]["categorie"] == "jeune_adulte"
    assert "640.70" in adult["body"]
    assert "640.70" not in child["body"]
    assert "640.70" not in youth["body"]
    assert "franchise incompatible" in child["calculated"]["motifs"]
    assert child["comparatif_statut"] == "incomplet"
    assert "NPA absent" in render_contact_email(
        {"prenom": "Noe", "nom": "Blanc", "naissance": "1980-05-02", "email": "noe@example.ch"},
        catalog,
        index,
    )["calculated"]["motifs"]
    assert "naissance manquante" in render_contact_email(
        {"prenom": "Noe", "nom": "Blanc", "npa": "1201", "lieu": "Genève", "email": "noe@example.ch"},
        catalog,
        index,
    )["calculated"]["motifs"]


def test_edit_marks_comparative_stale_and_draft_keeps_official_premium():
    catalog = _catalog()
    index = build_premium_index(catalog)
    message = render_contact_email(
        {"prenom": "Ada", "nom": "Martin", "npa": "1201", "lieu": "Genève", "naissance": "1980-05-02", "email": "ada@example.ch"},
        catalog,
        index,
    )
    payload = calculation_payload(message["calculated"], "stamp", "2026-10-27T00:00:00+00:00")
    contact = {
        "prenom": "Ada",
        "nom": "Martin",
        "npa": "1201",
        "naissance": "1980-05-02",
        "email": "ada@example.ch",
        "age_class": "AKA_03_ERW",
        "comparatif_statut": "calcule",
        "brouillon_statut": "valide",
        "comparatif": payload["comparatif"],
        "premiums_found": payload["premiums_found"],
    }
    edited = apply_identity_edit(contact, {"npa": "1003", "prenom": "Ada"})
    assert edited["recalculate"] is True
    assert edited["contact"]["comparatif_statut"] == "a_recalculer"
    assert edited["contact"]["brouillon_statut"] == "a_verifier"
    assert edited["contact"]["npa"] == "1003"
    saved = save_draft_text(
        {"subject": EMAIL_SUBJECT, "body": message["body"], "brouillon_statut": "brouillon", "to": "ada@example.ch"},
        contact,
        subject=EMAIL_SUBJECT,
        intro="Texte revu pour Ada.",
        closing=None,
    )
    assert saved["manual_edit"] is True
    assert "640.70" in saved["body"]
    assert "Texte revu pour Ada." in saved["body"]
    assert "[Compagnie]" not in saved["body"]
    assert payload["comparatif"]["lignes"][0]["premium"] == "640.70"
    protected = plan_prepare(contact, {"manual_edit": True}, catalog, index, "stamp", "2026-10-27T00:00:00+00:00")
    assert protected["action"] == "kept"
    assert protected["sent"] == 0
    assert protected["queued"] == 0


def test_preparation_send_is_refused_without_touching_drafts():
    emails = [{"status": "a_valider", "to": "ada@example.ch", "body": "<p>Bonjour Ada</p>"}]
    snapshot = [dict(item) for item in emails]
    decision = refuse_campaign_delivery({"id": "campagne", "status": "preparation"}, emails)
    assert decision["refused"] is True
    assert decision["sent"] == 0
    assert decision["queued"] == 0
    assert decision["status"] == "envoi_refuse"
    assert emails == snapshot
    assert "ada@example.ch" not in decision["detail"]
    kept = reimport_decisions(
        [{"contact": {"prenom": "Ada", "nom": "Martin", "naissance": "1980-05-02"}, "email": {"brouillon_statut": "valide"}}],
        [
            {"prenom": "Ada", "nom": "Martin", "naissance": "1980-05-02"},
            {"prenom": "Noe", "nom": "Blanc", "naissance": "1981-01-02"},
        ],
    )
    assert kept["removed"] == []
    assert len(kept["kept"]) == 1
    assert len(kept["add"]) == 1
    people = [
        present_person({"id": "1", "prenom": "Ada", "nom": "Martin", "premiums_found": 6, "comparatif_statut": "calcule", "email": "ada@example.ch"}, {"body": "<p></p>", "to": "ada@example.ch", "brouillon_statut": "brouillon"}),
        present_person({"id": "2", "prenom": "Noe", "nom": "Blanc", "premiums_found": 0, "comparatif_statut": "incomplet", "email": ""}, {"body": "<p></p>", "brouillon_statut": "a_verifier"}),
    ]
    stats = summarize(people, [{"status": "a_valider"}])
    assert stats["contacts"] == 2
    assert stats["avec_primes"] == 1
    assert stats["sans_primes"] == 1
    assert stats["envoyes"] == 0
    assert people[1]["bucket"] == "verifier"
    assert "Comparatif indisponible" in people[1]["comparatif"]["message"]
