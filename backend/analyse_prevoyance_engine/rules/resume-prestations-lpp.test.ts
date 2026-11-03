import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatChf } from "../mappers";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import {
  buildResumePrestationsLpp,
  fillResumeCapitalTax,
  renderResumeAgesHtml,
  renderResumePrestationsLppHtml,
} from "./resume-prestations-lpp.ts";
import type { AnalyseInput, LppByAge, PersonInput } from "../types.ts";

function row(age: number, capital: number, rente: number, renteReduite?: number): LppByAge {
  return renteReduite == null
    ? { age: age as LppByAge["age"], capital, rente }
    : { age: age as LppByAge["age"], capital, rente, renteReduite };
}

function person(partial: Partial<PersonInput> & Pick<PersonInput, "nom" | "prenom">): PersonInput {
  return {
    civilite: "Monsieur",
    dateNaissance: "1961-01-01",
    avsMensuel: 0,
    lpp: [row(65, 0, 0)],
    troisiemePilier: [],
    ...partial,
  } as PersonInput;
}

function input(partial: Partial<AnalyseInput>): AnalyseInput {
  return {
    afficherResumePrestationsLpp: true,
    client1: person({ nom: "Clement", prenom: "Corentin" }),
    conjoint: null,
    libresPassages: [],
    ...partial,
  } as AnalyseInput;
}

describe("résumé des prestations LPP à 65 ans", () => {
  it("case décochée : aucun bloc", () => {
    const block = buildResumePrestationsLpp(input({ afficherResumePrestationsLpp: false }));
    assert.equal(block, null);
    const absent = buildResumePrestationsLpp(input({ afficherResumePrestationsLpp: undefined }));
    assert.equal(absent, null);
  });

  it("deux personnes, libre passage sans rente, total = somme, note CPEG", () => {
    const block = buildResumePrestationsLpp(input({
      afficherTableauAgesLpp: true,
      client1: person({
        nom: "Clement",
        prenom: "Corentin",
        lppInstitution: "Pensionskasse Musik",
        lppType: "classique",
        lpp: [row(65, 442, 276)],
      }),
      conjoint: person({
        civilite: "Madame",
        nom: "Bouchardy",
        prenom: "Judith",
        lppInstitution: "CPEG",
        lppType: "etatique",
        lpp: [row(65, 58_437, 26_400, 23_196)],
        lppAvoirs: [
          {
            id: "cpev",
            institution: "CPEV",
            type: "etatique",
            rows: [row(65, 246_444, 30_000, 15_000)],
          },
          {
            id: "rp",
            institution: "Retraite Populaire",
            type: "etatique",
            rows: [row(65, 198_782, 9_542)],
          },
        ],
      }),
      libresPassages: [
        {
          id: "lp1",
          titulaire: "client1",
          institution: "Fondation",
          montant: 84_851,
          dateRetraitPossible: "",
          pctRetire: 100,
        },
      ],
    }));
    assert.ok(block);
    assert.equal(block.title, "Résumé des prestations deuxième pilier à 65 ans");
    assert.equal(block.tables.length, 2);
    assert.equal(block.tables[0].subtitle, "CLEMENT Corentin");
    assert.deepEqual(block.tables[0].headers, ["", "Capital", "Rente"]);
    const passage = block.tables[0].rows[1];
    assert.equal(passage.label, "Libre passage");
    assert.equal(passage.cells[1].kind, "bar");
    assert.equal(block.tables[0].totals[0].kind, "amount");
    assert.equal(block.tables[0].totals[1].kind, "amount");
    if (block.tables[0].totals[0].kind === "amount") {
      assert.equal(block.tables[0].totals[0].amount, 85_293);
    }
    if (block.tables[0].totals[1].kind === "amount") {
      assert.equal(block.tables[0].totals[1].amount, 276);
    }
    assert.equal(block.tables[0].notes.length, 0);
    assert.equal(block.tables[0].ages.length, 1);
    assert.equal(block.tables[0].ages[0].age, 65);
    assert.equal(block.tables[0].ages[0].capital, 442);
    assert.equal(block.tables[0].ages[0].rente, 276);
    assert.equal(block.tables[0].ages[0].impot, null);

    const judith = block.tables[1];
    assert.equal(judith.subtitle, "BOUCHARDY Judith");
    assert.deepEqual(judith.headers, ["", "Capital max", "Rente minimum", "Rente maximum"]);
    const retraite = judith.rows[2];
    assert.equal(retraite.cells[1].kind, "bar");
    assert.equal(judith.totals[0].kind, "amount");
    assert.equal(judith.totals[1].kind, "amount");
    assert.equal(judith.totals[2].kind, "amount");
    if (judith.totals[0].kind === "amount") assert.equal(judith.totals[0].amount, 503_663);
    if (judith.totals[1].kind === "amount") assert.equal(judith.totals[1].amount, 38_196);
    if (judith.totals[2].kind === "amount") assert.equal(judith.totals[2].amount, 65_942);
    assert.equal(judith.ages.length, 1);
    assert.equal(judith.ages[0].capital, 503_663);
    assert.equal(judith.ages[0].rente, null);
    assert.equal(judith.ages[0].renteMinimum, 38_196);
    assert.equal(judith.ages[0].renteMaximum, 65_942);
    assert.equal(judith.notes.length, 3);
    assert.match(judith.notes[0].text, /25 %/);
    assert.equal(judith.rows[0].mark, "*");
    assert.equal(judith.rows[1].mark, "**");
    assert.equal(judith.rows[2].mark, "***");

    const html = renderResumePrestationsLppHtml(block);
    assert.match(html, /Résumé des prestations deuxième pilier à 65 ans/);
    const ages = renderResumeAgesHtml(block);
    assert.match(ages, /Capital disponible et rente de 58 à 65 ans/);
    assert.match(ages, /Impôt sur le capital/);
    assert.match(ages, /58 à 65 ans/);
    assert.match(html, /CLEMENT Corentin/);
    assert.match(html, /BOUCHARDY Judith/);
    assert.match(html, /class="val cell-bar"/);
    assert.match(html, /Libre passage/);
    assert.match(html, /25 % de son avoir de vieillesse/);
    assert.ok(html.includes(formatChf(85_293)));
    assert.equal(html.includes("COMPARATIF DES RENTES"), false);
  });

  it("calcule l'impôt sur le capital disponible de 58 à 65 ans", async () => {
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    const taxed: number[] = [];
    taxCalculationService.calculateCapitalTax = async (params) => {
      taxed.push(params.capital);
      return {
        impotTotal: params.capital / 10,
      } as Awaited<ReturnType<typeof original>>;
    };
    try {
      const dossier = input({
        afficherTableauAgesLpp: true,
        taxGroupId: 100,
        taxLocationId: 100,
        taxYear: 2025,
        etatCivil: "Personne vivant seule",
        client1: person({
          nom: "Clement",
          prenom: "Corentin",
          lppInstitution: "Caisse",
          lpp: [row(60, 1_000, 100), row(65, 2_000, 200)],
        }),
      });
      const block = buildResumePrestationsLpp(dossier);
      assert.ok(block);
      assert.deepEqual(
        block.tables[0].ages.map((age) => age.age),
        [60, 65],
      );
      assert.equal(block.tables[0].ages[0].capital, 1_000);
      assert.equal(block.tables[0].ages[0].rente, 100);
      const lines = await fillResumeCapitalTax(dossier, block);
      assert.deepEqual(taxed, [1_000, 2_000]);
      assert.equal(lines[0].impot, 100);
      assert.equal(lines[1].impot, 200);
      assert.equal(block.tables[0].ages[1].impot, 200);
      const html = renderResumeAgesHtml(block);
      assert.match(html, /60 ans/);
      assert.match(html, /65 ans/);
      assert.equal(html.includes("61 ans"), false);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("laisse le résumé à 65 ans et retire la page des âges si la case est décochée", () => {
    const block = buildResumePrestationsLpp(input({
      afficherTableauAgesLpp: false,
      client1: person({
        nom: "Clement",
        prenom: "Corentin",
        lppInstitution: "Caisse",
        lpp: [row(60, 1_000, 100), row(65, 2_000, 200)],
      }),
    }));
    assert.ok(block);
    assert.equal(block.showResume, true);
    assert.equal(block.showAges, false);
    assert.equal(block.tables[0].ages.length, 0);
    assert.equal(renderResumeAgesHtml(block), "");
    const html = renderResumePrestationsLppHtml(block);
    assert.match(html, /Résumé des prestations deuxième pilier à 65 ans/);
    assert.equal(html.includes("Capital disponible et rente de 58 à 65 ans"), false);
  });

  it("met la page des âges dans le PDF quand la case est cochée", () => {
    const block = buildResumePrestationsLpp(input({
      afficherResumePrestationsLpp: false,
      afficherTableauAgesLpp: true,
      client1: person({
        nom: "Clement",
        prenom: "Corentin",
        lppInstitution: "Caisse",
        lpp: [row(60, 1_000, 100), row(65, 2_000, 200)],
      }),
    }));
    assert.ok(block);
    assert.equal(block.showResume, false);
    assert.equal(block.showAges, true);
    assert.deepEqual(block.tables[0].ages.map((age) => age.age), [60, 65]);
    const ages = renderResumeAgesHtml(block);
    assert.match(ages, /Capital disponible et rente de 58 à 65 ans/);
    assert.match(ages, /60 ans/);
    assert.match(ages, /65 ans/);
    const resume = renderResumePrestationsLppHtml(block);
    assert.equal(block.showResume, false);
    assert.match(resume, /CLEMENT Corentin/);
  });

  it("garde les deux tableaux quand les deux cases sont cochées", () => {
    const block = buildResumePrestationsLpp(input({
      afficherResumePrestationsLpp: true,
      afficherTableauAgesLpp: true,
      client1: person({
        nom: "Clement",
        prenom: "Corentin",
        lppInstitution: "Caisse",
        lpp: [row(60, 1_000, 100), row(65, 2_000, 200)],
      }),
    }));
    assert.ok(block);
    assert.equal(block.showResume, true);
    assert.equal(block.showAges, true);
    assert.match(renderResumePrestationsLppHtml(block), /à 65 ans/);
    assert.equal(block.tables[0].ages.length, 2);
    assert.match(renderResumeAgesHtml(block), /Capital disponible/);
    assert.equal(block.tables[0].ages[0].capital, 1_000);
    assert.equal(block.tables[0].ages[1].rente, 200);
  });
});
