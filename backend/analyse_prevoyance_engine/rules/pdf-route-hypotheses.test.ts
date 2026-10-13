import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { after, describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { helferAnalyseInput } from "../fixtures/helfer.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { buildReportPages } from "../pdf/renderPrintableReportHtml.ts";
import {
  closePdfBrowser,
  pdfGenerationService,
} from "../services/PdfGenerationService.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import type {
  AnalyseInput,
  AnalyseRecord,
  RenteHypothesisInput,
} from "../types.ts";

const offreA: RenteHypothesisInput = {
  id: "vaudoise",
  type: "certaine",
  compagnie: "Vaudoise",
  capitalPlace: 530_000,
  dureeAnnees: 20,
  renteGarantieAnnuelle: 23_136,
  participationExcedentsAnnuelle: 7_096,
  recommander: true,
};

const offreB: RenteHypothesisInput = {
  id: "helvetia",
  type: "viagere",
  compagnie: "Helvetia",
  capitalPlace: 200_000,
  dureeAnnees: null,
  renteGarantieAnnuelle: 10_000,
  participationExcedentsAnnuelle: 1_000,
  recommander: false,
};

function mockTax() {
  taxCalculationService.calculateCapitalTax = async (params) => ({
    age: params.ageAtPayment,
    capital: params.capital,
    gender: params.gender,
    relationship: params.relationship,
    taxGroupId: params.taxGroupId,
    taxYear: params.taxYear ?? 2025,
    taxCity: 0,
    taxCanton: 0,
    taxFed: 1,
    taxChurch: 0,
    impotTotal: 1,
    request: {},
    response: {},
  });
  taxCalculationService.calculateDetailedTaxes = async (params) => ({
    foyer: params.foyer ?? "default",
    age: params.age1,
    taxLocationId: params.taxLocationId,
    taxYear: params.taxYear ?? 2025,
    revenu1: params.revenue1,
    revenu2: params.revenue2,
    fortune: params.fortune,
    impotRevenuTotal: 1_000,
    impotFederal: 1_000,
    impotCanton: 0,
    impotCommune: 0,
    impotEglise: 0,
    request: {},
    response: {},
  });
}

function helferWithOffers(): AnalyseInput {
  const input = helferAnalyseInput();
  input.ageRetraiteSouhaite = 65;
  input.comparerAvecRenteLpp = true;
  input.renteHypotheses = [offreA, offreB];
  return input;
}

function recordOf(
  input: AnalyseInput,
  results: NonNullable<AnalyseRecord["results"]>,
): AnalyseRecord {
  return {
    id: "pdf-route-hypotheses",
    createdAt: "2026-10-13T00:00:00.000Z",
    updatedAt: "2026-10-13T00:00:00.000Z",
    clientId: null,
    status: "calculee",
    input,
    results,
  };
}

function extractPdfText(pdfPath: string): string {
  const outPath = `${pdfPath}.txt`;
  const script = [
    "import pymupdf, sys",
    "from pathlib import Path",
    "doc = pymupdf.open(sys.argv[1])",
    "Path(sys.argv[2]).write_text(",
    "    chr(10).join(page.get_text() for page in doc),",
    "    encoding='utf-8',",
    ")",
  ].join("\n");
  execFileSync("python", ["-c", script, pdfPath, outPath]);
  return readFileSync(outPath, "utf8");
}

describe("PDF route — hypothèses étape 9 (generatePdfBuffer)", {
  concurrency: false,
}, () => {
  mockTax();

  it("conserve Vaudoise et Helvetia dans le PDF fusionné, pas seulement le HTML", async () => {
    const input = helferWithOffers();
    const results = await retirementAnalysisService.run(input);
    const record = recordOf(input, results);
    const payload = buildReportPayload(record);
    const pages = buildReportPages(payload);
    assert.ok(payload.hypothesesRente);
    assert.ok(
      payload.hypothesesRente.columns.some((col) => col.compagnie === "Vaudoise"),
    );
    assert.ok(
      payload.hypothesesRente.columns.some((col) => col.compagnie === "Helvetia"),
    );
    assert.ok(pages.some((page) => page.html.includes("COMPARATIF DES RENTES")));

    const pdf = await pdfGenerationService.generatePdfBuffer(record);
    const dir = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../generated",
    );
    mkdirSync(dir, { recursive: true });
    const out = resolve(dir, "pdf-route-helfer-hypotheses.pdf");
    writeFileSync(out, pdf);
    assert.equal(pdf.subarray(0, 5).toString(), "%PDF-");

    const text = extractPdfText(out);
    const folded = text.toLocaleUpperCase("fr-CH");
    assert.ok(folded.includes("COMPARATIF DES RENTES"), "titre comparatif absent du PDF");
    assert.ok(folded.includes("VAUDOISE"), "colonne Vaudoise absente du PDF fusionné");
    assert.ok(folded.includes("HELVETIA"), "colonne Helvetia absente du PDF fusionné");
    assert.ok(/530\s*000/u.test(text));
    assert.ok(/200\s*000/u.test(text));
    assert.ok(folded.includes("SOLUTION RECOMMANDÉE") || folded.includes("SOLUTION RECOMMANDEE"));
    assert.ok(folded.includes("COMPARATIF DES SOLUTIONS DE RENTES"));
  });

  it("reprend la saisie wizard même si le dernier calcul n'a pas les offres", async () => {
    const staleInput = helferAnalyseInput();
    staleInput.ageRetraiteSouhaite = 65;
    staleInput.comparerAvecRenteLpp = true;
    staleInput.renteHypotheses = [];
    const results = await retirementAnalysisService.run(staleInput);
    const input = { ...staleInput, renteHypotheses: [offreA, offreB] };
    const pdf = await pdfGenerationService.generatePdfBuffer(
      recordOf(input, results),
    );
    const dir = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../generated",
    );
    mkdirSync(dir, { recursive: true });
    const out = resolve(dir, "pdf-route-stale-hypotheses.pdf");
    writeFileSync(out, pdf);
    const text = extractPdfText(out).toLocaleUpperCase("fr-CH");
    assert.ok(text.includes("VAUDOISE"));
    assert.ok(text.includes("HELVETIA"));
  });
});

after(async () => {
  await closePdfBrowser();
});
