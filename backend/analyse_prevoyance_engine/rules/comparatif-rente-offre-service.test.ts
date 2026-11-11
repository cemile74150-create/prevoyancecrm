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
    assert.equal(col.partImposable, 1742);
    assert.equal(col.revenuEncaisse, 7743);
    assert.equal(col.impotRevenu, 174.2);
    assert.equal(col.revenuNet, 7568.8);
    assert.equal(col.revenusNetsCumules, 7568.8 * 20);
    assert.equal(col.capitalResiduel, 130_000 - 6001 * 20);
    // Gain = cumulés + résiduel − capital = 151376 + 9980 − 130000
    assert.equal(col.gainNet, 31_356);
    assert.equal(col.impotFortuneSiNonAffecte, 26_000);
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
    assert.equal(income[0].revenue1, 1742);
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
    assert.equal(result.columns[0].partImposable, 1_100);
    assert.equal(result.columns[0].dureeAnnees, null);
    assert.equal(result.columns[0].fortuneAnnees, null);
    assert.equal(result.columns[0].revenusNetsCumules, null);
    assert.equal(result.columns[0].capitalResiduel, null);
    assert.equal(result.columns[0].gainNet, null);
    assert.equal(result.columns[0].totalImpotFortune, null);
    assert.equal(result.columns[0].impotFortuneSiNonAffecte, null);
    assert.equal(result.anneesAffichees, 0);
    assert.equal(result.inclureImpotFortune, true);
    assert.ok(calls.every((call) => call.fortune === 0));
    assert.equal(calls.length, 1);
  });

  it("rente certaine sans durée : gain et impôts fortune vides", async () => {
    const calls: DetailedTaxParams[] = [];
    const service = new ComparatifRenteOffreService({
      async calculateDetailedTaxes(params) {
        calls.push(params);
        return { impotRevenuTotal: 80 };
      },
    });
    const input = emptyAnalyseInput();
    input.taxLocationId = 7;
    input.renteHypotheses = [
      offre({
        dureeAnnees: null,
        renteGarantieAnnuelle: 5_000,
        participationExcedentsAnnuelle: 1_000,
      }),
    ];
    const result = await service.build(input);
    assert.equal(result.columns[0].impotRevenu, 80);
    assert.equal(result.columns[0].revenusNetsCumules, null);
    assert.equal(result.columns[0].capitalResiduel, null);
    assert.equal(result.columns[0].gainNet, null);
    assert.equal(result.columns[0].totalImpotFortune, null);
    assert.equal(result.columns[0].impotFortuneSiNonAffecte, null);
    assert.ok(calls.every((call) => call.fortune === 0));
    assert.equal(calls.length, 1);
  });

  it("au-delà de 40 ans, le gain et la fortune constante gardent la durée saisie", async () => {
    const service = new ComparatifRenteOffreService({
      async calculateDetailedTaxes(params) {
        const amount = params.revenue1 > 0 ? params.revenue1 * 0.1 : params.fortune * 0.01;
        return { impotRevenuTotal: Math.round(amount * 100) / 100 };
      },
    });
    const input = emptyAnalyseInput();
    input.taxLocationId = 7;
    input.ageRetraiteSouhaite = 65;
    input.renteHypotheses = [
      offre({
        capitalPlace: 10_000,
        dureeAnnees: 41,
        renteGarantieAnnuelle: 0,
        participationExcedentsAnnuelle: 1_000,
      }),
    ];
    const result = await service.build(input);
    const col = result.columns[0];
    assert.equal(col.dureeFortune, 40);
    assert.equal(col.fortuneAnnees?.length, 40);
    assert.equal(col.revenuNet, 900);
    assert.equal(col.revenusNetsCumules, 900 * 41);
    // Rente garantie 0 → le capital n'est pas consommé ; résiduel = capital.
    assert.equal(col.capitalResiduel, 10_000);
    assert.equal(col.gainNet, 900 * 41);
    assert.equal(col.totalImpotFortune, 4_000);
    assert.equal(col.impotFortuneSiNonAffecte, 4_100);
    assert.match(result.avertissement || "", /41 ans/);
  });

  it("ajoute AVS, rente LPP et autre revenu à l'impôt, pas la fortune ni l'AVS du dossier", async () => {
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
    input.client1.avsAnnuel = 50_115;
    input.fortune = 900_000;
    input.revenusAjoutesImpot = [
      { id: "avs", kind: "avs", montant: 24_570 },
      { id: "lpp", kind: "lpp", montant: 10_000 },
      { id: "autre", kind: "autre", libelle: "Location", montant: 1_000 },
      { id: "vide", kind: "autre", libelle: "Vide", montant: 0 },
    ];
    input.renteHypotheses = [offre({ participationExcedentsAnnuelle: 1742 })];
    const result = await service.build(input);
    assert.deepEqual(
      result.revenusAjoutes.map((row) => row.libelle),
      ["AVS", "Rente LPP", "Location"],
    );
    const income = calls.find((call) => call.revenue1 > 0 && call.fortune === 0);
    assert.equal(income?.revenue1, 1742 + 24_570 + 10_000 + 1_000);
    assert.ok(calls.every((call) => call.revenue1 !== 50_115));
    assert.ok(calls.every((call) => call.fortune !== 900_000));
    assert.equal(result.columns[0].impotRevenu, Math.round((1742 + 35_570) * 0.1 * 100) / 100);
  });
});
