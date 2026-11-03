import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  annuelAvs,
  analysesAvsDuDossier,
  buildAnalyseAvsPersonne,
  cumulAvs,
  formatAgeEquilibre,
  libelleEquilibre,
  renderAnalyseAvsHtml,
  suggestionAvsDepart,
} from "./analyse-avs-depart.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { buildReportPages } from "../pdf/renderPrintableReportHtml.ts";
import { emptyAnalyseInput, emptyPerson, type AnalyseRecord, type PersonComputed } from "../types.ts";

const EXEMPLE = {
  mensuel63Avant65: 1_578,
  mensuel63Des65: 1_664,
  mensuel64Avant65: 1_700,
  mensuel64Des65: 1_760,
  mensuel65: 1_890,
};

function personne(champs: Record<string, unknown> = {}) {
  return {
    prenom: "Paul",
    nom: "Martin",
    civilite: "Monsieur",
    dateNaissance: "1970-03-15",
    avsDepart: { ...EXEMPLE, ...champs },
  };
}

function recordCouple(monsieur: Record<string, unknown>, madame: Record<string, unknown>) {
  const input = emptyAnalyseInput();
  input.etatCivil = "Marié(e)";
  input.client1 = {
    ...emptyPerson("Monsieur"),
    prenom: "Paul",
    nom: "Martin",
    dateNaissance: "1970-03-15",
    avsDepart: monsieur,
  };
  input.conjoint = {
    ...emptyPerson("Madame"),
    prenom: "Agnès",
    nom: "Martin",
    dateNaissance: "1972-06-01",
    avsDepart: madame,
  };
  const base: PersonComputed = {
    ageLegal: 65,
    ageLegalLabel: "65 ans",
    dateDepart: "2035-04-01",
    avsAnnuel: 0,
    capitalLpp65: 0,
    renteLpp65: 0,
    lppPctDeblocable: 100,
    capitalLppRetire65: 0,
    renteLppResiduelle65: 0,
    renteTotale65: 0,
    total3ePilier: 0,
  };
  return {
    id: "avs-deux",
    createdAt: "2026-11-02T00:00:00.000Z",
    updatedAt: "2026-11-02T00:00:00.000Z",
    clientId: null,
    status: "calculee",
    input,
    results: {
      client1: base,
      conjoint: { ...base, ageLegal: 65 },
      incomeScenarios: [],
      capitalScenarios: [],
      lacune: {
        salaireAvant: 0,
        revenuApres: 0,
        lacune: 0,
        manquePour80: 0,
        tauxRemplacementReel: 0,
      },
      taxLocation: null,
      timeline: { years: [], events: [], byYear: {} },
      withdrawalPlanning: null,
      resumeCapitalTax: null,
    },
  } as unknown as AnalyseRecord;
}

describe("analyse AVS par âge de départ", () => {
  it("un assuré seul : cinq montants, annuel × 13, sans pourcentage", () => {
    const model = buildAnalyseAvsPersonne(personne());
    const [s63, s64, s65] = model.scenarios;
    assert.equal(s63.annuelAvant, annuelAvs(1_578));
    assert.equal(s63.annuelAvant, 20_514);
    assert.equal(s63.annuelDes65, 21_632);
    assert.equal(s63.recuAvant65, 41_028);
    assert.equal(s63.ecartMensuel, 312);
    assert.equal(s64.annuelAvant, annuelAvs(1_700));
    assert.equal(s64.recuAvant65, annuelAvs(1_700));
    assert.equal(s65.recuAvant65, 0);
    assert.equal(s65.annuelDes65, 24_570);
    assert.equal(model.courbes.length, 3);
    const html = renderAnalyseAvsHtml(model);
    assert.equal(html.includes("6,8"), false);
    assert.equal(html.includes("16,5"), false);
    assert.equal(html.includes("couple"), false);
    assert.match(html, /Analyse AVS – Paul Martin/);
    assert.match(html, /RENTE AVS – COMPARAISON DES ÂGES DE DÉPART/);
    assert.match(html, /ANALYSE DE L'ANTICIPATION AVS/);
    assert.match(html, /ÉVOLUTION DU CUMUL DES RENTES AVS/);
  });

  it("1 578 / 1 664 / 1 890 donne un équilibre à 79,0 ans", () => {
    const model = buildAnalyseAvsPersonne(personne());
    const s63 = model.scenarios[0];
    assert.equal(s63.equilibre.kind, "age");
    assert.equal(formatAgeEquilibre(s63.equilibre.age ?? 0), "79,0 ans");
    assert.equal(libelleEquilibre(s63.equilibre), "79,0 ans");
    const cumulAnticipe = cumulAvs(s63, s63.equilibre.age ?? 0);
    const cumulReference = cumulAvs(model.scenarios[2], s63.equilibre.age ?? 0);
    assert.ok(cumulAnticipe != null && cumulReference != null);
    assert.ok(Math.abs((cumulAnticipe ?? 0) - (cumulReference ?? 0)) < 0.05);
    const html = renderAnalyseAvsHtml(model);
    assert.match(html, /79,0 ans/);
    assert.match(html, /Âge d'équilibre – Départ à 63 ans : 79 ans/);
    assert.equal(html.includes("Départ à 63 ans : 79 ans"), true);
  });

  it("à 64 ans la rente change à 65 ans et n'est pas prolongée", () => {
    const model = buildAnalyseAvsPersonne(personne());
    const s64 = model.scenarios[1];
    assert.equal(cumulAvs(s64, 64), 0);
    assert.equal(cumulAvs(s64, 65), annuelAvs(1_700));
    assert.equal(cumulAvs(s64, 66), annuelAvs(1_700) + annuelAvs(1_760));
    assert.notEqual(annuelAvs(1_700), annuelAvs(1_760));
  });

  it("à 63 ans la rente d'anticipation s'arrête à 65 ans", () => {
    const model = buildAnalyseAvsPersonne(personne());
    const s63 = model.scenarios[0];
    assert.equal(cumulAvs(s63, 65), 41_028);
    assert.equal(cumulAvs(s63, 66), 41_028 + annuelAvs(1_664));
    assert.notEqual(annuelAvs(1_578), annuelAvs(1_664));
  });

  it("un scénario incomplet n'a ni courbe ni âge inventé", () => {
    const model = buildAnalyseAvsPersonne(
      personne({ mensuel63Des65: null, mensuel64Avant65: null, mensuel64Des65: null }),
    );
    assert.equal(model.scenarios[0].courbe, false);
    assert.equal(model.scenarios[0].equilibre.kind, "manquant");
    assert.equal(model.scenarios[1].courbe, false);
    assert.equal(model.courbes.some((courbe) => courbe.depart === 63), false);
    const html = renderAnalyseAvsHtml(model);
    assert.match(html, /À compléter/);
    assert.match(html, /Calcul impossible – données manquantes/);
    assert.equal(html.includes("0 ans"), false);
  });

  it("l'équilibre au-delà de 90 ans est signalé et n'est pas marqué sur le graphique", () => {
    const model = buildAnalyseAvsPersonne(
      personne({ mensuel63Des65: 1_889, mensuel65: 1_890 }),
    );
    const equilibre = model.scenarios[0].equilibre;
    assert.equal(equilibre.kind, "age");
    assert.equal(equilibre.horsPeriode, true);
    assert.match(libelleEquilibre(equilibre), /hors de la période représentée/);
    assert.equal(model.marques.some((marque) => marque.depart === 63), false);
  });

  it("si la référence ne rattrape jamais, aucun âge n'est inventé", () => {
    const model = buildAnalyseAvsPersonne(personne({ mensuel63Des65: 2_000, mensuel65: 1_890 }));
    assert.equal(model.scenarios[0].equilibre.kind, "non-atteint");
    assert.equal(libelleEquilibre(model.scenarios[0].equilibre), "Non atteint");
    assert.equal(model.scenarios[0].equilibre.age, undefined);
  });

  it("deux assurés restent indépendants, y compris dans le PDF", () => {
    const monsieur = buildAnalyseAvsPersonne({
      prenom: "Paul",
      nom: "Martin",
      civilite: "Monsieur",
      dateNaissance: "1970-03-15",
      avsDepart: EXEMPLE,
    });
    const madame = buildAnalyseAvsPersonne({
      prenom: "Agnès",
      nom: "Martin",
      civilite: "Madame",
      dateNaissance: "1972-06-01",
      avsDepart: {
        mensuel63Avant65: 900,
        mensuel63Des65: 950,
        mensuel64Avant65: 980,
        mensuel64Des65: 1_020,
        mensuel65: 1_100,
      },
    });
    assert.notEqual(monsieur.scenarios[0].recuAvant65, madame.scenarios[0].recuAvant65);
    const htmlMonsieur = renderAnalyseAvsHtml(monsieur);
    const htmlMadame = renderAnalyseAvsHtml(madame);
    assert.equal(htmlMonsieur.includes("Agnès"), false);
    assert.equal(htmlMadame.includes("Paul"), false);
    assert.equal(htmlMonsieur.includes("couple"), false);
    assert.equal(htmlMadame.includes("couple"), false);

    const pages = buildReportPages(
      buildReportPayload(
        recordCouple(EXEMPLE, {
          mensuel63Avant65: 900,
          mensuel63Des65: 950,
          mensuel64Avant65: 980,
          mensuel64Des65: 1_020,
          mensuel65: 1_100,
        }),
      ),
    );
    const avs = pages.filter((page) => page.html.includes("Analyse AVS"));
    assert.equal(avs.length, 2);
    assert.match(avs[0].html, /Paul Martin/);
    assert.equal(avs[0].html.includes("Agnès"), false);
    assert.match(avs[1].html, /Agnès Martin/);
    assert.equal(avs[1].html.includes("Paul"), false);
    assert.equal(avs[0].html.includes("79,0 ans"), true);
    assert.equal(avs[1].html.includes("79,0 ans"), false);
  });

  it("une personne seule ne produit qu'une page AVS", () => {
    const input = emptyAnalyseInput();
    input.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "Paul",
      nom: "Martin",
      dateNaissance: "1970-03-15",
      avsDepart: EXEMPLE,
    };
    const record = recordCouple(EXEMPLE, EXEMPLE);
    record.input = input;
    record.results = { ...record.results, conjoint: null };
    const pages = buildReportPages(buildReportPayload(record as AnalyseRecord));
    const avs = pages.filter((page) => page.html.includes("Analyse AVS"));
    assert.equal(avs.length, 1);
    assert.match(avs[0].html, /Paul Martin/);
  });

  it("le repli ne remplace pas une saisie et n'invente pas la rente dès 65 ans", () => {
    const suggestion = suggestionAvsDepart({
      avsMensuel: 1_890,
      avsRentesAnticipees: [{ age: 63, montantAnnuel: 20_514 }],
    });
    assert.equal(suggestion.mensuel65, 1_890);
    assert.equal(suggestion.mensuel63Avant65, 1_578);
    assert.equal(suggestion.mensuel63Des65, undefined);

    const vide = buildAnalyseAvsPersonne({
      avsMensuel: 1_890,
      avsDepart: { mensuel65: null },
    });
    assert.equal(vide.scenarios[2].mensuelDes65, null);

    const garde = buildAnalyseAvsPersonne({
      avsMensuel: 1_890,
      avsDepart: { mensuel65: 1_500 },
    });
    assert.equal(garde.scenarios[2].mensuelDes65, 1_500);
  });

  it("une femme dont l'âge légal n'est pas 65 ans voit un avertissement", () => {
    const model = buildAnalyseAvsPersonne({
      prenom: "Claire",
      nom: "Dupont",
      civilite: "Madame",
      dateNaissance: "1960-04-12",
      avsDepart: EXEMPLE,
    });
    assert.equal(model.ageLegal, 64);
    assert.match(model.avertissementAgeLegal || "", /64 ans/);
    assert.match(renderAnalyseAvsHtml(model), /n'est pas présenté comme son âge légal/);
  });

  it("rente habituelle seule : le PDF n'a pas le comparatif des âges de départ", () => {
    const record = recordCouple({}, {});
    record.input.client1.avsMensuel = 1_675;
    record.input.client1.avsAnnuel = 21_775;
    record.input.client1.avsDepart = { mensuel65: 1_675 };
    record.input.client1.anticipationAvsAnnees = 0;
    record.input.conjoint!.avsMensuel = 1_800;
    record.input.conjoint!.avsDepart = undefined;
    record.results!.client1.avsAnnuel = 21_775;
    const html = buildReportPages(buildReportPayload(record as AnalyseRecord))
      .map((page) => page.html)
      .join("\n");
    assert.equal(html.includes("RENTE AVS – COMPARAISON DES ÂGES DE DÉPART"), false);
    assert.equal(html.includes("ANALYSE DE L'ANTICIPATION AVS"), false);
    assert.equal(html.includes("ÉVOLUTION DU CUMUL DES RENTES AVS"), false);
    assert.equal(html.includes("Analyse AVS"), false);

    record.input.client1.avsDepart = { mensuel63Avant65: 1_400 };
    const avec = buildReportPages(buildReportPayload(record as AnalyseRecord));
    const avs = avec.filter((page) => page.html.includes("Analyse AVS"));
    assert.equal(avs.length, 1);
    assert.match(avs[0].html, /RENTE AVS – COMPARAISON DES ÂGES DE DÉPART/);
    assert.match(avs[0].html, /Paul Martin/);
    assert.equal(avs[0].html.includes("Agnès"), false);
  });
});
