import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it, after } from "node:test";
import { fileURLToPath } from "node:url";
import { formatChf } from "../mappers.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { buildReportPages } from "../pdf/renderPrintableReportHtml.ts";
import {
  closePdfBrowser,
  pdfGenerationService,
} from "../services/PdfGenerationService.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import {
  emptyAnalyseInput,
  emptyLppRows,
  type AnalyseInput,
  type AnalyseRecord,
  type WithdrawalPlanItem,
} from "../types.ts";

const FORBIDDEN_3B = [41_704, 57_337, 41_459];
const POLICES = [
  "L501434748",
  "L501434781",
  "SL45813",
  "L501434782",
  "L501434783",
];

const capitalsSent: number[] = [];

function lpp(capital: number, rente: number) {
  return emptyLppRows().map((row) =>
    row.age === 65 ? { age: 65 as const, capital, rente } : row,
  );
}

function pillar(
  id: string,
  type: "3A" | "3B",
  compagnie: string,
  police: string,
  echeance: string,
  montant: number,
) {
  return { id, type, compagnie, police, echeance, montant, prime: 1_200 };
}

function planItem(
  partial: Pick<
    WithdrawalPlanItem,
    "id" | "kind" | "titulaire" | "label" | "montantDisponible" | "anneeRetraitPrevue"
  > & { sourceId?: string; pctCapital?: number },
): WithdrawalPlanItem {
  return {
    institution: partial.kind === "lpp" ? "LPP" : "3e pilier",
    pctCapital: partial.pctCapital ?? 100,
    anneePremierePossible: partial.anneeRetraitPrevue,
    anneeDernierePossible: null,
    ...partial,
  };
}

function dossier(): AnalyseInput {
  const base = emptyAnalyseInput();
  const a1a = pillar("c-a1-3a", "3A", "Axa", "L501434748", "2038-01-01", 55_872);
  const a1b = pillar("c-a1-3b", "3B", "Axa", "L501434781", "2032-01-01", 41_704);
  const a2a = pillar("c-a2-3a", "3A", "Swiss Life", "SL45813", "2037-06-01", 45_813);
  const a2b = pillar("c-a2-3b-2039", "3B", "Axa", "L501434782", "2036-01-01", 57_337);
  const a2c = pillar("c-a2-3b-2035", "3B", "Axa", "L501434783", "2033-01-01", 41_459);

  const spreadItems = [
    planItem({
      id: "lpp-1",
      kind: "lpp",
      titulaire: "client1",
      label: "LPP Assuré 1",
      montantDisponible: 800_000,
      pctCapital: 100,
      anneeRetraitPrevue: 2040,
    }),
    planItem({
      id: "lpp-2",
      kind: "lpp",
      titulaire: "conjoint",
      label: "LPP Assuré 2",
      montantDisponible: 400_000,
      pctCapital: 100,
      anneeRetraitPrevue: 2040,
    }),
    planItem({
      id: "3p-a1a",
      kind: "3p",
      titulaire: "client1",
      label: "3A Assuré 1",
      montantDisponible: 55_872,
      anneeRetraitPrevue: 2041,
      sourceId: a1a.id,
    }),
    planItem({
      id: "3p-a1b",
      kind: "3p",
      titulaire: "client1",
      label: "3B Assuré 1",
      montantDisponible: 41_704,
      anneeRetraitPrevue: 2035,
      sourceId: a1b.id,
    }),
    planItem({
      id: "3p-a2a",
      kind: "3p",
      titulaire: "conjoint",
      label: "3A Assuré 2",
      montantDisponible: 45_813,
      anneeRetraitPrevue: 2041,
      sourceId: a2a.id,
    }),
    planItem({
      id: "3p-a2b",
      kind: "3p",
      titulaire: "conjoint",
      label: "3B Assuré 2",
      montantDisponible: 57_337,
      anneeRetraitPrevue: 2039,
      sourceId: a2b.id,
    }),
    planItem({
      id: "3p-a2c",
      kind: "3p",
      titulaire: "conjoint",
      label: "3B Assuré 2",
      montantDisponible: 41_459,
      anneeRetraitPrevue: 2035,
      sourceId: a2c.id,
    }),
  ];

  const groupedItems = spreadItems.map((item) => ({
    ...item,
    id: `g-${item.id}`,
    anneeRetraitPrevue:
      item.kind === "3p" && item.label.startsWith("3A")
        ? 2040
        : item.anneeRetraitPrevue,
  }));

  return {
    ...base,
    villeRecherche: "1700 Fribourg",
    taxLocationId: 170_000_000,
    taxGroupId: 170_000_000,
    etatCivil: "Marié(e)",
    salaireClient1: 120_000,
    salaireConjoint: 80_000,
    taxYear: 2025,
    client1: {
      ...base.client1,
      civilite: "Monsieur",
      nom: "TEST",
      prenom: "Assuré",
      dateNaissance: "1970-01-15",
      avsAnnuel: 28_000,
      lpp: lpp(800_000, 40_000),
      lppPctDeblocable: 25,
      troisiemePilier: [a1a, a1b],
    },
    conjoint: {
      ...base.client1,
      civilite: "Madame",
      nom: "TEST",
      prenom: "Deux",
      dateNaissance: "1970-06-01",
      avsAnnuel: 26_000,
      lpp: lpp(400_000, 20_000),
      lppPctDeblocable: 100,
      troisiemePilier: [a2a, a2b, a2c],
    },
    withdrawalScenarios: [
      {
        id: "spread",
        name: "Retraits répartis",
        includeInReport: true,
        items: spreadItems,
      },
      {
        id: "grouped",
        name: "Retraits regroupés",
        includeInReport: true,
        items: groupedItems,
      },
      {
        id: "decoy",
        name: "Hors rapport",
        includeInReport: false,
        items: spreadItems.map((item) => ({
          ...item,
          id: `x-${item.id}`,
          anneeRetraitPrevue: 2099,
        })),
      },
    ],
  };
}

describe("5 contrats 3A/3B", () => {
  const originalCapital = taxCalculationService.calculateCapitalTax.bind(
    taxCalculationService,
  );
  const originalIncome = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );

  taxCalculationService.calculateCapitalTax = async (params) => {
    capitalsSent.push(params.capital);
    const impotTotal = Math.round((params.capital * params.capital) / 1_000_000);
    return {
      age: params.ageAtPayment,
      capital: params.capital,
      gender: params.gender,
      relationship: params.relationship,
      taxGroupId: params.taxGroupId,
      taxYear: params.taxYear ?? 2025,
      taxCity: 0,
      taxCanton: 0,
      taxFed: impotTotal,
      taxChurch: 0,
      impotTotal,
      request: {},
      response: {},
    };
  };
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

  it("met les 5 contrats dans le payload, la frise et le PDF", async () => {
    const input = dossier();
    const results = await retirementAnalysisService.run(input);
    const record: AnalyseRecord = {
      id: "validation-5",
      createdAt: "2026-10-05T00:00:00.000Z",
      updatedAt: "2026-10-05T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const payload = buildReportPayload(record);
    const pages = buildReportPages(payload);
    const html = pages.map((page) => page.html).join("\n");

    assert.equal(payload.thirdPillarRows.length, 5);
    assert.deepEqual(
      payload.thirdPillarRows.map((row) => row.police),
      POLICES,
    );
    assert.equal(
      payload.thirdPillarRows.filter((row) => row.personKey === "client1").length,
      2,
    );
    assert.equal(
      payload.thirdPillarRows.filter((row) => row.personKey === "conjoint").length,
      3,
    );
    for (const row of payload.thirdPillarRows) {
      if (row.type === "3B") {
        assert.equal(row.exonere, true);
        assert.equal(row.impot, null);
        assert.equal(row.capitalNet, row.montant);
      } else {
        assert.equal(row.exonere, false);
        assert.ok(row.impot != null && row.impot > 0);
        assert.ok((row.capitalNet ?? 0) < row.montant);
      }
    }

    assert.equal(results.client1.total3ePilier, 55_872 + 41_704);
    assert.equal(results.conjoint?.total3ePilier, 45_813 + 57_337 + 41_459);
    assert.equal(results.client1.capitalLpp65, 800_000);
    assert.equal(results.client1.capitalLppRetire65, 200_000);
    assert.equal(results.conjoint?.capitalLppRetire65, 400_000);
    assert.equal(payload.aggregates.capitalLppAvecLibrePassage, 600_000);

    for (const forbidden of FORBIDDEN_3B) {
      assert.equal(
        capitalsSent.includes(forbidden),
        false,
        `3B ${forbidden} envoyé à l'impôt sur le capital`,
      );
    }
    assert.ok(capitalsSent.includes(55_872));
    assert.ok(capitalsSent.includes(45_813));

    const lppEvents = payload.timeline.events.filter((event) => event.kind === "lpp");
    assert.ok(lppEvents.length >= 2);
    assert.ok(lppEvents.every((event) => event.year === 2040));
    const pillarEvents = payload.timeline.events.filter((event) => event.kind === "3p");
    assert.equal(pillarEvents.length, 5);
    assert.deepEqual(
      pillarEvents.map((event) => event.year).sort((a, b) => a - b),
      [2035, 2035, 2039, 2041, 2041],
    );
    const byPolice = Object.fromEntries(
      pillarEvents.map((event) => [
        POLICES.find((police) => event.label.includes(police)),
        event.year,
      ]),
    );
    assert.equal(byPolice.L501434748, 2041);
    assert.equal(byPolice.L501434781, 2035);
    assert.equal(byPolice.SL45813, 2041);
    assert.equal(byPolice.L501434782, 2039);
    assert.equal(byPolice.L501434783, 2035);
    assert.equal(payload.timeline.years.includes(2099), false);
    assert.equal(payload.timeline.years.includes(2038), false);
    assert.equal(payload.timeline.years.includes(2032), false);

    for (const police of POLICES) {
      assert.ok(html.includes(police), police);
    }
    assert.equal(html.includes("contrat principal"), false);
    assert.equal(html.includes("Affichage"), false);
    assert.ok(html.includes("Exonéré d'impôt"));
    assert.ok(html.includes("Capital 2e pilier retirable, y compris libre passage"));
    assert.ok(html.includes("Rente LPP – Assuré"));
    assert.ok(html.includes("Rente LPP – Deux"));
    assert.equal(html.includes("Assuré 1"), false);
    assert.equal(html.includes("Assuré 2"), false);
    assert.ok(html.includes("LPP – Assuré – Capital + rente"));
    assert.ok(html.includes("LPP – Deux – Capital"));
    assert.ok(html.includes("Analyse des contrats de prévoyance 3A/3B"));
    assert.equal(html.includes("(suite)"), false);
    assert.ok(html.includes("Revenu touché"));
    assert.ok(html.includes("Manque de revenu"));
    assert.equal(html.includes("hatchGreen"), false);
    assert.equal(pages.length, payload.meta.pageCount);

    const spread = payload.withdrawalPlanning.scenarios.find((s) => s.id === "spread");
    const lpp2040 = spread?.byYear.find((year) => year.year === 2040);
    const lppSum = (lpp2040?.lines || [])
      .filter((line) => line.kind === "lpp")
      .reduce((sum, line) => sum + line.montantRetire, 0);
    assert.equal(lppSum, 600_000);

    const planning = results.withdrawalPlanning;
    assert.ok(planning);
    assert.equal(planning.strategyScenarioId, "spread");
    const ref = planning.sameYearReference;
    assert.ok(ref);
    assert.equal(ref.year, 2040);
    assert.equal(ref.sourceScenarioId, "spread");
    const taxableLpp3a = 200_000 + 55_872 + 400_000 + 45_813;
    const exempt3b = 41_704 + 57_337 + 41_459;
    assert.equal(
      ref.audits.reduce((sum, audit) => sum + audit.montantSoumis, 0),
      taxableLpp3a,
    );
    assert.equal(ref.capitalRetire, taxableLpp3a + exempt3b);
    assert.deepEqual(
      ref.audits
        .map((audit) => audit.montantSoumis)
        .filter((amount) => amount > 0)
        .sort((a, b) => a - b),
      [200_000 + 55_872 + 400_000 + 45_813],
    );
    for (const audit of ref.audits) {
      assert.equal(FORBIDDEN_3B.includes(audit.montantSoumis), false);
      for (const capital of audit.capitauxInclus) {
        assert.equal(capital.label.startsWith("3B"), false);
        assert.equal(FORBIDDEN_3B.includes(capital.montantRetire), false);
      }
    }
    assert.equal(
      ref.audits.some((audit) =>
        audit.capitauxInclus.some(
          (capital) => capital.kind === "lpp" && capital.montantRetire === 200_000,
        ),
      ),
      true,
    );
    assert.equal(
      ref.audits.some((audit) =>
        audit.capitauxInclus.some((capital) => capital.montantRetire === 800_000),
      ),
      false,
    );
    assert.ok(capitalsSent.includes(200_000 + 400_000 + 55_872 + 45_813));
    assert.equal(capitalsSent.includes(200_000 + 55_872), false);
    assert.equal(capitalsSent.includes(400_000 + 45_813), false);
    const spreadResult = planning.scenarios.find((scenario) => scenario.scenarioId === "spread");
    assert.ok(spreadResult);
    assert.equal(ref.impotTotal != null && spreadResult.impotTotal != null, true);
    const economie =
      Math.round(((ref.impotTotal ?? 0) - (spreadResult.impotTotal ?? 0)) * 100) / 100;
    assert.equal(planning.economieFiscale, economie);
    assert.ok(economie > 0);
    assert.equal(payload.withdrawalPlanning.economieFiscale, economie);
    const planHtml =
      pages.map((page) => page.html).find((page) => page.includes("Planification des retraits")) ||
      "";
    assert.ok(planHtml.includes("RETRAITS LA MÊME ANNÉE FISCALE"));
    assert.ok(planHtml.includes("STRATÉGIE DE RETRAITS PRÉPARÉE"));
    assert.ok(planHtml.includes("Prestations retirées"));
    assert.equal((planHtml.split(">2035<").length - 1), 1);
    assert.ok(planHtml.includes(`ÉCONOMIE FISCALE ESTIMÉE : ${formatChf(economie)}`));
    assert.equal(planHtml.includes("Dossier de démonstration"), false);
    assert.equal(planHtml.includes('class="eco eco-none"'), false);

    const pdf = await pdfGenerationService.generatePdfBuffer(record);
    const out = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../generated/validation-analyse-5-contrats.pdf",
    );
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, pdf);
    assert.ok(pdf.subarray(0, 5).toString() === "%PDF-");
    const text = extractPdfText(out);
    for (const police of POLICES) {
      assert.ok(text.includes(police), `PDF sans ${police}`);
    }
    assert.equal(text.includes("contrat principal"), false);
    assert.ok(text.includes("Exonér"));
    console.log(`PDF ${out} (${pdf.length} octets), contrats PDF ${POLICES.length}/${POLICES.length}`);

    const demoRecord: AnalyseRecord = {
      ...record,
      input: {
        ...input,
        conseillerNom:
          "DOSSIER DÉMO — impôts simulés par le test, pas un calcul ESTV réel",
        client1: { ...input.client1, prenom: "Démo", nom: "PLANIFICATION" },
        conjoint: input.conjoint
          ? { ...input.conjoint, prenom: "Démo", nom: "PLANIFICATION" }
          : null,
      },
    };
    const demoPdf = await pdfGenerationService.generatePdfBuffer(demoRecord);
    const demoOut = resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../generated/validation-planification-retraits.pdf",
    );
    writeFileSync(demoOut, demoPdf);
    const demoText = extractPdfText(demoOut);
    assert.ok(demoText.includes("DOSSIER"));
    assert.ok(demoText.includes("monstration") || demoText.includes("simul"));
    console.log(`PDF démo ${demoOut} (${demoPdf.length} octets) — impôts simulés, pas ESTV`);
  });

  it("n'affiche pas une économie positive quand l'échelonnement n'est pas plus favorable", async () => {
    const previous = taxCalculationService.calculateCapitalTax;
    const sent: number[] = [];
    taxCalculationService.calculateCapitalTax = async (params) => {
      sent.push(params.capital);
      return {
        age: params.ageAtPayment,
        capital: params.capital,
        gender: params.gender,
        relationship: params.relationship,
        taxGroupId: params.taxGroupId,
        taxYear: params.taxYear ?? 2025,
        taxCity: 0,
        taxCanton: 0,
        taxFed: 5_000,
        taxChurch: 0,
        impotTotal: 5_000,
        request: {},
        response: {},
      };
    };
    try {
      const input = dossier();
      input.withdrawalScenarios = input.withdrawalScenarios.map((scenario) => ({
        ...scenario,
        includeInReport: scenario.id === "spread",
      }));
      const results = await retirementAnalysisService.run(input);
      const planning = results.withdrawalPlanning;
      assert.ok(planning?.sameYearReference);
      assert.equal(planning.strategyScenarioId, "spread");
      const spread = planning.scenarios.find((scenario) => scenario.scenarioId === "spread");
      assert.ok(spread);
      assert.equal(
        planning.economieFiscale,
        Math.round(
          ((planning.sameYearReference.impotTotal ?? 0) - (spread.impotTotal ?? 0)) * 100,
        ) / 100,
      );
      assert.ok((planning.economieFiscale ?? 1) <= 0);
      for (const forbidden of FORBIDDEN_3B) {
        assert.equal(sent.includes(forbidden), false);
      }
      assert.ok(sent.includes(200_000 + 400_000 + 55_872 + 45_813));
      assert.equal(sent.includes(200_000 + 55_872), false);
      assert.equal(sent.includes(800_000), false);
      const record: AnalyseRecord = {
        id: "validation-eco-nulle",
        createdAt: "2026-10-05T00:00:00.000Z",
        updatedAt: "2026-10-05T00:00:00.000Z",
        clientId: null,
        status: "calculee",
        input,
        results,
      };
      const html = buildReportPages(buildReportPayload(record))
        .map((page) => page.html)
        .find((page) => page.includes("Planification des retraits"));
      assert.ok(html);
      assert.ok(html.includes('class="eco eco-none"'));
      assert.equal(html.includes('class="eco">'), false);
      assert.ok(html.includes("l'échelonnement n'est pas plus favorable"));
      assert.ok(html.includes("ÉCONOMIE FISCALE ESTIMÉE : 0 CHF"));
    } finally {
      taxCalculationService.calculateCapitalTax = previous;
    }
  });
});

after(async () => {
  await closePdfBrowser();
});

function extractPdfText(pdfPath: string): string {
  const script = [
    "import pymupdf, sys",
    "doc = pymupdf.open(sys.argv[1])",
    "sys.stdout.buffer.write(chr(10).join(page.get_text() for page in doc).encode('utf-8'))",
  ].join("\n");
  return execFileSync("python", ["-c", script, pdfPath], { encoding: "utf-8" });
}
