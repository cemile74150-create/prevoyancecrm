"""Lettre Word de rachat 3a et suppression d'une ligne d'échéance sans PDF."""
import io
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from echeance_3p_suivi import (  # noqa: E402
    document_excluded_from_new_echeance_line,
    echeance_3p_line_removal_plan,
)
from lettre_rachat_3a_word import (  # noqa: E402
    TEMPLATE_PATH,
    company_postal_lines,
    generate_lettre_rachat_docx,
)


def _plain(xml: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml))


def _document_plain(data: bytes) -> str:
    chunks = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.endswith(".xml"):
                chunks.append(zf.read(name).decode("utf-8"))
    return _plain("".join(chunks))


def test_lettre_rachat_remplit_client_police_et_date_sans_exemple():
    client = {
        "prenom": "Léa",
        "nom": "Martin",
        "adresse": "Rue du Test 12",
        "npa": "1000",
        "ville": "Lausanne",
        "avs_number": "756.1111.2222.33",
        "conjoint_prenom": "Paul",
        "conjoint_nom": "Martin",
    }
    line = {"company": "AXA", "policy_number": "1526334"}
    data, filename = generate_lettre_rachat_docx(client, line, when=date(2026, 10, 28))
    assert filename.endswith(".docx")
    assert "Martin" in filename and "1526334" in filename
    assert data[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
        assert "word/document.xml" in zf.namelist()
    plain = _document_plain(data)
    assert "Martin Léa" in plain
    assert "Léa Martin" in plain
    assert "Rue du Test 12" in plain
    assert "1000 Lausanne" in plain
    assert "756.1111.2222.33" in plain
    assert "AXA" in plain
    assert "1526334" in plain
    assert "28.10.2026" in plain
    assert "Paul Martin" in plain
    assert "Objet" in plain
    assert "Demande de rachat" in plain
    assert "Banque :" in xml
    assert "IBAN :" in xml
    assert not re.search(r"""w:val=["']yellow["']""", xml, flags=re.IGNORECASE)
    assert "<w:highlight" not in xml.lower()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.endswith(".xml"):
                continue
            part = zf.read(name).decode("utf-8")
            assert "yellow" not in part.lower()
    for leftover in (
        "Mathey",
        "Claudia",
        "Christian",
        "Adversan",
        "Villard-sur-Chamby",
        "1.637.398",
        "20 avril 2026",
        "756.7566.9954.21",
        "Case Postale",
        "8085",
        "assurances sur la Vie",
    ):
        assert leftover not in plain
    assert TEMPLATE_PATH.is_file()


def test_lettre_rachat_sans_adresse_compagnie_laisse_le_nom_seul():
    client = {"prenom": "Nora", "nom": "Favre"}
    line = {"company": "Zurich", "policy_number": "9.363.640"}
    assert company_postal_lines(line, {"extracted_echeances_3p": [{"company": "Zurich"}]}) == []
    data, _ = generate_lettre_rachat_docx(client, line, when=date(2026, 10, 28))
    plain = _document_plain(data)
    assert "Favre Nora" in plain
    assert "Zurich" in plain
    assert "9.363.640" in plain
    assert "28.10.2026" in plain
    assert "Case Postale" not in plain
    assert "8085" not in plain
    assert "assurances sur la Vie" not in plain
    assert "Mathey" not in plain
    assert "Adversan" not in plain
    assert "AVS n°" in plain
    assert "756.7566.9954.21" not in plain


def test_lettre_rachat_adresse_compagnie_seulement_si_stockee():
    line = {
        "company": "AXA",
        "policy_number": "9.363.640",
        "adresse_compagnie": "Avenue du Test 1\n1003 Lausanne",
    }
    assert company_postal_lines(line) == ["Avenue du Test 1", "1003 Lausanne"]
    data, _ = generate_lettre_rachat_docx(
        {"prenom": "Ines", "nom": "Blanc"},
        line,
        when=date(2026, 10, 28),
    )
    plain = _document_plain(data)
    assert "Avenue du Test 1" in plain
    assert "1003 Lausanne" in plain
    assert "8085" not in plain
    assert "Case Postale" not in plain


def test_suppression_ligne_ne_retire_aucun_document():
    line = {
        "id": "ligne-1",
        "company": "AXA",
        "policy_number": "1422234",
        "source_doc_id": "pdf-police",
        "rachat_doc_id": "pdf-confirmation",
    }
    autres_pdf = ["pdf-valeur-rachat", "pdf-ordre-paiement"]
    plan = echeance_3p_line_removal_plan(line)
    assert plan["delete_document_ids"] == []
    assert "pdf-police" not in plan["delete_document_ids"]
    assert "pdf-confirmation" not in plan["delete_document_ids"]
    for doc_id in autres_pdf:
        assert doc_id not in plan["delete_document_ids"]
    assert plan["exclude_from_auto_line_doc_ids"] == ["pdf-police"]
    assert document_excluded_from_new_echeance_line({"id": "pdf-police", "echeance_3p_exclu": True})
    assert not document_excluded_from_new_echeance_line({"id": "pdf-valeur-rachat"})
    assert echeance_3p_line_removal_plan({"id": "manuelle"})["delete_document_ids"] == []
    assert echeance_3p_line_removal_plan({"id": "manuelle"})["exclude_from_auto_line_doc_ids"] == []


def test_handlers_echeance_ne_marquent_pas_les_pdf_supprimes():
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    delete_body = server.split("async def delete_echeance_3p_line", 1)[1].split(
        "async def download_lettre_rachat_3a", 1
    )[0]
    update_body = server.split("async def update_echeance_3p_line", 1)[1].split(
        "async def delete_echeance_3p_line", 1
    )[0]
    assert "is_deleted" not in delete_body
    assert "echeance_3p_exclu" in delete_body
    assert "is_deleted" not in update_body
    assert "Supprimer cette ligne de suivi" in (ROOT.parent / "frontend" / "src" / "pages" / "ClientDetail.js").read_text(encoding="utf-8")
    confirm = (ROOT.parent / "frontend" / "src" / "pages" / "ClientDetail.js").read_text(encoding="utf-8")
    assert "retirée des Documents" not in confirm
    assert "Les documents restent" in confirm
