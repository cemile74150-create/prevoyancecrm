import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { revenuFiscalImposable } from "./rente-hypotheses.ts";
import {
  assietteOffreComparatif,
  fortunesDecroissantes,
  capitalResiduelOffre,
  gainNetOffre,
  impotFortuneCapitalNonAffecte,
  revenusNetsCumulesOffre,
  impotRevenuPourPdf,
  revenuEncaisseOffre,
  totalImpotFortune,
} from "./comparatif-rente-offre.ts";

describe("assiette de l'onglet comparatif", () => {
  it("rente certaine : 0 % de la garantie + 100 % de la participation", () => {
    assert.equal(
      assietteOffreComparatif({
        type: "certaine",
        renteGarantie: 6001,
        participationExcedents: 1742,
      }),
      1742,
    );
    assert.equal(
      assietteOffreComparatif({
        type: "certaine",
        renteGarantie: 10_000,
        participationExcedents: 1_000,
      }),
      1_000,
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

  it("rente viagère : 4 % de la garantie + 70 % de la participation, sans AVS ni LPP", () => {
    assert.equal(
      assietteOffreComparatif({
        type: "viagere",
        renteGarantie: 6001,
        participationExcedents: 1742,
      }),
      240.04 + 1219.4,
    );
    assert.equal(
      assietteOffreComparatif({
        type: "viagere",
        renteGarantie: 10_000,
        participationExcedents: 1_000,
      }),
      400 + 700,
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

describe("impôt de la rente sur le PDF", () => {
  it("garde le montant annuel : 340 sur 10 ans reste 340 par an", () => {
    const line = impotRevenuPourPdf("certaine", 340, 10);
    assert.equal(line.mode, "annuel");
    assert.equal(line.montant, 340);
    assert.equal(line.libelle, "Impôt de la rente (par an)");
    assert.equal(line.annees, null);
    assert.equal(impotRevenuPourPdf("viagere", 340, 20).montant, 340);
  });
});

describe("gain net et fortune non affectée", () => {
  it("capital résiduel = max(0, capital − rente garantie × durée)", () => {
    assert.equal(capitalResiduelOffre(130_000, 6_001, 20), 9_980);
    assert.equal(capitalResiduelOffre(10_000, 6_000, 5), 0);
    assert.equal(capitalResiduelOffre(400_000, 10_000, 10), 300_000);
    assert.equal(capitalResiduelOffre(130_000, 6_001, null), null);
    assert.equal(capitalResiduelOffre(130_000, 6_001, 0), null);
  });

  it("revenus nets cumulés = revenu net annuel × durée", () => {
    assert.equal(revenusNetsCumulesOffre(7_621.06, 20), 152_421.2);
    assert.equal(revenusNetsCumulesOffre(10_000, 10), 100_000);
    assert.equal(revenusNetsCumulesOffre(null, 20), null);
    assert.equal(revenusNetsCumulesOffre(10_000, 0), null);
  });

  it("gain = revenus cumulés + capital résiduel − capital initial", () => {
    // Sans résiduel (défaut 0) : revenus × durée − capital
    assert.equal(gainNetOffre(7621.06, 20, 130_000), 22_421.2);
    assert.equal(gainNetOffre(10_000, 10, 400_000), -300_000);
    // Avec résiduel 9980 : 152421.2 + 9980 − 130000
    assert.equal(gainNetOffre(7621.06, 20, 130_000, 9_980), 32_401.2);
    // Capital entièrement consommé : résiduel 0
    assert.equal(gainNetOffre(10_000, 5, 10_000, 0), 40_000);
    assert.equal(gainNetOffre(10_000, null, 400_000), null);
    assert.equal(gainNetOffre(null, 20, 130_000), null);
    assert.equal(gainNetOffre(10_000, 0, 400_000), null);
  });

  it("impôt fortune du capital non affecté = impôt annuel sur ce capital × durée", () => {
    assert.equal(impotFortuneCapitalNonAffecte(1_300, 20), 26_000);
    assert.equal(impotFortuneCapitalNonAffecte(400, 10), 4_000);
    assert.equal(impotFortuneCapitalNonAffecte(400, null), null);
    assert.equal(impotFortuneCapitalNonAffecte(null, 20), null);
    assert.equal(impotFortuneCapitalNonAffecte(400, 0), null);
  });
});
