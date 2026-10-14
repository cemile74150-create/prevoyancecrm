import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  effectiveLppWithdrawalAge,
  lppCapitalForWithdrawalAge,
  rentePontAtAge,
  resolveThirdPillarCapital,
} from "./planification-saisie.ts";

describe("rachat 3e pilier", () => {
  const contract = {
    echeance: "2028-12-31",
    montant: 100_000,
    valeursRachat: [{ date: "2027-06-15", montant: 93_000 }],
  };

  it("utilise 93 000 CHF pour un retrait en 2027, pas le capital 2028", () => {
    const resolved = resolveThirdPillarCapital(contract, 2027);
    assert.equal(resolved.montant, 93_000);
    assert.equal(resolved.statut, "rachat");
    assert.equal(resolved.avertissement, null);
  });

  it("utilise le capital à l'échéance lorsque le retrait est en 2028", () => {
    const resolved = resolveThirdPillarCapital(contract, 2028);
    assert.equal(resolved.montant, 100_000);
    assert.equal(resolved.statut, "echeance");
  });

  it("marque le capital d'échéance comme indicatif si le rachat manque", () => {
    const resolved = resolveThirdPillarCapital(
      { echeance: "2028-01-01", montant: 100_000, valeursRachat: [] },
      2027,
    );
    assert.equal(resolved.montant, 100_000);
    assert.equal(resolved.statut, "indicatif");
    assert.match(resolved.avertissement || "", /valeur de rachat/);
    assert.match(resolved.avertissementPdf || "", /capital à l'échéance/);
  });

  it("n'utilise pas la valeur de rachat d'une autre année", () => {
    const resolved = resolveThirdPillarCapital(contract, 2026);
    assert.equal(resolved.statut, "indicatif");
    assert.equal(resolved.montant, 100_000);
  });

  it("conserve les centimes saisis", () => {
    const resolved = resolveThirdPillarCapital(
      {
        echeance: "2028-01-01",
        montant: 100_000,
        valeursRachat: [{ date: "2027-01-01", montant: 93_000.55 }],
      },
      2027,
    );
    assert.equal(resolved.montant, 93_000.55);
  });
});

describe("âge de retrait LPP", () => {
  it("garde l'âge personnalisé même si l'âge du dossier diffère", () => {
    assert.equal(
      effectiveLppWithdrawalAge({ ageRetraitLppSouhaite: 63 }, 65),
      63,
    );
  });

  it("reprend l'âge du dossier tant qu'il n'est pas personnalisé", () => {
    assert.equal(effectiveLppWithdrawalAge({ ageRetraitLppSouhaite: null }, 65), 65);
    assert.equal(effectiveLppWithdrawalAge({}, 64), 64);
  });

  it("lit le capital de la ligne d'âge, sans inventer une autre ligne", () => {
    const rows = [
      { age: 65, capital: 100_000 },
      { age: 63, capital: 90_000 },
    ];
    assert.deepEqual(lppCapitalForWithdrawalAge(rows, 63), {
      capital: 90_000,
      found: true,
    });
    assert.equal(lppCapitalForWithdrawalAge(rows, 58).found, false);
  });
});

describe("rente-pont", () => {
  it("compte la rente seulement entre le début et la fin", () => {
    const bridges = [{ ageDebut: 63, ageFin: 65, montantAnnuel: 12_000 }];
    assert.equal(rentePontAtAge(bridges, 0, 63).montant, 12_000);
    assert.equal(rentePontAtAge(bridges, 0, 64).montant, 12_000);
    assert.equal(rentePontAtAge(bridges, 0, 65).montant, 0);
    assert.equal(rentePontAtAge(bridges, 0, 63).aVerifier, false);
  });

  it("ne projette pas un montant sans âge de fin", () => {
    const result = rentePontAtAge(
      [{ ageDebut: 62, ageFin: null, montantAnnuel: 8_000 }],
      0,
      62,
    );
    assert.equal(result.montant, 0);
    assert.equal(result.aVerifier, true);
  });

  it("n'additionne pas l'ancien montant unique en plus des lignes", () => {
    const result = rentePontAtAge(
      [{ ageDebut: 63, ageFin: 65, montantAnnuel: 10_000 }],
      99_000,
      63,
    );
    assert.equal(result.montant, 10_000);
  });
});
