/**
 * Rendu HTML multi-pages à partir du ReportPayload uniquement.
 * Aucun calcul métier ici — montants = payload.coherence / aggregates.
 */

import { formatChf } from "../mappers";
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
    pages.push({ kind: "portrait", html: page3a(payload, next(), total) });
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
      <th style="background:${BRAND};white-space:normal;line-height:1.25">Capital 2e pilier, y compris libre passage</th>
      <th style="background:${GRAY}">Âge de la retraite</th>
    </tr>
    <tr>
      <td>${formatChf(p.aggregates.avsTotal)}</td>
      <td>${formatChf(p.aggregates.capitalLppAvecLibrePassage)}</td>
      <td style="font-size:9pt">Assuré 1 : ${esc(p.client1.ageLegalLabel)}${c2 ? `<br/>Assuré 2 : ${esc(c2.ageLegalLabel)}` : ""}</td>
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
      ? `<p class="note">Capital LPP retiré selon % déblocable saisi (assuré 1 : ${p.client1.lppPctDeblocable} %${p.conjoint ? ` · assuré 2 : ${p.conjoint.lppPctDeblocable} %` : ""}). Rente LPP résiduelle maintenue sur le solde.</p>`
      : "";

  return `
  <div class="page-title">Comparaison des options de retraite : rente ou capital</div>
  <table class="data pair">
    <colgroup><col class="lab" /><col class="val" /><col class="val" /></colgroup>
    <tr><th class="lab"></th><th class="val">Retraite avec rente</th><th class="val">Retraite avec capital</th></tr>
    <tr><td class="lab">Capital LPP</td><td class="num">—</td><td class="num">${formatChf(a.capitalLppRetireTotal)}</td></tr>
    <tr><td class="lab">Impôt sur les capitaux</td><td class="num">—</td><td class="num tax">${formatChf(a.impotCapital65)}</td></tr>
    <tr><td class="lab">Capitaux après impôt</td><td class="num">—</td><td class="num">${formatChf(a.capitalNet65)}</td></tr>
    <tr><td class="lab">Rente LPP</td><td class="num">${formatChf(a.renteLppTotal)}</td><td class="num">${formatChf(a.renteLppResiduelleTotal)}</td></tr>
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

/**
 * Graphique évolution — SVG aire hachurée proche du PDF ref p.4.
 * Données = payload.evolution (moteur).
 */
function renderEvolutionChart(p: ReportPayload): string {
  const points = p.evolution.points;
  if (!points.length) {
    return `<div class="chart-title">EVOLUTION REVENU APRÈS LA RETRAITE</div>
      <p class="note">Pas de série d’évolution.</p>`;
  }

  // Fenêtre autour de la transition (comme le ref : ~avant + après)
  const firstRenteIdx = points.findIndex((x) => x.phase !== "salaire");
  const start = Math.max(0, (firstRenteIdx >= 0 ? firstRenteIdx : 2) - 2);
  const end = Math.min(points.length, start + 14);
  const slice = points.slice(start, end);

  const maxVal = Math.max(
    ...slice.map((x) => x.revenu),
    p.evolution.salaireReference,
    p.evolution.renteReference,
    1,
  );
  // Arrondi axe Y (pas de 50k comme ref)
  const yMax = Math.ceil(maxVal / 50_000) * 50_000 || 200_000;

  const W = 720;
  const H = 220;
  const padL = 68;
  const padR = 16;
  const padT = 12;
  const padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const xAt = (i: number) => padL + (i / Math.max(1, slice.length - 1)) * plotW;
  const yAt = (v: number) => padT + plotH - (v / yMax) * plotH;

  // Area path: before (salaire) then after (rente) — continuous line
  const linePts = slice
    .map((pt, i) => `${xAt(i).toFixed(1)},${yAt(pt.revenu).toFixed(1)}`)
    .join(" ");
  const areaPath =
    `M ${xAt(0).toFixed(1)},${yAt(0).toFixed(1)} ` +
    slice
      .map((pt, i) => `L ${xAt(i).toFixed(1)},${yAt(pt.revenu).toFixed(1)}`)
      .join(" ") +
    ` L ${xAt(slice.length - 1).toFixed(1)},${yAt(0).toFixed(1)} Z`;

  // Split areas: green for salaire/transition start, red for rente
  const splitIdx = slice.findIndex((x) => x.phase === "rente");
  const split = splitIdx < 0 ? slice.length : splitIdx;

  const areaSeg = (from: number, to: number) => {
    if (to <= from) return "";
    const seg = slice.slice(from, to + 1);
    if (!seg.length) return "";
    const xs = seg.map((_, j) => xAt(from + j));
    const ys = seg.map((pt) => yAt(pt.revenu));
    let d = `M ${xs[0].toFixed(1)},${yAt(0).toFixed(1)} `;
    for (let j = 0; j < seg.length; j++) {
      d += `L ${xs[j].toFixed(1)},${ys[j].toFixed(1)} `;
    }
    d += `L ${xs[xs.length - 1].toFixed(1)},${yAt(0).toFixed(1)} Z`;
    return d;
  };

  const beforePath = areaSeg(0, Math.min(split, slice.length - 1));
  const afterPath =
    split < slice.length - 1
      ? areaSeg(Math.max(0, split - 1), slice.length - 1)
      : "";

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => {
    const v = yMax * t;
    const y = yAt(v);
    return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="#e8e8e8" stroke-width="1"/>
      <text x="${padL - 8}" y="${y + 3}" text-anchor="end" font-size="9" fill="#666" font-family="Calibri, Segoe UI, sans-serif">${formatAxisChf(v)}</text>`;
  });

  const xLabels = slice
    .map((pt, i) => {
      if (i % 2 !== 0 && slice.length > 8) return "";
      return `<text x="${xAt(i)}" y="${H - 6}" text-anchor="middle" font-size="8" fill="#666" font-family="Calibri, Segoe UI, sans-serif">${pt.year}</text>`;
    })
    .join("");

  // Amount callouts near mid of each phase
  const midBefore = Math.floor(Math.max(0, split - 1) / 2);
  const midAfter =
    split < slice.length
      ? Math.min(slice.length - 1, split + Math.floor((slice.length - split) / 2))
      : -1;
  const callouts = [
    midBefore >= 0
      ? `<text x="${xAt(midBefore)}" y="${yAt(slice[midBefore].revenu) - 8}" text-anchor="middle" font-size="9" font-weight="700" fill="${GREEN}" font-family="Calibri, Segoe UI, sans-serif">${formatChf(slice[midBefore].revenu)}</text>`
      : "",
    midAfter >= 0
      ? `<text x="${xAt(midAfter)}" y="${yAt(slice[midAfter].revenu) - 8}" text-anchor="middle" font-size="9" font-weight="700" fill="${BRAND}" font-family="Calibri, Segoe UI, sans-serif">${formatChf(slice[midAfter].revenu)}</text>`
      : "",
  ].join("");

  return `
  <div class="chart-wrap">
    <div class="chart-title">EVOLUTION REVENU APRÈS LA RETRAITE</div>
    <div class="chart-legend">
      <span><i class="sw before"></i> Revenu avant retraite (salaire brut)</span>
      <span><i class="sw after"></i> Revenu après retraite (rente brute AVS + LPP)</span>
    </div>
    <svg class="chart-svg" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Évolution revenu après retraite">
      <defs>
        <pattern id="hatchGreen" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="#d4ecd9"/>
          <line x1="0" y1="0" x2="0" y2="8" stroke="${GREEN_LIGHT}" stroke-width="3"/>
        </pattern>
        <pattern id="hatchRed" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(-45)">
          <rect width="8" height="8" fill="#f5d4d4"/>
          <line x1="0" y1="0" x2="0" y2="8" stroke="#c45c5c" stroke-width="3"/>
        </pattern>
      </defs>
      ${yTicks.join("\n")}
      ${beforePath ? `<path d="${beforePath}" fill="url(#hatchGreen)" opacity="0.95"/>` : ""}
      ${afterPath ? `<path d="${afterPath}" fill="url(#hatchRed)" opacity="0.95"/>` : `<path d="${areaPath}" fill="url(#hatchGreen)" opacity="0.9"/>`}
      <polyline points="${linePts}" fill="none" stroke="#555" stroke-width="1.2"/>
      ${callouts}
      ${xLabels}
    </svg>
  </div>`;
}

function formatAxisChf(n: number): string {
  return new Intl.NumberFormat("fr-CH", {
    maximumFractionDigits: 0,
  }).format(n);
}

function page3a(p: ReportPayload, n: number, total: number): string {
  const show = p.flags.showConjoint;
  const byPerson = {
    client1: p.thirdPillarRows.filter((r) => r.personKey === "client1"),
    conjoint: p.thirdPillarRows.filter((r) => r.personKey === "conjoint"),
  };
  const c1 = byPerson.client1[0];
  const c2 = byPerson.conjoint[0];
  const name1 = c1?.personName.split(" ")[0] || p.client1.displayName;
  const name2 = c2?.personName.split(" ")[0] || p.conjoint?.displayName || "";

  const row = (label: string, v1: string, v2?: string) =>
    `<tr><td class="lab">${esc(label)}</td><td class="val">${v1}</td>${show ? `<td class="val">${v2 ?? "—"}</td>` : ""}</tr>`;

  return `
  <div class="page-title">Analyse des contrats de prévoyance 3a</div>
  <table class="data kv${show ? "" : " one"}">
    <colgroup>
      <col class="lab" />
      <col class="val" />
      ${show ? `<col class="val" />` : ""}
    </colgroup>
    <tr><th class="lab"></th><th class="val">${esc(name1)}</th>${show ? `<th class="val">${esc(name2)}</th>` : ""}</tr>
    ${row("Compagnie", c1?.compagnie || "—", c2?.compagnie || "—")}
    ${row("N° de police", c1?.police || "—", c2?.police || "—")}
    ${row("Type de contrat", c1 ? "3a" : "—", c2 ? "3a" : "—")}
    ${row("Échéance", c1?.echeanceLabel || "—", c2?.echeanceLabel || "—")}
    ${row("Valeur garantie à l’échéance", c1 ? formatChf(c1.montant) : "—", c2 ? formatChf(c2.montant) : "—")}
    ${row("Primes annuelles", c1 ? formatChf(c1.prime) : "—", c2 ? formatChf(c2.prime) : "—")}
    ${row("Impôt (estim.)", c1?.impot != null ? formatChf(c1.impot) : "—", c2?.impot != null ? formatChf(c2.impot) : "—")}
    ${row("Capital net (estim.)", c1?.capitalNet != null ? formatChf(c1.capitalNet) : "—", c2?.capitalNet != null ? formatChf(c2.capitalNet) : "—")}
  </table>
  ${
    byPerson.client1.length > 1 || byPerson.conjoint.length > 1
      ? `<p class="note">Contrats saisis : assuré 1 = ${byPerson.client1.length}${show ? `, assuré 2 = ${byPerson.conjoint.length}` : ""}. Affichage : contrat principal.</p>`
      : ""
  }
  <p class="note">Analyse réalisée sur la base des données disponibles à ce jour.</p>
  ${footer(n, total)}`;
}

type WithdrawalPlanning = ReportPayload["withdrawalPlanning"];
type WithdrawalScenario = WithdrawalPlanning["scenarios"][number];

function capitalKindLabel(kind: string): string {
  if (kind === "lpp") return "2e pilier";
  if (kind === "libre_passage") return "Libre passage";
  if (kind === "3p") return "3e pilier";
  if (kind === "autre") return "Autre";
  return kind;
}

function assureLabel(titulaire: string): string {
  return titulaire === "conjoint" ? "Assuré 2" : "Assuré 1";
}

function scenarioBlock(sc: WithdrawalScenario): string {
  const rows = sc.byYear
    .map((y) => {
      const lines = y.lines?.length ? y.lines : [null];
      return lines
        .map((line, index) => {
          const tax =
            index === 0
              ? `<td class="num tax" rowspan="${lines.length}" style="vertical-align:top">${formatChf(y.impot)}</td><td class="num" rowspan="${lines.length}" style="vertical-align:top">${formatChf(y.net)}</td>`
              : "";
          const who = line ? assureLabel(line.titulaire) : "—";
          const kind = line ? capitalKindLabel(line.kind) : "—";
          const where = line ? line.institution || line.label || "—" : "—";
          const capital = line ? line.montantRetire : y.capitalRetire;
          return `<tr>
            <td class="lab">${y.year}</td>
            <td class="lab">${esc(who)}</td>
            <td class="lab">${esc(kind)}</td>
            <td class="lab">${esc(where)}</td>
            <td class="num">${formatChf(capital)}</td>
            ${tax}
          </tr>`;
        })
        .join("");
    })
    .join("");
  return `
  <div class="sec-title">${esc(sc.name)}</div>
  <table class="data">
    <colgroup>
      <col style="width:34%" />
      <col style="width:33%" />
      <col style="width:33%" />
    </colgroup>
    <tr>
      <th class="val">Capital retiré</th>
      <th class="val">Impôts ESTV</th>
      <th class="val">Capital net</th>
    </tr>
    <tr>
      <td class="num">${formatChf(sc.capitalRetireTotal)}</td>
      <td class="num tax">${formatChf(sc.impotTotal)}</td>
      <td class="num">${formatChf(sc.capitalNet)}</td>
    </tr>
  </table>
  <table class="data">
    <colgroup>
      <col style="width:10%" />
      <col style="width:14%" />
      <col style="width:16%" />
      <col style="width:24%" />
      <col style="width:12%" />
      <col style="width:12%" />
      <col style="width:12%" />
    </colgroup>
    <tr>
      <th class="lab">Année</th>
      <th class="lab">Assuré</th>
      <th class="lab">Prestation</th>
      <th class="lab">Institution / contrat</th>
      <th class="val">Capital retiré</th>
      <th class="val">Impôt</th>
      <th class="val">Net</th>
    </tr>
    ${rows || `<tr><td class="lab" colspan="7">—</td></tr>`}
  </table>`;
}

function yearSpan(years: number[]): string {
  const unique = [...new Set(years)].filter((y) => Number.isFinite(y)).sort((a, b) => a - b);
  if (!unique.length) return "";
  if (unique.length === 1) return String(unique[0]);
  return `${unique[0]} et ${unique[unique.length - 1]}`;
}

function planningConclusion(wp: WithdrawalPlanning): string {
  const c = wp.comparisons[0];
  if (!c) return "";
  const from = wp.scenarios.find((s) => s.name === c.fromName);
  const to = wp.scenarios.find((s) => s.name === c.toName);
  const fromYears = (from?.byYear ?? []).map((y) => y.year);
  const toYears = (to?.byYear ?? []).map((y) => y.year);
  const fromSpan = yearSpan(fromYears);
  const toSpan = yearSpan(toYears);
  const fromName = esc(c.fromName);
  const toName = esc(c.toName);
  if (c.deltaImpot == null || c.deltaCapitalNet == null) {
    return `Comparaison entre « ${fromName} » et « ${toName} » : les écarts d’impôt ou de capital net ne sont pas disponibles.`;
  }
  const spread = toYears.length > fromYears.length && c.deltaImpot < 0;
  if (spread) {
    const when = toYears.length > 1 ? `entre ${toSpan}` : `en ${toSpan}`;
    const vs =
      fromYears.length <= 1
        ? `un retrait regroupé${fromSpan ? ` en ${fromSpan}` : " sur une seule année"}`
        : `« ${fromName} »${fromSpan ? ` (${fromSpan})` : ""}`;
    return `En répartissant les retraits ${when}, l’imposition est réduite de ${formatChf(Math.abs(c.deltaImpot))}, ce qui permet un gain net de ${formatChf(Math.abs(c.deltaCapitalNet))} par rapport à ${vs}.`;
  }
  const taxPhrase =
    c.deltaImpot === 0
      ? "l’imposition est identique"
      : c.deltaImpot < 0
        ? `l’imposition est réduite de ${formatChf(Math.abs(c.deltaImpot))}`
        : `l’imposition augmente de ${formatChf(Math.abs(c.deltaImpot))}`;
  const netPhrase =
    c.deltaCapitalNet === 0
      ? "le capital net est identique"
      : c.deltaCapitalNet > 0
        ? `le capital net augmente de ${formatChf(c.deltaCapitalNet)}`
        : `le capital net diminue de ${formatChf(Math.abs(c.deltaCapitalNet))}`;
  const fromBit = fromSpan ? ` (${fromSpan})` : "";
  const toBit = toSpan ? ` (${toSpan})` : "";
  return `Entre « ${fromName} »${fromBit} et « ${toName} »${toBit}, ${taxPhrase} et ${netPhrase}.`;
}

function planningScenariosHtml(sc: WithdrawalScenario): string {
  return `
  <div class="page-title">Planification des retraits de capitaux</div>
  ${scenarioBlock(sc)}`;
}

function planningGapsHtml(wp: WithdrawalPlanning): string {
  const rows = wp.comparisons
    .map(
      (c) => `<tr>
        <td class="lab">${esc(c.fromName)} → ${esc(c.toName)}${c.warning ? `<div class="note">${esc(c.warning)}</div>` : ""}</td>
        <td class="num tax">${formatChf(c.deltaImpot)}</td>
        <td class="num">${formatChf(c.deltaCapitalNet)}</td>
      </tr>`,
    )
    .join("");
  return `
  <div class="page-title">Planification des retraits de capitaux</div>
  <div class="sec-title">Écarts entre scénarios</div>
  <table class="data">
    <colgroup>
      <col style="width:52%" />
      <col style="width:24%" />
      <col style="width:24%" />
    </colgroup>
    <tr>
      <th class="lab">Comparaison</th>
      <th class="val">Δ Impôt</th>
      <th class="val">Δ Capital net</th>
    </tr>
    ${rows}
  </table>
  <div class="sec-title">Conclusion</div>
  <p class="plain">${planningConclusion(wp)}</p>`;
}

function withdrawalPlanningPages(
  p: ReportPayload,
  next: () => number,
  total: number,
): string[] {
  const wp = p.withdrawalPlanning;
  const pages = wp.scenarios.map(
    (sc) => `${planningScenariosHtml(sc)}${footer(next(), total)}`,
  );
  if (wp.comparisons.length) {
    pages.push(`${planningGapsHtml(wp)}${footer(next(), total)}`);
  }
  return pages;
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
        `<tr><td>${esc(e.label)}</td><td class="num">${formatChf(e.amount)}${e.kind === "avs" ? " /an" : ""}</td></tr>`,
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
  const row = (label: string, values: string[]) =>
    `<tr><td class="lab">${label}</td>${values.map((v) => `<td class="num">${v}</td>`).join("")}</tr>`;
  const showDuree = cols.some((c) => c.dureeAnnees != null);
  const head = cols
    .map((c) => `<th>${esc(c.label)}</th>`)
    .join("");
  const lines = [
    row("Capital placé", cols.map((c) => money(c.capitalPlace))),
    row("Compagnie", cols.map((c) => esc(c.compagnie || "—"))),
    row("Type de rente", cols.map((c) => esc(c.typeLabel))),
    row("Rente AVS", cols.map((c) => money(c.renteAvs))),
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
  <p class="note">Le revenu fiscal imposable suit la règle de l’offre (rente certaine ou viagère) et sert uniquement au calcul ESTV. Il est distinct du revenu total encaissé.</p>
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
  const renteLpp = cell(
    cols.map((c) =>
      c.id === "lpp" ? formatChf(p.aggregates.renteLppTotal) : formatChf(0),
    ),
  );
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
    <tr><td>Rente LPP</td>${renteLpp}</tr>
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

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
