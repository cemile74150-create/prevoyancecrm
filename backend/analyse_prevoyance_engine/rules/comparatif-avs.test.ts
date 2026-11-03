import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  AVS21_TAUX_REDUCTION_TRANSITOIRE,
  AVS_HORIZON_ANS,
  LABEL_EQUILIBRE_NON_ATTEINT,
  buildComparatifAvs,
  comparatifAvsDepuisAnalyse,
  cumulAu,
  formatAgeUneDecimale,
  renderComparatifAvsBlockHtml,
  type PersonneAvsSaisie,
} from "./comparatif-avs.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { buildReportPages } from "../pdf/renderPrintableReportHtml.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseRecord,
  type PersonComputed,
} from "../types.ts";

const NAISSANCE = "1970-03-15";

function personne(
  prenom: string,
  civilite: "Monsieur" | "Madame",
  mensuel: number,
  extra: Partial<PersonneAvsSaisie> = {},
): PersonneAvsSaisie {
  return {
    prenom,
    nom: "Exemple",
    civilite,
    dateNaissance: NAISSANCE,
    avsMensuel: mensuel,
    ...extra,
  };
}

describe("comparatif AVS", () => {
  it("A couple 1890/1890 synchro 65", () => {
    const model = buildComparatifAvs({
      couple: true,
      personnes: [
        personne("Paul", "Monsieur", 1890),
        personne("Marie", "Madame", 1890),
      ],
    });
    assert.equal(model.titre, "Synthèse pour le couple");
    assert.equal(model.lignes[0].annuelAffiche, 49_140);
    assert.equal(model.lignes[1].annuelAffiche, 45_798);
    assert.equal(model.lignes[2].annuelAffiche, 42_457);
    assert.equal(model.lignes[0].equilibreLabel, "—");
    assert.equal(model.lignes[1].equilibreLabel, "78,7 ans");
    assert.equal(model.lignes[2].equilibreLabel, "77,7 ans");
    assert.equal(Math.round((model.lignes[1].ageEquilibre ?? 0) * 10) / 10, 78.7);
    assert.equal(Math.round((model.lignes[2].ageEquilibre ?? 0) * 10) / 10, 77.7);
    assert.equal(model.lignes[1].mensuelsAffiches[0], 1_761);
    assert.ok(Math.abs((model.lignes[1].mensuelsExacts[0] ?? 0) - 1761.48) < 1e-6);
    assert.ok(Math.abs((model.lignes[1].annuelExact ?? 0) - 45_798.48) < 1e-4);
    assert.ok(Math.abs((model.lignes[2].annuelExact ?? 0) - 42_456.96) < 1e-4);
    const html = renderComparatifAvsBlockHtml(model);
    assert.match(html, /Rente Paul/);
    assert.match(html, /Rente Marie/);
    assert.equal(html.includes("Rente Madame"), false);
    assert.equal(html.includes("Rente Monsieur"), false);
    assert.match(html, /Âge d'équilibre — 1 an d'anticipation : 78,7 ans/);
    assert.match(html, /Âge d'équilibre — 2 ans d'anticipation : 77,7 ans/);
    assert.equal(html.includes("L'âge d'équilibre est le moment"), false);
    assert.equal(html.includes("13e rente"), false);
    assert.equal(model.xMax >= 78.7, true);
    assert.equal(model.xMax <= AVS_HORIZON_ANS, true);
  });

  it("B célibataire 1890, sans deuxième assuré", () => {
    const model = comparatifAvsDepuisAnalyse({
      etatCivil: "Personne vivant seule",
      client1: personne("Paul", "Monsieur", 1890, { nom: "Martin" }),
      conjoint: personne("Fantome", "Madame", 1890),
    });
    assert.equal(model.couple, false);
    assert.equal(model.personnes.length, 1);
    assert.equal(model.titre, "Synthèse AVS — Paul MARTIN");
    assert.equal(model.titreGraphique, "Évolution du cumul des rentes AVS — Paul MARTIN");
    assert.equal(model.lignes[0].annuelAffiche, 24_570);
    assert.equal(model.lignes[1].annuelAffiche, 22_899);
    assert.equal(model.lignes[2].annuelAffiche, 21_228);
    assert.equal(model.lignes[1].equilibreLabel, "78,7 ans");
    assert.equal(model.lignes[2].equilibreLabel, "77,7 ans");
    assert.ok(Math.abs((model.lignes[1].annuelExact ?? 0) - 22_899.24) < 1e-4);
    assert.ok(Math.abs((model.lignes[2].annuelExact ?? 0) - 21_228.48) < 1e-4);
    const html = renderComparatifAvsBlockHtml(model);
    assert.equal(html.includes("Fantome"), false);
    assert.equal(html.includes("Rente Marie"), false);
    assert.match(html, /data-personnes="1"/);
    assert.match(html, /Rente mensuelle/);
    assert.equal(html.includes("Total annuel"), false);
    assert.equal((html.match(/<path /g) || []).length, 3);
  });

  it("C 2000 et 1500 : somme exacte, sans arrondi avant l'annuel", () => {
    const model = buildComparatifAvs({
      couple: true,
      personnes: [
        personne("Paul", "Monsieur", 2000),
        personne("Marie", "Madame", 1500),
      ],
    });
    assert.equal(model.lignes[0].annuelExact, 45_500);
    const exactUnAn = ((2000 + 1500) * 932 * 13) / 1000;
    assert.ok(Math.abs((model.lignes[1].annuelExact ?? 0) - exactUnAn) < 1e-6);
    assert.equal(model.lignes[1].annuelAffiche, Math.round(exactUnAn));
    assert.equal(model.lignes[1].mensuelsExacts[0], (2000 * 932) / 1000);
    assert.equal(model.lignes[1].mensuelsExacts[1], (1500 * 932) / 1000);

    const sensible = buildComparatifAvs({
      couple: true,
      personnes: [
        personne("Paul", "Monsieur", 1890),
        personne("Marie", "Madame", 1000),
      ],
    });
    const exact = ((1890 + 1000) * 932 * 13) / 1000;
    assert.ok(Math.abs((sensible.lignes[1].annuelExact ?? 0) - exact) < 1e-6);
    assert.equal(sensible.lignes[1].annuelAffiche, Math.round(exact));
    const arrondiTropTot =
      Math.round(1890 * 0.932) * 13 + Math.round(1000 * 0.932) * 13;
    assert.notEqual(sensible.lignes[1].annuelAffiche, arrondiTropTot);
  });

  it("D départs décalés : pas d'addition avant la date réelle", () => {
    const model = buildComparatifAvs({
      couple: true,
      personnes: [
        personne("Paul", "Monsieur", 1890, { dateNaissance: "1970-01-15" }),
        personne("Marie", "Madame", 1890, { dateNaissance: "1972-06-15" }),
      ],
    });
    const seul = (29 * 1890 * 13) / 12;
    const juin = cumulAu(model, 0, "2037-06");
    const juillet = cumulAu(model, 0, "2037-07");
    assert.ok(juin != null && juillet != null);
    assert.ok(Math.abs(juin - seul) < 0.02);
    assert.ok(Math.abs(juillet - (seul + (2 * 1890 * 13) / 12)) < 0.02);
    assert.equal(cumulAu(model, 0, "2035-01"), 0);
  });

  it("E génération transitoire, intersection absente, rente vide, pas de double 13e", () => {
    const femme = buildComparatifAvs({
      couple: false,
      personnes: [
        personne("Claire", "Madame", 2000, { dateNaissance: "1961-05-15" }),
      ],
    });
    assert.equal(femme.personnes[0].ageReference, 64.25);
    assert.notEqual(femme.personnes[0].ageReference, 65);
    assert.match(femme.lignes[0].libelle, /64 ans et 3 mois/);
    const ordinaire = (2000 * 932) / 1000;
    const retenu = femme.lignes[1].mensuelsExacts[0] ?? 0;
    assert.ok(Math.abs(retenu - ordinaire) > 1);
    assert.equal(femme.lignes[1].taux[0], AVS21_TAUX_REDUCTION_TRANSITOIRE[1].eleve);
    assert.equal(femme.lignes[1].taux[0], 0.035);
    assert.match(femme.notesComplement.join(" "), /6,8 %/);
    assert.match(femme.notesComplement.join(" "), /n'est pas de 6,8 %/);
    assert.equal(
      renderComparatifAvsBlockHtml(femme).includes("n'est pas de 6,8 %"),
      false,
    );

    const sansRattrapage = buildComparatifAvs({
      couple: false,
      personnes: [
        personne("Claire", "Madame", 2000, {
          dateNaissance: "1961-05-15",
          revenuAnnuelMoyen: 50_000,
        }),
      ],
    });
    assert.equal(sansRattrapage.lignes[1].taux[0], 0);
    assert.equal(sansRattrapage.lignes[1].equilibreLabel, LABEL_EQUILIBRE_NON_ATTEINT);
    assert.match(sansRattrapage.lignes[1].equilibreLabel, /avant 110 ans/);
    assert.equal(sansRattrapage.lignes[1].ageEquilibre, null);

    const vide = buildComparatifAvs({
      couple: false,
      personnes: [
        {
          prenom: "Ada",
          civilite: "Madame",
          dateNaissance: "",
          avsMensuel: null,
        },
      ],
    });
    assert.equal(vide.lignes[1].equilibreLabel, LABEL_EQUILIBRE_NON_ATTEINT);
    assert.equal(vide.marques.length, 0);
    assert.doesNotThrow(() => renderComparatifAvsBlockHtml(vide));

    const zero = buildComparatifAvs({
      couple: false,
      personnes: [personne("Paul", "Monsieur", 0)],
    });
    assert.equal(zero.lignes[0].annuelAffiche, 0);
    assert.equal(zero.lignes[1].equilibreLabel, LABEL_EQUILIBRE_NON_ATTEINT);

    const stocke = buildComparatifAvs({
      couple: false,
      personnes: [
        personne("Paul", "Monsieur", 1890, {
          avsAnnuel: 24_570,
          avsRentesAnticipees: [{ age: 64, montantAnnuel: 20_000 }],
        }),
      ],
    });
    assert.equal(stocke.lignes[0].annuelExact, 24_570);
    assert.notEqual(stocke.lignes[0].annuelExact, 24_570 * 13);
    assert.equal(stocke.lignes[1].annuelExact, 20_000);
    assert.notEqual(stocke.lignes[1].annuelExact, 20_000 * 13);
    assert.equal(stocke.lignes[1].sources[0], "saisie");

    const avant2026 = buildComparatifAvs({
      couple: false,
      personnes: [
        personne("Paul", "Monsieur", 1890, { dateNaissance: "1958-01-15" }),
      ],
    });
    const fin2025 = cumulAu(avant2026, 0, "2025-12");
    const fin2026 = cumulAu(avant2026, 0, "2026-12");
    assert.ok(fin2025 != null && fin2026 != null);
    assert.ok(Math.abs(fin2025 - 35 * 1890) < 0.02);
    assert.ok(Math.abs(fin2026 - fin2025 - 1890 * 13) < 0.02);
    assert.ok(Math.abs(fin2026 - fin2025 - 1890 * 26) > 1);
  });

  it("affiche l'âge d'équilibre à la décimale inférieure", () => {
    assert.equal(formatAgeUneDecimale(92.568), "92,5 ans");
    assert.equal(formatAgeUneDecimale(88.118), "88,1 ans");
    assert.equal(formatAgeUneDecimale(78.705), "78,7 ans");
    assert.equal(formatAgeUneDecimale(77.705), "77,7 ans");
  });

  it("équilibre après 90 ans : 30 368, 29 305 et 27 950", () => {
    const mensuel = 30_368 / 13;
    const model = buildComparatifAvs({
      couple: false,
      personnes: [
        personne("Alex", "Monsieur", mensuel, {
          nom: "",
          avsRentesAnticipees: [
            { age: 64, montantAnnuel: 29_305 },
            { age: 63, montantAnnuel: 27_950 },
          ],
        }),
      ],
    });
    assert.equal(model.lignes[0].annuelExact, 30_368);
    assert.equal(model.lignes[1].annuelExact, 29_305);
    assert.equal(model.lignes[2].annuelExact, 27_950);
    const ref = model.lignes[0].annuelExact ?? 0;
    const unAn = model.lignes[1].annuelExact ?? 0;
    const deuxAns = model.lignes[2].annuelExact ?? 0;
    const ageUnAn = 65 + unAn / (ref - unAn);
    const ageDeuxAns = 65 + (deuxAns * 2) / (ref - deuxAns);
    assert.ok(ageUnAn > 92.5 && ageUnAn < 92.6);
    assert.equal(Math.floor(ageUnAn * 10 + 1e-8) / 10, 92.5);
    assert.equal(Math.floor(ageDeuxAns * 10 + 1e-8) / 10, 88.1);
    assert.equal(model.lignes[1].equilibreLabel, "92,5 ans");
    assert.equal(model.lignes[2].equilibreLabel, "88,1 ans");
    assert.equal(model.xMax >= 92.5, true);
    assert.equal(model.xMax <= AVS_HORIZON_ANS, true);
    const html = renderComparatifAvsBlockHtml(model);
    assert.match(html, /Âge d'équilibre — 1 an d'anticipation : 92,5 ans/);
    assert.match(html, /Âge d'équilibre — 2 ans d'anticipation : 88,1 ans/);
    assert.equal(html.includes("92,6 ans"), false);
    assert.equal(html.includes("L'âge d'équilibre est le moment"), false);
    assert.equal(html.includes("13e rente"), false);
    assert.equal((html.match(/<path /g) || []).length, 3);
  });

  it("le PDF de planification n'inclut pas le comparatif AVS", () => {
    const input = emptyAnalyseInput();
    input.client1 = {
      ...emptyPerson("Monsieur"),
      prenom: "Paul",
      nom: "Martin",
      dateNaissance: NAISSANCE,
      avsMensuel: 1890,
    };
    input.renteHypotheses = [
      {
        id: "offre",
        type: "certaine",
        compagnie: "Vaudoise",
        capitalPlace: 1_000,
        dureeAnnees: 10,
        renteGarantieAnnuelle: 100,
        participationExcedentsAnnuelle: 0,
      },
    ];
    const client1: PersonComputed = {
      ageLegal: 65,
      ageLegalLabel: "65 ans",
      dateDepart: "2035-04-01",
      avsAnnuel: 24_570,
      capitalLpp65: 0,
      renteLpp65: 0,
      lppPctDeblocable: 100,
      capitalLppRetire65: 0,
      renteLppResiduelle65: 0,
      renteTotale65: 24_570,
      total3ePilier: 0,
    };
    const record = {
      id: "avs-pdf",
      createdAt: "2026-10-29T00:00:00.000Z",
      updatedAt: "2026-10-29T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results: {
        client1,
        conjoint: null,
        incomeScenarios: [],
        capitalScenarios: [],
        lacune: {
          salaireAvant: 0,
          revenuApres: 24_570,
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
    const offresDe = (pages: { html: string }[]) =>
      pages.findIndex((page) =>
        page.html.includes('<div class="page-title">COMPARATIF DES RENTES</div>'),
      );

    for (const absent of [false, undefined] as const) {
      if (absent === undefined) delete input.afficherTableauAnticipationAvs;
      else input.afficherTableauAnticipationAvs = false;
      const payload = buildReportPayload(record);
      const pages = buildReportPages(payload);
      assert.equal(pages.length, payload.meta.pageCount);
      assert.equal(payload.comparatifAvs, null);
      assert.equal(
        pages.some((page) => page.html.includes("Comparatif des anticipations AVS")),
        false,
      );
      assert.equal(offresDe(pages), pages.length - 1);
    }

    input.afficherTableauAnticipationAvs = true;
    const payload = buildReportPayload(record);
    const pages = buildReportPages(payload);
    assert.equal(pages.length, payload.meta.pageCount);
    assert.equal(payload.comparatifAvs, null);
    assert.equal(
      pages.some((page) => page.html.includes("Comparatif des anticipations AVS")),
      false,
    );
    assert.equal(offresDe(pages), pages.length - 1);
  });
});
