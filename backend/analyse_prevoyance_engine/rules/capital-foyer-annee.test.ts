import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { planningSectionHtml } from "../pdf/renderPrintableReportHtml.ts";
import { indicativeRachatWarning } from "../report/buildReportPayload.ts";
import { RACHAT_ABSENT_UI } from "./planification-saisie.ts";
import {
  retirementScenarioService,
  withdrawalPlanningService,
} from "../services/RetirementScenarioService.ts";
import { avsCalculationService } from "../services/AVSCalculationService.ts";
import { timelineService } from "../services/TimelineService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type PersonComputed,
  type RetirementAge,
} from "../types.ts";

function personComputed(
  capital: number,
  year: number,
  age: RetirementAge,
): PersonComputed {
  return {
    ageLegal: 65,
    ageLegalLabel: "65 ans",
    dateDepart: `${year}-07-01`,
    dateFinActivite: `${year}-07-01`,
    ageLppRetenu: age,
    avsAnnuel: 0,
    capitalLpp65: capital,
    renteLpp65: 0,
    lppPctDeblocable: 100,
    capitalLppRetire65: capital,
    renteLppResiduelle65: 0,
    renteTotale65: 0,
    total3ePilier: 0,
  };
}

function coupleInput() {
  const input = emptyAnalyseInput();
  input.etatCivil = "Marié(e)";
  input.taxGroupId = 100;
  input.taxYear = 2026;
  input.client1 = emptyPerson("Monsieur");
  input.conjoint = emptyPerson("Madame");
  return input;
}

describe("impôt capital du couple selon l'année de retrait", () => {
  it("envoie la somme des deux capitaux quand le retrait est la même année", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: params.capital >= 500_000 ? 34_001 : 10_000,
        taxChurch: 0,
        impotTotal: params.capital >= 500_000 ? 34_001 : 10_000,
        request: {},
        response: null,
      };
    };
    try {
      const result = await retirementScenarioService.buildCapitalPathFoyer(
        coupleInput(),
        personComputed(400_000, 2030, 65),
        personComputed(182_004, 2030, 63),
        100,
      );
      assert.deepEqual(calls, [582_004]);
      assert.equal(result.capitalRetireTotal, 582_004);
      assert.equal(result.impot, 34_001);
      assert.equal(result.net, 548_003);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("calcule chaque assuré à part puis additionne si les années diffèrent", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: 10_000,
        taxChurch: 0,
        impotTotal: 10_000,
        request: {},
        response: null,
      };
    };
    try {
      const result = await retirementScenarioService.buildCapitalPathFoyer(
        coupleInput(),
        personComputed(400_000, 2030, 65),
        personComputed(182_004, 2032, 65),
        100,
      );
      assert.deepEqual(calls, [400_000, 182_004]);
      assert.equal(result.impot, 20_000);
      assert.equal(result.capitalRetireTotal, 582_004);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("place la LPP de 60 ans en 2029 même si le scénario dit 2034", () => {
    const input = emptyAnalyseInput();
    input.client1 = emptyPerson("Madame");
    input.client1.prenom = "Paula";
    input.client1.dateNaissance = "1969-06-15";
    input.client1.ageRetraitLppSouhaite = 60;
    input.client1.lppPctDeblocable = 100;
    input.client1.lpp = input.client1.lpp.map((row) =>
      row.age === 60 ? { ...row, capital: 100_000, rente: 4_000 } : row,
    );
    input.withdrawalScenarios = [
      {
        id: "a",
        name: "A",
        includeInReport: true,
        items: [
          {
            id: "lpp-client1",
            kind: "lpp",
            titulaire: "client1",
            label: "LPP",
            institution: "LPP",
            montantDisponible: 100_000,
            pctCapital: 100,
            anneeRetraitPrevue: 2034,
            anneePremierePossible: 2034,
            anneeDernierePossible: null,
          },
        ],
      },
    ];
    const computed = personComputed(100_000, 2034, 65);
    computed.dateFinActivite = "2029-07-01";
    const timeline = timelineService.build(input, computed, null);
    const lpp = timeline.events.find((event) => event.kind === "lpp");
    assert.equal(lpp?.year, 2029);
  });

  it("place l'AVS anticipée de 2 ans sur la frise, pas à l'âge légal", () => {
    const input = emptyAnalyseInput();
    input.client1 = emptyPerson("Monsieur");
    input.client1.prenom = "José";
    input.client1.dateNaissance = "1964-03-10";
    input.client1.anticipationAvsAnnees = 2;
    input.client1.avsAnnuel = 30_000;
    const computed = avsCalculationService.computePersonBasics(input.client1);
    const timeline = timelineService.build(input, computed, null);
    const avs = timeline.events.find((event) => event.kind === "avs");
    assert.equal(computed.datePerceptionAvs, "2027-04-01");
    assert.equal(avs?.year, 2027);
    assert.equal(avs?.amount, 25_920);
  });

  it("impose les deux LPP ensemble quand l'onglet LPP dit 60 ans la même année", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: 1,
        taxChurch: 0,
        impotTotal: 1,
        request: {},
        response: null,
      };
    };
    try {
      const input = coupleInput();
      input.client1.prenom = "José";
      input.client1.dateNaissance = "1969-03-10";
      input.client1.ageRetraitLppSouhaite = 60;
      input.client1.lppPctDeblocable = 100;
      input.client1.lpp = input.client1.lpp.map((row) =>
        row.age === 60 ? { ...row, capital: 400_000, rente: 1_000 } : row,
      );
      input.conjoint!.prenom = "Paula";
      input.conjoint!.dateNaissance = "1969-06-15";
      input.conjoint!.ageRetraitLppSouhaite = 60;
      input.conjoint!.lppPctDeblocable = 100;
      input.conjoint!.lpp = input.conjoint!.lpp.map((row) =>
        row.age === 60 ? { ...row, capital: 182_004, rente: 1_000 } : row,
      );
      input.withdrawalScenarios = [
        {
          id: "a",
          name: "A",
          includeInReport: true,
          items: [
            {
              id: "lpp-1",
              kind: "lpp",
              titulaire: "client1",
              label: "LPP José",
              institution: "LPP",
              montantDisponible: 400_000,
              pctCapital: 100,
              anneeRetraitPrevue: 2034,
              anneePremierePossible: 2034,
              anneeDernierePossible: null,
            },
            {
              id: "lpp-2",
              kind: "lpp",
              titulaire: "conjoint",
              label: "LPP Paula",
              institution: "LPP",
              montantDisponible: 182_004,
              pctCapital: 100,
              anneeRetraitPrevue: 2029,
              anneePremierePossible: 2029,
              anneeDernierePossible: null,
            },
          ],
        },
      ];
      const planning = await withdrawalPlanningService.run(
        input,
        personComputed(400_000, 2034, 65),
        personComputed(182_004, 2034, 65),
        100,
      );
      assert.ok(calls.length >= 1);
      assert.ok(calls.every((capital) => capital === 582_004));
      assert.equal(planning?.scenarios[0]?.byYear.length, 1);
      assert.equal(planning?.scenarios[0]?.byYear[0]?.year, 2029);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("impose en un seul appel la somme des capitaux imposables de la stratégie", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      const impotTotal = Math.round((params.capital * params.capital) / 1_000_000);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: impotTotal,
        taxChurch: 0,
        impotTotal,
        request: {},
        response: null,
      };
    };
    try {
      const input = coupleInput();
      input.client1.prenom = "William";
      input.client1.dateNaissance = "1961-12-13";
      input.client1.ageRetraitLppSouhaite = 65;
      input.client1.lppPctDeblocable = 100;
      input.client1.lpp = input.client1.lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 100_000, rente: 1_000 } : row,
      );
      input.client1.troisiemePilier = [
        {
          id: "3a-w",
          type: "3A",
          compagnie: "Helvetia",
          police: "1",
          echeance: "2027-06-01",
          montant: 10_000,
          prime: 0,
        },
        {
          id: "3b-w",
          type: "3B",
          compagnie: "X",
          police: "2",
          echeance: "2027-06-01",
          montant: 5_000,
          prime: 0,
        },
      ];
      input.conjoint!.prenom = "Ariane";
      input.conjoint!.dateNaissance = "1963-01-20";
      input.conjoint!.ageRetraitLppSouhaite = 65;
      input.conjoint!.lppPctDeblocable = 100;
      input.conjoint!.lpp = input.conjoint!.lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 80_000, rente: 1_000 } : row,
      );
      input.conjoint!.troisiemePilier = [
        {
          id: "3a-a",
          type: "3A",
          compagnie: "Axa",
          police: "3",
          echeance: "2027-01-01",
          montant: 20_000,
          prime: 0,
        },
      ];
      const line = (
        id: string,
        kind: "lpp" | "libre_passage" | "3p",
        titulaire: "client1" | "conjoint",
        montant: number,
        year: number,
        sourceId?: string,
      ) => ({
        id,
        kind,
        titulaire,
        label: id,
        institution: kind,
        montantDisponible: montant,
        pctCapital: 100,
        anneeRetraitPrevue: year,
        anneePremierePossible: year,
        anneeDernierePossible: null,
        sourceId,
      });
      input.withdrawalScenarios = [
        {
          id: "strategie",
          name: "Échelonné",
          includeInReport: true,
          items: [
            line("lpp-w", "lpp", "client1", 100_000, 2027),
            line("lpp-a", "lpp", "conjoint", 80_000, 2028),
            line("lp", "libre_passage", "conjoint", 1_000, 2026),
            line("3a-w", "3p", "client1", 10_000, 2027, "3a-w"),
            line("3a-a", "3p", "conjoint", 20_000, 2027, "3a-a"),
            line("3b-w", "3p", "client1", 5_000, 2027, "3b-w"),
          ],
        },
      ];
      const planning = await withdrawalPlanningService.run(
        input,
        personComputed(100_000, 2027, 65),
        personComputed(80_000, 2028, 65),
        100,
      );
      const taxable = 100_000 + 80_000 + 1_000 + 10_000 + 20_000;
      const ref = planning?.sameYearReference;
      assert.ok(ref);
      assert.equal(ref.capitalRetire, taxable + 5_000);
      assert.equal(ref.audits.length, 1);
      assert.equal(ref.audits[0]?.montantSoumis, taxable);
      assert.equal(
        ref.audits[0]?.capitauxInclus.some((capital) => capital.montantRetire === 5_000),
        false,
      );
      assert.equal(calls.filter((capital) => capital === taxable).length, 1);
      assert.equal(ref.impotTotal, Math.round((taxable * taxable) / 1_000_000));
      const slice2027 = Math.round((130_000 * 130_000) / 1_000_000);
      assert.ok((ref.impotTotal ?? 0) > slice2027);
      assert.equal(planning?.economieFiscale, (ref.impotTotal ?? 0) - (planning?.scenarios[0]?.impotTotal ?? 0));
      assert.ok((planning?.economieFiscale ?? 0) > 0);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("lit le capital LPP de l'âge correspondant à l'année choisie", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: 1,
        taxChurch: 0,
        impotTotal: 1,
        request: {},
        response: null,
      };
    };
    try {
      const input = coupleInput();
      input.conjoint = null;
      input.etatCivil = "Personne vivant seule";
      input.client1.prenom = "William";
      input.client1.dateNaissance = "1961-12-13";
      input.client1.ageRetraitLppSouhaite = 65;
      input.client1.lppPctDeblocable = 100;
      input.client1.lpp = input.client1.lpp.map((row) => {
        if (row.age === 65) return { ...row, capital: 350_359, rente: 1_000 };
        if (row.age === 64) return { ...row, capital: 300_000, rente: 1_000 };
        return row;
      });
      input.withdrawalScenarios = [
        {
          id: "sc",
          name: "Scénario",
          includeInReport: true,
          items: [
            {
              id: "lpp-w",
              kind: "lpp",
              titulaire: "client1",
              label: "LPP William",
              institution: "LPP",
              montantDisponible: 350_359,
              pctCapital: 100,
              anneeRetraitPrevue: 2027,
              anneePremierePossible: 2026,
              anneeDernierePossible: null,
            },
          ],
        },
      ];
      const computed = personComputed(350_359, 2027, 65);
      computed.dateFinActivite = "2027-01-01";
      const planning = await withdrawalPlanningService.run(input, computed, null, 100);
      assert.deepEqual(calls, [300_000, 300_000]);
      assert.equal(planning?.scenarios[0]?.byYear[0]?.year, 2026);
      assert.equal(planning?.scenarios[0]?.byYear[0]?.capitalRetire, 300_000);
      const timeline = timelineService.build(input, computed, null);
      const lpp = timeline.events.find((event) => event.kind === "lpp");
      assert.equal(lpp?.year, 2026);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("conserve un retrait partiel s'il ne dépasse pas le capital du nouvel âge", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: 1,
        taxChurch: 0,
        impotTotal: 1,
        request: {},
        response: null,
      };
    };
    try {
      const input = coupleInput();
      input.conjoint = null;
      input.etatCivil = "Personne vivant seule";
      input.client1.dateNaissance = "1961-12-13";
      input.client1.ageRetraitLppSouhaite = 65;
      input.client1.lppPctDeblocable = 100;
      input.client1.lpp = input.client1.lpp.map((row) =>
        row.age === 64 ? { ...row, capital: 400_000, rente: 1_000 } : row,
      );
      const kept = 148_678;
      input.withdrawalScenarios = [
        {
          id: "sc",
          name: "Partiel",
          includeInReport: true,
          items: [
            {
              id: "lpp-a",
              kind: "lpp",
              titulaire: "client1",
              label: "LPP Ariane",
              institution: "LPP",
              montantDisponible: 400_000,
              pctCapital: (kept / 400_000) * 100,
              anneeRetraitPrevue: 2027,
              anneePremierePossible: 2026,
              anneeDernierePossible: null,
            },
          ],
        },
      ];
      const planning = await withdrawalPlanningService.run(
        input,
        personComputed(400_000, 2027, 65),
        null,
        100,
      );
      assert.equal(planning?.scenarios[0]?.byYear[0]?.capitalRetire, kept);
      assert.ok(calls.every((capital) => capital === kept));
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("n'invente pas un capital LPP si l'année choisie n'est pas dans le tableau", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: 1,
        taxChurch: 0,
        impotTotal: 1,
        request: {},
        response: null,
      };
    };
    try {
      const input = coupleInput();
      input.conjoint = null;
      input.etatCivil = "Personne vivant seule";
      input.client1.dateNaissance = "1961-12-13";
      input.client1.ageRetraitLppSouhaite = 65;
      input.client1.lppPctDeblocable = 100;
      input.client1.lpp = input.client1.lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 350_359, rente: 1_000 } : row,
      );
      input.withdrawalScenarios = [
        {
          id: "sc",
          name: "Année vide",
          includeInReport: true,
          items: [
            {
              id: "lpp-w",
              kind: "lpp",
              titulaire: "client1",
              label: "LPP William",
              institution: "LPP",
              montantDisponible: 350_359,
              pctCapital: 100,
              anneeRetraitPrevue: 2027,
              anneePremierePossible: 2025,
              anneeDernierePossible: null,
            },
          ],
        },
      ];
      const planning = await withdrawalPlanningService.run(
        input,
        personComputed(350_359, 2027, 65),
        null,
        100,
      );
      assert.deepEqual(calls, []);
      assert.equal(planning?.scenarios[0]?.capitalRetireTotal, 0);
      assert.equal(planning?.sameYearReference, null);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("affiche les 3e piliers sur l'année de 1re possible, pas dans la LPP d'une autre année", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      const impot = Math.round(params.capital / 100);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: impot,
        taxChurch: 0,
        impotTotal: impot,
        request: {},
        response: null,
      };
    };
    try {
      const input = coupleInput();
      input.client1.prenom = "William";
      input.client1.dateNaissance = "1962-03-10";
      input.client1.ageRetraitLppSouhaite = 65;
      input.client1.lppPctDeblocable = 100;
      input.client1.lpp = input.client1.lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 350_359, rente: 1_000 } : row,
      );
      input.client1.troisiemePilier = [
        {
          id: "w3a",
          compagnie: "Helvetia",
          police: "1",
          echeance: "2027-01-01",
          montant: 63_046,
          prime: 0,
          type: "3A",
        },
      ];
      input.conjoint!.prenom = "Ariane";
      input.conjoint!.dateNaissance = "1963-05-12";
      input.conjoint!.ageRetraitLppSouhaite = 65;
      input.conjoint!.lppPctDeblocable = 50;
      input.conjoint!.lpp = input.conjoint!.lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 297_356, rente: 1_000 } : row,
      );
      input.conjoint!.troisiemePilier = [
        {
          id: "a3a",
          compagnie: "Axa",
          police: "2",
          echeance: "2027-01-01",
          montant: 69_454,
          prime: 0,
          type: "3A",
        },
        {
          id: "a3b",
          compagnie: "Axa",
          police: "3",
          echeance: "2027-01-01",
          montant: 2_000,
          prime: 0,
          type: "3B",
        },
      ];
      input.libresPassages = [
        {
          id: "lp",
          titulaire: "conjoint",
          institution: "Libre passage",
          montant: 1_017,
          pctRetire: 100,
          ageDeblocage: null,
          dateRetraitPossible: "2026-01-01",
        },
      ];
      const pillar = (
        id: string,
        titulaire: "client1" | "conjoint",
        sourceId: string,
        montant: number,
      ) => ({
        id,
        kind: "3p" as const,
        titulaire,
        label: id,
        institution: "3e pilier",
        montantDisponible: montant,
        pctCapital: 100,
        anneeRetraitPrevue: 2027,
        anneePremierePossible: 2026,
        anneeDernierePossible: null,
        sourceId,
      });
      input.withdrawalScenarios = [
        {
          id: "sc",
          name: "A — Regroupé",
          includeInReport: true,
          items: [
            {
              id: "lpp-w",
              kind: "lpp",
              titulaire: "client1",
              label: "LPP William",
              institution: "LPP",
              montantDisponible: 350_359,
              pctCapital: 100,
              anneeRetraitPrevue: 2027,
              anneePremierePossible: 2027,
              anneeDernierePossible: null,
            },
            {
              id: "lpp-a",
              kind: "lpp",
              titulaire: "conjoint",
              label: "LPP Ariane",
              institution: "LPP",
              montantDisponible: 297_356,
              pctCapital: 50,
              anneeRetraitPrevue: 2028,
              anneePremierePossible: 2028,
              anneeDernierePossible: null,
            },
            {
              id: "lp",
              kind: "libre_passage",
              titulaire: "conjoint",
              label: "Libre passage",
              institution: "Libre passage",
              montantDisponible: 1_017,
              pctCapital: 100,
              anneeRetraitPrevue: 2026,
              anneePremierePossible: 2026,
              anneeDernierePossible: null,
              sourceId: "lp",
            },
            pillar("w3", "client1", "w3a", 63_046),
            pillar("a3", "conjoint", "a3a", 69_454),
            pillar("b3", "conjoint", "a3b", 2_000),
          ],
        },
      ];
      const planning = await withdrawalPlanningService.run(
        input,
        personComputed(350_359, 2027, 65),
        personComputed(148_678, 2028, 65),
        100,
      );
      const scenario = planning?.scenarios[0];
      const byYear = scenario?.byYear ?? [];
      assert.deepEqual(
        byYear.map((year) => year.year),
        [2026, 2027, 2028],
      );
      const names = (year: number) =>
        (byYear.find((row) => row.year === year)?.lines ?? []).map(
          (line) => `${line.kind}:${line.titulaire}:${line.contratType ?? ""}:${line.exonere ? "exo" : "tax"}`,
        );
      assert.deepEqual(names(2026), [
        "libre_passage:conjoint::tax",
        "3p:client1:3A:tax",
        "3p:conjoint:3A:tax",
        "3p:conjoint:3B:exo",
      ]);
      assert.deepEqual(names(2027), ["lpp:client1::tax"]);
      assert.deepEqual(names(2028), ["lpp:conjoint::tax"]);
      assert.equal(byYear[0]?.capitalRetire, 63_046 + 69_454 + 1_017 + 2_000);
      assert.equal(byYear[1]?.capitalRetire, 350_359);
      assert.equal(byYear[2]?.capitalRetire, 148_678);
      const taxable2026 = 63_046 + 69_454 + 1_017;
      const taxableAll = taxable2026 + 350_359 + 148_678;
      assert.deepEqual(calls, [taxable2026, 350_359, 148_678, taxableAll]);
      assert.equal(planning?.sameYearReference?.capitalRetire, taxableAll + 2_000);
      assert.equal(planning?.sameYearReference?.impotTotal, Math.round(taxableAll / 100));
      assert.equal(
        planning?.economieFiscale,
        Math.round(taxableAll / 100) -
          (Math.round(taxable2026 / 100) + Math.round(350_359 / 100) + Math.round(148_678 / 100)),
      );
      const rachatPhrase = indicativeRachatWarning(input, "sc");
      assert.equal(
        rachatPhrase,
        "Aucune valeur de rachat n'a été renseignée pour William 3A Helvetia, Ariane 3A Axa et Ariane 3B Axa à la date de retrait sélectionnée : le capital à l'échéance est utilisé à titre indicatif et peut différer du montant réellement disponible.",
      );
      assert.equal(rachatPhrase?.includes(RACHAT_ABSENT_UI), false);
      const html = planningSectionHtml(
        {
          include: true,
          scenarios: [
            {
              id: "sc",
              name: "A",
              includeInReport: true,
              capitalRetireTotal: scenario?.capitalRetireTotal ?? 0,
              impotTotal: scenario?.impotTotal ?? null,
              capitalNet: scenario?.capitalNet ?? null,
              byYear: (scenario?.byYear ?? []).map((year) => ({
                year: year.year,
                capitalRetire: year.capitalRetire,
                impot: year.impot,
                net: year.net,
                lines: year.lines,
              })),
              audits: [],
            },
          ],
          comparisons: [],
          strategyScenarioId: "sc",
          sameYearReference: planning?.sameYearReference
            ? {
                year: planning.sameYearReference.year,
                capitalRetire: planning.sameYearReference.capitalRetire,
                impotTotal: planning.sameYearReference.impotTotal,
                capitalNet: planning.sameYearReference.capitalNet,
              }
            : null,
          economieFiscale: planning?.economieFiscale ?? null,
          avertissementRachat: rachatPhrase,
        },
        { client1: "William", conjoint: "Ariane" },
      );
      assert.ok(html.includes("William 3A imposable"));
      assert.ok(html.includes("Ariane 3A imposable"));
      assert.ok(html.includes("Ariane 3B exonéré"));
      assert.ok(html.includes("Libre passage Ariane"));
      assert.equal(html.includes("LPP William + "), false);
      assert.ok(html.includes(">2026<"));
      assert.ok(html.includes("LPP William"));
      assert.ok(html.includes("LPP Ariane"));
      assert.ok(html.includes(rachatPhrase || "phrase absente"));
      assert.equal(html.includes('class="note warn"'), false);
      assert.equal(html.includes(RACHAT_ABSENT_UI), false);
      assert.equal(html.includes("valeur de rachat confirmée"), false);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });

  it("garde une 1re possible LPP déjà égale à l'année prévue si le tableau a ce capital", async () => {
    const calls: number[] = [];
    const original = taxCalculationService.calculateCapitalTax.bind(
      taxCalculationService,
    );
    taxCalculationService.calculateCapitalTax = async (params) => {
      calls.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2026,
        taxCity: 0,
        taxCanton: 0,
        taxFed: 1,
        taxChurch: 0,
        impotTotal: 1,
        request: {},
        response: null,
      };
    };
    try {
      const input = coupleInput();
      input.conjoint = null;
      input.etatCivil = "Personne vivant seule";
      input.client1.prenom = "William";
      input.client1.dateNaissance = "1962-03-10";
      input.client1.ageRetraitLppSouhaite = 65;
      input.client1.lppPctDeblocable = 100;
      input.client1.lpp = input.client1.lpp.map((row) => {
        if (row.age === 65) return { ...row, capital: 350_359, rente: 1_000 };
        if (row.age === 64) return { ...row, capital: 300_000, rente: 1_000 };
        return row;
      });
      input.withdrawalScenarios = [
        {
          id: "sc",
          name: "LPP",
          includeInReport: true,
          items: [
            {
              id: "lpp-w",
              kind: "lpp",
              titulaire: "client1",
              label: "LPP William",
              institution: "LPP",
              montantDisponible: 300_000,
              pctCapital: 100,
              anneeRetraitPrevue: 2026,
              anneePremierePossible: 2026,
              anneeDernierePossible: null,
            },
          ],
        },
      ];
      const planning = await withdrawalPlanningService.run(
        input,
        personComputed(350_359, 2027, 65),
        null,
        100,
      );
      assert.equal(planning?.scenarios[0]?.byYear[0]?.year, 2026);
      assert.equal(planning?.scenarios[0]?.byYear[0]?.capitalRetire, 300_000);
      assert.deepEqual(calls, [300_000, 300_000]);
    } finally {
      taxCalculationService.calculateCapitalTax = original;
    }
  });
});
