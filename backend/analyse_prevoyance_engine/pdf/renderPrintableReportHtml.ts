/**
 * Rendu HTML multi-pages à partir du ReportPayload uniquement.
 * Aucun calcul métier ici — montants = payload.coherence / aggregates.
 */

import { formatChf, personFirstName } from "../mappers";
import type { ReportPayload } from "../report/ReportPayload";

const BRAND = "#800000";
const GREEN = "#255839";
const GREEN_LIGHT = "#388356";
const GRAY = "#595959";
const GRAY_SOFT = "#757171";

export type ReportPageKind = "portrait" | "landscape";

export interface ReportPageSpec {
  kind: ReportPageKind;
  html: string;
}

/**
 * Construit la liste ordonnée des pages (conditionnels inclus).
 * Orientation mixte : frise + Vaudoise en paysage.
 */
export function buildReportPages(payload: ReportPayload): ReportPageSpec[] {
  const pages: ReportPageSpec[] = [];
  let n = 0;
  const total = payload.meta.pageCount;
  const next = () => {
    n += 1;
    return n;
  };

  pages.push({ kind: "portrait", html: pageCover(payload, next(), total) });
  pages.push({ kind: "portrait", html: pageAgency(next(), total) });
  pages.push({ kind: "portrait", html: pageBilan(payload, next(), total) });
  pages.push({
    kind: "portrait",
    html: pageCompareRenteCapital(payload, next(), total),
  });

  if (payload.flags.hasThirdPillar) {
    for (const html of thirdPillarPages(payload, next, total)) {
      pages.push({ kind: "portrait", html });
    }
  }
  // fiscalOptimization.include === false → page masquée (pas d’invention)

  if (payload.withdrawalPlanning?.include) {
    for (const html of withdrawalPlanningPages(payload, next, total)) {
      pages.push({ kind: "portrait", html });
    }
  }

  pages.push({ kind: "landscape", html: pageFrise(payload, next(), total) });

  if (payload.vaudoise?.include) {
    pages.push({
      kind: "landscape",
      html: pageComparatifVaudoise(payload, next(), total),
    });
  }

  if (payload.hypothesesRente) {
    pages.push({
      kind: "landscape",
      html: pageHypothesesRente(payload, next(), total),
    });
  }

  return pages;
}

/** Document HTML complet (preview navigateur) — orientations via CSS @page. */
export function renderPrintableReportHtml(payload: ReportPayload): string {
  const pages = buildReportPages(payload);
  const body = pages
    .map((p) => {
      const orient = p.kind === "landscape" ? "landscape" : "portrait";
      return `<div class="sheet sheet-${orient}">${p.html}</div>`;
    })
    .join("\n");

  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Analyse de prévoyance — ${esc(payload.client1.displayName)}</title>
<style>${reportCss()}</style>
</head>
<body>
${body}
</body>
</html>`;
}

/** HTML d’un sous-ensemble de pages (même orientation) pour Playwright PDF. */
export function renderOrientedHtml(
  payload: ReportPayload,
  kind: ReportPageKind,
): string | null {
  const pages = buildReportPages(payload).filter((p) => p.kind === kind);
  if (!pages.length) return null;
  const body = pages
    .map((p) => `<div class="sheet sheet-${kind}">${p.html}</div>`)
    .join("\n");
  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Analyse de prévoyance — ${esc(payload.client1.displayName)}</title>
<style>${reportCss(kind)}</style>
</head>
<body>
${body}
</body>
</html>`;
}

/**
 * Marge unique du rapport.
 * Gauche = 12 mm + 1 cm de décalage. Droite inchangée (12 mm) pour que
 * les tableaux à 100 % restent dans la page.
 */
export function reportCss(forceOrient?: ReportPageKind) {
  const portrait = `@page { size: A4 portrait; margin: 12mm 12mm 12mm 22mm; }`;
  const landscape = `@page { size: A4 landscape; margin: 8mm 12mm 8mm 22mm; }`;
  const pageRule =
    forceOrient === "landscape"
      ? landscape
      : forceOrient === "portrait"
        ? portrait
        : `
  ${portrait}
  @page landscape-page { size: A4 landscape; margin: 8mm 12mm 8mm 22mm; }
  .sheet-landscape { page: landscape-page; }
  `;

  return `
  ${pageRule}
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: "Candara", "Calibri Light", "Segoe UI", "Trebuchet MS", Helvetica, Arial, sans-serif;
    color: #161616;
    font-size: 10.5pt;
  }
  .sheet {
    page-break-after: always;
    position: relative;
    width: 100%;
    padding-bottom: 8mm;
  }
  .sheet-portrait { min-height: 268mm; }
  .sheet-landscape { min-height: 188mm; }
  .sheet:last-child { page-break-after: auto; }
  .footer {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    text-align: center;
    color: #8a8686;
    font-size: 8pt;
    font-weight: 400;
    letter-spacing: 0.06em;
  }
  .brand-row { display: flex; justify-content: space-between; align-items: flex-start; }
  .logo-img { height: 42px; width: auto; display: block; }
  .logo-fallback .ag {
    color: ${GRAY_SOFT};
    font-family: "Georgia", "Palatino Linotype", "Book Antiqua", serif;
    letter-spacing: 0.1em; font-size: 10pt;
  }
  .logo-fallback .md {
    color: ${BRAND};
    font-family: "Georgia", "Palatino Linotype", "Book Antiqua", serif;
    font-weight: 700; font-size: 17pt; letter-spacing: 0.06em; line-height: 1.05;
  }
  .logo-fallback .tag {
    color: ${GRAY_SOFT}; font-size: 7pt; margin-top: 3px; letter-spacing: 0.08em;
  }
  .contacts { text-align: right; color: #3A3838; font-size: 9pt; line-height: 1.55; }
  .contacts .ico { color: ${BRAND}; margin-right: 4px; }
  h1.cover-title {
    text-align: center; margin: 48mm 0 0;
    font-family: "Georgia", "Palatino Linotype", "Book Antiqua", serif;
  }
  h1.cover-title .l1 {
    display: block; color: #3A3838; font-size: 24pt; font-weight: 500; letter-spacing: 0.08em;
  }
  h1.cover-title .l2 {
    display: block; color: ${BRAND}; font-size: 32pt; font-weight: 700;
    letter-spacing: 0.05em; margin-top: 6px;
  }
  .rules { border: none; border-top: 2px solid ${BRAND}; margin: 12px 16%; }
  .subtitle {
    text-align: center; color: ${GRAY_SOFT}; font-size: 8.5pt;
    letter-spacing: 0.14em; margin-top: 12px;
  }
  .meta-table { width: 68%; margin: 36mm auto 0; border-collapse: collapse; }
  .meta-table td { padding: 11px 6px; border-bottom: 1px solid #d0d0d0; font-size: 11pt; }
  .meta-table .lab {
    color: ${GRAY_SOFT}; width: 38%; text-transform: uppercase; font-size: 9pt; letter-spacing: 0.04em;
  }
  .pill {
    display: inline-block; background: ${BRAND}; color: #fff;
    padding: 10px 22px 10px 14px; border-radius: 0 20px 20px 0;
    font-size: 13pt; margin: 0 0 16px -4px; line-height: 1.25;
  }
  .sec-title {
    color: ${BRAND}; font-size: 11.5pt; font-weight: 600;
    margin: 14px 0 6px; padding-bottom: 3px; border-bottom: 1.5px solid ${BRAND};
  }
  .page-title {
    font-size: 12.5pt; font-weight: 700; letter-spacing: 0.04em;
    margin: 0 0 12px; text-transform: uppercase; color: #1a1a1a;
    line-height: 1.25; padding-right: 4mm;
  }
  table.data {
    width: 100%;
    border-collapse: collapse;
    margin: 0 0 10px;
    font-size: 9pt;
    table-layout: fixed;
  }
  table.data th {
    background: ${BRAND};
    color: #fff;
    padding: 7px 8px;
    text-align: center;
    font-weight: 600;
    font-size: 8pt;
    line-height: 1.15;
    vertical-align: middle;
    white-space: normal;
  }
  table.data th.gray { background: ${GRAY}; }
  table.data td {
    padding: 7px 10px;
    border-bottom: 1px solid #e2e2e2;
    vertical-align: middle;
    line-height: 1.15;
    height: 28px;
  }
  table.data th.lab,
  table.data td.lab {
    text-align: left;
  }
  table.data th.val,
  table.data td.val,
  table.data td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
    padding-right: 10px;
  }
  table.data th.val {
    white-space: normal;
    overflow: visible;
    line-height: 1.2;
  }
  table.data.kv { width: 100%; }
  table.data.kv col.lab { width: 42%; }
  table.data.kv col.val { width: 29%; }
  table.data.kv.one col.lab { width: 58%; }
  table.data.kv.one col.val { width: 42%; }
  table.data.pair col.lab { width: 40%; }
  table.data.pair col.val { width: 30%; }
  table.data td.tax { color: #c00000; }
  table.data tr.alt td { background: #fafafa; }
  .synth { width: 100%; border-collapse: collapse; margin-top: 8px; }
  .synth th { color: #fff; padding: 8px; font-size: 9pt; }
  .synth td { text-align: center; padding: 8px 10px; border: 1px solid #ddd; font-weight: 600; vertical-align: middle; line-height: 1.15; height: 32px; }
  .note { font-size: 8.5pt; font-style: italic; color: ${GRAY}; margin-top: 6px; line-height: 1.35; }
  .eco {
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 16px; background: ${BRAND}; color: #fff;
    font-weight: 700; letter-spacing: 0.04em; padding: 14px 16px; font-size: 13.5pt;
  }
  .eco-none {
    background: #f7f4f4; color: #1a1a1a; border: 2.5px solid ${BRAND};
  }
  table.pillars { font-size: 8pt; }
  table.pillars th { white-space: normal; line-height: 1.2; font-size: 7.5pt; }
  .chart-wrap { margin: 8px 0 14px; }
  .chart-title {
    text-align: center; font-size: 11pt; font-weight: 700; letter-spacing: 0.06em;
    color: #3A3838; margin: 12px 0 6px;
  }
  .chart-legend {
    display: flex; justify-content: center; gap: 18px; font-size: 8pt; color: #444; margin-bottom: 4px;
  }
  .chart-legend .sw {
    display: inline-block; width: 28px; height: 12px; margin-right: 6px; vertical-align: middle;
    border: 1px solid #999;
  }
  .chart-legend .sw.before {
    background: repeating-linear-gradient(45deg, ${GREEN_LIGHT}, ${GREEN_LIGHT} 2px, #a8d5b5 2px, #a8d5b5 5px);
  }
  .chart-legend .sw.after {
    background: repeating-linear-gradient(-45deg, #c45c5c, #c45c5c 2px, #f0c4c4 2px, #f0c4c4 5px);
  }
  .chart-svg { width: 100%; height: auto; display: block; border: 1px solid #e5e5e5; background: #fff; }
  .gain { color: ${GREEN}; font-weight: 700; }
  .agency h3 { color: ${BRAND}; margin: 14px 0 4px; font-size: 12pt; }
  .agency p { margin: 0 0 8px; line-height: 1.4; font-size: 10pt; }
  .agency ul { margin: 4px 0 0 18px; padding: 0; }
  .timeline {
    display: flex; gap: 0; margin: 18px 0 22px;
    border-top: 2.5px solid #c8c8c8; padding-top: 0;
  }
  .tl-col { flex: 1; position: relative; padding-top: 16px; min-width: 0; padding-right: 4px; }
  .tl-col::before {
    content: ""; position: absolute; top: -8px; left: 0;
    width: 16px; height: 12px; background: ${BRAND}; border-radius: 1px;
  }
  .tl-year { color: ${BRAND}; font-weight: 700; font-size: 13pt; margin-bottom: 6px; }
  .tl-ev { font-size: 8pt; margin: 3px 0; line-height: 1.3; color: #333; }
  .frise-title {
    text-align: center; color: ${BRAND}; font-size: 22pt; font-weight: 700;
    letter-spacing: 0.04em; margin: 4px 0 2px;
    font-family: "Georgia", "Palatino Linotype", serif;
  }
  .frise-sub {
    text-align: center; letter-spacing: 0.14em; margin-bottom: 12px;
    font-size: 10pt; color: #3A3838;
  }
  /* Comparaison des rentes : une colonne visuelle par offre, filets fins. */
  table.data.compare th,
  table.data.compare td,
  table.data.compare td.num {
    text-align: center;
  }
  table.data.compare th.lab,
  table.data.compare td.lab {
    text-align: left;
  }
  table.data.compare th {
    white-space: normal;
    overflow-wrap: break-word;
    line-height: 1.25;
    padding: 8px 6px;
    vertical-align: bottom;
  }
  table.data.compare td.num {
    font-variant-numeric: tabular-nums;
    padding-left: 6px;
    padding-right: 6px;
  }
  table.data.compare th.col-lpp,
  table.data.compare td.col-lpp {
    border-left: 1px solid #e4e4e4;
  }
  table.data.compare td.col-offer {
    border-left: 1px solid #d5d5d5;
  }
  table.data.compare th.col-offer {
    border-left: 1px solid rgba(255, 255, 255, 0.35);
  }
  table.data.compare td.col-after-lpp {
    border-left: 1px solid #8a8a8a;
  }
  table.data.compare th.col-after-lpp {
    border-left: 1px solid rgba(255, 255, 255, 0.85);
  }
  .plain { font-size: 10.5pt; line-height: 1.4; margin: 0 0 8px; }
  `;
}

/** Placeholder SVG inline (asset `public/brand/logo-agence-mendes.svg`) — stable hors réseau. */
function logoBlock(compact = false): string {
  if (compact) {
    return `<div class="logo logo-fallback">
      <span class="md" style="font-size:11pt">AGENCE MENDES</span>
      <span style="color:${GRAY_SOFT};font-size:7.5pt"> / Assurément différent depuis 1993</span>
    </div>`;
  }
  return `<div class="logo logo-fallback" title="Placeholder — remplacer par public/brand/logo-agence-mendes.png">
    <div class="ag">AGENCE</div>
    <div class="md">MENDES</div>
    <div class="tag">ASSUREMENT DIFFERENT DEPUIS 1993</div>
  </div>`;
}

function contactsBlock(): string {
  return `<div class="contacts">
    <span class="ico">✉</span> info@agencemendes.ch<br/>
    <span class="ico">☎</span> +41 22 339 30 10
  </div>`;
}

function footer(n: number, _total: number): string {
  if (n <= 1) return "";
  return `<div class="footer">${n}</div>`;
}

function pageCover(p: ReportPayload, n: number, total: number): string {
  const names = p.meta.isCouple && p.conjoint
    ? `${esc(p.client1.displayName)}<br/>${esc(p.conjoint.displayName)}`
    : esc(p.client1.displayName);
  return `
  <div class="brand-row">${logoBlock()}${contactsBlock()}</div>
  <h1 class="cover-title"><span class="l1">ANALYSE DE</span><span class="l2">PREVOYANCE</span></h1>
  <hr class="rules" /><hr class="rules" style="margin-top:8px" />
  <p class="subtitle">ETUDE DE RETRAITE ET OPTIMISATION PATRIMONIALE</p>
  <table class="meta-table">
    <tr><td class="lab">Client</td><td>${names}</td></tr>
    <tr><td class="lab">Conseiller</td><td>${esc(p.meta.conseillerNom || "—")}</td></tr>
    <tr><td class="lab">Date du rapport</td><td>${esc(p.meta.dateRapportLabel)}</td></tr>
  </table>
  ${footer(n, total)}`;
}

function pageAgency(n: number, total: number): string {
  return `
  <div class="agency">
  <div class="pill">L'historique de<br/>l'Agence Mendes</div>
  <h3>1993 Plus de 30 ans d’expérience</h3>
  <p>Depuis plus de 25 ans, nous sommes au service de nos clients dans toute la Suisse Romande et le Tessin. Notre spécialité : le conseil dans les domaines de l’assurance, de l’hypothèque et des placements garantis.</p>
  <h3>60'000 clients satisfaits</h3>
  <p>Nous défendons de nombreuses valeurs, dont la transparence et le conseil. Nos clients l’ont bien compris, nous avons établi avec eux une relation de confiance.</p>
  <h3>Plus de 30 collaborateurs</h3>
  <p>Nos conseillers suivent des formations régulièrement, ils connaissent donc les dernières nouveautés sur les produits et la réglementation. Nous assurons un travail de suivi administratif efficace.</p>
  <h3>50 partenaires reconnus</h3>
  <p>Nous travaillons avec les plus grandes compagnies d’assurance tout en restant neutres et objectifs. Nous proposons des comparatifs sans parti pris qui seront adaptés aux besoins du client. En tant que courtier reconnu, nos services sont rétribués par les compagnies d’assurance, sans influence sur le conseil.</p>
  <h3 style="color:#161616">Plus qu’un courtier en assurances</h3>
  <p>Pour mieux répondre aux besoins de nos clients dans le cadre d’un conseil global, nous offrons les prestations suivantes :</p>
  <ul>
    <li>analyse et conseil en prévoyance</li>
    <li>analyse et conseil fiscal</li>
    <li>recherche du meilleur financement hypothécaire (reprise ou nouveau)</li>
  </ul>
  </div>
  ${footer(n, total)}`;
}

function pageBilan(p: ReportPayload, n: number, total: number): string {
  const c2 = p.flags.showConjoint ? p.conjoint : null;
  const cols = `<colgroup><col class="lab" /><col class="val" /><col class="val" /></colgroup>`;
  const spouse = (html: string) => `<td class="val">${c2 ? html : ""}</td>`;
  const when = (label: string, age: string) =>
    `${esc(label)}<br/><span style="color:#666">(${esc(age)})</span>`;
  return `
  <div class="page-title">Bilan de prévoyance retraite</div>
  <div class="sec-title">1. Profil des assurés</div>
  <table class="data kv">
    ${cols}
    <tr>
      <td class="lab"></td>
      <td class="val"><strong>${esc(p.client1.displayName)}</strong></td>
      ${spouse(c2 ? `<strong>${esc(c2.displayName)}</strong>` : "")}
    </tr>
    <tr>
      <td class="lab">Situation personnelle</td>
      <td class="val">${esc(p.meta.etatCivil)}</td>
      ${spouse(esc(p.meta.etatCivil))}
    </tr>
    <tr>
      <td class="lab">Date de naissance</td>
      <td class="val">${esc(p.client1.dateNaissanceLabel)}</td>
      ${spouse(c2 ? esc(c2.dateNaissanceLabel) : "")}
    </tr>
    <tr>
      <td class="lab">Revenu brut par an</td>
      <td class="val">${formatChf(p.client1.salaire)}</td>
      ${spouse(c2 ? formatChf(c2.salaire) : "")}
    </tr>
  </table>
  <div class="sec-title">2. Hypothèse de planification retraite</div>
  <table class="data kv">
    ${cols}
    <tr>
      <th class="lab">Prestations</th>
      <th class="val">${esc(p.client1.displayName)}</th>
      <th class="val">${c2 ? esc(c2.displayName) : ""}</th>
    </tr>
    <tr>
      <td class="lab">Fin de l'activité lucrative</td>
      <td class="val">${when(p.client1.dateDepartLabel, p.client1.ageLegalLabel)}</td>
      ${spouse(c2 ? when(c2.dateDepartLabel, c2.ageLegalLabel) : "")}
    </tr>
    <tr>
      <td class="lab">Retrait AVS</td>
      <td class="val">${when(p.client1.dateDepartLabel, p.client1.ageLegalLabel)}</td>
      ${spouse(c2 ? when(c2.dateDepartLabel, c2.ageLegalLabel) : "")}
    </tr>
  </table>
  <div class="sec-title">3. Patrimoine de prévoyance actuel</div>
  <table class="data kv">
    ${cols}
    <tr>
      <th class="lab">Poste</th>
      <th class="val">${esc(p.client1.displayName)}</th>
      <th class="val">${c2 ? esc(c2.displayName) : ""}</th>
    </tr>
    <tr>
      <td class="lab">AVS estimée</td>
      <td class="val">${formatChf(p.client1.avsAnnuel)} /an</td>
      ${spouse(c2 ? `${formatChf(c2.avsAnnuel)} /an` : "")}
    </tr>
    <tr>
      <td class="lab">Capital 2e pilier (LPP)</td>
      <td class="val">${formatChf(p.client1.capitalLpp65)}</td>
      ${spouse(c2 ? formatChf(c2.capitalLpp65) : "")}
    </tr>
    <tr>
      <td class="lab">% LPP déblocable</td>
      <td class="val">${p.client1.lppPctDeblocable} %</td>
      ${spouse(c2 ? `${c2.lppPctDeblocable} %` : "")}
    </tr>
    <tr>
      <td class="lab">3e pilier</td>
      <td class="val">${formatChf(p.client1.total3ePilier)}</td>
      ${spouse(c2 ? formatChf(c2.total3ePilier) : "")}
    </tr>
    ${
      p.flags.hasRentePont
        ? `<tr><td class="lab">Rente pont</td><td class="val">${p.client1.hasRentePont ? formatChf(p.client1.rentePont) : "—"}</td>${spouse(c2 ? (c2.hasRentePont ? formatChf(c2.rentePont) : "—") : "")}</tr>`
        : ""
    }
    <tr>
      <td class="lab">Libre passage</td>
      <td class="val">${formatChf(p.client1.librePassage)}</td>
      ${spouse(c2 ? formatChf(c2.librePassage) : "")}
    </tr>
  </table>
  <div class="sec-title">4. Synthèse des prestations attendues à la retraite</div>
  <table class="synth">
    <tr>
      <th style="background:${GREEN}">AVS estimée</th>
      <th style="background:${BRAND};white-space:normal;line-height:1.25">Capital 2e pilier retirable, y compris libre passage</th>
      <th style="background:${GRAY}">Âge de la retraite</th>
    </tr>
    <tr>
      <td>${formatChf(p.aggregates.avsTotal)}</td>
      <td>${formatChf(p.aggregates.capitalLppAvecLibrePassage)}</td>
      <td style="font-size:9pt">${esc(insuredName(p.client1, "Assuré 1"))} : ${esc(p.client1.ageLegalLabel)}${c2 ? `<br/>${esc(insuredName(c2, "Assuré 2"))} : ${esc(c2.ageLegalLabel)}` : ""}</td>
    </tr>
  </table>
  ${footer(n, total)}`;
}

function pageCompareRenteCapital(
  p: ReportPayload,
  n: number,
  total: number,
): string {
  const a = p.aggregates;
  const chart = renderEvolutionChart(p);
  const notePct =
    p.client1.lppPctDeblocable < 100 ||
    (p.conjoint != null && p.conjoint.lppPctDeblocable < 100)
      ? `<p class="note">Capital LPP retiré selon % déblocable saisi (${esc(insuredName(p.client1, "Assuré 1"))} : ${p.client1.lppPctDeblocable} %${p.conjoint ? ` · ${esc(insuredName(p.conjoint, "Assuré 2"))} : ${p.conjoint.lppPctDeblocable} %` : ""}). Rente LPP résiduelle maintenue sur le solde.</p>`
      : "";

  return `
  <div class="page-title">Comparaison des options de retraite : rente ou capital</div>
  <table class="data pair">
    <colgroup><col class="lab" /><col class="val" /><col class="val" /></colgroup>
    <tr><th class="lab"></th><th class="val">Retraite avec rente</th><th class="val">Retraite avec capital</th></tr>
    <tr><td class="lab">Capital LPP</td><td class="num">—</td><td class="num">${formatChf(a.capitalLppRetireTotal)}</td></tr>
    <tr><td class="lab">Impôt sur les capitaux</td><td class="num">—</td><td class="num tax">${formatChf(a.impotCapital65)}</td></tr>
    <tr><td class="lab">Capitaux après impôt</td><td class="num">—</td><td class="num">${formatChf(a.capitalNet65)}</td></tr>
    <tr><td class="lab">Rente LPP – ${esc(insuredName(p.client1, "Assuré 1"))}</td><td class="num">${formatChf(p.client1.renteLpp65)}</td><td class="num">${formatChf(p.client1.renteLppResiduelle65)}</td></tr>
    ${p.conjoint ? `<tr><td class="lab">Rente LPP – ${esc(insuredName(p.conjoint, "Assuré 2"))}</td><td class="num">${formatChf(p.conjoint.renteLpp65)}</td><td class="num">${formatChf(p.conjoint.renteLppResiduelle65)}</td></tr>` : ""}
    <tr><td class="lab">Rente AVS</td><td class="num">${formatChf(a.avsTotal)}</td><td class="num">${formatChf(a.avsTotal)}</td></tr>
    <tr><td class="lab">Impôts ICC &amp; IFD</td><td class="num tax">${formatChf(a.impotRevenuCouple1)}</td><td class="num tax">${formatChf(a.impotRevenuCouple2)}</td></tr>
    <tr><td class="lab">Rente après impôt</td><td class="num">${formatChf(a.renteApresImpot)}</td><td class="num">${formatChf(a.renteNetteCheminCapital)}</td></tr>
    <tr><td class="lab">Capital disponible</td><td class="num">—</td><td class="num">${formatChf(a.capitalNet65)}</td></tr>
  </table>
  ${notePct}
  ${chart}
  <div class="sec-title">Indicateurs de maintien de niveau de vie</div>
  <table class="data">
    <tr><th class="gray">Indicateur</th><th class="gray">Montant</th></tr>
    <tr><td>Salaire brut avant retraite</td><td class="num">${formatChf(a.salaireAvant)}</td></tr>
    <tr><td>Revenu brut après retraite</td><td class="num">${formatChf(a.revenuApres)}</td></tr>
    <tr><td>Lacune de prévoyance annuelle</td><td class="num">${formatChf(a.lacune)}</td></tr>
    <tr><td>Manque à gagner annuel pour maintenir 80&nbsp;%</td><td class="num">${formatChf(a.manquePour80)}</td></tr>
  </table>
  <p class="note">Pour conserver un niveau de vie similaire, il est généralement recommandé de disposer d’un revenu de retraite représentant au moins 80&nbsp;% du revenu avant retraite.</p>
  ${footer(n, total)}`;
}

function formatAxisChf(n: number): string {
  return new Intl.NumberFormat("fr-CH", {
    maximumFractionDigits: 0,
  }).format(n);
}

/**
 * Barres empilées : hauteur totale = revenu avant retraite.
 * Bas = revenu de référence (AVS + rente LPP complète). Haut = manque.
 */
function renderEvolutionChart(p: ReportPayload): string {
  const points = p.evolution.points;
  if (!points.length) {
    return `<div class="chart-title">ÉVOLUTION REVENU APRÈS LA RETRAITE</div>
      <p class="note">Pas de série d’évolution.</p>`;
  }

  const reference = Math.max(p.evolution.salaireReference || 0, 1);
  const firstChange = points.findIndex((x) => x.phase !== "salaire");
  const start = Math.max(0, (firstChange >= 0 ? firstChange : 0) - 1);
  const end = Math.min(points.length, start + 12);
  const slice = points.slice(start, end);
  const yMax = Math.max(
    reference,
    ...slice.map((pt) => pt.revenu),
    1,
  );

  const W = 720;
  const H = 248;
  const padL = 74;
  const padR = 10;
  const padT = 14;
  const padB = 30;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const yAt = (v: number) => padT + plotH - (v / yMax) * plotH;
  const colW = Math.max(18, plotW / slice.length - 8);

  const yTicks: string[] = [];
  const steps = 4;
  for (let i = 0; i <= steps; i++) {
    const val = (yMax * i) / steps;
    const y = yAt(val);
    yTicks.push(
      `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="#e4e4e4" stroke-width="1"/>`,
      `<text x="${padL - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end" font-size="8" fill="#666">${formatAxisChf(val)}</text>`,
    );
  }

  const bars = slice
    .map((pt, i) => {
      const received = Math.max(0, pt.revenu);
      const gap = Math.max(0, reference - received);
      const x = padL + (i + 0.5) * (plotW / slice.length) - colW / 2;
      const yReceived = yAt(received);
      const hReceived = yAt(0) - yReceived;
      const yGap = yAt(received + gap);
      const hGap = yReceived - yGap;
      const receivedLabel =
        hReceived > 16
          ? `<text x="${(x + colW / 2).toFixed(1)}" y="${(yReceived + hReceived / 2 + 3).toFixed(1)}" text-anchor="middle" font-size="7.5" fill="#fff">${formatAxisChf(received)}</text>`
          : "";
      const gapLabel =
        hGap > 16
          ? `<text x="${(x + colW / 2).toFixed(1)}" y="${(yGap + hGap / 2 + 3).toFixed(1)}" text-anchor="middle" font-size="7.5" fill="#fff">${formatAxisChf(gap)}</text>`
          : "";
      return `<rect x="${x.toFixed(1)}" y="${yReceived.toFixed(1)}" width="${colW.toFixed(1)}" height="${Math.max(0, hReceived).toFixed(1)}" fill="${GREEN}"/>
        <rect x="${x.toFixed(1)}" y="${yGap.toFixed(1)}" width="${colW.toFixed(1)}" height="${Math.max(0, hGap).toFixed(1)}" fill="#9a3b3b"/>
        ${receivedLabel}${gapLabel}
        <text x="${(x + colW / 2).toFixed(1)}" y="${H - 10}" text-anchor="middle" font-size="8" fill="#444">${pt.year}</text>`;
    })
    .join("\n");

  return `
  <div class="chart-wrap">
    <div class="chart-title">ÉVOLUTION REVENU APRÈS LA RETRAITE</div>
    <div class="chart-legend">
      <span><i class="sw before"></i> Revenu de référence (AVS + LPP complète)</span>
      <span><i class="sw after"></i> Manque de revenu</span>
    </div>
    <svg class="chart-svg" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Évolution revenu après retraite">
      ${yTicks.join("\n")}
      ${bars}
    </svg>
    <p class="note">La hauteur de chaque barre correspond au revenu avant retraite. Le bas est le revenu de retraite de référence (AVS + rente LPP complète, sans retrait en capital), le haut est le manque pour retrouver ce niveau.</p>
  </div>`;
}

const THIRD_PILLAR_ROWS_PER_PAGE = 8;

function thirdPillarPages(
  p: ReportPayload,
  next: () => number,
  total: number,
): string[] {
  const rows = p.thirdPillarRows;
  if (!rows.length) return [];
  const has3b = rows.some((row) => row.type === "3B");
  const contratsLabel = `${rows.length} contrat${rows.length > 1 ? "s" : ""} saisi${rows.length > 1 ? "s" : ""}.`;
  const note3b = has3b
    ? " Les 3B restent dans le capital et ne sont pas soumis à l'impôt sur les prestations en capital."
    : "";
  const pages: string[] = [];
  for (let offset = 0; offset < rows.length; offset += THIRD_PILLAR_ROWS_PER_PAGE) {
    const slice = rows.slice(offset, offset + THIRD_PILLAR_ROWS_PER_PAGE);
    const body = slice
      .map((row) => {
        const tax = row.exonere || row.type === "3B"
          ? "Exonéré d'impôt"
          : row.impot == null
            ? "—"
            : formatChf(row.impot);
        const net = row.capitalNet == null ? "—" : formatChf(row.capitalNet);
        return `<tr>
          <td>${esc(row.personKey === "conjoint" ? insuredName(p.conjoint, "Assuré 2") : insuredName(p.client1, "Assuré 1"))}</td>
          <td>${esc(row.compagnie)}</td>
          <td>${esc(row.police)}</td>
          <td>${esc(row.type)}</td>
          <td>${esc(row.echeanceLabel)}</td>
          <td class="num">${formatChf(row.montant)}</td>
          <td class="num">${formatChf(row.prime)}</td>
          <td class="num${row.exonere ? "" : " tax"}">${tax}</td>
          <td class="num">${net}</td>
        </tr>`;
      })
      .join("");
    const continued = offset > 0 ? " (suite)" : "";
    pages.push(`
  <div class="page-title">Analyse des contrats de prévoyance 3A/3B${continued}</div>
  <table class="data pillars">
    <colgroup>
      <col style="width:11%" />
      <col style="width:13%" />
      <col style="width:14%" />
      <col style="width:8%" />
      <col style="width:12%" />
      <col style="width:12%" />
      <col style="width:10%" />
      <col style="width:10%" />
      <col style="width:10%" />
    </colgroup>
    <tr>
      <th>Assuré</th>
      <th>Compagnie</th>
      <th>N° de police</th>
      <th>Type</th>
      <th>Échéance</th>
      <th>Valeur à l'échéance</th>
      <th>Prime annuelle</th>
      <th>Impôt estimé</th>
      <th>Capital net</th>
    </tr>
    ${body}
  </table>
  <p class="note">${contratsLabel}${note3b}</p>
  ${footer(next(), total)}`);
  }
  return pages;
}

type WithdrawalPlanning = ReportPayload["withdrawalPlanning"];
type WithdrawalScenario = WithdrawalPlanning["scenarios"][number];

function yearIsFullyExempt(year: WithdrawalScenario["byYear"][number]): boolean {
  const lines = year.lines || [];
  return lines.length > 0 && lines.every((line) => line.exonere);
}

function yearPrestationShort(year: WithdrawalScenario["byYear"][number]): string {
  const lines = year.lines || [];
  const parts: string[] = [];
  if (lines.some((line) => line.kind === "lpp")) parts.push("LPP");
  if (lines.some((line) => line.kind === "libre_passage")) parts.push("Libre passage");
  if (lines.some((line) => line.kind === "3p" && line.contratType === "3A")) {
    parts.push("3A");
  }
  if (lines.some((line) => line.kind === "3p" && line.contratType === "3B")) {
    parts.push("3B");
  }
  if (
    lines.some((line) => line.kind === "3p" && !line.contratType) &&
    !lines.some((line) => line.kind === "3p" && line.contratType)
  ) {
    parts.push("3e pilier");
  }
  if (lines.some((line) => line.kind === "autre")) parts.push("Autre");
  return parts.join(" + ") || "—";
}

function strategyScenario(wp: WithdrawalPlanning): WithdrawalScenario | null {
  if (!wp.scenarios.length) return null;
  if (wp.strategyScenarioId) {
    const found = wp.scenarios.find((scenario) => scenario.id === wp.strategyScenarioId);
    if (found) return found;
  }
  return [...wp.scenarios].sort(
    (a, b) => a.byYear.length - b.byYear.length || a.id.localeCompare(b.id),
  )[wp.scenarios.length - 1];
}

function sameYearBlock(wp: WithdrawalPlanning): string {
  const ref = wp.sameYearReference;
  if (!ref) return "";
  return `
  <div class="sec-title">RETRAITS LA MÊME ANNÉE FISCALE</div>
  <p class="note">Année fiscale ${ref.year}. Tous les capitaux de la stratégie préparée sont retirés ensemble. Les 3B restent dans le capital retiré et sont exonérés d'impôt.</p>
  <table class="data">
    <colgroup>
      <col style="width:34%" />
      <col style="width:33%" />
      <col style="width:33%" />
    </colgroup>
    <tr>
      <th>Capital retiré</th>
      <th>Impôt total</th>
      <th>Capital net</th>
    </tr>
    <tr>
      <td class="num">${formatChf(ref.capitalRetire)}</td>
      <td class="num tax">${formatChf(ref.impotTotal)}</td>
      <td class="num">${formatChf(ref.capitalNet)}</td>
    </tr>
  </table>`;
}

function strategyBlock(sc: WithdrawalScenario): string {
  const rows = sc.byYear
    .map((year) => {
      const exempt = yearIsFullyExempt(year);
      const tax = exempt ? "Exonéré d'impôt" : formatChf(year.impot);
      return `<tr>
        <td class="lab">${year.year}</td>
        <td>${yearPrestationShort(year)}</td>
        <td class="num">${formatChf(year.capitalRetire)}</td>
        <td class="num${exempt ? "" : " tax"}">${tax}</td>
      </tr>`;
    })
    .join("");
  return `
  <div class="sec-title">STRATÉGIE DE RETRAITS PRÉPARÉE</div>
  <p class="note">${esc(sc.name)}</p>
  <table class="data">
    <colgroup>
      <col style="width:14%" />
      <col style="width:32%" />
      <col style="width:27%" />
      <col style="width:27%" />
    </colgroup>
    <tr>
      <th>Année</th>
      <th>Prestations retirées</th>
      <th>Capital retiré</th>
      <th>Impôt</th>
    </tr>
    ${rows || `<tr><td colspan="4">—</td></tr>`}
    <tr>
      <td class="lab" colspan="2">Total des capitaux</td>
      <td class="num">${formatChf(sc.capitalRetireTotal)}</td>
      <td></td>
    </tr>
    <tr>
      <td class="lab" colspan="2">Total des impôts</td>
      <td></td>
      <td class="num tax">${formatChf(sc.impotTotal)}</td>
    </tr>
    <tr>
      <td class="lab" colspan="2">Capital net</td>
      <td class="num" colspan="2">${formatChf(sc.capitalNet)}</td>
    </tr>
  </table>`;
}

function economieBanner(gain: number | null): string {
  const formula = `<p class="note">Économie = impôt si tous les capitaux imposables étaient retirés la même année − total des impôts du scénario échelonné.</p>`;
  if (gain == null) {
    return `<p class="note">Économie fiscale non estimée : un impôt manque sur la référence ou sur la stratégie.</p>`;
  }
  if (gain > 0) {
    return `<div class="eco"><span>ÉCONOMIE FISCALE ESTIMÉE : ${formatChf(gain)}</span></div>${formula}`;
  }
  return `<div class="eco eco-none"><span>ÉCONOMIE FISCALE ESTIMÉE : 0 CHF — l'échelonnement n'est pas plus favorable</span></div>${formula}`;
}

function planningReportHtml(wp: WithdrawalPlanning): string {
  const strategy = strategyScenario(wp);
  return `
  <div class="page-title">Planification des retraits de capitaux</div>
  ${sameYearBlock(wp)}
  ${strategy ? strategyBlock(strategy) : ""}
  ${economieBanner(wp.economieFiscale)}`;
}

function withdrawalPlanningPages(
  p: ReportPayload,
  next: () => number,
  total: number,
): string[] {
  const demo = p.meta.conseillerNom.includes("DOSSIER DÉMO")
    ? `<p class="note"><strong>Dossier de démonstration.</strong> Les impôts de ce fichier sont simulés pour la validation locale. Ce ne sont pas des résultats ESTV.</p>`
    : "";
  return [`${demo}${planningReportHtml(p.withdrawalPlanning)}${footer(next(), total)}`];
}

function pageFrise(p: ReportPayload, n: number, total: number): string {
  const years = p.timeline.years;
  const cols = years
    .map((y) => {
      const evs = p.timeline.byYear[y] || [];
      return `<div class="tl-col"><div class="tl-year">${y}</div>${evs
        .map((e) => `<div class="tl-ev">${esc(e.label)}</div>`)
        .join("")}</div>`;
    })
    .join("");

  const detail = p.timeline.events
    .map(
      (e) =>
        `<tr><td>${esc(e.label)}</td><td class="num">${formatChf(e.amount)}${timelineAmountSuffix(e)}</td></tr>`,
    )
    .join("");

  return `
  <div class="brand-row" style="margin-bottom:6px">
    ${logoBlock(true)}
    <div class="contacts" style="font-size:8pt">info@agencemendes.ch &nbsp; +41 22 339 30 10</div>
  </div>
  <div class="frise-title">Frise chronologique</div>
  <div class="frise-sub">PRESTATIONS DE RETRAITE</div>
  <div class="sec-title">Vue d’ensemble</div>
  <div class="timeline">${cols || "<p class='note'>Aucun événement</p>"}</div>
  <div class="sec-title">Détail des prestations</div>
  <table class="data">
    <tr><th>Prestation</th><th>Montant</th></tr>
    ${detail}
  </table>
  ${footer(n, total)}`;
}

function pageHypothesesRente(p: ReportPayload, n: number, total: number): string {
  const block = p.hypothesesRente;
  if (!block) return "";
  const cols = block.columns;
  const withLpp = block.comparerAvecRenteLpp;
  const ageLabel = block.ageRetraite
    ? `à ${block.ageRetraite} ans`
    : "à l'âge du dossier";
  const money = (value: number | null) =>
    value == null ? "—" : formatChf(value);
  const colRole = (index: number) => {
    const col = cols[index];
    if (col.kind === "lpp") return "col-lpp";
    const prev = index > 0 ? cols[index - 1] : null;
    return prev?.kind === "lpp" ? "col-offer col-after-lpp" : "col-offer";
  };
  const row = (label: string, values: string[]) =>
    `<tr><td class="lab">${label}</td>${values.map((v, i) => `<td class="num ${colRole(i)}">${v}</td>`).join("")}</tr>`;
  const showDuree = cols.some((c) => c.dureeAnnees != null);
  const head = cols
    .map((c, i) => `<th class="${colRole(i)}">${esc(c.label)}</th>`)
    .join("");
  const lines = [
    row("Capital placé", cols.map((c) => money(c.capitalPlace))),
    row("Compagnie", cols.map((c) => esc(c.compagnie || "—"))),
    row("Type de rente", cols.map((c) => esc(c.typeLabel))),
    row("Rente AVS", cols.map((c) => money(c.renteAvs))),
    row(
      "Rente LPP résiduelle",
      cols.map((c) => (c.kind === "lpp" ? "—" : money(c.renteLppResiduelle))),
    ),
    row("Rente garantie", cols.map((c) => money(c.renteGarantie))),
    row(
      "Participation aux excédents",
      cols.map((c) => (c.kind === "lpp" ? "—" : money(c.participationExcedents))),
    ),
  ];
  if (showDuree) {
    lines.splice(
      3,
      0,
      row(
        "Durée de la rente",
        cols.map((c) => (c.dureeAnnees != null ? `${c.dureeAnnees} ans` : "—")),
      ),
    );
  }
  lines.push(
    row("Revenu total encaissé", cols.map((c) => money(c.revenuBrutEncaisse))),
    row("Revenu fiscal imposable", cols.map((c) => money(c.revenuFiscalImposable))),
    row(
      "Impôts ICC &amp; IFD",
      cols.map((c) =>
        c.impotEstv == null ? "—" : `<span class="tax">${formatChf(c.impotEstv)}</span>`,
      ),
    ),
    row("Revenu net annuel", cols.map((c) => money(c.revenuNetApresImpot))),
  );
  if (withLpp) {
    lines.push(
      row(
        "Écart net annuel vs LPP",
        cols.map((c) =>
          c.kind === "lpp" || c.ecartNetAnnuelVsLpp == null
            ? "—"
            : formatChf(c.ecartNetAnnuelVsLpp),
        ),
      ),
    );
  }
  const rendements = withLpp
    ? ""
    : cols
        .filter((c) => c.kind === "hypothese" && c.revenuAnnuelSurCapital != null)
        .map(
          (c) =>
            `<tr><td class="lab">Revenu annuel / capital · ${esc(c.label)}</td><td class="num">${new Intl.NumberFormat("fr-CH", { style: "percent", maximumFractionDigits: 2 }).format(c.revenuAnnuelSurCapital || 0)}</td></tr>`,
        )
        .join("");
  const note = withLpp
    ? ""
    : rendements
      ? `<div class="sec-title">Revenu annuel obtenu sur le capital placé</div><table class="data"><tr><th class="lab">Indicateur</th><th>Valeur</th></tr>${rendements}</table><p class="note">Ce ratio rapporte le revenu encaissé au capital placé. Ce n’est pas un gain en capital.</p>`
      : "";

  return `
  <div class="page-title">Comparaison des rentes ${esc(ageLabel)}</div>
  <table class="data compare">
    <colgroup>
      <col style="width:28%" />
      ${cols.map(() => `<col />`).join("")}
    </colgroup>
    <tr><th class="lab"></th>${head}</tr>
    ${lines.join("")}
  </table>
  ${note}
  <p class="note">Le revenu fiscal imposable suit la règle de l’offre (rente certaine ou viagère) et sert uniquement au calcul ESTV. La rente LPP résiduelle est encaissée et imposable en totalité. Il est distinct du revenu total encaissé.</p>
  ${footer(n, total)}`;
}

function pageComparatifVaudoise(
  p: ReportPayload,
  n: number,
  total: number,
): string {
  const v = p.vaudoise!;
  const cols = v.columns;
  const head = cols
    .map((c) => {
      const outline = c.recommended
        ? ` style="outline:2px solid ${GREEN}"`
        : "";
      return `<th class="gray"${outline}>${esc(c.label)}</th>`;
    })
    .join("");

  const cell = (vals: (string | null)[]) =>
    vals.map((x) => `<td class="num">${x ?? "—"}</td>`).join("");

  const renteAvs = cell(cols.map(() => formatChf(p.aggregates.avsTotal)));
  const renteCert = cell(
    cols.map((c) =>
      c.id === "lpp" ? "—" : formatChf(c.renteCertaine),
    ),
  );
  const part = cell(
    cols.map((c) => `${Math.round(c.partImposable * 100)}%`),
  );
  const impot = cell(
    cols.map((c) =>
      c.impot != null ? `<span class="tax">${formatChf(c.impot)}</span>` : "—",
    ),
  );
  const nette = cell(cols.map((c) => formatChf(c.renteNette)));
  const gain = cell(
    cols.map((c) => {
      if (c.id === "lpp" || c.gainNetVsLpp == null) return "—";
      const sign = c.gainNetVsLpp >= 0 ? "+" : "";
      return `<span class="gain">${sign}${formatChf(c.gainNetVsLpp)}</span>`;
    }),
  );

  const capitalRows = cols
    .filter((c) => c.id !== "lpp")
    .map(
      (c) =>
        `<td class="num">${formatChf(c.capitalAffecte)}</td>`,
    )
    .join("");
  const conserveRows = cols
    .filter((c) => c.id !== "lpp")
    .map(
      (c) =>
        `<td class="num">${formatChf(Math.max(0, v.capitalDisponible - c.capitalAffecte))}</td>`,
    )
    .join("");

  return `
  <div class="brand-row" style="margin-bottom:8px">
    ${logoBlock(true)}
    <div class="contacts" style="font-size:8pt">info@agencemendes.ch &nbsp; +41 22 339 30 10</div>
  </div>
  <div class="page-title" style="font-size:13pt;text-transform:none">Comparaison : Rente LPP vs Rente Certaine</div>
  <table class="data">
    <tr>
      <td>Capital disponible à la retraite</td>
      ${cols
        .filter((c) => c.id !== "lpp")
        .map(() => `<td class="num">${formatChf(v.capitalDisponible)}</td>`)
        .join("")}
    </tr>
    <tr><td>Capital affecté à la rente</td>${capitalRows}</tr>
    <tr><td>Capital conservé disponible</td>${conserveRows}</tr>
  </table>
  <table class="data" style="font-size:8.5pt">
    <tr><th class="gray"></th>${head}</tr>
    <tr><td>Rente AVS</td>${renteAvs}</tr>
    <tr><td>Rente LPP – ${esc(insuredName(p.client1, "Assuré 1"))}</td>${cell(cols.map((c) => c.id === "lpp" ? formatChf(p.client1.renteLpp65) : formatChf(0)))}</tr>
    ${p.conjoint ? `<tr><td>Rente LPP – ${esc(insuredName(p.conjoint, "Assuré 2"))}</td>${cell(cols.map((c) => c.id === "lpp" ? formatChf(p.conjoint!.renteLpp65) : formatChf(0)))}</tr>` : ""}
    <tr><td>Rente certaine</td>${renteCert}</tr>
    <tr><td>Part imposable</td>${part}</tr>
    <tr><td>Impôts ICC &amp; IFD</td>${impot}</tr>
    <tr><td>Rente nette annuelle</td>${nette}</tr>
    <tr><td>Gain net annuel</td>${gain}</tr>
  </table>
  <div class="sec-title">Indicateurs clés de la recommandation</div>
  <table class="data">
    <tr><th class="gray">Indicateur</th><th class="gray">Valeur</th></tr>
    <tr><td>Revenu net supplémentaire annuel</td><td class="num gain">${formatChf(v.indicateurs.revenuNetSupplementaire)}</td></tr>
    <tr><td>Gain total cumulé sur 20 ans</td><td class="num gain">${formatChf(v.indicateurs.gainCumul20Ans)}</td></tr>
    <tr><td>Économie fiscale annuelle (LPP vs AVS-seul)</td><td class="num">${formatChf(v.indicateurs.economieFiscaleAnnuelle)}</td></tr>
  </table>
  ${footer(n, total)}`;
}

function insuredName(
  person: { prenom?: string | null } | null | undefined,
  fallback: "Assuré 1" | "Assuré 2",
): string {
  return personFirstName(person, fallback);
}

function timelineAmountSuffix(event: { kind: string; label: string }): string {
  if (event.kind === "avs") return " /an";
  if (event.kind === "lpp" && event.label.endsWith("– Rente")) return " /an";
  return "";
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
