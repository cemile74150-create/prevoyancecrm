import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  AVS_MENSUALITES_PAR_AN,
  avsCalculationService,
} from "../services/AVSCalculationService.ts";
import { emptyPerson } from "../types.ts";
import { HELFER_EXCEL } from "../fixtures/helfer.ts";

describe("AVS annuelle = mensuelle × 13", () => {
  it("1890 → 24570 et 1965 → 25545, pas × 12", () => {
    assert.equal(AVS_MENSUALITES_PAR_AN, 13);
    assert.equal(avsCalculationService.annualFromMonthly(1_890), 24_570);
    assert.equal(avsCalculationService.annualFromMonthly(1_965), 25_545);
    assert.equal(
      avsCalculationService.annualFromMonthly(1_890) +
        avsCalculationService.annualFromMonthly(1_965),
      50_115,
    );
    assert.notEqual(avsCalculationService.annualFromMonthly(1_890), 1_890 * 12);
    assert.notEqual(avsCalculationService.annualFromMonthly(1_965), 1_965 * 12);
    assert.notEqual(
      avsCalculationService.annualFromMonthly(1_890) +
        avsCalculationService.annualFromMonthly(1_965),
      46_260,
    );
  });

  it("HELFER : annuel saisi = mensuel × 13", () => {
    assert.equal(HELFER_EXCEL.client1.avsMensuel * 13, HELFER_EXCEL.client1.avsAnnuel);
    assert.equal(HELFER_EXCEL.conjoint.avsMensuel * 13, HELFER_EXCEL.conjoint.avsAnnuel);
    assert.equal(HELFER_EXCEL.aggregates.avsTotal, 24_570 + 25_545);
  });

  it("sans annuel enregistré, le moteur déduit × 13", () => {
    const william = emptyPerson("Monsieur");
    william.avsMensuel = 1_890;
    william.avsAnnuel = null;
    const ariane = emptyPerson("Madame");
    ariane.avsMensuel = 1_965;
    ariane.avsAnnuel = null;
    assert.equal(avsCalculationService.resolveAnnual(william), 24_570);
    assert.equal(avsCalculationService.resolveAnnual(ariane), 25_545);
  });
});
