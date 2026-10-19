import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { formatChf } from "../mappers.ts";
import {
  HELFER_EXCEL,
  HELFER_LPP_ONCE,
  helferAnalyseInput,
} from "../fixtures/helfer.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { renderPrintableReportHtml } from "../pdf/renderPrintableReportHtml.ts";
import { lppCalculationService } from "../services/LPPCalculationService.ts";
import { avsCalculationService } from "../services/AVSCalculationService.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseInput,
  type AnalyseRecord,
} from "../types.ts";

const {
  wiliamAvoir,
  wiliamRetirable,
  arianeAvoir,
  arianeRetirable,
  arianeRenteResiduelle,
  arianeLp,
  arianeAssietteFiscale,
  doublePctBug,
} = HELFER_LPP_ONCE;

function lppAt(capital: number, rente = 16_057) {
  return emptyPerson("Madame").lpp.map((row) =>
    row.age === 65 ? { ...row, capital, rente } : row,
  );
}

function payloadFrom(source: AnalyseInput) {
  return JSON.parse(JSON.stringify(source)) as AnalyseInput;
}

function recordOf(input: AnalyseInput, results: AnalyseRecord["results"]): AnalyseRecord {
  return {
    id: "lpp-once-test",
    createdAt: "2026-10-12T00:00:00.000Z",
    updatedAt: "2026-10-12T00:00:00.000Z",
    clientId: null,
    status: "calculee",
    input,
    results,
  };
}

describe("LPPCalculationService — % une seule fois", () => {
  it("297356 × 100 % = 297356 ; × 50 % = 148678 ; × 25 % = 74339", () => {
    assert.equal(lppCalculationService.capitalRetire(297_356, 100), 297_356);
    assert.equal(lppCalculationService.capitalRetire(297_356, 50), 148_678);
    assert.equal(lppCalculationService.capitalRetire(297_356, 25), 74_339);
    assert.equal(lppCalculationService.capitalRetire(350_359, 100), 350_359);
  });

  it("0 / 75 / valeur libre : une application, pas deux", () => {
    assert.equal(lppCalculationService.capitalRetire(297_356, 0), 0);
    assert.equal(lppCalculationService.capitalRetire(297_356, 75), 223_017);
    assert.equal(lppCalculationService.capitalRetire(297_356, 40), 118_942.4);
    assert.equal(
      lppCalculationService.capitalEffectivementRetirable(297_356, 50, 148_678),
      148_678,
    );
    assert.equal(
      lppCalculationService.capitalRetire(148_678, 50),
      74_339,
      "réappliquer le % sur le retirable = bug historique",
    );
    assert.ok(lppCalculationService.isAlreadyRetirable(148_678, 297_356, 50));
    assert.equal(lppCalculationService.isAlreadyRetirable(297_356, 297_356, 50), false);
  });

  it("rente résiduelle une fois sur la rente totale", () => {
    assert.equal(lppCalculationService.renteResiduelle(16_057, 50), 8_028.5);
    assert.equal(lppCalculationService.renteResiduelle(16_057, 100), 0);
    assert.equal(lppCalculationService.renteResiduelle(16_057, 0), 16_057);
    assert.equal(lppCalculationService.renteResiduelle(16_057, 25), 12_042.75);
  });
});

describe("HELFER — chaîne formulaire → payload → PDF (sans ESTV réel)", () => {
  const capitalsSent: number[] = [];
  const originalCapital = taxCalculationService.calculateCapitalTax.bind(
    taxCalculationService,
  );
  const originalIncome = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );

  taxCalculationService.calculateCapitalTax = async (params) => {
    capitalsSent.push(params.capital);
    return {
      age: params.ageAtPayment,
      capital: params.capital,
      gender: params.gender,
      relationship: params.relationship,
      taxGroupId: params.taxGroupId,
      taxYear: params.taxYear ?? 2025,
      taxCity: 0,
      taxCanton: 0,
      taxFed: 0,
      taxChurch: 0,
      impotTotal: Math.round(params.capital * 0.04),
      request: { mocked: true, assiette: params.capital },
      response: {},
    };
  };
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

  after(() => {
    taxCalculationService.calculateCapitalTax = originalCapital;
    taxCalculationService.calculateDetailedTaxes = originalIncome;
  });

  it("saisie / save / reopen : avoir 297356, retirable 148678, pas de 2e %", async () => {
    const form = helferAnalyseInput();
    const arianeRow = form.conjoint!.lpp.find((r) => r.age === 65)!;
    assert.equal(arianeRow.capital, arianeAvoir);
    assert.equal(form.conjoint!.lppPctDeblocable, 50);
    assert.equal(form.client1.lpp.find((r) => r.age === 65)!.capital, wiliamAvoir);

    const saved = payloadFrom(form);
    const reopened = payloadFrom(saved);
    assert.equal(reopened.conjoint!.lpp.find((r) => r.age === 65)!.capital, arianeAvoir);
    assert.equal(reopened.conjoint!.lppPctDeblocable, 50);

    const preview = avsCalculationService.computePersonBasics(reopened.conjoint!);
    assert.equal(preview.capitalLpp65, arianeAvoir);
    assert.equal(preview.capitalLppRetire65, arianeRetirable);
    assert.equal(preview.renteLppResiduelle65, arianeRenteResiduelle);

    capitalsSent.length = 0;
    const results = await retirementAnalysisService.run(reopened);
    assert.equal(results.conjoint?.capitalLpp65, arianeAvoir);
    assert.equal(results.conjoint?.capitalLppRetire65, arianeRetirable);
    assert.equal(results.conjoint?.renteLppResiduelle65, arianeRenteResiduelle);
    assert.equal(results.client1.capitalLppRetire65, wiliamRetirable);
    assert.equal(results.capitalPathFoyer?.conjoint?.lppRetire, arianeRetirable);
    assert.equal(results.capitalPathFoyer?.conjoint?.capitalRetire, arianeAssietteFiscale);
    assert.equal(results.capitalPathFoyer?.lppRetireTotal, wiliamRetirable + arianeRetirable);
    assert.ok(
      !capitalsSent.some((c) => Math.abs(c - doublePctBug) < 0.05),
      `assiette bug 75 356 encore envoyée à ESTV : ${capitalsSent.join(", ")}`,
    );
    assert.ok(
      capitalsSent.some((c) => Math.abs(c - arianeAssietteFiscale) < 0.05),
      "Ariane LPP+LP 149 694.75 doit être l’assiette fiscale",
    );
    assert.ok(capitalsSent.some((c) => Math.abs(c - wiliamAvoir) < 0.05));

    const payload = buildReportPayload(recordOf(reopened, results));
    assert.equal(payload.conjoint?.capitalLpp65, arianeAvoir);
    assert.equal(payload.conjoint?.capitalLppRetire65, arianeRetirable);
    assert.equal(payload.conjoint?.renteLppResiduelle65, arianeRenteResiduelle);
    assert.equal(payload.aggregates.capitalLppRetireTotal, wiliamRetirable + arianeAssietteFiscale);
    assert.equal(
      payload.aggregates.capitalLppAvecLibrePassage,
      wiliamRetirable + arianeRetirable + arianeLp,
    );
    assert.equal(payload.coherence.capitalLpp65, wiliamAvoir + arianeAvoir);
    assert.equal(payload.coherence.capitalLppRetire65, wiliamRetirable + arianeRetirable);

    const html = renderPrintableReportHtml(payload);
    assert.ok(html.includes("Avoir LPP total"));
    assert.ok(html.includes("Capital LPP disponible"));
    assert.ok(html.includes(formatChf(arianeAvoir)));
    assert.ok(html.includes(formatChf(arianeRetirable)));
    assert.equal(html.includes(formatChf(75_356)), false);
    assert.equal(html.includes(formatChf(74_339)), false);

    const arianeEvent = results.timeline?.events.find(
      (e) => e.person === "conjoint" && e.kind === "lpp",
    );
    assert.equal(arianeEvent?.amount, arianeRetirable);

    const lppAriane = (reopened.withdrawalScenarios || [])
      .flatMap((s) => s.items)
      .find((i) => i.kind === "lpp" && i.titulaire === "conjoint");
    assert.ok(lppAriane);
    assert.equal(lppAriane!.montantDisponible, arianeAvoir);
    const wpAriane = results.withdrawalPlanning?.scenarios[0]?.byYear
      .flatMap((y) => y.lines)
      .find((l) => l.kind === "lpp" && l.titulaire === "conjoint");
    assert.equal(wpAriane?.montantRetire, arianeRetirable);
  });

  it("ligne déjà au retirable : ne pas réappliquer le %", async () => {
    const input = helferAnalyseInput();
    for (const sc of input.withdrawalScenarios || []) {
      for (const item of sc.items) {
        if (item.kind === "lpp" && item.titulaire === "conjoint") {
          item.montantDisponible = arianeRetirable;
          item.pctCapital = 50;
        }
      }
    }
    const results = await retirementAnalysisService.run(input);
    const line = results.withdrawalPlanning?.scenarios[0]?.byYear
      .flatMap((y) => y.lines)
      .find((l) => l.kind === "lpp" && l.titulaire === "conjoint");
    assert.equal(line?.montantRetire, arianeRetirable);
    assert.equal(results.conjoint?.capitalLppRetire65, arianeRetirable);
  });

  it("les deux assurés : 0 / 25 / 50 / 75 / 100 et valeur libre", async () => {
    const cases: Array<{ p1: number; p2: number }> = [
      { p1: 100, p2: 100 },
      { p1: 50, p2: 50 },
      { p1: 25, p2: 75 },
      { p1: 0, p2: 100 },
      { p1: 40, p2: 0 },
    ];
    for (const { p1, p2 } of cases) {
      const input = helferAnalyseInput();
      input.client1.lppPctDeblocable = p1;
      input.conjoint!.lppPctDeblocable = p2;
      const results = await retirementAnalysisService.run(input);
      assert.equal(
        results.client1.capitalLppRetire65,
        lppCalculationService.capitalRetire(wiliamAvoir, p1),
        `Wiliam ${p1} %`,
      );
      assert.equal(
        results.conjoint?.capitalLppRetire65,
        lppCalculationService.capitalRetire(arianeAvoir, p2),
        `Ariane ${p2} %`,
      );
      assert.equal(
        results.client1.renteLppResiduelle65,
        lppCalculationService.renteResiduelle(HELFER_EXCEL.client1.lpp65Rente, p1),
      );
      assert.equal(
        results.conjoint?.renteLppResiduelle65,
        lppCalculationService.renteResiduelle(HELFER_EXCEL.conjoint.lpp65Rente, p2),
      );
    }
  });
});

describe("diagnostic — autres analyses (lecture seule)", () => {
  it("signale le pattern Excel HELFER (capital déjà retirable + taux irréaliste)", () => {
    const stale = emptyPerson("Madame");
    stale.lppPctDeblocable = 50;
    stale.lpp = lppAt(148_678, 16_057);
    const diag = lppCalculationService.diagnosePerson(stale);
    assert.equal(diag.retirableOnce, 74_339);
    assert.equal(diag.doublePct, 37_169.5);
    assert.equal(diag.risqueCapitalDejaRetirable, true);

    const corrected = emptyPerson("Madame");
    corrected.lppPctDeblocable = 50;
    corrected.lpp = lppAt(297_356, 16_057);
    const ok = lppCalculationService.diagnosePerson(corrected);
    assert.equal(ok.retirableOnce, 148_678);
    assert.equal(ok.risqueCapitalDejaRetirable, false);
  });

  it("les dossiers à 100 % ne sont pas concernés par le double %", () => {
    const input = emptyAnalyseInput();
    input.client1.lppPctDeblocable = 100;
    input.client1.lpp = lppAt(350_359, 21_024);
    const diag = lppCalculationService.diagnosePerson(input.client1);
    assert.equal(diag.retirableOnce, 350_359);
    assert.equal(diag.doublePct, 350_359);
    assert.equal(diag.risqueCapitalDejaRetirable, false);
  });
});
