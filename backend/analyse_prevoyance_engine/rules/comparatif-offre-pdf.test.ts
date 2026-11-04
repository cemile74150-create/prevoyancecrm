import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatChf } from "../mappers.ts";
import {
  renderComparatifOffreHtml,
  analyseReportHasFortuneLine,
  analyseReportHasOffreResultatLines,
} from "../pdf/renderComparatifOffreHtml.ts";
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
    gainNet: (6001 - IMPOT_ANNUEL) * 20 - 130_000,
    recommander: true,
    fortuneAnnees: fortunes.map((fortune, index) => ({
      annee: index + 1,
      fortune,
      impotFortune: impots[index],
    })),
    totalImpotFortune: totalImpotFortune(impots),
    impotFortuneSiNonAffecte: Math.round(130_000 * 0.01) * 20,
    dureeFortune: 20,
  };
}

describe("PDF comparatif d'offres — même mise en page, une ligne fortune", () => {
  it("130000 / 6001 / 20 ans : impôt annuel, deux lignes fortune, pas de gain net", () => {
    const column = certaine20();
    const line = impotRevenuPourPdf("certaine", IMPOT_ANNUEL, 20);
    assert.equal(line.libelle, "Impôt de la rente (par an)");
    assert.equal(line.montant, IMPOT_ANNUEL);
    assert.equal(column.gainNet, 5189 * 20 - 130_000);
    assert.equal(column.impotFortuneSiNonAffecte, 26_000);

    const html = renderComparatifOffreHtml(
      { columns: [column], anneesAffichees: 20, avertissement: null },
      "Exemple",
    );
    assert.match(html, /class="page-title">COMPARATIF DES RENTES</);
    assert.match(html, /class="data compare"/);
    assert.match(html, /Répartition du capital à la retraite/);
    assert.match(html, /Caractéristiques/);
    assert.match(html, /Prestations brutes/);
    assert.match(html, /Fiscalité/);
    assert.match(html, /Revenus nets/);
    assert.match(html, /Impôt de la rente \(par an\)/);
    assert.equal(html.includes("Total ICC / IFD sur"), false);
    assert.equal(html.includes("sur 20 ans</span>"), false);
    assert.ok(html.includes(formatChf(IMPOT_ANNUEL)));
    assert.equal(html.includes(formatChf(IMPOT_ANNUEL * 20)), false);
    assert.equal(html.includes("Gain net"), false);
    assert.equal(html.includes("gain net"), false);
    assert.equal(html.includes("row-gain"), false);
    assert.equal(html.includes(formatChf(column.gainNet)), false);
    assert.match(html, /Total impôt fortune sur 20 ans/);
    assert.match(html, /Impôt fortune si capital non affecté/);
    assert.ok(html.includes(formatChf(26_000)));
    const revenu = html.indexOf("Revenu net");
    const fortune = html.indexOf("Total impôt fortune sur 20 ans");
    const constant = html.indexOf("Impôt fortune si capital non affecté");
    assert.ok(revenu >= 0 && revenu < fortune && fortune < constant);
    assert.equal(html.includes("Année 1"), false);
    assert.equal(html.includes("Année 20"), false);
    assert.equal(html.includes(">AVS<"), false);
    assert.equal(analyseReportHasFortuneLine(), false);
    assert.equal(analyseReportHasOffreResultatLines(), false);
    assert.equal(html.includes('class="revenu-fiscal-note"'), false);
    assert.equal(html.includes('class="fiscal-note"'), false);
    assert.equal(
      html.includes("0 % de la rente garantie + 100 % de la participation aux excédents"),
      false,
    );
    assert.equal(html.includes("L'impôt de la rente est annuel"), false);
  });

  it("rente viagère : impôt annuel, gain et impôts fortune vides, sans durée inventée", () => {
    const html = renderComparatifOffreHtml({
      columns: [
        {
          ...certaine20(),
          id: "helvetia",
          label: "Helvetia",
          type: "viagere",
          typeLabel: "Rente viagère",
          dureeAnnees: null,
          gainNet: null,
          fortuneAnnees: null,
          totalImpotFortune: null,
          impotFortuneSiNonAffecte: null,
          dureeFortune: null,
        },
      ],
      anneesAffichees: 0,
      avertissement: null,
    });
    assert.match(html, /Impôt de la rente \(par an\)/);
    assert.equal(html.includes("Total ICC / IFD sur"), false);
    assert.equal(html.includes("sur 20 ans"), false);
    assert.equal(html.includes("Année 1"), false);
    assert.equal(html.includes("Gain net"), false);
    assert.equal(html.includes("gain net"), false);
    assert.match(html, /Impôt fortune si capital non affecté/);
    assert.equal(html.includes(formatChf(26_000)), false);
    assert.equal(html.includes(formatChf((6001 - IMPOT_ANNUEL) * 20 - 130_000)), false);
    assert.match(html, /Total impôt fortune</);
    assert.equal(html.includes('class="revenu-fiscal-note"'), false);
    assert.equal(html.includes('class="fiscal-note"'), false);
    assert.equal(
      html.includes("4 % de la rente garantie + 70 % de la participation aux excédents"),
      false,
    );
  });
});
