import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, describe, it } from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ageRetraitePersonne } from "./age-retraite.ts";
import { avsCalculationService } from "../services/AVSCalculationService.ts";
import { renteHypothesisService } from "../services/RenteHypothesisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import { timelineService } from "../services/TimelineService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  librePassageRetire,
  type LppByAge,
  type RenteHypothesisInput,
} from "../types.ts";
import {
  buildCalendarPreview,
  scenarioWithdrawalYear,
} from "../withdrawalPlanUtils.ts";

const here = dirname(fileURLToPath(import.meta.url));

function lpp(rente63: number, rente65: number): LppByAge[] {
  return [65, 64, 63, 62, 61, 60].map((age) => ({
    age: age as LppByAge["age"],
    capital: 0,
    rente: age === 63 ? rente63 : age === 65 ? rente65 : 0,
  }));
}

const offre: RenteHypothesisInput = {
  id: "offre",
  type: "viagere",
  compagnie: "Test",
  capitalPlace: 100_000,
  dureeAnnees: null,
  renteGarantieAnnuelle: 5_000,
  participationExcedentsAnnuelle: 0,
};

describe("formulaire — AVS, âges, libre passage, année de retrait", () => {
  const original = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );
  taxCalculationService.calculateDetailedTaxes = async (params) => ({
    foyer: params.foyer ?? "default",
    age: params.age1,
    taxLocationId: params.taxLocationId,
    taxYear: params.taxYear ?? 2025,
    revenu1: params.revenue1,
    revenu2: params.revenue2,
    fortune: params.fortune,
    impotRevenuTotal: 100,
    impotFederal: 100,
    impotCanton: 0,
    impotCommune: 0,
    impotEglise: 0,
    request: { age1: params.age1, age2: params.age2 },
    response: {},
  });

  it("AVS annuelle = mensuelle × 12 si l'annuel n'est pas déjà enregistré", () => {
    const person = emptyPerson("Monsieur");
    person.avsMensuel = 1_890;
    person.avsAnnuel = null;
    assert.equal(avsCalculationService.resolveAnnual(person), 1_890 * 12);
  });

  it("un annuel déjà enregistré reste prioritaire", () => {
    const person = emptyPerson("Monsieur");
    person.avsMensuel = 1_890;
    person.avsAnnuel = 24_570;
    assert.equal(avsCalculationService.resolveAnnual(person), 24_570);
  });

  it("personne seule : l'âge souhaité choisit la rente LPP et l'AVS × 12", async () => {
    const input = emptyAnalyseInput();
    input.taxLocationId = 1;
    input.etatCivil = "Personne vivant seule";
    input.client1.dateNaissance = "1962-03-15";
    input.client1.avsMensuel = 200;
    input.client1.avsAnnuel = null;
    input.client1.ageRetraiteSouhaite = 63;
    input.client1.lpp = lpp(10_000, 20_000);
    input.comparerAvecRenteLpp = true;
    const built = await renteHypothesisService.build(input);
    const lppCol = built?.columns.find((col) => col.kind === "lpp");
    assert.equal(built?.ageRetraite, 63);
    assert.equal(lppCol?.renteAvs, 2_400);
    assert.equal(lppCol?.renteGarantie, 10_000);
  });

  it("couple : les deux âges souhaités sont distincts", async () => {
    const input = emptyAnalyseInput();
    input.taxLocationId = 1;
    input.etatCivil = "Marié(e)";
    input.ageRetraiteSouhaite = null;
    input.client1.avsMensuel = 1_000;
    input.client1.avsAnnuel = null;
    input.client1.ageRetraiteSouhaite = 63;
    input.client1.lpp = lpp(10_000, 20_000);
    input.conjoint = emptyPerson("Madame");
    input.conjoint.dateNaissance = "1964-04-02";
    input.conjoint.avsMensuel = 500;
    input.conjoint.avsAnnuel = null;
    input.conjoint.ageRetraiteSouhaite = 65;
    input.conjoint.lpp = lpp(3_000, 8_000);
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [offre];
    assert.equal(ageRetraitePersonne(input.client1, input.ageRetraiteSouhaite), 63);
    assert.equal(ageRetraitePersonne(input.conjoint, input.ageRetraiteSouhaite), 65);
    const built = await renteHypothesisService.build(input);
    const lppCol = built?.columns.find((col) => col.kind === "lpp");
    assert.equal(lppCol?.renteAvs, 12_000 + 6_000);
    assert.equal(lppCol?.renteGarantie, 10_000 + 8_000);
  });

  it("analyse déjà enregistrée : l'âge du dossier reste utilisé si l'assuré n'a pas le sien", () => {
    const person = emptyPerson("Monsieur");
    assert.equal(ageRetraitePersonne(person, 64), 64);
  });

  it("libre passage : le calcul utilise 100 % même si un ancien pourcentage diffère", () => {
    const lp = {
      id: "lp",
      titulaire: "client1" as const,
      institution: "Fondation",
      montant: 1_017,
      dateRetraitPossible: "",
      pctRetire: 40,
    };
    assert.equal(librePassageRetire(lp), 1_017);
  });

  it("1re possible est l'année du scénario ; l'année prévue reste l'échéance", () => {
    const item = {
      id: "c",
      kind: "3p" as const,
      titulaire: "client1" as const,
      label: "3A",
      institution: "Axa",
      montantDisponible: 10_000,
      pctCapital: 100,
      anneeRetraitPrevue: 2030,
      anneePremierePossible: 2034,
      anneeDernierePossible: null,
    };
    assert.equal(scenarioWithdrawalYear(item), 2034);
    assert.equal(buildCalendarPreview([item])[0].year, 2034);
    assert.equal(item.anneeRetraitPrevue, 2030);
  });

  it("scénario déjà enregistré sans 1re possible : on relit l'année prévue", () => {
    const item = {
      id: "old",
      kind: "lpp" as const,
      titulaire: "client1" as const,
      label: "LPP",
      institution: "LPP",
      montantDisponible: 5_000,
      pctCapital: 100,
      anneeRetraitPrevue: 2031,
      anneePremierePossible: null,
      anneeDernierePossible: null,
    };
    assert.equal(scenarioWithdrawalYear(item), 2031);
    assert.equal(buildCalendarPreview([item])[0].year, 2031);
  });

  it("la frise PDF suit 1re possible, pas l'échéance du contrat", () => {
    const input = emptyAnalyseInput();
    input.client1.dateNaissance = "1962-01-01";
    input.client1.prenom = "Jean";
    input.client1.troisiemePilier = [
      {
        id: "p1",
        compagnie: "Axa",
        police: "1",
        echeance: "2030-06-01",
        montant: 10_000,
        prime: 0,
        type: "3A",
      },
    ];
    input.withdrawalScenarios = [
      {
        id: "sc",
        name: "Perso",
        includeInReport: true,
        items: [
          {
            id: "i1",
            kind: "3p",
            titulaire: "client1",
            label: "3A",
            institution: "Axa",
            montantDisponible: 10_000,
            pctCapital: 100,
            anneeRetraitPrevue: 2030,
            anneePremierePossible: 2036,
            anneeDernierePossible: null,
            sourceId: "p1",
          },
        ],
      },
    ];
    const basics = avsCalculationService.computePersonBasics(input.client1);
    const timeline = timelineService.build(input, basics, null);
    const pillar = timeline.events.find((event) => event.kind === "3p");
    assert.equal(pillar?.year, 2036);
  });

  after(() => {
    taxCalculationService.calculateDetailedTaxes = original;
  });
});

describe("libellés du formulaire conseiller", () => {
  const root = resolve(here, "../../../frontend/src");
  const files = [
    "analyse-prevoyance/components/AnalysePrevoyanceApp.tsx",
    "analyse-prevoyance/components/AvsFields.tsx",
    "analyse-prevoyance/components/LppFields.tsx",
    "analyse-prevoyance/components/LibrePassageFields.tsx",
    "analyse-prevoyance/components/WithdrawalPlanningFields.tsx",
    "analyse-prevoyance/components/PersonIdentityFields.tsx",
    "analyse-prevoyance/components/CommuneSearch.tsx",
    "analyse-prevoyance/components/ThirdPillarFields.tsx",
    "analyse-prevoyance/components/RenteHypothesisFields.tsx",
    "analyse-prevoyance/components/ResultsPanel.tsx",
    "analyse-prevoyance/components/ConfirmDeleteButton.tsx",
    "pages/EffectuerAnalyseEditor.js",
  ];

  it("n'affiche pas ESTV, ni le statut, ni Restaurer", () => {
    const source = files.map((file) => readFileSync(resolve(root, file), "utf8")).join("\n");
    assert.equal(source.includes("ESTV"), false);
    assert.equal(source.includes("Fiche client"), false);
    assert.equal(source.includes("Restaurer"), false);
    assert.equal(source.includes("Année fiscale ESTV"), false);
    assert.equal(source.includes("% LPP déblocable"), false);
    assert.equal(source.includes("Capital effectivement retiré"), false);
    assert.equal(source.includes("Âge de fin d'activité"), false);
    assert.match(source, /% LPP disponible/);
    assert.match(source, /Âge de retraite souhaité \(début des rentes de retraite\)/);
    assert.match(source, /Êtes-vous sûr de vouloir supprimer cet élément \? Cette action ne pourra pas être annulée\./);
    assert.match(source, /← Analyses/);
    assert.match(source, /LeoSoft · Effectuer une analyse/);
  });
});
