import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { helferAnalyseInput } from "../fixtures/helfer.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import {
  AVS_SIMULATION_DISCLAIMER,
  renderPrintableReportHtml,
} from "../pdf/renderPrintableReportHtml.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import {
  lppTimelineFate,
  timelineService,
} from "../services/TimelineService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseInput,
  type AnalyseRecord,
  type PersonComputed,
  type RenteHypothesisInput,
} from "../types.ts";

function computed(partial: Partial<PersonComputed> = {}): PersonComputed {
  return {
    ageLegal: 65,
    ageLegalLabel: "65 ans",
    dateDepart: "2030-06-01",
    avsAnnuel: 20_000,
    capitalLpp65: 100_000,
    renteLpp65: 6_000,
    lppPctDeblocable: 100,
    capitalLppRetire65: 100_000,
    renteLppResiduelle65: 0,
    renteTotale65: 26_000,
    total3ePilier: 0,
    ...partial,
  };
}

describe("libellés PDF — prénoms et destin LPP", () => {
  it("déduit Capital, Rente ou Capital + rente du % déblocable", () => {
    assert.equal(lppTimelineFate(undefined), "Capital");
    assert.equal(lppTimelineFate(null), "Capital");
    assert.equal(lppTimelineFate(100), "Capital");
    assert.equal(lppTimelineFate(0), "Rente");
    assert.equal(lppTimelineFate(50), "Capital + rente");
    assert.equal(lppTimelineFate(25), "Capital + rente");
  });

  it("nomme la frise avec le prénom et le destin LPP", () => {
    const input = emptyAnalyseInput();
    input.etatCivil = "Marié(e)";
    input.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "Wiliam",
      lppPctDeblocable: 100,
    };
    input.conjoint = {
      ...emptyPerson("Madame"),
      prenom: "Ariane",
      lppPctDeblocable: 50,
    };
    const timeline = timelineService.build(
      input,
      computed({ lppPctDeblocable: 100, capitalLppRetire65: 350_359 }),
      computed({
        dateDepart: "2031-02-01",
        lppPctDeblocable: 50,
        capitalLpp65: 148_678,
        capitalLppRetire65: 74_339,
        renteLpp65: 16_057,
        renteLppResiduelle65: 8_028.5,
      }),
    );
    const labels = timeline.events.map((event) => event.label);
    assert.ok(labels.includes("AVS – Wiliam"));
    assert.ok(labels.includes("AVS – Ariane"));
    assert.ok(labels.includes("LPP – Wiliam – Capital"));
    assert.ok(labels.includes("LPP – Ariane – Capital + rente"));
    const ariane = timeline.events.find(
      (event) => event.label === "LPP – Ariane – Capital + rente",
    );
    assert.equal(ariane?.amount, 74_339);
  });

  it("affiche une rente pure et retombe sur Assuré N si le prénom manque", () => {
    const input = emptyAnalyseInput();
    input.client1 = { ...emptyPerson("Monsieur"), prenom: "  " };
    const timeline = timelineService.build(
      input,
      computed({
        lppPctDeblocable: 0,
        capitalLppRetire65: 0,
        renteLpp65: 6_000,
        renteLppResiduelle65: 6_000,
      }),
      null,
    );
    const lpp = timeline.events.find((event) => event.kind === "lpp");
    assert.equal(lpp?.label, "LPP – Assuré 1 – Rente");
    assert.equal(lpp?.amount, 6_000);
    assert.equal(
      timeline.events.find((event) => event.kind === "avs")?.label,
      "AVS – Assuré 1",
    );
  });
});

const offreA: RenteHypothesisInput = {
  id: "vaudoise",
  type: "certaine",
  compagnie: "Vaudoise",
  capitalPlace: 530_000,
  dureeAnnees: 20,
  renteGarantieAnnuelle: 23_136,
  participationExcedentsAnnuelle: 7_096,
};

const offreB: RenteHypothesisInput = {
  id: "helvetia",
  type: "viagere",
  compagnie: "Helvetia",
  capitalPlace: 200_000,
  dureeAnnees: null,
  renteGarantieAnnuelle: 10_000,
  participationExcedentsAnnuelle: 1_000,
};

const offreC: RenteHypothesisInput = {
  id: "swisslife",
  type: "viagere",
  compagnie: "Swiss Life",
  capitalPlace: 150_000,
  dureeAnnees: null,
  renteGarantieAnnuelle: 7_500,
  participationExcedentsAnnuelle: 800,
};

function comparaisonSection(html: string): string {
  const start = html.indexOf("Comparaison des rentes à");
  assert.ok(start >= 0, "page comparaison des rentes absente");
  const tableStart = html.indexOf('<table class="data compare">', start);
  assert.ok(tableStart >= 0, "tableau compare absent");
  const tableEnd = html.indexOf("</table>", tableStart);
  return html.slice(start, tableEnd + "</table>".length);
}

function compareBodyLabels(section: string): string[] {
  return [...section.matchAll(/<td class="lab">([^<]*)<\/td>/g)].map((m) => m[1]);
}

async function htmlOf(input: AnalyseInput): Promise<string> {
  const results = await retirementAnalysisService.run(input);
  const record: AnalyseRecord = {
    id: "compare-visual",
    createdAt: "2026-10-07T00:00:00.000Z",
    updatedAt: "2026-10-07T00:00:00.000Z",
    clientId: null,
    status: "calculee",
    input,
    results,
  };
  return renderPrintableReportHtml(buildReportPayload(record));
}

describe("HTML Helfer — présentation sans calcul fiscal réel", { concurrency: false }, () => {
  const originalCapital = taxCalculationService.calculateCapitalTax.bind(
    taxCalculationService,
  );
  const originalIncome = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );

  taxCalculationService.calculateCapitalTax = async (params) => ({
    age: params.ageAtPayment,
    capital: params.capital,
    gender: params.gender,
    relationship: params.relationship,
    taxGroupId: params.taxGroupId,
    taxYear: params.taxYear ?? 2025,
    taxCity: 0,
    taxCanton: 0,
    taxFed: 1,
    taxChurch: 0,
    impotTotal: 1,
    request: {},
    response: {},
  });
  taxCalculationService.calculateDetailedTaxes = async (params) => ({
    foyer: params.foyer ?? "default",
    age: params.age1,
    taxLocationId: params.taxLocationId,
    taxYear: params.taxYear ?? 2025,
    revenu1: params.revenue1,
    revenu2: params.revenue2,
    fortune: params.fortune,
    impotRevenuTotal: 1_000,
    impotFederal: 1_000,
    impotCanton: 0,
    impotCommune: 0,
    impotEglise: 0,
    request: {},
    response: {},
  });

  after(() => {
    taxCalculationService.calculateCapitalTax = originalCapital;
    taxCalculationService.calculateDetailedTaxes = originalIncome;
  });

  it("remplace Assuré 1/2 et sépare les colonnes d'offres", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [offreA, offreB];
    const results = await retirementAnalysisService.run(input);
    const record: AnalyseRecord = {
      id: "helfer-labels",
      createdAt: "2026-10-07T00:00:00.000Z",
      updatedAt: "2026-10-07T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const html = renderPrintableReportHtml(buildReportPayload(record));
    const lppLabels = (results.timeline?.events || [])
      .filter((event) => event.kind === "lpp")
      .map((event) => event.label);

    assert.deepEqual(lppLabels, [
      "LPP – Wiliam – Capital",
      "LPP – Ariane – Capital + rente",
    ]);
    assert.equal(
      results.timeline?.events.find((event) => event.person === "client1" && event.kind === "lpp")
        ?.amount,
      results.client1.capitalLppRetire65,
    );
    assert.equal(
      results.timeline?.events.find((event) => event.person === "conjoint" && event.kind === "lpp")
        ?.amount,
      results.conjoint?.capitalLppRetire65,
    );
    assert.ok(html.includes("LPP – Wiliam – Capital"));
    assert.ok(html.includes("LPP – Ariane – Capital + rente"));
    assert.ok(html.includes("Rente LPP – Wiliam"));
    assert.ok(html.includes("Rente LPP – Ariane"));
    assert.ok(html.includes("Capital LPP – Wiliam"));
    assert.ok(html.includes("Capital LPP – Ariane"));
    assert.equal(html.includes('<td class="lab">Capital LPP</td>'), false);
    const payload = buildReportPayload(record);
    const capitalSplit =
      payload.client1.capitalCheminCapital +
      (payload.conjoint?.capitalCheminCapital ?? 0);
    assert.equal(Math.round(capitalSplit * 100) / 100, payload.aggregates.capitalLppRetireTotal);
    assert.equal(payload.aggregates.impotCapital65, results.capitalPathFoyer?.impot ?? null);
    assert.equal(payload.aggregates.capitalNet65, results.capitalPathFoyer?.net ?? null);
    assert.ok(html.includes("Comparaison des rentes à 65 ans"));
    assert.ok(html.includes('class="num col-lpp"'));
    assert.ok(html.includes('class="num col-offer col-after-lpp"'));
    assert.ok(html.includes("col-offer"));
    assert.match(html, /table\.data\.compare td\.col-after-lpp/);
    assert.equal(html.includes("Assuré 1"), false);
    assert.equal(html.includes("Assuré 2"), false);
    assert.equal(html.includes("assuré 1"), false);
    assert.equal(html.includes("assuré 2"), false);

    const compare = comparaisonSection(html);
    assert.equal(compare.includes('<td class="lab">Capital placé</td>'), false);
    assert.equal(compare.includes('<td class="lab">Compagnie</td>'), false);
    assert.equal(compare.includes('<td class="lab">Type de rente</td>'), false);
    assert.equal(compare.includes('<td class="lab">Durée de la rente</td>'), false);
    assert.ok(compare.includes("Rente LPP (référence)"));
    assert.ok(compare.includes("Vaudoise"));
    assert.ok(compare.includes("Helvetia"));
    assert.ok(compare.includes("Rente certaine"));
    assert.ok(compare.includes("20 ans"));
    assert.ok(compare.includes("Rente viagère"));
    assert.deepEqual(compareBodyLabels(compare), [
      "Rente AVS",
      "Rente LPP résiduelle",
      "Rente garantie",
      "Participation aux excédents",
      "Revenu total encaissé",
      "Revenu fiscal imposable",
      "Impôts ICC &amp; IFD",
      "Revenu net annuel",
      "Écart net annuel vs LPP",
    ]);
    assert.ok(compare.includes("row-net"));
    assert.ok(compare.includes("row-ecart"));
    assert.equal(compare.includes("calculateur officiel AVS"), false);
  });

  it("met la compagnie, le capital et le type dans l'en-tête — 1 offre certaine", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = false;
    input.renteHypotheses = [offreA];
    const html = await htmlOf(input);
    const compare = comparaisonSection(html);
    assert.ok(compare.includes("Vaudoise"));
    assert.ok(compare.includes("Rente certaine"));
    assert.ok(compare.includes("20 ans"));
    assert.equal(compare.includes("Rente LPP (référence)"), false);
    assert.equal(compare.includes("Helvetia"), false);
    assert.equal(compare.includes('<td class="lab">Capital placé</td>'), false);
    assert.equal(compare.includes("Écart net annuel vs LPP"), false);
    assert.ok(html.includes("Revenu annuel obtenu sur le capital placé"));
  });

  it("aligne N offres mixtes certaine et viagère", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [offreA, offreB, offreC];
    const html = await htmlOf(input);
    const compare = comparaisonSection(html);
    assert.ok(compare.includes("Vaudoise"));
    assert.ok(compare.includes("Helvetia"));
    assert.ok(compare.includes("Swiss Life"));
    assert.ok(compare.includes("Rente certaine"));
    assert.ok(compare.includes("Rente viagère"));
    assert.equal((compare.match(/col-offer/g) || []).length >= 2, true);
  });

  it("ajoute la mention AVS simulation seulement si une case est cochée", async () => {
    const off = helferAnalyseInput();
    off.ageRetraiteSouhaite = 65;
    off.comparerAvecRenteLpp = true;
    off.renteHypotheses = [offreA];
    const htmlOff = await htmlOf(off);
    assert.equal(htmlOff.includes("calculateur officiel AVS"), false);

    const on = helferAnalyseInput();
    on.ageRetraiteSouhaite = 65;
    on.comparerAvecRenteLpp = true;
    on.renteHypotheses = [offreA];
    on.client1 = { ...on.client1, avsMontantIssuSimulation: true };
    const htmlOn = await htmlOf(on);
    assert.ok(htmlOn.includes(AVS_SIMULATION_DISCLAIMER));
    assert.ok(htmlOn.includes("calculateur officiel AVS"));
    assert.ok(htmlOn.includes("avs-sim-note"));

    const conjointOnly = helferAnalyseInput();
    conjointOnly.ageRetraiteSouhaite = 65;
    conjointOnly.comparerAvecRenteLpp = true;
    conjointOnly.renteHypotheses = [offreA];
    conjointOnly.conjoint = {
      ...conjointOnly.conjoint!,
      avsMontantIssuSimulation: true,
    };
    const htmlConjoint = await htmlOf(conjointOnly);
    assert.ok(htmlConjoint.includes("calculateur officiel AVS"));
  });

  it("relit le booléen AVS simulation sans migration", () => {
    assert.equal(emptyPerson().avsMontantIssuSimulation, false);
    const legacy = JSON.parse(JSON.stringify({ client1: { prenom: "Jean" } }));
    assert.equal(Boolean(legacy.client1.avsMontantIssuSimulation), false);
    const saved = JSON.parse(
      JSON.stringify({
        ...emptyPerson("Monsieur"),
        avsMontantIssuSimulation: true,
      }),
    );
    assert.equal(saved.avsMontantIssuSimulation, true);
    const reopened = JSON.parse(JSON.stringify(saved));
    assert.equal(reopened.avsMontantIssuSimulation, true);
  });

  it("n'affiche qu'une ligne Capital LPP s'il n'y a qu'un assuré", async () => {
    const input = emptyAnalyseInput();
    input.etatCivil = "Personne vivant seule";
    input.taxLocationId = 170_000_000;
    input.taxGroupId = 170_000_000;
    input.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "Marc",
      nom: "Seul",
      lppPctDeblocable: 100,
      lpp: emptyPerson("Monsieur").lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 80_000, rente: 4_800 } : row,
      ),
    };
    input.conjoint = null;
    const results = await retirementAnalysisService.run(input);
    const record: AnalyseRecord = {
      id: "solo-capital",
      createdAt: "2026-10-07T00:00:00.000Z",
      updatedAt: "2026-10-07T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const payload = buildReportPayload(record);
    const html = renderPrintableReportHtml(payload);
    assert.ok(html.includes("Capital LPP – Marc"));
    assert.equal(html.includes("Capital LPP – Assuré 2"), false);
    assert.equal((html.match(/Capital LPP – /g) || []).length, 1);
    assert.equal(payload.conjoint, null);
    assert.equal(payload.client1.capitalCheminCapital, payload.aggregates.capitalLppRetireTotal);
  });
});
