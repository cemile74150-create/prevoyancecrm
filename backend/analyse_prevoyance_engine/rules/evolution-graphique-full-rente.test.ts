import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { helferAnalyseInput } from "../fixtures/helfer.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { renderPrintableReportHtml } from "../pdf/renderPrintableReportHtml.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import type { AnalyseRecord } from "../types.ts";

const VERT = 87_196;
const ROUGE = 79_595;
const SALAIRE = 166_791;
const RESIDUELLE_ANNEE_COMPLETE = 58_143.5;

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** Même prorata que PostRetirementEvolutionService.personYearIncome. */
function personYearIncome(
  year: number,
  departIso: string,
  salaire: number,
  rente: number,
): number {
  const [y, m] = departIso.split("-").map(Number);
  if (year < y) return salaire;
  if (year > y) return rente;
  return round2((salaire * ((m || 1) - 1)) / 12 + (rente * (13 - (m || 1))) / 12);
}

function axisChf(n: number): string {
  return new Intl.NumberFormat("fr-CH", { maximumFractionDigits: 0 }).format(n);
}

function chartBars(chartHtml: string): Map<number, { vert: string; rouge: string }> {
  const bars = new Map<number, { vert: string; rouge: string }>();
  const re =
    /<text[^>]*fill="#fff"[^>]*>([^<]*)<\/text>\s*<text[^>]*fill="#fff"[^>]*>([^<]*)<\/text>\s*<text[^>]*fill="#444"[^>]*>(\d{4})<\/text>/g;
  for (const match of chartHtml.matchAll(re)) {
    bars.set(Number(match[3]), { vert: match[1], rouge: match[2] });
  }
  return bars;
}

describe("graphique évolution Helfer — full rente LPP", () => {
  const originalCapital = taxCalculationService.calculateCapitalTax.bind(
    taxCalculationService,
  );
  const originalIncome = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );

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

  after(() => {
    taxCalculationService.calculateCapitalTax = originalCapital;
    taxCalculationService.calculateDetailedTaxes = originalIncome;
  });

  it("William 100 % et Ariane 50 % : vert 87196 et rouge 79595 dès 2028", async () => {
    const input = helferAnalyseInput();
    assert.equal(input.client1.lppPctDeblocable, 100);
    assert.equal(input.conjoint?.lppPctDeblocable, 50);

    const results = await retirementAnalysisService.run(input);
    const conjoint = results.conjoint;
    assert.ok(conjoint);
    assert.equal(results.client1.dateDepart, "2027-01-01");
    assert.equal(conjoint.dateDepart, "2027-11-01");
    assert.equal(results.client1.avsAnnuel + conjoint.avsAnnuel, 50_115);
    assert.equal(results.client1.renteLpp65, 21_024);
    assert.equal(conjoint.renteLpp65, 16_057);
    assert.equal(results.client1.renteLppResiduelle65, 0);
    assert.equal(conjoint.renteLppResiduelle65, 8_028.5);
    assert.equal(results.client1.capitalLppRetire65, 350_359);
    assert.equal(conjoint.capitalLppRetire65, 74_339);

    assert.equal(results.lacune.salaireAvant, SALAIRE);
    assert.equal(results.lacune.revenuApres, VERT);
    assert.equal(results.lacune.lacune, ROUGE);

    const evolution = results.evolution;
    assert.ok(evolution);
    assert.equal(evolution.renteReference, results.lacune.revenuApres);
    assert.equal(evolution.salaireReference, SALAIRE);

    const pleines = evolution.rows.filter((row) => row.year >= 2028);
    assert.ok(pleines.length >= 2);
    for (const row of pleines) {
      assert.equal(row.phase, "rente");
      assert.equal(row.revenu, VERT);
      assert.equal(round2(evolution.salaireReference - row.revenu), ROUGE);
      assert.notEqual(row.revenu, RESIDUELLE_ANNEE_COMPLETE);
    }

    const annee2027 = evolution.rows.find((row) => row.year === 2027);
    assert.ok(annee2027);
    assert.equal(annee2027.phase, "transition");
    const pleine2027 = round2(
      personYearIncome(
        2027,
        results.client1.dateDepart,
        input.salaireClient1,
        results.client1.renteTotale65,
      ) +
        personYearIncome(
          2027,
          conjoint.dateDepart,
          input.salaireConjoint,
          conjoint.renteTotale65,
        ),
    );
    const residuelle2027 = round2(
      personYearIncome(
        2027,
        results.client1.dateDepart,
        input.salaireClient1,
        results.client1.avsAnnuel + results.client1.renteLppResiduelle65,
      ) +
        personYearIncome(
          2027,
          conjoint.dateDepart,
          input.salaireConjoint,
          conjoint.avsAnnuel + conjoint.renteLppResiduelle65,
        ),
    );
    assert.equal(annee2027.revenu, pleine2027);
    assert.notEqual(annee2027.revenu, residuelle2027);
    assert.notEqual(annee2027.revenu, VERT);

    const record: AnalyseRecord = {
      id: "helfer-graphique",
      createdAt: "2026-10-07T00:00:00.000Z",
      updatedAt: "2026-10-07T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const html = renderPrintableReportHtml(buildReportPayload(record));
    const chartStart = html.indexOf("ÉVOLUTION REVENU APRÈS LA RETRAITE");
    const chartEnd = html.indexOf("Indicateurs de maintien de niveau de vie");
    assert.ok(chartStart >= 0 && chartEnd > chartStart);
    const chart = html.slice(chartStart, chartEnd);
    assert.match(chart, /rente LPP complète, sans retrait en capital/);
    assert.equal(chart.includes("pourcentage déblocable"), false);
    assert.equal(chart.includes(axisChf(RESIDUELLE_ANNEE_COMPLETE)), false);

    const bars = chartBars(chart);
    for (const year of [2028, 2029, 2030]) {
      const bar = bars.get(year);
      assert.ok(bar, `barre ${year}`);
      assert.equal(bar.vert, axisChf(VERT));
      assert.equal(bar.rouge, axisChf(ROUGE));
    }
    const bar2027 = bars.get(2027);
    assert.ok(bar2027);
    assert.equal(bar2027.vert, axisChf(pleine2027));
    assert.notEqual(bar2027.vert, axisChf(residuelle2027));

    const indicateurs = html.slice(chartEnd);
    assert.match(indicateurs, /Revenu brut après retraite/);
    assert.ok(indicateurs.includes(axisChf(VERT)));
  });
});
