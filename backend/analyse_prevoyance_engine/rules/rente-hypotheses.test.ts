import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { helferAnalyseInput } from "../fixtures/helfer.ts";
import { renteHypothesisService } from "../services/RenteHypothesisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import type { RenteHypothesisInput } from "../types.ts";
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
  it("Vaudoise : 70 % des excédents une seule fois, rente garantie hors assiette", () => {
    const avs = 24_570 + 25_545;
    const participation = 7_096;
    const partImposable = 4_967.2;
    const fiscal = revenuFiscalImposable({
      type: "certaine",
      renteAvs: avs,
      renteGarantie: 23_136,
      participationExcedents: participation,
    });
    assert.equal(fiscal, avs + partImposable);
    assert.equal(fiscal, 55_082.2);
    assert.notEqual(fiscal, avs + partImposable + partImposable);
    assert.equal(
      revenuBrutEncaisse({
        renteAvs: avs,
        renteGarantie: 23_136,
        participationExcedents: participation,
      }),
      avs + 23_136 + participation,
    );
  });

  it("AVS + 70 % des participations, sans la rente garantie", () => {
    assert.equal(
      revenuFiscalImposable({ type: "certaine", ...base }),
      30_000 + 700,
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
  it("AVS + 4 % de la rente garantie + 70 % des participations", () => {
    assert.equal(
      revenuFiscalImposable({ type: "viagere", ...base }),
      30_000 + 800 + 700,
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

  it("certaine : résiduelle imposable à 100 %, excédents toujours à 70 % une fois", () => {
    const fiscal = revenuFiscalImposable({
      type: "certaine",
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle: residuelle,
    });
    assert.equal(fiscal, 63_110.7);
    assert.equal(fiscal, avs + residuelle + participation * 0.7);
    assert.notEqual(fiscal, avs + residuelle * 0.7 + participation * 0.7);
    assert.notEqual(fiscal, avs + residuelle + residuelle + participation * 0.7);
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

  it("viagère : résiduelle à 100 %, plus 4 % de la garantie et 70 % des excédents", () => {
    const fiscal = revenuFiscalImposable({
      type: "viagere",
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle: residuelle,
    });
    assert.equal(fiscal, avs + residuelle + garantie * 0.04 + participation * 0.7);
  });

  it("100 % déblocable : la résiduelle nulle ne change pas l'assiette", () => {
    const fiscal = revenuFiscalImposable({
      type: "certaine",
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle: 0,
    });
    assert.equal(fiscal, 55_082.2);
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
    assert.equal(certaine.revenuFiscalImposable, 63_110.7);
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
    assert.equal(offre?.revenuFiscalImposable, 55_082.2);
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
