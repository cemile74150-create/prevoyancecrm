/**
 * PDF du comparatif d'offres.
 * Même mise en page que pageComparatifDesRentes (en-tête, titre, tableau .compare).
 * Différence : une seule ligne « Total impôt fortune sur N ans », sans calendrier.
 * Le rapport d'analyse n'est pas modifié et ne reçoit pas cette ligne.
 */
import { readFileSync } from "fs";
import { formatChf } from "../mappers";
import { reportCss } from "./renderPrintableReportHtml";
import {
  impotRevenuPourPdf,
  LIBELLE_ICC_ANNUEL,
  type OffreRenteType,
} from "../rules/comparatif-rente-offre";
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
      return `<th class="${colRole(col)}"><span class="compare-head-title">${esc(col.label)}</span><span class="compare-head-meta">${esc(money(col.capitalPlace))}</span><span class="compare-head-type">${esc(typeLine)}</span>${reco}</th>`;
    })
    .join("");

  const row = (label: string, values: string[], trClass = "") =>
    `<tr${trClass ? ` class="${trClass}"` : ""}><td class="lab">${label}</td>${values
      .map((value, index) => `<td class="num ${colRole(cols[index])}">${value}</td>`)
      .join("")}</tr>`;
  const sec = (label: string) =>
    `<tr class="sec-row"><td colspan="${cols.length + 1}">${label}</td></tr>`;

  const revenuLabel = revenuRowLabel(cols);
  const revenuUnifie =
    revenuLabel.startsWith("Total ICC") || revenuLabel === LIBELLE_ICC_ANNUEL;

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
      ? "Rente certaine. Revenu fiscal = 70 % de la participation aux excédents. La rente garantie est encaissée, elle n'entre pas dans le revenu imposable. Pas d'AVS ni de LPP."
      : "",
    hasViagere
      ? "Rente viagère. Revenu fiscal = 4 % de la rente garantie + 100 % de la participation aux excédents. Pas d'AVS ni de LPP. L'impôt reste annuel : aucune durée n'est inventée."
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
    ${row(
      revenuLabel,
      cols.map((col) => {
        const line = impotRevenuPourPdf(col.type as OffreRenteType, col.impotRevenu, col.dureeAnnees);
        if (line.montant == null) return "—";
        const hint = revenuUnifie
          ? ""
          : line.mode === "annuel"
            ? `<br/><span>annuel</span>`
            : line.annees
              ? `<br/><span>sur ${line.annees} ans</span>`
              : "";
        return `<span class="tax">${esc(money(line.montant))}</span>${hint}`;
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
  </table>
  ${notes.map((note) => `<p class="revenu-fiscal-note">${esc(note)}</p>`).join("")}
  <p class="fiscal-note">* L'ICC/IFD d'une rente certaine est le total payé sur la durée (impôt annuel × nombre d'années). Il n'est pas détaillé année par année. La ligne d'impôt sur la fortune est le total sur cette même durée.</p>
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

function revenuRowLabel(cols: ComparatifOffreColumn[]): string {
  const lines = cols.map((col) =>
    impotRevenuPourPdf(col.type, col.impotRevenu, col.dureeAnnees),
  );
  const totals = lines.filter((line) => line.mode === "total");
  if (totals.length === lines.length && totals.length > 0) {
    const years = [...new Set(totals.map((line) => line.annees))];
    if (years.length === 1 && years[0] != null) {
      return `Total ICC / IFD sur ${years[0]} ans`;
    }
  }
  if (lines.length > 0 && lines.every((line) => line.mode === "annuel")) return LIBELLE_ICC_ANNUEL;
  return "ICC / IFD";
}

export function analyseReportHasFortuneLine(): boolean {
  const source = readFileSync(new URL("./renderPrintableReportHtml.ts", import.meta.url), "utf8");
  return source.includes("Total impôt fortune");
}
