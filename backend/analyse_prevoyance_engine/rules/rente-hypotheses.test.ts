import assert from "node:assert/strict";
import { describe, it } from "node:test";
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
