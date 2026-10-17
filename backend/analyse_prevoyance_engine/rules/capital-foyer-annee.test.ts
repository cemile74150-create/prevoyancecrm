import assert from "node:assert/strict";
import { describe, it } from "node:test";
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
});
