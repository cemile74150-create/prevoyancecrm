/**
 * PDF du comparatif d'offres.
 * Même mise en page que pageComparatifDesRentes (en-tête, titre, tableau .compare).
 * L'impôt de la rente reste annuel.
 * Sous le revenu net : total d'impôt fortune sur la durée,
 * impôt fortune si le capital n'est pas affecté. Pas de ligne Gain net.
 * Les revenus ajoutés (AVS, rente LPP, autre) entrent dans l'impôt sur le revenu.
 * Pas de calendrier année par année.
 * Le rapport d'analyse n'est pas modifié et ne reçoit pas ces lignes.
 */
import { readFileSync } from "fs";
import { formatChf } from "../mappers";
import { reportCss } from "./renderPrintableReportHtml";
import {
  impotRevenuPourPdf,
  LIBELLE_IMPOT_RENTE_ANNUEL,
  type OffreRenteType,
} from "../rules/comparatif-rente-offre";
import { compagnieEstPax, NOTE_PAX_DIFFERE } from "../rules/rente-hypotheses";
import type {
  ComparatifOffreColumn,
  ComparatifRenteOffreResult,
} from "../services/ComparatifRenteOffreService";

const GRAY_SOFT = "#757171";

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return formatChf(value);
}

function logoCompact(): string {
  return `<div class="logo logo-fallback">
      <span class="md" style="font-size:11pt">AGENCE MENDES</span>
      <span style="color:${GRAY_SOFT};font-size:7.5pt"> / Assurément différent depuis 1993</span>
    </div>`;
}

export function renderComparatifOffreHtml(
  result: ComparatifRenteOffreResult,
  clientLabel = "",
): string {
  const cols = result.columns || [];
  const labelPct = cols.length <= 1 ? 36 : cols.length === 2 ? 28 : cols.length === 3 ? 22 : 18;
  const rest = ((100 - labelPct) / Math.max(cols.length, 1)).toFixed(2);
  const colgroup = `<colgroup><col style="width:${labelPct}%" />${cols
    .map(() => `<col style="width:${rest}%" />`)
    .join("")}</colgroup>`;

  const colRole = (col: ComparatifOffreColumn) =>
    col.recommander ? "col-offer col-reco" : "col-offer";

  const head = cols
    .map((col) => {
      const typeLine =
        col.type === "viagere"
          ? "Rente viagère"
          : col.dureeAnnees != null
            ? `Rente certaine · ${col.dureeAnnees} ans`
            : "Rente certaine";
      const reco = col.recommander
        ? `<span class="reco-flag">Solution recommandée</span>`
        : "";
      const title = `${esc(col.label)}${compagnieEstPax(col.compagnie || col.label) ? " *" : ""}`;
      return `<th class="${colRole(col)}"><span class="compare-head-title">${title}</span><span class="compare-head-meta">${esc(money(col.capitalPlace))}</span><span class="compare-head-type">${esc(typeLine)}</span>${reco}</th>`;
    })
    .join("");

  const row = (label: string, values: string[], trClass = "") =>
    `<tr${trClass ? ` class="${trClass}"` : ""}><td class="lab">${label}</td>${values
      .map((value, index) => `<td class="num ${colRole(cols[index])}">${value}</td>`)
      .join("")}</tr>`;
  const sec = (label: string) =>
    `<tr class="sec-row"><td colspan="${cols.length + 1}">${label}</td></tr>`;

  const fortuneDurations = [
    ...new Set(
      cols.map((col) => col.dureeFortune).filter((value): value is number => value != null),
    ),
  ];
  const fortuneLabel =
    fortuneDurations.length === 1
      ? `Total impôt fortune sur ${fortuneDurations[0]} ans`
      : fortuneDurations.length === 0
        ? "Total impôt fortune"
        : "Total impôt fortune sur la durée";

  const hasCertaine = cols.some((col) => col.type === "certaine");
  const hasViagere = cols.some((col) => col.type === "viagere");
  const notes = [
    hasCertaine
      ? "Rente certaine. Revenu fiscal de l'offre = 0 % de la rente garantie + 100 % de la participation aux excédents. La rente garantie est encaissée, elle n'entre pas dans le revenu imposable. AVS, rente LPP ou autre revenu seulement s'ils sont ajoutés."
      : "",
    hasViagere
      ? "Rente viagère. Revenu fiscal de l'offre = 4 % de la rente garantie + 70 % de la participation aux excédents. AVS, rente LPP ou autre revenu seulement s'ils sont ajoutés. L'impôt reste annuel : aucune durée n'est inventée."
      : "",
  ].filter(Boolean);

  const who = clientLabel.trim()
    ? `<p class="note">${esc(clientLabel.trim())}</p>`
    : "";

  const inner = `
  <div class="brand-row" style="margin-bottom:8px">
    ${logoCompact()}
    <div class="contacts" style="font-size:8pt">info@agencemendes.ch &nbsp; +41 22 339 30 10</div>
  </div>
  <div class="page-title">COMPARATIF DES RENTES</div>
  ${who}
  <div class="keep-with-note">
  <table class="data compare">
    ${colgroup}
    <tr><th class="lab"></th>${head}</tr>
    ${sec("Répartition du capital à la retraite")}
    ${row("Capital affecté à la rente", cols.map((col) => esc(money(col.capitalPlace))))}
    ${sec("Caractéristiques")}
    ${row("Type", cols.map((col) => esc(col.type === "viagere" ? "Rente viagère" : "Rente certaine")))}
    ${row(
      "Durée",
      cols.map((col) =>
        esc(col.type === "viagere" ? "À vie" : col.dureeAnnees != null ? `${col.dureeAnnees} ans` : "—"),
      ),
    )}
    ${sec("Prestations brutes")}
    ${row("Rente certaine / viagère", cols.map((col) => esc(money(col.renteGarantie))))}
    ${row("Participation aux excédents", cols.map((col) => esc(money(col.participationExcedents))))}
    ${sec("Fiscalité")}
    ${row("Part imposable", cols.map((col) => esc(money(col.partImposable))))}
    ${(result.revenusAjoutes || [])
      .map((revenu) =>
        row(revenu.libelle, cols.map(() => esc(money(revenu.montant)))),
      )
      .join("")}
    ${row(
      LIBELLE_IMPOT_RENTE_ANNUEL,
      cols.map((col) => {
        const line = impotRevenuPourPdf(col.type as OffreRenteType, col.impotRevenu, col.dureeAnnees);
        if (line.montant == null) return "—";
        return `<span class="tax">${esc(money(line.montant))}</span>`;
      }),
    )}
    ${sec("Revenus nets")}
    ${row(
      "Revenu net",
      cols.map((col) => esc(money(col.revenuNet))),
      "row-net",
    )}
    ${row(
      fortuneLabel,
      cols.map((col) => (col.totalImpotFortune == null ? "—" : esc(money(col.totalImpotFortune)))),
      "row-net",
    )}
    ${row(
      "Impôt fortune si capital non affecté",
      cols.map((col) =>
        col.impotFortuneSiNonAffecte == null ? "—" : esc(money(col.impotFortuneSiNonAffecte)),
      ),
    )}
  </table>
  ${notes.map((note) => `<p class="revenu-fiscal-note">${esc(note)}</p>`).join("")}
  ${cols.some((col) => compagnieEstPax(col.compagnie || col.label)) ? `<p class="note">${esc(NOTE_PAX_DIFFERE)}</p>` : ""}
  <p class="fiscal-note">* L'impôt de la rente est annuel : il n'est pas multiplié par la durée. Les revenus ajoutés (AVS, rente LPP, autre) entrent dans cet impôt lorsqu'ils sont saisis. Le total d'impôt sur la fortune est la somme des impôts sur le capital qui diminue chaque année de la rente garantie. La dernière ligne est l'impôt sur ce même capital s'il n'est pas affecté à la rente (fortune constante × durée). Sans durée, les deux impôts sur la fortune restent vides.</p>
  </div>`;

  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>COMPARATIF DES RENTES</title>
<style>${reportCss("portrait")}</style>
</head>
<body>
<div class="sheet sheet-portrait">${inner}</div>
</body>
</html>`;
}

export function analyseReportHasFortuneLine(): boolean {
  const source = readFileSync(new URL("./renderPrintableReportHtml.ts", import.meta.url), "utf8");
  return source.includes("Total impôt fortune");
}

/** Ces libellés appartiennent au comparatif d'offres, pas au rapport d'analyse. */
export function analyseReportHasOffreResultatLines(): boolean {
  const source = readFileSync(new URL("./renderPrintableReportHtml.ts", import.meta.url), "utf8");
  return (
    source.includes("Impôt fortune si capital non affecté") ||
    source.includes("Gain net") ||
    source.includes(LIBELLE_IMPOT_RENTE_ANNUEL)
  );
}
