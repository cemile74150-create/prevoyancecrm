import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { emptyAnalyseInput, type RenteHypothesisInput } from "../types.ts";
import { ComparatifRenteOffreService } from "../services/ComparatifRenteOffreService.ts";
import type { DetailedTaxParams } from "../services/TaxCalculationService.ts";

function offre(partial: Partial<RenteHypothesisInput> = {}): RenteHypothesisInput {
  return {
    id: "vaudoise",
    type: "certaine",
    compagnie: "Vaudoise",
    capitalPlace: 130_000,
    dureeAnnees: 20,
    renteGarantieAnnuelle: 6001,
    participationExcedentsAnnuelle: 0,
    recommander: true,
    ...partial,
  };
}

describe("calcul comparatif — appels ESTV isolés", () => {
  it("impôt revenu sur l'offre seule, fortune décroissante, somme sur 20 ans", async () => {
    const calls: DetailedTaxParams[] = [];
    const service = new ComparatifRenteOffreService({
      async calculateDetailedTaxes(params) {
        calls.push(params);
        const amount = params.revenue1 > 0 ? params.revenue1 * 0.1 : params.fortune * 0.01;
        return { impotRevenuTotal: Math.round(amount * 100) / 100 };
      },
    });
    const input = emptyAnalyseInput();
    input.taxLocationId = 42;
    input.taxYear = 2026;
    input.ageRetraiteSouhaite = 65;
    input.client1.avsAnnuel = 50_115;
    input.fortune = 900_000;
    input.renteHypotheses = [offre({ participationExcedentsAnnuelle: 1742 })];

    const result = await service.build(input);
    const col = result.columns[0];
    assert.equal(col.partImposable, 1219.4);
    assert.equal(col.revenuEncaisse, 7743);
    assert.equal(col.impotRevenu, 121.94);
    assert.equal(col.fortuneAnnees?.length, 20);
    assert.equal(col.fortuneAnnees?.[0].fortune, 130_000);
    assert.equal(col.fortuneAnnees?.[1].fortune, 123_999);
    assert.equal(col.fortuneAnnees?.[2].fortune, 117_998);
    assert.equal(col.fortuneAnnees?.[0].impotFortune, 1300);
    assert.equal(col.fortuneAnnees?.[1].impotFortune, 1239.99);

    const expectedTotal =
      Math.round(
        (col.fortuneAnnees || []).reduce((sum, row) => sum + (row.impotFortune || 0), 0) * 100,
      ) / 100;
    assert.equal(col.totalImpotFortune, expectedTotal);
    assert.equal(result.anneesAffichees, 20);

    const income = calls.filter((call) => call.revenue1 > 0);
    assert.equal(income.length, 1);
    assert.equal(income[0].revenue1, 1219.4);
    assert.equal(income[0].fortune, 0);
    assert.equal(income[0].revenue2, 0);
    assert.ok(calls.every((call) => call.revenue1 !== 50_115));
    assert.ok(calls.every((call) => call.fortune !== 900_000));

    const wealth = calls.filter((call) => call.revenue1 === 0 && call.fortune > 0);
    assert.equal(wealth.length, 20);
    const byFortune = new Map(wealth.map((call) => [call.fortune, call]));
    assert.equal(byFortune.get(130_000)?.age1, 65);
    assert.equal(byFortune.get(123_999)?.age1, 66);
  });

  it("rente viagère : pas de calendrier de fortune", async () => {
    const calls: DetailedTaxParams[] = [];
    const service = new ComparatifRenteOffreService({
      async calculateDetailedTaxes(params) {
        calls.push(params);
        return { impotRevenuTotal: 100 };
      },
    });
    const input = emptyAnalyseInput();
    input.taxLocationId = 7;
    input.renteHypotheses = [
      offre({
        id: "helvetia",
        type: "viagere",
        compagnie: "Helvetia",
        dureeAnnees: 20,
        renteGarantieAnnuelle: 10_000,
        participationExcedentsAnnuelle: 1_000,
      }),
    ];
    const result = await service.build(input);
    assert.equal(result.columns[0].partImposable, 1_400);
    assert.equal(result.columns[0].fortuneAnnees, null);
    assert.equal(result.columns[0].totalImpotFortune, null);
    assert.equal(result.anneesAffichees, 0);
    assert.ok(calls.every((call) => call.fortune === 0));
    assert.equal(calls.length, 1);
  });
});
