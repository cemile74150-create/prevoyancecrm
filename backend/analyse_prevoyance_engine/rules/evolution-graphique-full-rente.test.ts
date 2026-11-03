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

/** Même prorata que PostRetirementEvolutionService : le mois de la date est encore du salaire. */
function personYearIncome(
  year: number,
  departIso: string,
  salaire: number,
  rente: number,
): number {
  const [y, m, d] = departIso.split("-").map(Number);
  if (year < y) return salaire;
  if (year > y) return rente;
  const month = m || 1;
  const day = d || 1;
  const daysInMonth = new Date(y, month, 0).getDate();
  const salaryMonths = Math.min(
    12,
    month + (day <= 1 ? 0 : (day - 1) / daysInMonth),
  );
  return round2((salaire * salaryMonths + rente * (12 - salaryMonths)) / 12);
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
    assert.equal(conjoint.capitalLppRetire65, 148_678);

    assert.equal(results.lacune.salaireAvant, SALAIRE);
    assert.equal(results.lacune.revenuApres, VERT);
    assert.equal(results.lacune.lacune, ROUGE);

    const evolution = results.evolution;
    assert.ok(evolution);
    assert.equal(evolution.renteReference, VERT);
    assert.equal(evolution.salaireReference, SALAIRE);

    const pleines = evolution.rows.filter((row) => row.year >= 2028);
    assert.ok(pleines.length >= 2);
    for (const row of pleines) {
      assert.equal(row.phase, "rente");
      assert.equal(row.revenu, VERT);
      assert.notEqual(row.revenu, RESIDUELLE_ANNEE_COMPLETE);
    }

    const annee2027 = evolution.rows.find((row) => row.year === 2027);
    assert.ok(annee2027);
    assert.equal(annee2027.phase, "transition");
    const reference2027 = round2(
      personYearIncome(
        2027,
        results.client1.dateFinActivite || results.client1.dateDepart,
        input.salaireClient1,
        results.client1.renteTotale65,
      ) +
        personYearIncome(
          2027,
          conjoint.dateFinActivite || conjoint.dateDepart,
          input.salaireConjoint,
          conjoint.renteTotale65,
        ),
    );
    assert.equal(annee2027.revenu, reference2027);
    assert.notEqual(annee2027.revenu, RESIDUELLE_ANNEE_COMPLETE);

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
    const chartStart = html.indexOf("ÉVOLUTION DU REVENU DE RETRAITE DE RÉFÉRENCE");
    const chartEnd = html.indexOf("Indicateurs du scénario 100 % rente");
    assert.ok(chartStart >= 0 && chartEnd > chartStart);
    const chart = html.slice(chartStart, chartEnd);
    assert.match(chart, /Revenu de référence \(AVS \+ LPP complète\)/);
    assert.match(chart, /Manque de revenu/);
    assert.equal(chart.includes("AVS + rente LPP résiduelle"), false);

    const bars = chartBars(chart);
    for (const year of [2028, 2029, 2030]) {
      const bar = bars.get(year);
      assert.ok(bar, `barre ${year}`);
      assert.equal(bar.vert, axisChf(VERT));
      assert.equal(bar.rouge, axisChf(ROUGE));
    }
    const bar2027 = bars.get(2027);
    assert.ok(bar2027);
    assert.equal(bar2027.vert, axisChf(reference2027));

    const indicateurs = html.slice(chartEnd);
    assert.match(indicateurs, /Revenu brut du scénario 100 % rente/);
    assert.ok(indicateurs.includes(axisChf(VERT)));
  });

  it("proratise chaque fin d'activité : février 2028 n'est pas l'année de rente pleine", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    const results = await retirementAnalysisService.run(input);
    const conjoint = results.conjoint;
    assert.ok(conjoint);
    assert.equal(results.client1.dateFinActivite, "2027-01-01");
    assert.equal(conjoint.dateFinActivite, "2028-02-01");
    assert.equal(conjoint.dateDepart, "2027-11-01");
    assert.notEqual(conjoint.dateFinActivite, conjoint.dateDepart);

    const evolution = results.evolution;
    assert.ok(evolution);
    const row = (year: number) => evolution.rows.find((item) => item.year === year);
    const y2026 = row(2026);
    const y2027 = row(2027);
    const y2028 = row(2028);
    const y2029 = row(2029);
    assert.ok(y2026 && y2027 && y2028 && y2029);

    assert.equal(y2026.revenu, SALAIRE);
    assert.equal(y2026.phase, "salaire");

    const williamRente = results.client1.renteTotale65;
    const arianeAvs = conjoint.avsAnnuel;
    const arianeLpp = conjoint.renteLpp65;
    const williamSalaire = input.salaireClient1;
    const arianeSalaire = input.salaireConjoint;
    assert.equal(conjoint.datePerceptionAvs, "2027-11-01");
    assert.notEqual(conjoint.datePerceptionAvs, conjoint.dateFinActivite);
    const william2027 = round2((williamSalaire * 1) / 12 + (williamRente * 11) / 12);
    const ariane2027 = round2(arianeSalaire + arianeAvs / 12);
    assert.equal(y2027.revenu, round2(william2027 + ariane2027));
    assert.equal(y2027.phase, "transition");
    assert.notEqual(y2027.revenu, round2(williamRente + conjoint.renteTotale65));
    const gap2027 = round2(SALAIRE - y2027.revenu);
    assert.notEqual(gap2027, ROUGE);

    const ariane2028 = round2((arianeSalaire * 2 + arianeAvs * 12 + arianeLpp * 10) / 12);
    const expected2028 = round2(williamRente + ariane2028);
    assert.equal(y2028.revenu, expected2028);
    assert.equal(y2028.phase, "transition");
    assert.equal(y2029.revenu, VERT);
    assert.equal(y2029.phase, "rente");
    assert.notEqual(y2028.revenu, y2029.revenu);
    assert.notEqual(round2(SALAIRE - y2028.revenu), round2(SALAIRE - y2029.revenu));
    assert.ok(y2028.revenu > y2029.revenu);
    assert.ok(y2028.revenu < y2027.revenu);

    const record: AnalyseRecord = {
      id: "helfer-fin-activite",
      createdAt: "2026-10-19T00:00:00.000Z",
      updatedAt: "2026-10-19T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const html = renderPrintableReportHtml(buildReportPayload(record));
    const chartStart = html.indexOf("ÉVOLUTION DU REVENU DE RETRAITE DE RÉFÉRENCE");
    const chartEnd = html.indexOf("Indicateurs du scénario 100 % rente");
    assert.ok(chartStart >= 0 && chartEnd > chartStart);
    const bars = chartBars(html.slice(chartStart, chartEnd));
    assert.equal(bars.get(2027)?.vert, axisChf(y2027.revenu));
    assert.equal(bars.get(2027)?.rouge, axisChf(SALAIRE - y2027.revenu));
    assert.equal(bars.get(2028)?.vert, axisChf(y2028.revenu));
    assert.equal(bars.get(2028)?.rouge, axisChf(SALAIRE - y2028.revenu));
    assert.equal(bars.get(2029)?.vert, axisChf(VERT));
    assert.notEqual(bars.get(2028)?.vert, bars.get(2029)?.vert);
    assert.ok(html.includes("Indicateurs du scénario 100 % rente"));
  });
});
