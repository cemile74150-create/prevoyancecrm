import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { avsCalculationService } from "../services/AVSCalculationService.ts";
import { postRetirementEvolutionService } from "../services/PostRetirementEvolutionService.ts";
import { timelineService } from "../services/TimelineService.ts";
import { lppTableAge } from "../services/LPPCalculationService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseInput,
} from "../types.ts";

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

function dossier(patch: (input: AnalyseInput) => void): AnalyseInput {
  const input = emptyAnalyseInput();
  input.client1 = emptyPerson("Madame");
  input.client1.prenom = "Claire";
  input.client1.nom = "Martin";
  input.client1.dateNaissance = "1966-08-01";
  input.client1.avsMensuel = 1_890;
  input.client1.avsAnnuel = 24_570;
  input.client1.ageRetraiteSouhaite = 62;
  input.client1.lppPctDeblocable = 0;
  input.client1.lpp = input.client1.lpp.map((row) =>
    row.age === 62
      ? { ...row, capital: 180_000, rente: 9_000 }
      : row.age === 65
        ? { ...row, capital: 400_000, rente: 20_000 }
        : row,
  );
  input.salaireClient1 = 90_000;
  patch(input);
  return input;
}

describe("AVS déjà active et âge professionnel LPP", () => {
  it("une AVS déjà active ne démarre pas à l'âge LPP et n'est pas doublée", () => {
    const input = dossier((item) => {
      item.client1.avsDejaActive = true;
      item.client1.dateDebutRenteAvs = "2026-07-01";
      item.client1.renteAvsPercueMensuelle = 1_750;
    });
    const computed = avsCalculationService.computePersonBasics(input.client1, {
      dossierAgeRetraite: 62,
    });
    assert.equal(computed.avsDejaActive, true);
    assert.equal(computed.datePerceptionAvs, "2026-07-01");
    assert.equal(computed.avsAnnuel, 1_750 * 13);
    assert.notEqual(computed.avsAnnuel, 24_570);
    assert.equal(computed.dateFinActivite, "2028-09-01");
    assert.notEqual(computed.datePerceptionAvs, computed.dateFinActivite);
    assert.equal(computed.ageLppRetenu, 62);
    assert.equal(computed.renteLpp65, 9_000);
    assert.notEqual(computed.renteLpp65, 20_000);
    assert.equal(computed.capitalLpp65, 180_000);
    assert.equal(computed.renteTotale65, round2(1_750 * 13 + 9_000));

    const evolution = postRetirementEvolutionService.build(input, computed, null, {
      startYear: 2026,
      endYear: 2028,
    });
    const y2026 = evolution.rows.find((row) => row.year === 2026);
    const y2027 = evolution.rows.find((row) => row.year === 2027);
    assert.ok(y2026 && y2027);
    const avs = 1_750 * 13;
    assert.equal(y2026.revenu, round2((90_000 * 12 + avs * 6) / 12));
    assert.equal(y2027.revenu, round2(90_000 + avs));
    assert.notEqual(y2027.revenu, round2(avs * 2 + 9_000));

    const timeline = timelineService.build(input, computed, null);
    const avsEvents = timeline.events.filter((event) => event.kind === "avs");
    assert.equal(avsEvents.length, 1);
    assert.equal(avsEvents[0].year, 2026);
    assert.equal(avsEvents[0].amount, avs);
    const lppEvents = timeline.events.filter((event) => event.kind === "lpp");
    assert.ok(lppEvents.every((event) => event.year === 2028));
    assert.equal(
      lppEvents.some((event) => event.label.includes("Rente")),
      true,
    );
  });

  it("sans la case, l'anticipation actuelle reste en place", () => {
    const person = emptyPerson("Monsieur");
    person.dateNaissance = "1962-06-15";
    person.avsAnnuel = 30_000;
    person.anticipationAvsAnnees = 2;
    const computed = avsCalculationService.computePersonBasics(person);
    assert.equal(computed.avsDejaActive, false);
    assert.equal(computed.avsAnnuel, 30_000);
    assert.equal(computed.datePerceptionAvs, "2025-07-01");
  });

  it("58 et 59 ans sont lus tels quels, sans le montant de 65 ans", () => {
    const person = emptyPerson("Monsieur");
    person.dateNaissance = "1968-01-10";
    person.ageRetraiteSouhaite = 58;
    person.lppPctDeblocable = 100;
    person.lpp = person.lpp.map((row) => {
      if (row.age === 58) return { ...row, capital: 120_000, rente: 6_000 };
      if (row.age === 59) return { ...row, capital: 130_000, rente: 6_500 };
      if (row.age === 65) return { ...row, capital: 900_000, rente: 40_000 };
      return row;
    });
    const computed = avsCalculationService.computePersonBasics(person);
    assert.equal(lppTableAge(58), 58);
    assert.equal(lppTableAge(59), 59);
    assert.equal(computed.ageLppRetenu, 58);
    assert.equal(computed.capitalLpp65, 120_000);
    assert.equal(computed.renteLpp65, 6_000);
    assert.equal(computed.lppAvertissement, null);
    assert.equal(computed.capitalLppRetire65, 120_000);
    assert.equal(computed.renteLppResiduelle65, 0);

    person.ageRetraiteSouhaite = 59;
    person.lpp = person.lpp.map((row) =>
      row.age === 59 ? { ...row, capital: 0, rente: 0 } : row,
    );
    const manque = avsCalculationService.computePersonBasics(person);
    assert.equal(manque.ageLppRetenu, 59);
    assert.equal(manque.capitalLpp65, 0);
    assert.equal(manque.renteLpp65, 0);
    assert.match(manque.lppAvertissement || "", /59 ans/);
    assert.equal((manque.lppAvertissement || "").includes("900"), false);
  });

  it("une caisse garde son âge 59 même si le profil est à 62", () => {
    const person = emptyPerson("Madame");
    person.dateNaissance = "1966-05-01";
    person.ageRetraiteSouhaite = 62;
    person.lppPctDeblocable = 100;
    person.lpp = person.lpp.map((row) =>
      row.age === 62 ? { ...row, capital: 50_000, rente: 2_000 } : row,
    );
    person.lppAvoirs = [
      {
        id: "caisse-59",
        institution: "Caisse B",
        ageRetrait: 59,
        pctDeblocable: 0,
        rows: person.lpp.map((row) =>
          row.age === 59 ? { ...row, capital: 80_000, rente: 4_800 } : { ...row, capital: 0, rente: 0 },
        ),
      },
    ];
    const computed = avsCalculationService.computePersonBasics(person);
    const secondaire = computed.lppLignes?.find((line) => line.id === "caisse-59");
    assert.ok(secondaire);
    assert.equal(secondaire.age, 59);
    assert.equal(secondaire.capital, 80_000);
    assert.equal(secondaire.renteResiduelle, 4_800);
    assert.equal(computed.capitalLpp65, 130_000);
    assert.notEqual(secondaire.capital, 50_000);
  });

  it("deux assurés gardent des dates AVS et LPP distinctes", () => {
    const input = dossier((item) => {
      item.etatCivil = "Marié(e)";
      item.client1.avsDejaActive = true;
      item.client1.dateDebutRenteAvs = "2026-07-01";
      item.client1.renteAvsPercueMensuelle = 1_750;
      item.conjoint = emptyPerson("Monsieur");
      item.conjoint.prenom = "Paul";
      item.conjoint.dateNaissance = "1962-06-15";
      item.conjoint.ageRetraiteSouhaite = 64;
      item.conjoint.avsAnnuel = 20_000;
      item.conjoint.lpp = item.conjoint.lpp.map((row) =>
        row.age === 64 ? { ...row, capital: 10_000, rente: 3_000 } : row,
      );
      item.salaireConjoint = 70_000;
    });
    const madame = avsCalculationService.computePersonBasics(input.client1);
    const monsieur = avsCalculationService.computePersonBasics(input.conjoint!);
    assert.equal(madame.datePerceptionAvs, "2026-07-01");
    assert.equal(madame.avsAnnuel, 22_750);
    assert.equal(monsieur.avsDejaActive, false);
    assert.notEqual(monsieur.datePerceptionAvs, madame.datePerceptionAvs);
    assert.equal(monsieur.ageLppRetenu, 64);
    assert.equal(monsieur.renteLpp65, 3_000);
    assert.notEqual(monsieur.dateFinActivite, madame.dateFinActivite);
  });
});
