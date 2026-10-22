import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { postRetirementEvolutionService } from "../services/PostRetirementEvolutionService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type PersonComputed,
} from "../types.ts";

function computed(
  dateFinActivite: string,
  dateDepart: string,
  rente: number,
): PersonComputed {
  return {
    ageLegal: 65,
    ageLegalLabel: "65 ans",
    dateDepart,
    dateFinActivite,
    avsAnnuel: 0,
    capitalLpp65: 0,
    renteLpp65: 0,
    lppPctDeblocable: 100,
    capitalLppRetire65: 0,
    renteLppResiduelle65: 0,
    renteTotale65: rente,
    total3ePilier: 0,
  };
}

describe("évolution — fin d'activité de chaque assuré", () => {
  it("février 2028 n'est pas une année de rente pleine, et l'autre date reste la sienne", () => {
    const input = emptyAnalyseInput();
    input.etatCivil = "Marié(e)";
    input.salaireClient1 = 120_000;
    input.salaireConjoint = 60_000;
    input.conjoint = emptyPerson("Madame");
    const evolution = postRetirementEvolutionService.build(
      input,
      computed("2027-06-15", "2026-01-01", 40_000),
      computed("2028-02-01", "2027-11-01", 20_000),
    );
    const row = (year: number) => evolution.rows.find((item) => item.year === year);
    const y2027 = row(2027);
    const y2028 = row(2028);
    const y2029 = row(2029);
    assert.ok(y2027 && y2028 && y2029);

    const daysInJune = 30;
    const williamMonths = 6 + (15 - 1) / daysInJune;
    const william2027 =
      Math.round(((120_000 * williamMonths + 40_000 * (12 - williamMonths)) / 12) * 100) / 100;
    assert.equal(y2027.revenu, Math.round((william2027 + 60_000) * 100) / 100);
    assert.notEqual(y2027.revenu, 40_000 + 20_000);
    assert.notEqual(Math.round((180_000 - y2027.revenu) * 100) / 100, 180_000 - 60_000);

    const ariane2028 = Math.round(((60_000 * 2 + 20_000 * 10) / 12) * 100) / 100;
    assert.equal(y2028.revenu, Math.round((40_000 + ariane2028) * 100) / 100);
    assert.equal(y2029.revenu, 60_000);
    assert.notEqual(y2028.revenu, y2029.revenu);
    assert.notEqual(
      Math.round((180_000 - y2028.revenu) * 100) / 100,
      Math.round((180_000 - y2029.revenu) * 100) / 100,
    );

    const laterInFebruary = postRetirementEvolutionService.build(
      input,
      computed("2027-01-01", "2026-01-01", 40_000),
      computed("2028-02-15", "2027-11-01", 20_000),
    );
    const mid = laterInFebruary.rows.find((item) => item.year === 2028);
    assert.ok(mid);
    assert.notEqual(mid.revenu, y2028.revenu);
  });
});
