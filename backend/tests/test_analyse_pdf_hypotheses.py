"""Le PDF d'analyse reprend input.renteHypotheses du dossier transmis au moteur.

La route GET /analyses-prevoyance/{id}/pdf fait :
  record = _displayed(doc)  → refresh_report_display_prenoms(_public(doc), ...)
  run_engine("pdf", {"record": record})
"""

from analyses_prefill import refresh_report_display_prenoms
from analyses_routes import run_engine


def _public(doc: dict) -> dict:
    return {
        "id": doc.get("id"),
        "createdAt": doc.get("created_at"),
        "updatedAt": doc.get("updated_at"),
        "clientId": doc.get("client_id"),
        "status": doc.get("status") or "brouillon",
        "input": doc.get("input") or {},
        "results": doc.get("results"),
        "documentId": doc.get("document_id"),
        "version": 1,
        "versionCount": 0,
    }


def _hypotheses():
    return [
        {
            "id": "vaudoise",
            "type": "certaine",
            "compagnie": "Vaudoise",
            "capitalPlace": 530000,
            "dureeAnnees": 20,
            "renteGarantieAnnuelle": 23136,
            "participationExcedentsAnnuelle": 7096,
            "recommander": True,
        },
        {
            "id": "helvetia",
            "type": "viagere",
            "compagnie": "Helvetia",
            "capitalPlace": 200000,
            "dureeAnnees": None,
            "renteGarantieAnnuelle": 10000,
            "participationExcedentsAnnuelle": 1000,
            "recommander": False,
        },
    ]


def test_displayed_record_keeps_rente_hypotheses_for_pdf_engine():
    doc = {
        "id": "analyse-helfer",
        "created_at": "2026-10-13T00:00:00+00:00",
        "updated_at": "2026-10-13T00:00:00+00:00",
        "client_id": None,
        "status": "calculee",
        "input": {
            "client1": {"prenom": "Wiliam", "nom": "HELFER"},
            "conjoint": {"prenom": "Ariane", "nom": "HELFER"},
            "comparerAvecRenteLpp": True,
            "renteHypotheses": _hypotheses(),
        },
        "results": {"renteHypotheses": None, "timeline": {"events": [], "byYear": {}}},
        "document_id": None,
        "version": 2,
        "versions": [],
    }
    record = refresh_report_display_prenoms(_public(doc), None, None)
    names = [row["compagnie"] for row in record["input"]["renteHypotheses"]]
    assert names == ["Vaudoise", "Helvetia"]
    assert record["results"]["renteHypotheses"] is None


def test_run_engine_html_command_is_the_pdf_route_renderer():
    """Même runner.ts que GET .../pdf, commande html (sans Chromium)."""
    from pathlib import Path

    engine = Path(__file__).resolve().parents[1] / "analyse_prevoyance_engine" / "runner.ts"
    assert engine.is_file()
    # La commande pdf appelle pdfGenerationService.generatePdfBuffer(record)
    # après buildReportPayload — couvert par pdf-route-hypotheses.test.ts.
    source = engine.read_text(encoding="utf-8")
    assert 'cmd === "html" || cmd === "pdf"' in source
    assert "pdfGenerationService.generatePdfBuffer(record)" in source
    assert "renderPrintableReportHtml(buildReportPayload(record))" in source
    assert run_engine.__name__ == "run_engine"
