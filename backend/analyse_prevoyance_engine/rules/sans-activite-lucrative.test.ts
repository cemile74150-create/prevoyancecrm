import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildReportPages,
  renderPrintableReportHtml,
} from "../pdf/renderPrintableReportHtml.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { anneeRetraitLibrePassage } from "./libre-passage-annee.ts";
import { personHasLppSaisie } from "./lpp-saisie.ts";
import {
  emptyAnalyseInput,
  emptyLibrePassage,
  emptyPerson,
  type AnalyseInput,
  type AnalyseRecord,
} from "../types.ts";

/** Cas type Janique SOLER : sans activité, sans LPP, avec LP + 3e + AVS. */
function inputJaniqueType(): AnalyseInput {
  const input = emptyAnalyseInput();
  input.villeRecherche = "Genève";
  input.taxLocationId = 170_000_000;
  input.taxGroupId = 170_000_000;
  input.etatCivil = "Personne vivant seule";
  input.salaireClient1 = 0;
  input.ageRetraiteSouhaite = 65;
  input.client1 = {
    ...emptyPerson("Madame"),
    prenom: "Janique",
    nom: "SOLER",
    dateNaissance: "1964-06-15",
    sansActiviteLucrative: true,
    avsAnnuel: 22_802,
    avsMensuel: 0,
    troisiemePilier: [
      {
        id: "3p-1",
        type: "3A",
        compagnie: "Test",
        police: "1",
        montant: 121_443,
        prime: 0,
        echeance: "2029-01-01",
        valeursRachat: [],
      },
    ],
  };
  input.libresPassages = [
    {
      ...emptyLibrePassage("client1"),
      id: "lp-1",
      institution: "Libre passage",
      montant: 199_486,
      pctRetire: 100,
      dateRetraitPossible: "2027-03-01",
      ageDeblocage: null,
    },
  ];
  return input;
}

async function recordOf(input: AnalyseInput): Promise<AnalyseRecord> {
  const results = await retirementAnalysisService.run(input);
  return {
    id: "janique-type",
    createdAt: "2026-11-04T00:00:00.000Z",
    updatedAt: "2026-11-04T00:00:00.000Z",
    clientId: null,
    status: "calculee",
    input,
    results,
  };
}

describe("sans activité lucrative — bilan PDF", () => {
  it("Janique : pas de fin d'activité, pas de lignes LPP, AVS / 3e / LP conservés", async () => {
    const record = await recordOf(inputJaniqueType());
    const payload = buildReportPayload(record);
    assert.equal(payload.client1.sansActiviteLucrative, true);
    assert.equal(payload.client1.hasLppSaisie, false);
    assert.equal(payload.client1.salaire, 0);
    assert.equal(payload.client1.avsAnnuel, 22_802);
    assert.equal(payload.client1.total3ePilier, 121_443);
    assert.equal(payload.client1.librePassage, 199_486);

    const page = buildReportPages(payload).find((p) =>
      p.html.includes("Bilan de votre prévoyance retraite"),
    );
    assert.ok(page, "page bilan absente");
    const html = page!.html;
    const sec2 = html.indexOf("2. Hypothèse de planification retraite");
    const sec3 = html.indexOf("3. Prévoyance actuelle");
    const sec4 = html.indexOf("4. Synthèse");
    assert.ok(sec2 >= 0 && sec3 > sec2 && sec4 > sec3);
    const hyp = html.slice(sec2, sec3);
    const prev = html.slice(sec3, sec4);

    assert.equal(hyp.includes("Fin de l'activité lucrative"), false);
    assert.ok(hyp.includes("Début de perception AVS"));

    assert.equal(prev.includes("Avoir LPP total"), false);
    assert.equal(prev.includes("% LPP disponible"), false);
    assert.equal(prev.includes("Capital LPP disponible"), false);
    assert.ok(prev.includes("AVS estimée"));
    assert.ok(prev.includes("3e pilier"));
    assert.ok(prev.includes("Libre passage"));
  });

  it("une LPP renseignée fait réapparaître les trois lignes", async () => {
    const input = inputJaniqueType();
    input.client1 = {
      ...input.client1,
      lpp: emptyPerson("Madame").lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 50_000, rente: 3_000 } : row,
      ),
    };
    assert.equal(personHasLppSaisie(input.client1), true);
    const html = renderPrintableReportHtml(
      buildReportPayload(await recordOf(input)),
    );
    const start = html.indexOf("3. Prévoyance actuelle");
    const end = html.indexOf("4. Synthèse", start);
    const prev = html.slice(start, end);
    assert.ok(prev.includes("Avoir LPP total"));
    assert.ok(prev.includes("% LPP disponible"));
    assert.ok(prev.includes("Capital LPP disponible"));
    assert.ok(prev.includes("Libre passage"));
  });

  it("couple : fin d'activité masquée seulement pour l'assuré sans activité", async () => {
    const input = inputJaniqueType();
    input.etatCivil = "Marié(e)";
    input.salaireConjoint = 90_000;
    input.conjoint = {
      ...emptyPerson("Monsieur"),
      prenom: "Paul",
      nom: "SOLER",
      dateNaissance: "1962-01-10",
      sansActiviteLucrative: false,
      ageRetraiteSouhaite: 63,
      avsAnnuel: 24_000,
      lpp: emptyPerson("Monsieur").lpp.map((row) =>
        row.age === 65 ? { ...row, capital: 100_000, rente: 6_000 } : row,
      ),
    };
    const html = renderPrintableReportHtml(
      buildReportPayload(await recordOf(input)),
    );
    const sec2 = html.indexOf("2. Hypothèse de planification retraite");
    const sec3 = html.indexOf("3. Prévoyance actuelle");
    const hyp = html.slice(sec2, sec3);
    assert.ok(hyp.includes("Fin de l'activité lucrative"));
    assert.ok(hyp.includes("—"));
    assert.ok(hyp.includes("Début de perception AVS"));

    const prev = html.slice(sec3, html.indexOf("4. Synthèse", sec3));
    assert.ok(prev.includes("Avoir LPP total"));
    assert.ok(prev.includes("—"));
  });
});

describe("libre passage — année de retrait", () => {
  it("utilise la date de l'onglet Libre passage, pas la fin d'activité", () => {
    assert.equal(
      anneeRetraitLibrePassage(
        { dateRetraitPossible: "2027-03-01", ageDeblocage: null },
        "1964-06-15",
      ),
      2027,
    );
    assert.equal(
      anneeRetraitLibrePassage(
        { dateRetraitPossible: "", ageDeblocage: 63 },
        "1964-06-15",
      ),
      2027,
    );
    // Sans date ni âge LP : pas d'année inventée depuis une fin d'activité.
    assert.equal(
      anneeRetraitLibrePassage(
        { dateRetraitPossible: "", ageDeblocage: null },
        "1964-06-15",
      ),
      null,
    );
  });
});
