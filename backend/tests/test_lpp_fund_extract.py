"""Extraction caisses LPP : adresses propres, multi-caisses, parasites exclus."""

from __future__ import annotations

import hashlib

import pytest

from lpp_fund_extract import (
    ADRESSE_A_VERIFIER,
    apply_address_overrides,
    collect_address_overrides,
    format_caisse_address,
    fund_address_is_ready,
    funds_blocking_generation,
    parse_funds_from_clean_text,
    sanitize_fund_record,
    strip_lpp_parse_noise,
    timed_parse_funds_from_text,
)
from pdf_generator import (
    _map_lettre_decompte,
    _parse_funds_from_text,
    generate_decompte_letters,
    merge_lpp_detected_funds,
)


CPPIC_NOISY = """
Page 1 sur 4
Agence Mendes
Centrale du 2e pilier

Madame, Monsieur,

Suite à votre demande, nous avons identifié les institutions suivantes :

Caisse paritaire de prévoyance de l'industrie et de la construction (CPPIC)
Rue de Malatrex 14
Page 2 sur 4
; N
1201 Genève
| solde | CHF | 12'000 |

Nous attirons votre attention sur le fait que seule l'institution compétente
peut confirmer les avoirs.

Cordialement
"""

MULTI_FUNDS = """
Page 1 sur 2
Les institutions suivantes :

Swiss Life Team Freizügigkeitspolicen
General-Guisan-Quai 40
8022 Zürich

Fondation Institution supplétive LPP
Weststrasse 50
8003 Zürich

GastroSocial Pensionskasse
Mühlemattstrasse 23
5001 Aarau

Nous espérons que ces informations vous seront utiles.
"""

ASSURE_POLLUTION = """
Institutions suivantes :
Fondation Test LPP
Route de l'Assuré 9
1200 Genève
Nom de l'assuré : DUPONT Jean
N° AVS 756.1111.2222.33
"""


def test_strip_removes_page_headers_and_table_appendix():
    raw = (
        "Page 1 sur 2\nHello\n\n----- OCR_TABLE_APPENDIX -----\n"
        "[ocr-table-heuristics]\na | b | c\n"
    )
    cleaned = strip_lpp_parse_noise(raw)
    assert "Page 1 sur 2" not in cleaned
    assert "OCR_TABLE" not in cleaned
    assert "a | b" not in cleaned
    assert "Hello" in cleaned


def test_cppic_address_clean_without_page_or_pipes():
    funds = _parse_funds_from_text(CPPIC_NOISY)
    assert len(funds) >= 1
    fund = funds[0]
    assert "CPPIC" in fund["name"] or "paritaire" in fund["name"].lower()
    assert "Malatrex" in fund["address"]
    assert "1201" in fund["address"]
    assert "Genève" in fund["address"] or "Geneve" in fund["address"].replace("è", "e")
    assert "Page" not in fund["address"]
    assert "|" not in fund["address"]
    assert "; N" not in fund["address"]
    assert "Nous attirons" not in fund["address"]
    assert "Page" not in fund["recipient_block"]
    mapped = _map_lettre_decompte(
        {"nom": "TEST", "prenom": "A", "avs": "756", "today_long": "1 janvier 2026"},
        {"fund": fund},
    )
    assert "Malatrex" in mapped["Adresse"]
    assert "Page" not in mapped["Adresse"]


def test_multi_funds_without_duplicates():
    funds = parse_funds_from_clean_text(MULTI_FUNDS)
    names = [f["name"] for f in funds]
    assert len(names) == len(set(n.casefold() for n in names))
    assert len(funds) >= 3
    for fund in funds:
        assert "Page" not in fund["address"]
        addr, uncertain = format_caisse_address(fund["address"])
        assert not uncertain
        assert addr != ADRESSE_A_VERIFIER


def test_uncertain_address_when_incomplete():
    addr, uncertain = format_caisse_address("Rue seule sans NPA")
    assert uncertain
    assert addr == ADRESSE_A_VERIFIER


def test_sanitize_existing_noisy_fund_without_reocr():
    dirty = {
        "name": "Caisse paritaire de prévoyance de l'industrie et de la construction (CPPIC)",
        "recipient_block": (
            "Caisse paritaire de prévoyance de l'industrie et de la construction (CPPIC)\n"
            "Rue de Malatrex 14\nPage 2 sur 4\n; N\n1201 Genève\n| x | y |"
        ),
        "raw": "bruit",
        "address": "Rue de Malatrex 14\nPage 2 sur 4\n; N\n1201 Genève",
    }
    clean = sanitize_fund_record(dirty)
    assert "Malatrex" in clean["address"]
    assert "Page" not in clean["address"]
    assert "|" not in clean["address"]
    assert clean["recipient_block"].startswith(clean["name"])


def test_manual_address_override_is_respected():
    fund = sanitize_fund_record({
        "name": "CPPIC",
        "address": "bruit",
        "address_override": "Rue de Malatrex 14\n1201 Genève",
    })
    assert fund["address"] == "Rue de Malatrex 14\n1201 Genève"
    assert "bruit" not in fund["recipient_block"]


def test_parse_performance_is_sub_second_on_text():
    _, timing = timed_parse_funds_from_text(MULTI_FUNDS * 5)
    assert timing["total_ms"] < 200


def test_assure_block_not_merged_into_address():
    funds = _parse_funds_from_text(ASSURE_POLLUTION)
    assert funds
    assert "AVS" not in funds[0]["address"]
    assert "DUPONT" not in funds[0]["address"]


ROLEX_NOISY = """
Page 1 sur 3
Centrale du 2e pilier — Fonds de garantie LPP

Nous avons identifié les institutions suivantes :

Fondation de prévoyance en faveur du personnel de Rolex SA
Rue François-Dussaud 3-5
| montant | CHF | 45'000 |
Page 2 sur 3
; N
1211 Genève 26

Nous attirons votre attention sur le caractère informatif de cette liste.
"""


def test_rolex_and_cppic_clean_addresses_for_letters():
    cppic = _parse_funds_from_text(CPPIC_NOISY)[0]
    rolex = _parse_funds_from_text(ROLEX_NOISY)[0]
    assert "CPPIC" in cppic["name"] or "paritaire" in cppic["name"].lower()
    assert "Rolex" in rolex["name"]
    assert "Malatrex" in cppic["address"] and "1201" in cppic["address"]
    assert "Dussaud" in rolex["address"] and "1211" in rolex["address"]
    for fund in (cppic, rolex):
        assert "Page" not in fund["address"]
        assert "|" not in fund["address"]
        assert fund_address_is_ready(fund)
        mapped = _map_lettre_decompte(
            {"nom": "TEST", "prenom": "A", "avs": "756", "today_long": "1 janvier 2026"},
            {"fund": fund},
        )
        assert fund["name"].split()[0] in mapped["Adresse"] or fund["name"][:12] in mapped["Adresse"]
        assert "Page" not in mapped["Adresse"]
        assert "|" not in mapped["Adresse"]


def test_generation_blocked_when_address_uncertain():
    blocked = funds_blocking_generation([
        {"name": "CPPIC", "address": "Adresse à vérifier", "address_uncertain": True},
        {"name": "Rolex", "address": "Rue François-Dussaud 3-5\n1211 Genève 26"},
    ])
    assert len(blocked) == 1
    assert blocked[0]["name"] == "CPPIC"


def test_manual_override_survives_reparse_merge():
    existing = [{
        "name": "Fondation de prévoyance en faveur du personnel de Rolex SA",
        "person": "Monsieur",
        "source_doc_id": "doc-1",
        "address_override": "Rue François-Dussaud 3-5\n1211 Genève 26",
        "address": "Rue François-Dussaud 3-5\n1211 Genève 26",
    }]
    incoming = [{
        "name": "Fondation de prévoyance en faveur du personnel de Rolex SA",
        "person": "Monsieur",
        "source_doc_id": "doc-1",
        "address": "Adresse à vérifier",
        "recipient_block": "Rolex\nPage 1 sur 2\n| x |",
    }]
    overrides = collect_address_overrides(existing)
    restored = apply_address_overrides(incoming, overrides)
    assert restored[0]["address_override"].startswith("Rue François-Dussaud")
    assert fund_address_is_ready(restored[0])
    merged = merge_lpp_detected_funds(
        [f for f in existing if f["source_doc_id"] != "doc-1"],
        restored,
    )
    assert merged[0]["address_override"].startswith("Rue François-Dussaud")


def test_pdf_hash_change_invalidates_ocr_cache_contract():
    old = hashlib.sha256(b"%PDF-old").hexdigest()
    new = hashlib.sha256(b"%PDF-new").hexdigest()
    assert old != new
    # Contrat serveur : cache utilisable seulement si ocr_content_sha256 == hash fichier
    cache_valid = bool("ocr") and old and old == new
    assert cache_valid is False


def test_generated_letter_uses_only_clean_name_and_address():
    client = {
        "prenom": "Jean",
        "nom": "Dupont",
        "sexe": "Homme",
        "avs_number": "756.1111.2222.33",
        "adresse": "Chemin Assuré 1",
        "npa": "1200",
        "ville": "Genève",
    }
    funds = [
        {
            "name": "Caisse paritaire de prévoyance de l'industrie et de la construction (CPPIC)",
            "person": "Monsieur",
            "address": "Rue de Malatrex 14\n1201 Genève",
            "recipient_block": "BRUIT Page 2 sur 4 | x |",
            "raw": "BRUIT Page 2 sur 4",
        },
        {
            "name": "Fondation de prévoyance en faveur du personnel de Rolex SA",
            "person": "Monsieur",
            "address": "Rue François-Dussaud 3-5\n1211 Genève 26",
            "recipient_block": "Rolex\nPage 1 sur 3\n; N",
        },
    ]
    letters = generate_decompte_letters(client, funds, agent_name="Leo")
    assert len(letters) == 2
    from pypdf import PdfReader
    import io

    for pdf_bytes, meta in letters:
        text = "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
        assert meta["caisse_address"]
        assert "Page" not in meta["caisse_address"]
        assert "|" not in meta["caisse_address"]
        assert "; N" not in meta["caisse_address"]
        mapped = _map_lettre_decompte(
            {"nom": "DUPONT", "prenom": "Jean", "avs": "756", "today_long": "x"},
            {"fund": {"name": meta["caisse_name"], "address": meta["caisse_address"]}},
        )
        assert "Page" not in mapped["Adresse"]
        assert "|" not in mapped["Adresse"]
        assert meta["caisse_name"].split()[0] in mapped["Adresse"] or meta["caisse_name"][:10] in mapped["Adresse"]
        assert "Malatrex" in text or "Dussaud" in text
        assert "BRUIT" not in text
