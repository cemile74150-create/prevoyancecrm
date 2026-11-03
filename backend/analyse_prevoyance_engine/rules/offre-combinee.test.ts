import assert from "node:assert/strict";
import { after, describe, it } from "node:test";
import { formatChf } from "../mappers.ts";
import {
  buildReportPages,
  renderPrintableReportHtml,
} from "../pdf/renderPrintableReportHtml.ts";
import { buildReportPayload } from "../report/buildReportPayload.ts";
import { renteHypothesisService } from "../services/RenteHypothesisService.ts";
import { retirementAnalysisService } from "../services/RetirementAnalysisService.ts";
import { taxCalculationService } from "../services/TaxCalculationService.ts";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseRecord,
  type RenteHypothesisInput,
} from "../types.ts";
import {
  anneeToutesVerses,
  differeVersementAnnees,
  offresDeHypothese,
  offreVersee,
  periodesVersement,
  revenuBrutPeriode,
  revenuFiscalImposable,
  revenuFiscalPeriode,
  totauxAnneeCommune,
} from "./rente-hypotheses.ts";

const AVS = 27_950;

const hypothese: RenteHypothesisInput = {
  id: "combinee",
  type: "viagere",
  compagnie: "Retraite Populaire",
  capitalPlace: 400_000,
  dureeAnnees: null,
  dureeDiffereAnnees: null,
  renteGarantieAnnuelle: 15_140,
  participationExcedentsAnnuelle: 2_013,
  offres: [
    {
      id: "rp",
      type: "viagere",
      compagnie: "Retraite Populaire",
      capitalPlace: 400_000,
      dureeAnnees: null,
      dureeDiffereAnnees: null,
      renteGarantieAnnuelle: 15_140,
      participationExcedentsAnnuelle: 2_013,
    },
    {
      id: "pax",
      type: "certaine",
      compagnie: "PAX",
      capitalPlace: 599_118,
      dureeAnnees: 20,
      dureeDiffereAnnees: 1,
      renteGarantieAnnuelle: 22_538,
      participationExcedentsAnnuelle: 13_110,
    },
  ],
};

function inputAvec(row: RenteHypothesisInput = hypothese) {
  const input = emptyAnalyseInput();
  input.ageRetraiteSouhaite = 65;
  input.taxLocationId = 170_000_000;
  input.comparerAvecRenteLpp = false;
  input.client1 = {
    ...emptyPerson("Monsieur"),
    prenom: "Exemple",
    nom: "Test",
    dateNaissance: "1961-01-15",
    avsAnnuel: AVS,
    anticipationAvsAnnees: 0,
  };
  input.renteHypotheses = [row];
  return input;
}

describe("offre combinée — une hypothèse", () => {
  const offres = offresDeHypothese(hypothese);

  it("calcule 43 074,70 sans compter AVS deux fois, et affiche 43 075", () => {
    const fiscal = revenuFiscalPeriode({
      renteAvs: AVS,
      renteLppResiduelle: 0,
      offres,
      annee: 2,
    });
    assert.equal(fiscal.toFixed(2), "43074.70");
    assert.equal(Math.round(fiscal), 43_075);
    assert.match(formatChf(fiscal), /43[’'\s\u00a0\u202f]?075/);

    const additionColonnes =
      revenuFiscalImposable({
        type: "viagere",
        renteAvs: AVS,
        renteGarantie: 15_140,
        participationExcedents: 2_013,
      }) +
      revenuFiscalImposable({
        type: "certaine",
        renteAvs: AVS,
        renteGarantie: 22_538,
        participationExcedents: 13_110,
      });
    assert.notEqual(fiscal, additionColonnes);
    assert.equal(additionColonnes, fiscal + AVS);
  });

  it("totalise capital, rentes, participations et prestations de l'année commune", () => {
    const totaux = totauxAnneeCommune(offres);
    assert.equal(totaux.annee, 2);
    assert.equal(totaux.capitalTotal, 999_118);
    assert.equal(totaux.rentesGaranties, 37_678);
    assert.equal(totaux.participations, 15_123);
    assert.equal(totaux.prestationsAnnuelles, 52_801);
    assert.equal(
      revenuBrutPeriode({
        renteAvs: AVS,
        renteLppResiduelle: 0,
        offres,
        annee: 2,
      }),
      AVS + 52_801,
    );
  });

  it("suit les calendriers : année 1 viagère, puis les deux, puis de nouveau la viagère", () => {
    assert.equal(offreVersee(offres[0], 1), true);
    assert.equal(offreVersee(offres[1], 1), false);
    assert.equal(offreVersee(offres[1], 2), true);
    assert.equal(offreVersee(offres[1], 21), true);
    assert.equal(offreVersee(offres[1], 22), false);
    assert.equal(offreVersee(offres[0], 22), true);

    const seule = revenuFiscalPeriode({
      renteAvs: AVS,
      offres,
      annee: 1,
    });
    assert.equal(seule.toFixed(2), "29964.70");
    assert.equal(
      revenuFiscalPeriode({ renteAvs: AVS, offres, annee: 22 }).toFixed(2),
      seule.toFixed(2),
    );

    const periodes = periodesVersement({ renteAvs: AVS, offres });
    assert.equal(periodes[0].anneeDebut, 1);
    assert.equal(periodes[0].anneeFin, 1);
    assert.equal(periodes[1].anneeDebut, 2);
    assert.equal(periodes[1].anneeFin, 21);
    assert.equal(periodes[1].revenuFiscal.toFixed(2), "43074.70");
    assert.equal(periodes[1].revenuBrut, AVS + 52_801);
    assert.equal(periodes[2].anneeDebut, 22);
    assert.equal(periodes[2].anneeFin, null);
    assert.equal(periodes[2].revenuFiscal.toFixed(2), seule.toFixed(2));
  });

  it("fait entrer le différé PAX d'un an même si le champ est vide, sans l'ajouter au champ saisi", () => {
    assert.equal(
      differeVersementAnnees({ compagnie: "PAX", dureeDiffereAnnees: null }),
      1,
    );
    assert.equal(
      differeVersementAnnees({ compagnie: "PAX", dureeDiffereAnnees: 1 }),
      1,
    );
    assert.equal(
      differeVersementAnnees({ compagnie: "Retraite Populaire", dureeDiffereAnnees: null }),
      0,
    );
    const sansChamp = offresDeHypothese({
      ...hypothese,
      offres: [
        hypothese.offres![0],
        { ...hypothese.offres![1], dureeDiffereAnnees: null },
      ],
    });
    assert.equal(anneeToutesVerses(sansChamp), 2);
    assert.equal(offreVersee(sansChamp[1], 1), false);
  });

  it("laisse une hypothèse à une seule offre sur les champs déjà saisis", () => {
    const seule: RenteHypothesisInput = {
      id: "deja",
      type: "certaine",
      compagnie: "Vaudoise",
      capitalPlace: 530_000,
      dureeAnnees: 20,
      renteGarantieAnnuelle: 23_136,
      participationExcedentsAnnuelle: 7_096,
    };
    const lus = offresDeHypothese(seule);
    assert.equal(lus.length, 1);
    assert.equal(lus[0].compagnie, "Vaudoise");
    assert.equal(lus[0].renteGarantie, 23_136);
    assert.equal(seule.offres, undefined);
  });
});

describe("offre combinée — une colonne et un seul impôt", { concurrency: false }, () => {
  const original = taxCalculationService.calculateDetailedTaxes.bind(
    taxCalculationService,
  );
  const originalCapital = taxCalculationService.calculateCapitalTax.bind(
    taxCalculationService,
  );
  let appels: number[] = [];

  taxCalculationService.calculateDetailedTaxes = async (params) => {
    if (params.foyer === "hypothese-rente") appels.push(params.revenue1);
    return {
      foyer: params.foyer ?? "default",
      age: params.age1,
      taxLocationId: params.taxLocationId,
      taxYear: params.taxYear ?? 2025,
      revenu1: params.revenue1,
      revenu2: params.revenue2,
      fortune: params.fortune,
      impotRevenuTotal: 5_000,
      impotFederal: 5_000,
      impotCanton: 0,
      impotCommune: 0,
      impotEglise: 0,
      request: {},
      response: {},
    };
  };
  taxCalculationService.calculateCapitalTax = async (params) => ({
    age: params.ageAtPayment,
    capital: params.capital,
    gender: params.gender,
    relationship: params.relationship,
    taxGroupId: params.taxGroupId,
    taxYear: params.taxYear ?? 2025,
    taxCity: 0,
    taxCanton: 0,
    taxFed: 0,
    taxChurch: 0,
    impotTotal: 0,
    request: {},
    response: {},
  });

  after(() => {
    taxCalculationService.calculateDetailedTaxes = original;
    taxCalculationService.calculateCapitalTax = originalCapital;
  });

  it("appelle ESTV une fois sur 43 074,70 et ne crée pas une deuxième colonne", async () => {
    appels = [];
    const built = await renteHypothesisService.build(inputAvec());
    assert.equal(built?.columns.length, 1);
    const col = built?.columns[0];
    assert.ok(col);
    assert.equal(col.kind, "hypothese");
    assert.equal(col.revenuFiscalImposable.toFixed(2), "43074.70");
    assert.equal(col.capitalPlace, 999_118);
    assert.equal(col.renteGarantie, 37_678);
    assert.equal(col.participationExcedents, 15_123);
    assert.equal(col.renteAvs, AVS);
    assert.equal(col.renteLppResiduelle, 0);
    assert.equal(col.impotEstv, 5_000);
    assert.equal(col.revenuNetApresImpot, AVS + 52_801 - 5_000);
    assert.match(col.label, /Retraite Populaire/);
    assert.match(col.label, /PAX/);
    assert.equal(col.offres?.length, 2);
    assert.equal(appels.length, 1);
    assert.equal(appels[0].toFixed(2), "43074.70");
    assert.notEqual(col.impotEstv, 10_000);
  });

  it("imprime une seule colonne HTML avec les deux compagnies", async () => {
    appels = [];
    const input = inputAvec();
    const results = await retirementAnalysisService.run(input);
    const record: AnalyseRecord = {
      id: "offre-combinee",
      createdAt: "2026-10-29T00:00:00.000Z",
      updatedAt: "2026-10-29T00:00:00.000Z",
      clientId: null,
      status: "calculee",
      input,
      results,
    };
    const payload = buildReportPayload(record);
    const html = renderPrintableReportHtml(payload);
    const pages = buildReportPages(payload);
    const start = html.indexOf("COMPARATIF DES RENTES");
    assert.ok(start >= 0);
    const tableStart = html.indexOf('<table class="data compare">', start);
    const tableEnd = html.indexOf("</table>", tableStart);
    const compare = html.slice(start, tableEnd);
    const headers = [...compare.matchAll(/<th class="col-offer[^"]*">([\s\S]*?)<\/th>/g)];
    assert.equal(headers.length, 1);
    assert.match(headers[0][1], /Retraite Populaire/);
    assert.match(headers[0][1], /PAX/);
    assert.match(headers[0][1], /où les deux rentes sont versées/);
    assert.match(headers[0][1], /Rente viagère/);
    assert.match(headers[0][1], /Rente certaine/);
    assert.match(headers[0][1], /20 ans/);
    const partRow = (compare.split("Part imposable")[1] || "").split("</tr>")[0];
    assert.ok(partRow.includes(formatChf(43_074.7)));
    assert.equal(compare.includes("Gain net"), false);
    assert.equal(html.includes("Caisses LPP"), false);
    const solutions = pages.findIndex((page) =>
      page.html.includes("Comparatif des solutions de rentes"),
    );
    const offres = pages.findIndex((page) =>
      page.html.includes('<div class="page-title">COMPARATIF DES RENTES</div>'),
    );
    assert.ok(offres > solutions);
    assert.equal(offres, pages.length - 1);
    assert.ok(pages[solutions].html.includes("Valeur de rachat 31.12"));
    const hypotheseAppels = appels.filter((montant) => montant.toFixed(2) === "43074.70");
    assert.equal(hypotheseAppels.length, 1);
  });

  it("n'écrit pas Différé : 1 quand seul la note PAX décale le versement", async () => {
    const input = inputAvec({
      ...hypothese,
      offres: [
        hypothese.offres![0],
        { ...hypothese.offres![1], dureeDiffereAnnees: null },
      ],
    });
    const results = await retirementAnalysisService.run(input);
    const html = renderPrintableReportHtml(
      buildReportPayload({
        id: "pax-note",
        createdAt: "2026-10-29T00:00:00.000Z",
        updatedAt: "2026-10-29T00:00:00.000Z",
        clientId: null,
        status: "calculee",
        input,
        results,
      }),
    );
    const start = html.indexOf('<div class="page-title">COMPARATIF DES RENTES</div>');
    assert.ok(start >= 0);
    const tableEnd = html.indexOf("</table>", html.indexOf('<table class="data compare">', start));
    const compare = html.slice(start, tableEnd);
    assert.match(compare, /où les deux rentes sont versées/);
    assert.equal(compare.includes("Différé : 1"), false);
    assert.match(html, /Pour les contrats PAX/);
  });
});
