import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatChf } from "../mappers.ts";
import { buildReportPages } from "../pdf/renderPrintableReportHtml.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { avsCalculationService } from "../services/AVSCalculationService.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { timelineService } from "../services/TimelineService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseRecord,
  type PersonInput,
} from "../types.ts";

const REFERENCE = 2_150 * 13;
const REDUITE = 24_149;
const AUTRE = 1_800 * 13;

function personne(civilite: "Monsieur" | "Madame", annuel: number): PersonInput {
  const person = emptyPerson(civilite);
  person.avsMensuel = annuel / 13;
  person.avsAnnuel = annuel;
  return person;
}

function ligne(html: string, label: string): string {
  const marker = `<td class="lab">${label}</td>`;
  const start = html.indexOf(marker);
  assert.ok(start >= 0, label);
  return html.slice(start, html.indexOf("</tr>", start));
}

function synthese(html: string): string {
  const start = html.indexOf("4. Synthèse des prestations attendues à la retraite");
  assert.ok(start >= 0);
  const next = html.indexOf("sec-title", start + 20);
  return html.slice(start, next === -1 ? html.length : next);
}

describe("AVS de référence dans le PDF", () => {
  it("2 150 mensuel et 2 ans d'anticipation gardent 27 950, pas 24 149", () => {
    const input = emptyAnalyseInput();
    input.etatCivil = "Marié(e)";
    input.salaireClient1 = 90_000;
    input.salaireConjoint = 70_000;
    input.client1 = personne("Monsieur", REFERENCE);
    input.client1.prenom = "Paul";
    input.client1.nom = "Martin";
    input.client1.dateNaissance = "1962-06-15";
    input.client1.anticipationAvsAnnees = 2;
    input.client1.avsRentesAnticipees = [];
    input.conjoint = personne("Madame", AUTRE);
    input.conjoint.prenom = "Agnès";
    input.conjoint.nom = "Martin";
    input.conjoint.dateNaissance = "1964-04-01";

    const client1 = avsCalculationService.computePersonBasics(input.client1);
    const conjoint = avsCalculationService.computePersonBasics(input.conjoint!);
    assert.equal(client1.avsAnnuel, 27_950);
    assert.equal(client1.renteTotale65, 27_950);
    assert.equal(client1.datePerceptionAvs, "2025-07-01");
    assert.equal(client1.agePerceptionAvsLabel, "63 ans (anticipation 2 ans)");
    assert.equal(conjoint.avsAnnuel, AUTRE);
    assert.notEqual(conjoint.avsAnnuel, client1.avsAnnuel);

    const lacune = retirementAnalysisService.computeLacune(
      input,
      client1.renteTotale65,
      conjoint.renteTotale65,
    );
    assert.equal(lacune.revenuApres, REFERENCE + AUTRE);

    const timeline = timelineService.build(input, client1, conjoint);
    const montants = timeline.events
      .filter((event) => event.kind === "avs")
      .map((event) => event.amount)
      .sort((a, b) => a - b);
    assert.deepEqual(montants, [AUTRE, REFERENCE].sort((a, b) => a - b));

    const record = {
      id: "avs-reference",
      createdAt: "2026-11-02T00:00:00.000Z",
      updatedAt: "2026-11-02T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results: {
        client1,
        conjoint,
        incomeScenarios: [],
        capitalScenarios: [],
        lacune,
        taxLocation: null,
        timeline,
        withdrawalPlanning: null,
        resumeCapitalTax: null,
        errors: [],
        computedAt: "2026-11-02T00:00:00.000Z",
      },
    } as AnalyseRecord;
    const html = buildReportPages(buildReportPayload(record))
      .map((page) => page.html)
      .join("\n");
    const estimee = ligne(html, "AVS estimée");
    const total = synthese(html);
    const reference = formatChf(REFERENCE);
    const autre = formatChf(AUTRE);
    const reduite = formatChf(REDUITE);
    assert.match(estimee, new RegExp(reference.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.match(estimee, new RegExp(autre.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.equal(estimee.includes(reduite), false);
    assert.match(total, new RegExp(formatChf(REFERENCE + AUTRE).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    assert.equal(total.includes(reduite), false);
    assert.match(html, /63 ans \(anticipation 2 ans\)/);
    assert.equal(html.includes("RENTE AVS – COMPARAISON DES ÂGES DE DÉPART"), false);
    assert.equal(html.includes("ANALYSE DE L'ANTICIPATION AVS"), false);
  });
});
