import { formatDateFr } from "../rules/avs-age";
import { formatChf, formatPct, personDisplayName } from "../mappers";
import type { AnalyseRecord } from "../types";

/**
 * Moteur de rapport — preview HTML (pas de PDF définitif en Phase 2).
 * Structure basée sur ANALYSE RETRAITE de l’inventaire.
 */
export class RetirementReportService {
  renderHtml(record: AnalyseRecord): string {
    const { input, results } = record;
    if (!results) {
      return wrapHtml(
        "<p>Aucun résultat calculé. Lancez d’abord le calcul depuis le formulaire.</p>",
      );
    }

    const c1 = input.client1;
    const c2 = input.conjoint;
    const r1 = results.client1;
    const r2 = results.conjoint;
    const couple1 = results.incomeScenarios.find((s) => s.foyer === "Couple1");

    const sections: string[] = [];

    sections.push(`
      <header class="cover">
        <p class="brand">Analyse de prévoyance</p>
        <h1>Rapport de prévisualisation</h1>
        <p class="meta">Client : <strong>${esc(personDisplayName(c1))}</strong>
          ${input.etatCivil === "Marié(e)" && c2 ? ` &amp; <strong>${esc(personDisplayName(c2))}</strong>` : ""}</p>
        <p class="meta">Conseiller : ${esc(input.conseillerNom || "—")} · ${esc(formatDateFr(new Date()))}</p>
        <p class="meta muted">Document HTML de prévisualisation — PDF définitif non généré (Phase 2).</p>
      </header>
    `);

    sections.push(`
      <section>
        <h2>1. Profil des assurés</h2>
        <table>
          <thead><tr><th></th><th>Assuré 1</th>${r2 ? "<th>Assuré 2</th>" : ""}</tr></thead>
          <tbody>
            <tr><td>Nom</td><td>${esc(personDisplayName(c1))}</td>${r2 ? `<td>${esc(personDisplayName(c2!))}</td>` : ""}</tr>
            <tr><td>Situation</td><td colspan="${r2 ? 2 : 1}">${esc(input.etatCivil)} · ${esc(input.villeRecherche || "—")}</td></tr>
            <tr><td>Naissance</td><td>${esc(c1.dateNaissance ? formatDateFr(c1.dateNaissance) : "—")}</td>${r2 ? `<td>${esc(c2!.dateNaissance ? formatDateFr(c2!.dateNaissance) : "—")}</td>` : ""}</tr>
            <tr><td>Revenu brut / an</td><td>${formatChf(input.salaireClient1)}</td>${r2 ? `<td>${formatChf(input.salaireConjoint)}</td>` : ""}</tr>
          </tbody>
        </table>
      </section>
    `);

    sections.push(`
      <section>
        <h2>2. Hypothèse de planification</h2>
        <table>
          <thead><tr><th></th><th>Assuré 1</th>${r2 ? "<th>Assuré 2</th>" : ""}</tr></thead>
          <tbody>
            <tr><td>Âge légal AVS</td><td>${esc(r1.ageLegalLabel)}</td>${r2 ? `<td>${esc(r2.ageLegalLabel)}</td>` : ""}</tr>
            <tr><td>Date de départ</td><td>${esc(formatDateFr(r1.dateDepart))}</td>${r2 ? `<td>${esc(formatDateFr(r2.dateDepart))}</td>` : ""}</tr>
          </tbody>
        </table>
      </section>
    `);

    sections.push(`
      <section>
        <h2>3. Patrimoine de prévoyance actuel</h2>
        <table>
          <thead><tr><th></th><th>Assuré 1</th>${r2 ? "<th>Assuré 2</th>" : ""}</tr></thead>
          <tbody>
            <tr><td>AVS annuelle estimée</td><td>${formatChf(r1.avsAnnuel)}</td>${r2 ? `<td>${formatChf(r2.avsAnnuel)}</td>` : ""}</tr>
            <tr><td>Capital LPP (65)</td><td>${formatChf(r1.capitalLpp65)}</td>${r2 ? `<td>${formatChf(r2.capitalLpp65)}</td>` : ""}</tr>
            <tr><td>Rente LPP (65)</td><td>${formatChf(r1.renteLpp65)}</td>${r2 ? `<td>${formatChf(r2.renteLpp65)}</td>` : ""}</tr>
            <tr><td>3e pilier (total)</td><td>${formatChf(r1.total3ePilier)}</td>${r2 ? `<td>${formatChf(r2.total3ePilier)}</td>` : ""}</tr>
          </tbody>
        </table>
      </section>
    `);

    sections.push(`
      <section>
        <h2>4. Synthèse des prestations attendues (65)</h2>
        <ul>
          <li>Rente totale assuré 1 : <strong>${formatChf(r1.renteTotale65)}</strong></li>
          ${r2 ? `<li>Rente totale assuré 2 : <strong>${formatChf(r2.renteTotale65)}</strong></li>` : ""}
          <li>Commune fiscale : ${esc(input.villeRecherche || "—")} (TaxLocationID ${results.taxLocation?.TaxLocationID ?? "—"})</li>
        </ul>
      </section>
    `);

    const capital65 = results.capitalScenarios.find((s) => s.age === 65);
    sections.push(`
      <section>
        <h2>5. Comparaison rente vs capital</h2>
        <table>
          <thead><tr><th>Indicateur</th><th>Montant</th></tr></thead>
          <tbody>
            <tr><td>Capital LPP 65 brut</td><td>${formatChf(capital65?.capital)}</td></tr>
            <tr><td>Impôt capital (ESTV)</td><td>${formatChf(capital65?.impot)}</td></tr>
            <tr><td>Capital net</td><td>${formatChf(capital65?.net)}</td></tr>
            <tr><td>Impôt revenu foyer (Couple1)</td><td>${formatChf(couple1?.impot?.impotRevenuTotal)}</td></tr>
            <tr><td>— dont IFD</td><td>${formatChf(couple1?.impot?.impotFederal)}</td></tr>
            <tr><td>— dont canton</td><td>${formatChf(couple1?.impot?.impotCanton)}</td></tr>
            <tr><td>— dont commune</td><td>${formatChf(couple1?.impot?.impotCommune)}</td></tr>
          </tbody>
        </table>
      </section>
    `);

    sections.push(`
      <section>
        <h2>6. Indicateurs maintien niveau de vie</h2>
        <table>
          <tbody>
            <tr><td>Salaire avant retraite</td><td>${formatChf(results.lacune.salaireAvant)}</td></tr>
            <tr><td>Revenu après (AVS+LPP 65)</td><td>${formatChf(results.lacune.revenuApres)}</td></tr>
            <tr><td>Lacune</td><td>${formatChf(results.lacune.lacune)}</td></tr>
            <tr><td>Manque pour 80 %</td><td>${formatChf(results.lacune.manquePour80)}</td></tr>
            <tr><td>Taux de remplacement</td><td>${formatPct(results.lacune.tauxRemplacementReel)} (cible ${formatPct(results.lacune.tauxRemplacementCible)})</td></tr>
          </tbody>
        </table>
      </section>
    `);

    if (c1.troisiemePilier.length) {
      sections.push(`
        <section>
          <h2>7. Analyse contrats 3a</h2>
          <table>
            <thead><tr><th>Compagnie</th><th>Police</th><th>Échéance</th><th>Montant</th><th>Prime</th></tr></thead>
            <tbody>
              ${c1.troisiemePilier
                .map(
                  (t) => `<tr>
                    <td>${esc(t.compagnie)}</td>
                    <td>${esc(t.police)}</td>
                    <td>${esc(t.echeance)}</td>
                    <td>${formatChf(t.montant)}</td>
                    <td>${formatChf(t.prime)}</td>
                  </tr>`,
                )
                .join("")}
            </tbody>
          </table>
          ${
            results.thirdPillarTax
              ? `<p>Impôt estimé sur total 3P (${formatChf(results.thirdPillarTax.capital)}) : <strong>${formatChf(results.thirdPillarTax.impotTotal)}</strong></p>`
              : ""
          }
        </section>
      `);
    }

    sections.push(`
      <section>
        <h2>8. Comparatif capitaux par âge 65→60</h2>
        <table>
          <thead><tr><th>Âge</th><th>Capital</th><th>Impôt</th><th>Net</th><th>Rente</th></tr></thead>
          <tbody>
            ${results.capitalScenarios
              .map(
                (s) => `<tr>
                  <td>${s.age}</td>
                  <td>${formatChf(s.capital)}</td>
                  <td>${s.error ? esc(s.error) : formatChf(s.impot)}</td>
                  <td>${formatChf(s.net)}</td>
                  <td>${formatChf(s.rente)}</td>
                </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    `);

    sections.push(`
      <section>
        <h2>9. Scénarios d’impôt sur les rentes</h2>
        <table>
          <thead><tr><th>Foyer</th><th>Âge</th><th>Revenu 1</th><th>Revenu 2</th><th>Impôt total</th></tr></thead>
          <tbody>
            ${results.incomeScenarios
              .map(
                (s) => `<tr>
                  <td>${esc(s.foyer)} — ${esc(s.label)}</td>
                  <td>${s.age}</td>
                  <td>${formatChf(s.revenu1)}</td>
                  <td>${formatChf(s.revenu2)}</td>
                  <td>${s.error ? esc(s.error) : formatChf(s.impot?.impotRevenuTotal)}</td>
                </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    `);

    if (results.errors.length) {
      sections.push(`
        <section class="warn">
          <h2>Alertes</h2>
          <ul>${results.errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
        </section>
      `);
    }

    return wrapHtml(sections.join("\n"));
  }
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function wrapHtml(body: string): string {
  return `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Prévisualisation — Analyse de prévoyance</title>
  <style>
    :root {
      --ink: #1a2332;
      --muted: #5a6575;
      --line: #d5dbe3;
      --bg: #f4f6f8;
      --accent: #0d5c63;
      --paper: #ffffff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Source Serif 4", "Libre Baskerville", Georgia, serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.45;
    }
    .page {
      max-width: 880px;
      margin: 0 auto;
      padding: 2rem 1.25rem 4rem;
    }
    .cover {
      background: linear-gradient(160deg, #0d5c63 0%, #1a3344 70%);
      color: #f7fafb;
      padding: 2rem 1.5rem;
      margin-bottom: 1.5rem;
      border-radius: 4px;
    }
    .brand { letter-spacing: 0.08em; text-transform: uppercase; font-size: 0.8rem; opacity: 0.85; margin: 0 0 0.5rem; font-family: system-ui, sans-serif; }
    h1 { margin: 0 0 0.75rem; font-size: 1.75rem; font-weight: 600; }
    h2 { font-size: 1.15rem; color: var(--accent); border-bottom: 1px solid var(--line); padding-bottom: 0.35rem; margin: 1.75rem 0 0.75rem; }
    .meta { margin: 0.25rem 0; font-family: system-ui, sans-serif; font-size: 0.95rem; }
    .muted { opacity: 0.8; font-size: 0.85rem; }
    section {
      background: var(--paper);
      padding: 0.5rem 1.25rem 1.25rem;
      margin-bottom: 0.75rem;
      border: 1px solid var(--line);
      border-radius: 4px;
    }
    table { width: 100%; border-collapse: collapse; font-family: system-ui, sans-serif; font-size: 0.9rem; }
    th, td { text-align: left; padding: 0.45rem 0.4rem; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
    ul { font-family: system-ui, sans-serif; }
    .warn { border-color: #c45c26; }
    @media print {
      body { background: white; }
      .page { padding: 0; }
      section, .cover { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <div class="page">${body}</div>
</body>
</html>`;
}

export const retirementReportService = new RetirementReportService();
