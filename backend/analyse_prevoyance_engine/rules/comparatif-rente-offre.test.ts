import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { revenuFiscalImposable } from "./rente-hypotheses.ts";
import {
  assietteOffreComparatif,
  fortunesDecroissantes,
  revenuEncaisseOffre,
  totalImpotFortune,
} from "./comparatif-rente-offre.ts";

describe("assiette de l'onglet comparatif", () => {
  it("rente certaine : 70 % de la participation, rente garantie hors assiette", () => {
    assert.equal(
      assietteOffreComparatif({
        type: "certaine",
        renteGarantie: 6001,
        participationExcedents: 1742,
      }),
      1219.4,
    );
    assert.equal(
      assietteOffreComparatif({
        type: "certaine",
        renteGarantie: 6001,
        participationExcedents: 0,
      }),
      0,
    );
  });

  it("ne change pas la règle du rapport d'analyse (participation à 100 %)", () => {
    assert.equal(
      revenuFiscalImposable({
        type: "certaine",
        renteAvs: 50115,
        renteGarantie: 6001,
        participationExcedents: 1742,
        renteLppResiduelle: 8029,
      }),
      50115 + 8029 + 1742,
    );
  });

  it("rente viagère : 4 % de la garantie + 100 % de la participation, sans AVS ni LPP", () => {
    assert.equal(
      assietteOffreComparatif({
        type: "viagere",
        renteGarantie: 6001,
        participationExcedents: 1742,
      }),
      1982.04,
    );
  });
});

describe("fortune décroissante", () => {
  it("130000 diminué de 6001 pendant 20 ans", () => {
    const caps = fortunesDecroissantes(130_000, 6001, 20);
    assert.equal(caps.length, 20);
    assert.equal(caps[0], 130_000);
    assert.equal(caps[1], 123_999);
    assert.equal(caps[2], 117_998);
    assert.equal(caps[19], Math.round((130_000 - 19 * 6001) * 100) / 100);
    assert.ok(caps.every((value, index) => index === 0 || value <= caps[index - 1]));
  });

  it("ne descend pas sous zéro", () => {
    assert.deepEqual(fortunesDecroissantes(10_000, 6_000, 5), [10_000, 4_000, 0, 0, 0]);
  });

  it("ignore une durée vide ou une rente viagère sans durée", () => {
    assert.deepEqual(fortunesDecroissantes(130_000, 6_001, 0), []);
    assert.deepEqual(fortunesDecroissantes(130_000, 6_001, -3), []);
  });
});

describe("total impôt fortune", () => {
  it("somme les impôts annuels", () => {
    assert.equal(totalImpotFortune([1200, 1100.5, 0]), 2300.5);
    const caps = fortunesDecroissantes(130_000, 6001, 20);
    const impots = caps.map((fortune) => Math.round(fortune * 0.01 * 100) / 100);
    assert.equal(totalImpotFortune(impots), Math.round(impots.reduce((s, n) => s + n, 0) * 100) / 100);
  });

  it("reste vide si une année n'a pas d'impôt", () => {
    assert.equal(totalImpotFortune([100, null]), null);
    assert.equal(totalImpotFortune([]), null);
  });
});

describe("revenu encaissé de l'offre", () => {
  it("additionne la rente garantie et la participation", () => {
    assert.equal(revenuEncaisseOffre(6001, 1742), 7743);
  });
});
