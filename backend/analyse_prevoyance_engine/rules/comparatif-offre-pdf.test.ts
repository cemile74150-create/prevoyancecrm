import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatChf } from "../mappers.ts";
import { renderComparatifOffreHtml, analyseReportHasFortuneLine } from "../pdf/renderComparatifOffreHtml.ts";
import {
  fortunesDecroissantes,
  impotRevenuPourPdf,
  totalImpotFortune,
} from "./comparatif-rente-offre.ts";
import type { ComparatifOffreColumn } from "../services/ComparatifRenteOffreService.ts";

const IMPOT_ANNUEL = 812;

function certaine20(): ComparatifOffreColumn {
  const fortunes = fortunesDecroissantes(130_000, 6001, 20);
  const impots = fortunes.map((fortune) => Math.round(fortune * 0.01));
  return {
    id: "vaudoise",
    label: "Vaudoise",
    compagnie: "Vaudoise",
    type: "certaine",
    typeLabel: "Rente certaine",
    capitalPlace: 130_000,
    dureeAnnees: 20,
    renteGarantie: 6001,
    participationExcedents: 0,
    revenuEncaisse: 6001,
    partImposable: 1219.4,
    impotRevenu: IMPOT_ANNUEL,
    revenuNet: 6001 - IMPOT_ANNUEL,
    recommander: true,
    fortuneAnnees: fortunes.map((fortune, index) => ({
      annee: index + 1,
      fortune,
      impotFortune: impots[index],
    })),
    totalImpotFortune: totalImpotFortune(impots),
    dureeFortune: 20,
  };
}

describe("PDF comparatif d'offres — même mise en page, une ligne fortune", () => {
  it("130000 / 6001 / 20 ans : total ICC, total fortune, pas de calendrier", () => {
    const line = impotRevenuPourPdf("certaine", IMPOT_ANNUEL, 20);
    assert.equal(line.libelle, "Total ICC / IFD sur 20 ans");
    assert.equal(line.montant, 16_240);

    const html = renderComparatifOffreHtml(
      { columns: [certaine20()], anneesAffichees: 20, avertissement: null },
      "Exemple",
    );
    assert.match(html, /class="page-title">COMPARATIF DES RENTES</);
    assert.match(html, /class="data compare"/);
    assert.match(html, /Répartition du capital à la retraite/);
    assert.match(html, /Caractéristiques/);
    assert.match(html, /Prestations brutes/);
    assert.match(html, /Fiscalité/);
    assert.match(html, /Revenus nets/);
    assert.match(html, /Total ICC \/ IFD sur 20 ans/);
    assert.ok(html.includes(formatChf(16_240)));
    assert.match(html, /Total impôt fortune sur 20 ans/);
    assert.equal(html.includes("Année 1"), false);
    assert.equal(html.includes("Année 20"), false);
    assert.equal(html.includes(">AVS<"), false);
    assert.equal(analyseReportHasFortuneLine(), false);
  });

  it("rente viagère : impôt annuel, sans total sur une durée inventée", () => {
    const html = renderComparatifOffreHtml({
      columns: [
        {
          ...certaine20(),
          id: "helvetia",
          label: "Helvetia",
          type: "viagere",
          typeLabel: "Rente viagère",
          dureeAnnees: null,
          fortuneAnnees: null,
          totalImpotFortune: null,
          dureeFortune: null,
        },
      ],
      anneesAffichees: 0,
      avertissement: null,
    });
    assert.match(html, /ICC \/ IFD annuel/);
    assert.equal(html.includes("Total ICC / IFD sur"), false);
    assert.equal(html.includes("Année 1"), false);
    assert.match(html, /Total impôt fortune</);
  });
});
