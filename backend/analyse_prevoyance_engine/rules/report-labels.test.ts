import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { helferAnalyseInput } from "../fixtures/helfer.ts";
import { formatChf } from "../mappers.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import {
  buildReportPages,
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
    assert.ok(labels.includes("LPP – Ariane – Capital"));
    assert.ok(labels.includes("LPP – Ariane – Rente réduite"));
    const arianeCapital = timeline.events.find(
      (event) => event.label === "LPP – Ariane – Capital",
    );
    const arianeRente = timeline.events.find(
      (event) => event.label === "LPP – Ariane – Rente réduite",
    );
    assert.equal(arianeCapital?.amount, 74_339);
    assert.equal(arianeRente?.amount, 8_028.5);
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

  it("garde le capital de chaque caisse, avec la rente réduite quand elle existe", () => {
    const input = emptyAnalyseInput();
    input.etatCivil = "Marié(e)";
    input.client1 = {
      ...emptyPerson("Madame"),
      prenom: "Judith",
      dateNaissance: "1973-06-01",
    };
    input.conjoint = {
      ...emptyPerson("Monsieur"),
      prenom: "Corentin",
      dateNaissance: "1978-03-01",
    };
    const timeline = timelineService.build(
      input,
      computed({
        dateDepart: "2038-06-01",
        lppLignes: [
          {
            id: "cpeg",
            institution: "CPEG",
            pct: 100,
            type: "etatique",
            age: 65,
            capital: 58_437,
            rente: 26_400,
            capitalRetire: 58_437,
            renteResiduelle: 23_196,
          },
          {
            id: "cpev",
            institution: "CPEV",
            pct: 100,
            type: "etatique",
            age: 65,
            capital: 246_444,
            rente: 30_000,
            capitalRetire: 246_444,
            renteResiduelle: 15_000,
          },
          {
            id: "rp",
            institution: "Retraite Populaire",
            pct: 100,
            type: "etatique",
            age: 65,
            capital: 198_782,
            rente: 9_542,
            capitalRetire: 198_782,
            renteResiduelle: 0,
          },
        ],
      }),
      computed({
        dateDepart: "2043-03-01",
        lppLignes: [
          {
            id: "pk",
            institution: "Pensionskasse",
            pct: 100,
            type: "classique",
            age: 65,
            capital: 422,
            rente: 23,
            capitalRetire: 422,
            renteResiduelle: 0,
          },
        ],
      }),
    );
    const lpp = timeline.events.filter((event) => event.kind === "lpp");
    const amount = (label: string) => lpp.find((event) => event.label === label)?.amount;
    assert.equal(amount("LPP – Judith – CPEG – Capital"), 58_437);
    assert.equal(amount("LPP – Judith – CPEG – Rente réduite"), 23_196);
    assert.equal(amount("LPP – Judith – CPEV – Capital"), 246_444);
    assert.equal(amount("LPP – Judith – CPEV – Rente réduite"), 15_000);
    assert.equal(amount("LPP – Judith – Retraite Populaire – Capital"), 198_782);
    assert.equal(
      lpp.some((event) => event.label.includes("Retraite Populaire") && event.label.includes("Rente")),
      false,
    );
    assert.equal(amount("LPP – Corentin – Pensionskasse – Capital"), 422);
    assert.equal(
      lpp.filter((event) => event.label.includes("Capital")).length,
      4,
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

function lppPctDisponibleRow(html: string): string {
  const marker = '<td class="lab">% LPP disponible</td>';
  const start = html.indexOf(marker);
  assert.ok(start >= 0, "ligne % LPP disponible absente");
  const end = html.indexOf("</tr>", start);
  assert.ok(end > start);
  return html.slice(start, end);
}

function comparaisonSection(html: string): string {
  const marker = '<div class="page-title">COMPARATIF DES RENTES</div>';
  const start = html.indexOf(marker);
  assert.ok(start >= 0, "page COMPARATIF DES RENTES absente");
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
      "LPP – Ariane – Capital",
      "LPP – Ariane – Rente réduite",
    ]);
    assert.equal(
      results.timeline?.events.find((event) => event.person === "client1" && event.kind === "lpp")
        ?.amount,
      results.client1.capitalLppRetire65,
    );
    const arianeLpp = (results.timeline?.events || []).filter(
      (event) => event.person === "conjoint" && event.kind === "lpp",
    );
    assert.equal(
      arianeLpp.find((event) => event.label.endsWith("Capital"))?.amount,
      results.conjoint?.capitalLppRetire65,
    );
    assert.equal(
      arianeLpp.find((event) => event.label.endsWith("Rente réduite"))?.amount,
      results.conjoint?.renteLppResiduelle65,
    );
    assert.ok(html.includes("LPP – Wiliam – Capital"));
    assert.ok(html.includes("LPP – Ariane – Capital + rente réduite"));
    const arianeRow = html.indexOf("<td>LPP – Ariane – Capital + rente réduite</td>");
    assert.ok(arianeRow >= 0);
    const arianeDetail = html.slice(arianeRow, arianeRow + 400);
    assert.match(arianeDetail, /\/an/);
    assert.ok(arianeDetail.includes(formatChf(results.conjoint?.capitalLppRetire65)));
    assert.ok(html.includes("/an"));
    assert.ok(html.includes("Rente LPP – Wiliam"));
    assert.ok(html.includes("Rente LPP – Ariane"));
    assert.ok(html.includes("Capital LPP disponible"));
    assert.equal(html.includes("Caisses LPP"), false);
    const pctRow = lppPctDisponibleRow(html);
    const pctCells = [...pctRow.matchAll(/<td class="val">([^<]*)<\/td>/g)].map((m) => m[1]);
    assert.deepEqual(pctCells, ["100 %", "50 %"]);
    assert.equal(pctRow.includes("selon règlement de la caisse"), false);
    assert.equal(html.includes('<td class="lab">Capital LPP</td>'), false);
    const payload = buildReportPayload(record);
    const capitalSplit =
      payload.client1.capitalCheminCapital +
      (payload.conjoint?.capitalCheminCapital ?? 0);
    assert.equal(Math.round(capitalSplit * 100) / 100, payload.aggregates.capitalLppRetireTotal);
    assert.equal(payload.aggregates.impotCapital65, results.capitalPathFoyer?.impot ?? null);
    assert.equal(payload.aggregates.capitalNet65, results.capitalPathFoyer?.net ?? null);
    assert.ok(html.includes("COMPARATIF DES RENTES"));
    assert.equal(html.includes("Comparaison des rentes à"), false);
    assert.equal(html.includes("Comparaison : Rente LPP vs Rente Certaine"), false);
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
    assert.ok(compare.includes("Rente LPP (référence)"));
    assert.ok(compare.includes("Vaudoise"));
    assert.ok(compare.includes("Helvetia"));
    assert.ok(compare.includes("Rente certaine"));
    assert.ok(compare.includes("20 ans"));
    assert.ok(compare.includes("Rente viagère"));
    assert.ok(compare.includes('<td class="lab">Type</td>'));
    assert.ok(compare.includes('<td class="lab">Durée</td>'));
    assert.ok(compare.includes('<td class="lab">Part imposable</td>'));
    assert.ok(compare.includes('<td class="lab">Revenu net</td>'));
    assert.ok(compare.includes("LPP – Wiliam"));
    assert.ok(compare.includes("LPP – Ariane"));
    assert.ok(compare.includes("row-net"));
    assert.ok(compare.includes("row-ecart"));
    assert.equal(compare.includes("Solution recommandée"), false);
    assert.equal(/class="[^"]*col-reco/.test(compare), false);
    assert.equal(compare.includes("calculateur officiel AVS"), false);
  });

  it("bilan : 100 % sans rente réduite, règlement si rente réduite, 50 % conservé", async () => {
    const input = emptyAnalyseInput();
    input.etatCivil = "Marié(e)";
    input.taxLocationId = 170_000_000;
    input.taxGroupId = 170_000_000;
    input.ageRetraiteSouhaite = 65;
    input.afficherResumePrestationsLpp = true;
    input.client1 = {
      ...emptyPerson("Madame"),
      prenom: "Judith",
      nom: "Bouchardy Clement",
      dateNaissance: "1973-06-01",
      lppPctDeblocable: 100,
      lppInstitution: "CPEG",
      lppType: "etatique",
      lppRetraitEtatique: "capital_max",
      lpp: emptyPerson("Madame").lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 58_437, rente: 26_400, renteReduite: 23_196 } : row,
      ),
      lppAvoirs: [
        {
          id: "cpev",
          institution: "CPEV",
          type: "etatique",
          rows: emptyPerson("Madame").lpp.map((row) =>
            row.age === 65 ? { ...row, capital: 246_444, rente: 30_000, renteReduite: 15_000 } : row,
          ),
        },
        {
          id: "rp",
          institution: "Retraite Populaire",
          type: "etatique",
          rows: emptyPerson("Madame").lpp.map((row) =>
            row.age === 65 ? { ...row, capital: 198_782, rente: 9_542 } : row,
          ),
        },
      ],
    };
    input.conjoint = {
      ...emptyPerson("Monsieur"),
      prenom: "Corentin",
      nom: "Clement",
      dateNaissance: "1978-03-01",
      lppPctDeblocable: 100,
      lppInstitution: "Pensionskasse Musik",
      lppType: "classique",
      lpp: emptyPerson("Monsieur").lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 422, rente: 276 } : row,
      ),
    };
    const html = await htmlOf(input);
    const start = html.indexOf("3. Prévoyance actuelle");
    const end = html.indexOf("4. Synthèse", start);
    assert.ok(start >= 0 && end > start);
    const bilan = html.slice(start, end);
    assert.equal(bilan.includes("Caisses LPP"), false);
    assert.equal(html.includes("Caisses LPP"), false);
    for (const label of [
      "AVS estimée",
      "Avoir LPP total",
      "% LPP disponible",
      "Capital LPP disponible",
      "3e pilier",
      "Libre passage",
    ]) {
      assert.ok(bilan.includes(label), label);
    }
    const pctRow = lppPctDisponibleRow(html);
    const cells = [...pctRow.matchAll(/<td class="val">([^<]*)<\/td>/g)].map((m) => m[1]);
    assert.deepEqual(cells, ["selon règlement de la caisse", "100 %"]);
    assert.equal(pctRow.includes("25 %"), false);

    const half = emptyAnalyseInput();
    half.etatCivil = "Marié(e)";
    half.taxLocationId = 170_000_000;
    half.taxGroupId = 170_000_000;
    half.ageRetraiteSouhaite = 65;
    half.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "Corentin",
      nom: "Clement",
      dateNaissance: "1978-03-01",
      lppPctDeblocable: 50,
      lppInstitution: "Pensionskasse Musik",
      lppType: "classique",
      lpp: emptyPerson("Monsieur").lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 422, rente: 276 } : row,
      ),
    };
    half.conjoint = {
      ...emptyPerson("Madame"),
      prenom: "Judith",
      nom: "Bouchardy",
      dateNaissance: "1973-06-01",
      lppPctDeblocable: 100,
      lppInstitution: "CPEG",
      lppType: "etatique",
      lppRetraitEtatique: "capital_max",
      lpp: emptyPerson("Madame").lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 58_437, rente: 26_400, renteReduite: 23_196 } : row,
      ),
    };
    const halfHtml = await htmlOf(half);
    const halfRow = lppPctDisponibleRow(halfHtml);
    const halfCells = [...halfRow.matchAll(/<td class="val">([^<]*)<\/td>/g)].map((m) => m[1]);
    assert.deepEqual(halfCells, ["50 %", "selon règlement de la caisse"]);
    assert.equal(halfHtml.includes("Caisses LPP"), false);
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
    assert.equal(compare.includes("Écart vs référence"), false);
    assert.equal(html.includes("Revenu annuel obtenu sur le capital placé"), false);
    assert.equal(html.includes("Ce ratio rapporte le revenu encaissé"), false);
    assert.equal(html.includes("Revenu annuel / capital"), false);
    assert.ok(html.includes("COMPARATIF DES RENTES"));
    assert.equal(html.includes("Gain net"), false);
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

  it("n'imprime plus la mention AVS simulation sous le comparatif", async () => {
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
    assert.equal(htmlOn.includes("calculateur officiel AVS"), false);
    assert.equal(htmlOn.includes("avs-sim-note"), false);

    const conjointOnly = helferAnalyseInput();
    conjointOnly.ageRetraiteSouhaite = 65;
    conjointOnly.comparerAvecRenteLpp = true;
    conjointOnly.renteHypotheses = [offreA];
    conjointOnly.conjoint = {
      ...conjointOnly.conjoint!,
      avsMontantIssuSimulation: true,
    };
    const htmlConjoint = await htmlOf(conjointOnly);
    assert.equal(htmlConjoint.includes("calculateur officiel AVS"), false);
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
    assert.ok(html.includes("Capital LPP disponible"));
    assert.equal(html.includes("Caisses LPP"), false);
    assert.ok(html.includes("Marc"));
    assert.equal(html.includes("Assuré 2"), false);
    assert.equal(payload.conjoint, null);
    assert.equal(payload.client1.capitalCheminCapital, payload.aggregates.capitalLppRetireTotal);
  });

  it("cadre vert uniquement si le conseiller coche Recommander", async () => {
    const off = helferAnalyseInput();
    off.ageRetraiteSouhaite = 65;
    off.comparerAvecRenteLpp = true;
    off.renteHypotheses = [offreA, offreB];
    const htmlOff = await htmlOf(off);
    assert.equal(htmlOff.includes("Solution recommandée"), false);
    assert.equal(/class="[^"]*col-reco/.test(htmlOff), false);

    const on = helferAnalyseInput();
    on.ageRetraiteSouhaite = 65;
    on.comparerAvecRenteLpp = true;
    on.renteHypotheses = [{ ...offreA, recommander: true }, offreB];
    const htmlOn = await htmlOf(on);
    const compare = comparaisonSection(htmlOn);
    assert.ok(compare.includes("Solution recommandée"));
    assert.ok(/class="[^"]*col-reco/.test(compare));
    const vaudoiseHead = compare.indexOf("Vaudoise");
    const helvetiaHead = compare.indexOf("Helvetia");
    const reco = compare.indexOf("Solution recommandée");
    assert.ok(vaudoiseHead >= 0 && helvetiaHead >= 0 && reco >= 0);
    assert.ok(reco > vaudoiseHead && reco < helvetiaHead);
  });

  it("affiche un tiret si N/A, distinct d'un zéro, sans 0 % forcé", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [{ ...offreA, participationExcedentsAnnuelle: 0 }];
    const html = await htmlOf(input);
    const compare = comparaisonSection(html);
    assert.ok(compare.includes("—"));
    const partRow = (compare.split("Part imposable")[1] || "").split("</tr>")[0];
    assert.equal(partRow.includes("0%"), false);
    const seul = emptyAnalyseInput();
    seul.etatCivil = "Personne vivant seule";
    seul.taxLocationId = 170_000_000;
    seul.taxGroupId = 170_000_000;
    seul.comparerAvecRenteLpp = true;
    seul.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "Marc",
      nom: "Demo",
      dateNaissance: "1960-01-01",
    };
    seul.renteHypotheses = [offreA];
    const htmlSeul = await htmlOf(seul);
    const last = comparaisonSection(htmlSeul);
    assert.ok(last.includes("LPP – Marc"));
    assert.equal(last.includes("LPP – Assuré 2"), false);
  });

  it("affiche les offres saisies même si le dernier calcul ne les contient pas", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = true;
    input.renteVaudoise15 = null;
    input.renteVaudoise20 = null;
    input.renteHypotheses = [];
    const results = await retirementAnalysisService.run(input);
    assert.equal(
      Boolean(results.renteHypotheses?.columns.some((col) => col.kind === "hypothese")),
      false,
    );

    const stale: AnalyseRecord = {
      id: "stale-hypotheses",
      createdAt: "2026-10-07T00:00:00.000Z",
      updatedAt: "2026-10-07T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input: { ...input, renteHypotheses: [offreA, offreB] },
      results,
    };
    const html = renderPrintableReportHtml(buildReportPayload(stale));
    assert.ok(html.includes("Comparatif des solutions de rentes"));
    const compare = comparaisonSection(html);
    assert.ok(compare.includes("Vaudoise"));
    assert.ok(compare.includes("Helvetia"));
    assert.ok(compare.includes("20 ans"));
    assert.ok(compare.includes("Rente certaine"));
    assert.ok(compare.includes("Rente viagère"));
    assert.ok(/530\s*000/u.test(compare));
    assert.ok(/200\s*000/u.test(compare));
    assert.equal(compare.includes("Solution recommandée"), false);
  });

  it("ne laisse sous le comparatif que la note fiscale et, s'il y a Pax, la note de différé", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [offreA];
    const html = await htmlOf(input);
    const start = html.indexOf('<div class="page-title">COMPARATIF DES RENTES</div>');
    assert.ok(start >= 0, "page COMPARATIF DES RENTES absente");
    const tableStart = html.indexOf('<table class="data compare">', start);
    assert.ok(tableStart >= 0, "tableau compare absent");
    const tableEnd = html.indexOf("</table>", tableStart);
    assert.ok(tableEnd >= 0);
    const page = html.slice(start);
    const fiscal =
      "Le montant de l'impôt présenté est une estimation calculée uniquement sur la base des rentes AVS et LPP prises en compte dans cette analyse.";
    const fiscalPos = page.indexOf(fiscal);
    assert.ok(fiscalPos > tableEnd - start, "la note * doit suivre le tableau");
    assert.equal(page.includes("Rente certaine. Revenu fiscal"), false);
    assert.equal(page.includes("Rente viagère. Revenu fiscal"), false);
    assert.equal(page.includes("calculateur officiel AVS"), false);
    assert.equal(page.includes("Aucun cumul"), false);
    assert.equal(page.includes("revenu-fiscal-note"), false);
    assert.equal(page.includes("avs-sim-note"), false);
  });

  it("écrit le différé saisi et n'invente pas Différé : 0", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [
      { ...offreA, dureeAnnees: 20, dureeDiffereAnnees: 3 },
      { ...offreB, dureeDiffereAnnees: 3 },
    ];
    const html = await htmlOf(input);
    const compare = comparaisonSection(html);
    assert.ok(compare.includes("Différé"));
    assert.ok(compare.includes("Différé : 3 ans"));
    assert.ok(compare.includes("3"));
    const dureeRow = (compare.split('<td class="lab">Durée</td>')[1] || "").split("</tr>")[0];
    assert.ok(dureeRow.includes("20 ans"));
    assert.ok(dureeRow.includes("À vie"));
    assert.equal(dureeRow.includes("Différé"), false);
    const differeRow = (compare.split('<td class="lab">Différé</td>')[1] || "").split("</tr>")[0];
    assert.ok(differeRow.includes("Différé : 3 ans"));
    assert.equal(compare.includes("Différé : 0"), false);
    assert.equal(compare.includes("Gain net"), false);
    assert.equal(
      html.includes(
        "100 % de la participation aux excédents. La rente garantie est encaissée et n'entre pas dans l'impôt",
      ),
      false,
    );
    assert.ok(html.includes("4 % de la rente garantie + 70 % de la participation aux excédents"));
    assert.equal(html.includes("4 % de la rente garantie + 100 % de la participation"), false);
    assert.equal(html.includes("70 % de la participation aux excédents. La rente garantie"), false);

    const sans = helferAnalyseInput();
    sans.ageRetraiteSouhaite = 65;
    sans.comparerAvecRenteLpp = false;
    sans.renteHypotheses = [{ ...offreA, dureeDiffereAnnees: 0 }, offreB];
    const htmlSans = await htmlOf(sans);
    const compareSans = comparaisonSection(htmlSans);
    assert.equal(compareSans.includes("Différé : 0"), false);
    assert.equal(compareSans.includes('<td class="lab">Différé</td>'), false);

    const calcule = helferAnalyseInput();
    calcule.ageRetraiteSouhaite = 65;
    calcule.comparerAvecRenteLpp = false;
    calcule.renteHypotheses = [offreA];
    const results = await retirementAnalysisService.run(calcule);
    const stale: AnalyseRecord = {
      id: "differe-apres-calcul",
      createdAt: "2026-10-07T00:00:00.000Z",
      updatedAt: "2026-10-07T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input: {
        ...calcule,
        renteHypotheses: [{ ...offreA, dureeDiffereAnnees: 3 }],
      },
      results,
    };
    const htmlStale = renderPrintableReportHtml(buildReportPayload(stale));
    assert.ok(comparaisonSection(htmlStale).includes("Différé : 3 ans"));
    assert.equal(comparaisonSection(htmlStale).includes("Différé : 0"), false);
  });

  it("place le comparatif des offres après les solutions, en dernière page", async () => {
    const input = helferAnalyseInput();
    input.ageRetraiteSouhaite = 65;
    input.comparerAvecRenteLpp = true;
    input.renteHypotheses = [offreA, offreB];
    const results = await retirementAnalysisService.run(input);
    const record: AnalyseRecord = {
      id: "ordre-pages",
      createdAt: "2026-10-07T00:00:00.000Z",
      updatedAt: "2026-10-07T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const pages = buildReportPages(buildReportPayload(record));
    const solutions = pages.findIndex((page) =>
      page.html.includes("Comparatif des solutions de rentes"),
    );
    const offres = pages.findIndex((page) =>
      page.html.includes('<div class="page-title">COMPARATIF DES RENTES</div>'),
    );
    assert.ok(solutions >= 0, "page solutions absente");
    assert.ok(offres > solutions, "le comparatif des offres doit suivre les solutions");
    assert.equal(offres, pages.length - 1);
    assert.ok(pages[offres].html.includes("Vaudoise"));
    assert.equal(pages[offres].html.includes("Revenu annuel obtenu sur le capital placé"), false);
    assert.equal(pages[solutions].html.includes("COMPARATIF DES RENTES"), false);
    const solutionsHtml = pages[solutions].html;
    assert.ok(solutionsHtml.includes("Valeur de rachat 31.12"));
    assert.ok(solutionsHtml.includes("Pas de fortune imposable"));
    assert.ok(solutionsHtml.includes("Fortune imposable selon la variante choisie avec des particularités VD"));
    assert.ok(solutionsHtml.includes("Fortune imposable (montant versé en cas de résiliation)"));
    const timbre = solutionsHtml.indexOf("Droit de timbre fédéral");
    const rachat = solutionsHtml.indexOf("Valeur de rachat 31.12");
    const imposable = solutionsHtml.indexOf("Part du revenu imposable");
    assert.ok(timbre >= 0 && timbre < rachat && rachat < imposable);
    assert.ok(solutionsHtml.includes("4 % de la rente garantie + 70 % de la participation aux excédents"));
    assert.ok(solutionsHtml.includes("0 % de la rente garantie + 100 % de la participation aux excédents"));
    assert.ok(solutionsHtml.includes("100 % de la rente versée"));
    assert.equal(solutionsHtml.includes("4 % de la rente garantie + 100 % de la participation"), false);
    assert.equal(solutionsHtml.includes("impôt anticipé 35 %"), false);
  });

  it("signale Pax sans remplir le différé, et pas Rentes Genevoises", async () => {
    const phrase =
      "Pour les contrats PAX, un différé d’un an s’applique systématiquement avant le premier versement de la rente.";
    const ancienne = "Avec Pax, il y aura toujours un différé de 1 an.";
    const paxInput = helferAnalyseInput();
    paxInput.ageRetraiteSouhaite = 65;
    paxInput.comparerAvecRenteLpp = false;
    paxInput.renteHypotheses = [{ ...offreA, compagnie: "Pax", dureeDiffereAnnees: null }];
    const htmlPax = await htmlOf(paxInput);
    assert.ok(htmlPax.includes(phrase));
    assert.equal(htmlPax.includes(ancienne), false);
    assert.ok(htmlPax.includes("Pax *"));
    assert.equal(htmlPax.includes("Différé : 1"), false);
    const pagePax = htmlPax.slice(
      htmlPax.indexOf('<div class="page-title">COMPARATIF DES RENTES</div>'),
    );
    const etoile = pagePax.indexOf("Le montant de l'impôt présenté est une estimation");
    const notePax = pagePax.indexOf(phrase);
    assert.ok(etoile >= 0 && notePax > etoile, "la note Pax suit la phrase *");
    assert.ok(pagePax.includes("compare-footnotes"));

    const geneveInput = helferAnalyseInput();
    geneveInput.ageRetraiteSouhaite = 65;
    geneveInput.comparerAvecRenteLpp = false;
    geneveInput.renteHypotheses = [{ ...offreA, compagnie: "Rentes Genevoises" }];
    const htmlGeneve = await htmlOf(geneveInput);
    assert.equal(htmlGeneve.includes(phrase), false);
    assert.ok(htmlGeneve.includes("Rentes Genevoises"));
  });
});
