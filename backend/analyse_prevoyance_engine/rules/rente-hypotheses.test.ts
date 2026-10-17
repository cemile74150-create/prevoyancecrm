import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { helferAnalyseInput } from "../fixtures/helfer.ts";
import { formatChf } from "../mappers.ts";
import { renderPrintableReportHtml } from "../pdf/renderPrintableReportHtml.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { renteHypothesisService } from "../services/RenteHypothesisService.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseRecord,
  type LppByAge,
  type RenteHypothesisInput,
} from "../types.ts";
import {
  revenuBrutEncaisse,
  revenuFiscalImposable,
  revenuFiscalRenteLpp,
  revenuNetApresImpot,
} from "./rente-hypotheses.ts";

const base = {
  renteAvs: 30_000,
  renteGarantie: 20_000,
  participationExcedents: 1_000,
};

describe("rente certaine — revenu fiscal", () => {
  it("Vaudoise : 100 % des excédents une seule fois, rente garantie hors assiette", () => {
    const avs = 24_570 + 25_545;
    const participation = 7_096;
    const fiscal = revenuFiscalImposable({
      type: "certaine",
      renteAvs: avs,
      renteGarantie: 23_136,
      participationExcedents: participation,
    });
    assert.equal(fiscal, avs + participation);
    assert.equal(fiscal, 57_211);
    assert.notEqual(fiscal, avs + participation + participation);
    assert.equal(
      revenuBrutEncaisse({
        renteAvs: avs,
        renteGarantie: 23_136,
        participationExcedents: participation,
      }),
      avs + 23_136 + participation,
    );
  });

  it("AVS + 100 % des participations, sans la rente garantie", () => {
    assert.equal(
      revenuFiscalImposable({ type: "certaine", ...base }),
      30_000 + 1_000,
    );
  });

  it("ne change pas si la rente garantie change", () => {
    const a = revenuFiscalImposable({ type: "certaine", ...base, renteGarantie: 1 });
    const b = revenuFiscalImposable({
      type: "certaine",
      ...base,
      renteGarantie: 99_000,
    });
    assert.equal(a, b);
  });
});

describe("rente viagère — revenu fiscal", () => {
  it("AVS + 4 % de la rente garantie + 100 % des participations", () => {
    assert.equal(
      revenuFiscalImposable({ type: "viagere", ...base }),
      30_000 + 800 + 1_000,
    );
  });

  it("inclut 4 % de la garantie, pas la garantie entière", () => {
    const fiscal = revenuFiscalImposable({
      type: "viagere",
      renteAvs: 0,
      renteGarantie: 10_000,
      participationExcedents: 0,
    });
    assert.equal(fiscal, 400);
    assert.notEqual(fiscal, 10_000);
  });
});

describe("encaissé, impôt et net", () => {
  it("le brut encaissé additionne AVS, garantie et participations", () => {
    assert.equal(revenuBrutEncaisse(base), 51_000);
  });

  it("le fiscal certaine n'est pas le brut encaissé", () => {
    const fiscal = revenuFiscalImposable({ type: "certaine", ...base });
    assert.notEqual(fiscal, revenuBrutEncaisse(base));
  });

  it("revenu net = brut encaissé − impôt ESTV", () => {
    assert.equal(revenuNetApresImpot(51_000, 4_250), 46_750);
  });

  it("la rente LPP de référence est imposable en totalité avec l'AVS", () => {
    assert.equal(revenuFiscalRenteLpp(28_000, 18_000), 46_000);
  });
});

describe("rente LPP résiduelle dans les offres", () => {
  const avs = 24_570 + 25_545;
  const residuelle = 8_028.5;
  const garantie = 23_136;
  const participation = 7_096;

  it("certaine : résiduelle imposable à 100 %, excédents à 100 % une fois", () => {
    const fiscal = revenuFiscalImposable({
      type: "certaine",
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle: residuelle,
    });
    assert.equal(fiscal, 65_239.5);
    assert.equal(fiscal, avs + residuelle + participation);
    assert.notEqual(fiscal, avs + residuelle * 0.7 + participation);
    assert.notEqual(fiscal, avs + residuelle + residuelle + participation);
    assert.equal(
      revenuBrutEncaisse({
        renteAvs: avs,
        renteGarantie: garantie,
        participationExcedents: participation,
        renteLppResiduelle: residuelle,
      }),
      88_375.5,
    );
  });

  it("viagère : résiduelle à 100 %, plus 4 % de la garantie et 100 % des excédents", () => {
    const fiscal = revenuFiscalImposable({
      type: "viagere",
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle: residuelle,
    });
    assert.equal(fiscal, avs + residuelle + garantie * 0.04 + participation);
  });

  it("100 % déblocable : la résiduelle nulle ne change pas l'assiette", () => {
    const fiscal = revenuFiscalImposable({
      type: "certaine",
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle: 0,
    });
    assert.equal(fiscal, 57_211);
  });
});

const vaudoise: RenteHypothesisInput = {
  id: "vaudoise",
  type: "certaine",
  compagnie: "Vaudoise",
  capitalPlace: 530_000,
  dureeAnnees: 20,
  renteGarantieAnnuelle: 23_136,
  participationExcedentsAnnuelle: 7_096,
};

const autre: RenteHypothesisInput = {
  id: "autre",
  type: "viagere",
  compagnie: "Autre",
  capitalPlace: 200_000,
  dureeAnnees: null,
  renteGarantieAnnuelle: 10_000,
  participationExcedentsAnnuelle: 1_000,
};

describe("comparatif — rente LPP résiduelle du foyer", () => {
  const original = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );

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

  it("Helfer : 50 % d'Ariane, 0 pour William, sur chaque offre et pas sur la référence LPP", async () => {
    const input = {
      ...helferAnalyseInput(),
      ageRetraiteSouhaite: 65,
      comparerAvecRenteLpp: true,
      renteHypotheses: [vaudoise, autre],
    };
    const built = await renteHypothesisService.build(input);
    assert.ok(built);
    const lpp = built.columns.find((col) => col.kind === "lpp");
    const offres = built.columns.filter((col) => col.kind === "hypothese");
    assert.equal(lpp?.renteLppResiduelle, null);
    assert.equal(lpp?.renteGarantie, 21_024 + 16_057);
    assert.equal(lpp?.revenuFiscalImposable, 50_115 + 37_081);
    assert.equal(offres.length, 2);
    for (const col of offres) {
      assert.equal(col.renteLppResiduelle, 8_028.5);
    }
    const certaine = offres[0];
    assert.equal(certaine.revenuFiscalImposable, 65_239.5);
    assert.equal(certaine.revenuBrutEncaisse, 88_375.5);
    assert.equal(certaine.revenuNetApresImpot, 88_375.5 - 1_000);
    assert.equal(certaine.ecartNetAnnuelVsLpp, 87_375.5 - (lpp?.revenuNetApresImpot ?? 0));
  });

  it("additionne les résiduelles des deux assurés", async () => {
    const input = helferAnalyseInput();
    input.client1.lppPctDeblocable = 50;
    input.conjoint!.lppPctDeblocable = 25;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [vaudoise];
    const built = await renteHypothesisService.build(input);
    const offre = built?.columns.find((col) => col.kind === "hypothese");
    assert.equal(offre?.renteLppResiduelle, 21_024 * 0.5 + 16_057 * 0.75);
  });

  it("100 % des deux côtés : résiduelle 0, assiette certaine inchangée", async () => {
    const input = helferAnalyseInput();
    input.client1.lppPctDeblocable = 100;
    input.conjoint!.lppPctDeblocable = 100;
    input.renteHypotheses = [vaudoise];
    const built = await renteHypothesisService.build(input);
    const offre = built?.columns.find((col) => col.kind === "hypothese");
    assert.equal(offre?.renteLppResiduelle, 0);
    assert.equal(offre?.revenuFiscalImposable, 57_211);
  });

  it("personne seule à 25 % déblocable : conserve 75 % de sa rente", async () => {
    const input = helferAnalyseInput();
    input.etatCivil = "Personne vivant seule";
    input.conjoint = null;
    input.client1.lppPctDeblocable = 25;
    input.renteHypotheses = [vaudoise];
    const built = await renteHypothesisService.build(input);
    const offre = built?.columns.find((col) => col.kind === "hypothese");
    assert.equal(offre?.renteLppResiduelle, 21_024 * 0.75);
    assert.equal(offre?.renteAvs, 24_570);
  });

  after(() => {
    taxCalculationService.calculateDetailedTaxes = original;
  });
});

function lppAt(ageRente: Array<[number, number]>): LppByAge[] {
  return emptyPerson().lpp.map((row) => {
    const hit = ageRente.find(([age]) => age === row.age);
    return hit ? { ...row, capital: 100_000, rente: hit[1] } : row;
  });
}

describe("colonne 100 % rente — part imposable = rentes affichées", () => {
  const original = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );

  it("deux assurés : AVS + LPP José + LPP Ana Paula, sans la rente d'un autre âge", async () => {
    const jose = 21_144;
    const ana = 8_892;
    const avsJose = 20_000;
    const avsAna = 24_057;
    const extraAge65 = 2_220;
    const input = emptyAnalyseInput();
    input.etatCivil = "Marié(e)";
    input.ageRetraiteSouhaite = 65;
    input.taxLocationId = 170_000_000;
    input.taxGroupId = 170_000_000;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [
      {
        id: "certaine-0",
        type: "certaine",
        compagnie: "Offre",
        capitalPlace: 100_000,
        dureeAnnees: 10,
        renteGarantieAnnuelle: 12_000,
        participationExcedentsAnnuelle: 0,
      },
    ];
    input.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "José",
      nom: "Test",
      dateNaissance: "1961-06-01",
      avsAnnuel: avsJose,
      ageRetraitLppSouhaite: 64,
      lppPctDeblocable: 50,
      lpp: lppAt([
        [64, jose],
        [65, jose + extraAge65],
      ]),
    };
    input.conjoint = {
      ...emptyPerson("Madame"),
      prenom: "Ana Paula",
      nom: "Test",
      dateNaissance: "1964-03-01",
      avsAnnuel: avsAna,
      ageRetraitLppSouhaite: 64,
      lppPctDeblocable: 100,
      lpp: lppAt([
        [64, ana],
        [65, ana],
      ]),
    };

    const household = avsJose + avsAna + jose + ana;
    const originalCapital = taxCalculationService.calculateCapitalTax.bind(
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
      taxFed: 0,
      taxChurch: 0,
      impotTotal: 0,
      request: {},
      response: {},
    });
    taxCalculationService.calculateDetailedTaxes = async (params) => {
      const sum = Math.round(params.revenue1 + params.revenue2);
      const jointHousehold = params.foyer === "Couple1" && sum === household;
      return {
        foyer: params.foyer ?? "default",
        age: params.age1,
        taxLocationId: params.taxLocationId,
        taxYear: params.taxYear ?? 2025,
        revenu1: params.revenue1,
        revenu2: params.revenue2,
        fortune: params.fortune,
        impotRevenuTotal: jointHousehold ? 3_633 : sum === household ? 3_809 : 2_570,
        impotFederal: jointHousehold ? 3_633 : 3_809,
        impotCanton: 0,
        impotCommune: 0,
        impotEglise: 0,
        request: {},
        response: {},
      };
    };

    const results = await retirementAnalysisService.run(input);
    const record: AnalyseRecord = {
      id: "deux-lpp",
      createdAt: "2026-10-16T00:00:00.000Z",
      updatedAt: "2026-10-16T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const lpp = results.renteHypotheses?.columns.find((col) => col.kind === "lpp");
    assert.ok(lpp);
    assert.equal(results.client1.renteLpp65, jose);
    assert.equal(results.conjoint?.renteLpp65, ana);
    const part = lpp.renteAvs + results.client1.renteLpp65 + (results.conjoint?.renteLpp65 ?? 0);
    assert.equal(part, avsJose + avsAna + jose + ana);
    assert.equal(lpp.revenuFiscalImposable, part);
    assert.equal(lpp.revenuFiscalImposable, 74_093);
    assert.equal(part + extraAge65, 76_313);
    assert.notEqual(lpp.revenuFiscalImposable, 76_313);
    assert.notEqual(lpp.revenuFiscalImposable, part + extraAge65);
    assert.notEqual(
      lpp.revenuFiscalImposable,
      part + results.client1.renteLppResiduelle65,
    );
    assert.equal(lpp.participationExcedents, 0);
    assert.equal(lpp.impotEstv, 3_633);
    assert.notEqual(lpp.impotEstv, 3_809);
    assert.equal(lpp.revenuNetApresImpot, part - 3_633);

    const html = renderPrintableReportHtml(buildReportPayload(record));
    const start = html.indexOf("COMPARATIF DES RENTES");
    const card = html.slice(start);
    assert.ok(card.includes("LPP – José"));
    assert.ok(card.includes("LPP – Ana Paula"));
    const partRow = (card.split("Part imposable")[1] || "").split("</tr>")[0];
    assert.ok(partRow.includes(formatChf(part)));
    const taxRow = (card.split("ICC / IFD")[1] || "").split("</tr>")[0];
    const netRow = (card.split("Revenu net")[1] || "").split("</tr>")[0];
    assert.ok(taxRow.includes(formatChf(3_633)));
    assert.equal(taxRow.includes(formatChf(3_809)), false);
    assert.ok(netRow.includes(formatChf(part - 3_633)));
    assert.equal(partRow.includes(formatChf(part + extraAge65)), false);
    const options = html.slice(html.indexOf("Comparaison des options de retraite"));
    const optionsTax = (options.split("Impôts ICC")[1] || "").split("</tr>")[0];
    assert.ok(optionsTax.includes(formatChf(3_633)));
    assert.equal(optionsTax.includes(formatChf(3_809)), false);
    const optionsNet = (options.split("Rente après impôt")[1] || "").split("</tr>")[0];
    assert.ok(optionsNet.includes(formatChf(part - 3_633)));

    const couple1 = results.incomeScenarios.find((s) => s.foyer === "Couple1");
    assert.equal((couple1?.revenu1 ?? 0) + (couple1?.revenu2 ?? 0), 74_093);
    assert.equal(couple1?.impot?.impotRevenuTotal, lpp.impotEstv);
    taxCalculationService.calculateCapitalTax = originalCapital;
  });

  it("100 % retiré : rente résiduelle nulle, revenu capital = AVS seule", async () => {
    const jose = 21_144;
    const ana = 8_892;
    const avsJose = 20_000;
    const avsAna = 24_057;
    const input = emptyAnalyseInput();
    input.etatCivil = "Marié(e)";
    input.ageRetraiteSouhaite = 65;
    input.taxLocationId = 170_000_000;
    input.taxGroupId = 170_000_000;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [
      {
        id: "certaine-0",
        type: "certaine",
        compagnie: "Offre",
        capitalPlace: 582_004,
        dureeAnnees: 10,
        renteGarantieAnnuelle: 0,
        participationExcedentsAnnuelle: 0,
      },
    ];
    input.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "José",
      nom: "Test",
      dateNaissance: "1961-06-01",
      avsAnnuel: avsJose,
      ageRetraitLppSouhaite: 64,
      lppPctDeblocable: 100,
      lpp: lppAt([
        [64, jose],
        [65, jose + 2_220],
      ]),
    };
    input.conjoint = {
      ...emptyPerson("Madame"),
      prenom: "Ana Paula",
      nom: "Test",
      dateNaissance: "1964-03-01",
      avsAnnuel: avsAna,
      lppPctDeblocable: 100,
      lpp: lppAt([[65, ana]]),
    };
    const household = avsJose + avsAna + jose + ana;
    const avsOnly = avsJose + avsAna;
    const originalCapital = taxCalculationService.calculateCapitalTax.bind(
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
      taxFed: 0,
      taxChurch: 0,
      impotTotal: 0,
      request: {},
      response: {},
    });
    taxCalculationService.calculateDetailedTaxes = async (params) => {
      const sum = Math.round(params.revenue1 + params.revenue2);
      return {
        foyer: params.foyer ?? "default",
        age: params.age1,
        taxLocationId: params.taxLocationId,
        taxYear: params.taxYear ?? 2025,
        revenu1: params.revenue1,
        revenu2: params.revenue2,
        fortune: params.fortune,
        impotRevenuTotal:
          params.foyer === "Couple1" && sum === household
            ? 3_633
            : sum === household
              ? 3_809
              : 2_570,
        impotFederal: 0,
        impotCanton: 0,
        impotCommune: 0,
        impotEglise: 0,
        request: {},
        response: {},
      };
    };

    const results = await retirementAnalysisService.run(input);
    taxCalculationService.calculateCapitalTax = originalCapital;
    assert.equal(results.client1.renteLppResiduelle65, 0);
    assert.equal(results.conjoint?.renteLppResiduelle65, 0);
    assert.equal(results.capitalPathFoyer?.renteResiduelleTotal, 0);
    const couple2 = results.incomeScenarios.find((s) => s.foyer === "Couple2");
    assert.equal((couple2?.revenu1 ?? 0) + (couple2?.revenu2 ?? 0), avsOnly);
    assert.equal(couple2?.impot?.impotRevenuTotal, 2_570);
    const couple1 = results.incomeScenarios.find((s) => s.foyer === "Couple1");
    assert.equal((couple1?.revenu1 ?? 0) + (couple1?.revenu2 ?? 0), household);
    assert.equal(results.lacune.revenuApres, household);

    const record: AnalyseRecord = {
      id: "capital-100",
      createdAt: "2026-10-16T00:00:00.000Z",
      updatedAt: "2026-10-16T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const payload = buildReportPayload(record);
    const lpp = results.renteHypotheses?.columns.find((col) => col.kind === "lpp");
    assert.equal(lpp?.impotEstv, couple1?.impot?.impotRevenuTotal);
    assert.equal(lpp?.impotEstv, 3_633);
    assert.equal(lpp?.revenuNetApresImpot, household - 3_633);
    assert.equal(payload.aggregates.renteApresImpot, household - 3_633);
    assert.equal(payload.aggregates.renteNetteCheminCapital, avsOnly - 2_570);
    const html = renderPrintableReportHtml(payload);
    const page = html.slice(html.indexOf("Comparaison des options de retraite"));
    const joseRow = (page.split("Rente LPP – José")[1] || "").split("</tr>")[0];
    assert.ok(joseRow.includes(formatChf(jose)));
    assert.ok(joseRow.includes("—"));
    assert.equal(joseRow.includes(formatChf(jose + 2_220)), false);
    const anaRow = (page.split("Rente LPP – Ana Paula")[1] || "").split("</tr>")[0];
    assert.ok(anaRow.includes(formatChf(ana)));
    assert.ok(anaRow.includes("—"));
  });

  after(() => {
    taxCalculationService.calculateDetailedTaxes = original;
  });
});
