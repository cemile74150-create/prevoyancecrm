import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { avsCalculationService } from "../services/AVSCalculationService.ts";
import { lppCalculationService } from "../services/LPPCalculationService.ts";
import {
  emptyLppRows,
  emptyPerson,
  type LppByAge,
} from "../types.ts";

function rows(age: number, capital: number, rente: number, renteReduite = 0): LppByAge[] {
  return emptyLppRows().map((row) =>
    row.age === age ? { ...row, capital, rente, renteReduite } : row,
  );
}

describe("plusieurs LPP et caisse étatique", () => {
  it("additionne chaque caisse classique après son pourcentage, une seule fois", () => {
    const person = emptyPerson("Monsieur");
    person.lppPctDeblocable = 100;
    person.lppInstitution = "Publica";
    person.lpp = rows(64, 200_000, 12_000);
    person.lppAvoirs = [
      {
        id: "ciepp",
        institution: "CIEPP",
        pctDeblocable: 50,
        rows: rows(64, 80_000, 6_000),
      },
    ];
    const at64 = lppCalculationService.aggregateAtAge(person, 64);
    assert.equal(at64.capital, 280_000);
    assert.equal(at64.capitalRetire, 240_000);
    assert.equal(at64.rente, 18_000);
    assert.equal(at64.renteResiduelle, 3_000);
    assert.equal(at64.lines[1].capitalRetire, 40_000);
    assert.equal(
      lppCalculationService.capitalRetireForItem(person, "ciepp", 64),
      40_000,
    );
    assert.equal(
      lppCalculationService.capitalRetireForItem(person, undefined, 64),
      200_000,
    );
  });

  it("une seule LPP à 50 % reste le calcul historique, à 65 ans", () => {
    const person = emptyPerson("Monsieur");
    person.dateNaissance = "1970-01-10";
    person.lppPctDeblocable = 50;
    person.lpp = rows(65, 100_000, 6_000);
    const computed = avsCalculationService.computePersonBasics(person);
    assert.equal(computed.ageLppRetenu, 65);
    assert.equal(computed.capitalLpp65, 100_000);
    assert.equal(computed.capitalLppRetire65, 50_000);
    assert.equal(computed.renteLpp65, 6_000);
    assert.equal(computed.renteLppResiduelle65, 3_000);
    assert.equal(computed.dateFinActivite, computed.dateDepart);
    assert.equal(computed.datePerceptionAvs, computed.dateDepart);
    assert.equal(computed.lppLignes?.length, 1);
  });

  it("conserve la rente réduite d'une caisse étatique dans le scénario capital", () => {
    const person = emptyPerson("Madame");
    person.lppType = "etatique";
    person.lppRetraitEtatique = "capital_max";
    person.lppRenteUnite = "annuel";
    person.lppPctDeblocable = 50;
    person.lpp = rows(65, 120_000, 24_000, 9_600);
    const line = lppCalculationService.aggregateAtAge(person, 65).lines[0];
    assert.equal(line.capitalRetire, 120_000);
    assert.equal(line.rente, 24_000);
    assert.equal(line.renteResiduelle, 9_600);
    assert.equal(
      lppCalculationService.capitalRetireForItem(person, undefined, 65),
      120_000,
    );
  });

  it("une caisse étatique en rente entière ne retire aucun capital", () => {
    const person = emptyPerson("Monsieur");
    person.lppType = "etatique";
    person.lppRetraitEtatique = "rente_entiere";
    person.lppRenteUnite = "mensuel";
    person.lpp = rows(65, 80_000, 2_000, 800);
    const line = lppCalculationService.aggregateAtAge(person, 65).lines[0];
    assert.equal(line.capitalRetire, 0);
    assert.equal(line.rente, 24_000);
    assert.equal(line.renteResiduelle, 24_000);
  });

  it("sépare la fin d'activité LPP à 64 ans du retrait AVS à 65 ans", () => {
    const person = emptyPerson("Monsieur");
    person.dateNaissance = "1962-06-15";
    person.ageRetraitLppSouhaite = 64;
    person.lppPctDeblocable = 100;
    person.lpp = emptyLppRows().map((row) => {
      if (row.age === 64) return { ...row, capital: 200_000, rente: 12_000 };
      if (row.age === 65) return { ...row, capital: 999_999, rente: 99_999 };
      return row;
    });
    const computed = avsCalculationService.computePersonBasics(person, {
      agePerceptionAvs: 65,
    });
    assert.equal(computed.ageLppRetenu, 64);
    assert.equal(computed.capitalLpp65, 200_000);
    assert.notEqual(computed.capitalLpp65, 999_999);
    assert.equal(computed.dateFinActivite, "2026-07-01");
    assert.equal(computed.ageFinActiviteLabel, "64 ans");
    assert.equal(computed.datePerceptionAvs, "2027-07-01");
    assert.equal(computed.agePerceptionAvsLabel, "65 ans");
  });

  it("conserve le parcours à étapes et le comparatif des rentes", () => {
    const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
    const wizard = readFileSync(
      resolve(root, "frontend/src/analyse-prevoyance/lib/analyseWizard.ts"),
      "utf8",
    );
    const nav = readFileSync(
      resolve(root, "frontend/src/analyse-prevoyance/components/AnalyseWizardNav.tsx"),
      "utf8",
    );
    const pdf = readFileSync(
      resolve(root, "backend/analyse_prevoyance_engine/pdf/renderPrintableReportHtml.ts"),
      "utf8",
    );
    const saisie = readFileSync(
      resolve(root, "frontend/src/analyse-prevoyance/lib/planificationSaisie.ts"),
      "utf8",
    );
    assert.match(wizard, /export const ANALYSE_STEPS/);
    assert.match(wizard, /3e piliers/);
    assert.match(nav, /Étapes/);
    assert.match(pdf, /COMPARATIF DES RENTES/);
    assert.match(saisie, /effectiveLppWithdrawalAge/);
    assert.equal(pdf.includes("Âge de fin d'activité"), false);
  });
});
