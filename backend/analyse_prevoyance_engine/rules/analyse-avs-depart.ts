/**
 * Comparatif AVS individuel : départs à 63, 64 et 65 ans.
 * Un seul calcul pour l'écran et le PDF. Aucune somme de couple,
 * aucun pourcentage de réduction appliqué aux montants saisis.
 *
 * Annuel = mensuel × 13. Le cumul est nominal, sans impôt ni rendement.
 */
import { formatLegalAgeLabel, getLegalRetirementAge } from "./avs-age";

export const AVS_VERSEMENTS_PAR_AN = 13;
export const AVS_AGE_REFERENCE = 65;
export const AVS_HORIZON_GRAPHIQUE = 90;
export const COULEUR_DEPART_63 = "#C4A36A";
export const COULEUR_DEPART_64 = "#E29AAD";
export const COULEUR_DEPART_65 = "#800000";

const DEPARTS = [63, 64, 65] as const;
export type AgeDepartAvs = (typeof DEPARTS)[number];

export interface AvsDepartSaisie {
  mensuel63Avant65?: number | null;
  mensuel63Des65?: number | null;
  mensuel64Avant65?: number | null;
  mensuel64Des65?: number | null;
  mensuel65?: number | null;
}

export interface PersonneAvsDepart {
  prenom?: string | null;
  nom?: string | null;
  civilite?: string | null;
  dateNaissance?: string | null;
  avsMensuel?: number | null;
  avsRentesAnticipees?: Array<{
    age?: number | null;
    montantAnnuel?: number | null;
  }> | null;
  avsDepart?: AvsDepartSaisie | null;
}

export type CelluleAvs =
  | { kind: "montant"; valeur: number; fort?: boolean }
  | { kind: "texte"; valeur: string; fort?: boolean }
  | { kind: "vide" }
  | { kind: "manquant" };

export interface EquilibreAvs {
  kind: "reference" | "manquant" | "non-atteint" | "age";
  age?: number;
  horsPeriode?: boolean;
}

export interface ScenarioAvs {
  depart: AgeDepartAvs;
  anneesAnticipation: 0 | 1 | 2;
  mensuelAvant: number | null;
  mensuelDes65: number | null;
  annuelAvant: number | null;
  annuelDes65: number | null;
  recuAvant65: number | null;
  ecartMensuel: number | null;
  equilibre: EquilibreAvs;
  courbe: boolean;
}

export interface PointCumulAvs {
  age: number;
  cumul: number;
}

export interface CourbeCumulAvs {
  depart: AgeDepartAvs;
  couleur: string;
  points: PointCumulAvs[];
}

export interface MarqueEquilibreAvs {
  depart: 63 | 64;
  age: number;
  cumul: number;
  etiquette: string;
}

export interface AnalyseAvsPersonne {
  prenom: string;
  nom: string;
  nomComplet: string;
  ageLegal: number | null;
  avertissementAgeLegal: string | null;
  scenarios: [ScenarioAvs, ScenarioAvs, ScenarioAvs];
  courbes: CourbeCumulAvs[];
  marques: MarqueEquilibreAvs[];
  yMax: number;
}

export function annuelAvs(mensuel: number): number {
  return mensuel * AVS_VERSEMENTS_PAR_AN;
}

export function formatChfAvs(valeur: number): string {
  return new Intl.NumberFormat("fr-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(Math.round(valeur));
}

/** Affichage du tableau : 78,965 → « 79,0 ans ». */
export function formatAgeEquilibre(age: number): string {
  const arrondi = Math.round(age * 10) / 10;
  return `${arrondi.toFixed(1).replace(".", ",")} ans`;
}

/** Étiquette du graphique : années et mois, sans inventer un âge. */
export function formatAgeAnneesMois(age: number): string {
  let annees = Math.floor(age + 1e-9);
  let mois = Math.round((age - annees) * 12);
  if (mois === 12) {
    annees += 1;
    mois = 0;
  }
  if (mois <= 0) return `${annees} ans`;
  return `${annees} ans et ${mois} mois`;
}

export function cumulAvs(scenario: ScenarioAvs, age: number): number | null {
  if (!scenario.courbe || scenario.mensuelDes65 == null) return null;
  if (age < scenario.depart) return 0;
  const annuelApres = annuelAvs(scenario.mensuelDes65);
  if (scenario.depart === AVS_AGE_REFERENCE) {
    return (age - AVS_AGE_REFERENCE) * annuelApres;
  }
  if (scenario.mensuelAvant == null || scenario.annuelAvant == null) return null;
  if (age <= AVS_AGE_REFERENCE) {
    return (age - scenario.depart) * scenario.annuelAvant;
  }
  const avant = (AVS_AGE_REFERENCE - scenario.depart) * scenario.annuelAvant;
  return avant + (age - AVS_AGE_REFERENCE) * annuelApres;
}

/**
 * Âge où le cumul de référence rejoint le cumul anticipé.
 * Null si les données manquent, si le rattrapage est impossible,
 * ou si l'avance est nulle (ce n'est pas un équilibre à 0 an).
 */
export function ageEquilibreAvs(
  anticipe: ScenarioAvs,
  reference: ScenarioAvs,
): EquilibreAvs {
  if (
    !anticipe.courbe ||
    !reference.courbe ||
    anticipe.recuAvant65 == null ||
    anticipe.annuelDes65 == null ||
    reference.annuelDes65 == null
  ) {
    return { kind: "manquant" };
  }
  const ecartAnnuel = reference.annuelDes65 - anticipe.annuelDes65;
  if (anticipe.recuAvant65 <= 0) return { kind: "non-atteint" };
  if (ecartAnnuel <= 0) return { kind: "non-atteint" };
  const age = AVS_AGE_REFERENCE + anticipe.recuAvant65 / ecartAnnuel;
  if (!Number.isFinite(age) || age <= 0) return { kind: "non-atteint" };
  return {
    kind: "age",
    age,
    horsPeriode: age > AVS_HORIZON_GRAPHIQUE,
  };
}

export function libelleEquilibre(equilibre: EquilibreAvs): string {
  if (equilibre.kind === "reference") return "Référence";
  if (equilibre.kind === "manquant") return "Calcul impossible – données manquantes";
  if (equilibre.kind === "non-atteint") return "Non atteint";
  const age = formatAgeEquilibre(equilibre.age ?? 0);
  if (equilibre.horsPeriode) return `${age} — hors de la période représentée`;
  return age;
}

function montantSaisi(valeur: number | null | undefined): number | null {
  if (valeur == null || !Number.isFinite(valeur) || valeur < 0) return null;
  return valeur;
}

/** Repli uniquement pour un montant déjà enregistré ailleurs. Jamais la rente d'après 65. */
export function suggestionAvsDepart(personne: PersonneAvsDepart): AvsDepartSaisie {
  const suggestion: AvsDepartSaisie = {};
  const reference = montantSaisi(personne.avsMensuel);
  if (reference != null && reference > 0) suggestion.mensuel65 = reference;
  for (const ligne of personne.avsRentesAnticipees || []) {
    const annuel = montantSaisi(ligne.montantAnnuel);
    if (annuel == null || annuel <= 0) continue;
    const mensuel = Math.round((annuel / AVS_VERSEMENTS_PAR_AN) * 100) / 100;
    if (ligne.age === 63) suggestion.mensuel63Avant65 = mensuel;
    if (ligne.age === 64) suggestion.mensuel64Avant65 = mensuel;
  }
  return suggestion;
}

function lireMontant(
  stocke: number | null | undefined,
  suggestion: number | null | undefined,
): number | null {
  if (stocke === null) return null;
  const saisi = montantSaisi(stocke);
  if (saisi != null) return saisi;
  return montantSaisi(suggestion);
}

function scenarioDe(
  depart: AgeDepartAvs,
  mensuelAvant: number | null,
  mensuelDes65: number | null,
  reference: number | null,
): ScenarioAvs {
  const anneesAnticipation = (AVS_AGE_REFERENCE - depart) as 0 | 1 | 2;
  if (depart === AVS_AGE_REFERENCE) {
    const annuelDes65 = mensuelDes65 == null ? null : annuelAvs(mensuelDes65);
    return {
      depart,
      anneesAnticipation: 0,
      mensuelAvant: null,
      mensuelDes65,
      annuelAvant: null,
      annuelDes65,
      recuAvant65: 0,
      ecartMensuel: null,
      equilibre: { kind: "reference" },
      courbe: mensuelDes65 != null,
    };
  }
  const annuelAvant = mensuelAvant == null ? null : annuelAvs(mensuelAvant);
  const annuelDes65 = mensuelDes65 == null ? null : annuelAvs(mensuelDes65);
  const recuAvant65 = annuelAvant == null ? null : annuelAvant * anneesAnticipation;
  const ecartMensuel =
    mensuelAvant == null || reference == null ? null : reference - mensuelAvant;
  const brouillon: ScenarioAvs = {
    depart,
    anneesAnticipation,
    mensuelAvant,
    mensuelDes65,
    annuelAvant,
    annuelDes65,
    recuAvant65,
    ecartMensuel,
    equilibre: { kind: "manquant" },
    courbe: mensuelAvant != null && mensuelDes65 != null,
  };
  return brouillon;
}

export function buildAnalyseAvsPersonne(personne: PersonneAvsDepart): AnalyseAvsPersonne {
  const suggestion = suggestionAvsDepart(personne);
  const saisie = personne.avsDepart || {};
  const m63Avant = lireMontant(saisie.mensuel63Avant65, suggestion.mensuel63Avant65);
  const m63Apres = lireMontant(saisie.mensuel63Des65, null);
  const m64Avant = lireMontant(saisie.mensuel64Avant65, suggestion.mensuel64Avant65);
  const m64Apres = lireMontant(saisie.mensuel64Des65, null);
  const m65 = lireMontant(saisie.mensuel65, suggestion.mensuel65);

  const s63 = scenarioDe(63, m63Avant, m63Apres, m65);
  const s64 = scenarioDe(64, m64Avant, m64Apres, m65);
  const s65 = scenarioDe(65, null, m65, m65);
  s63.equilibre = ageEquilibreAvs(s63, s65);
  s64.equilibre = ageEquilibreAvs(s64, s65);

  const scenarios: [ScenarioAvs, ScenarioAvs, ScenarioAvs] = [s63, s64, s65];
  const courbes = scenarios.filter((scenario) => scenario.courbe).map(courbeDe);
  const marques = marquesDe(scenarios);
  const yMax = Math.max(
    1,
    ...courbes.flatMap((courbe) => courbe.points.map((point) => point.cumul)),
  );

  const prenom = texte(personne.prenom);
  const nom = texte(personne.nom);
  const nomComplet = `${prenom} ${nom}`.trim();
  const ageLegal = ageLegalDe(personne);

  return {
    prenom,
    nom,
    nomComplet,
    ageLegal,
    avertissementAgeLegal:
      ageLegal != null && ageLegal !== AVS_AGE_REFERENCE
        ? `L'âge légal AVS de cette personne est de ${formatLegalAgeLabel(ageLegal)}. 65 ans n'est pas présenté comme son âge légal de référence.`
        : null,
    scenarios,
    courbes,
    marques,
    yMax,
  };
}

const CLES_ANTICIPATION = [
  "mensuel63Avant65",
  "mensuel63Des65",
  "mensuel64Avant65",
  "mensuel64Des65",
] as const;

function montantPositif(valeur: number | null | undefined): boolean {
  return valeur != null && Number.isFinite(Number(valeur)) && Number(valeur) > 0;
}

/**
 * Page PDF seulement si une rente anticipée a été écrite.
 * La rente habituelle, et sa recopie automatique en mensuel65, ne comptent pas.
 */
export function anticipationAvsRenseignee(personne: PersonneAvsDepart | null | undefined): boolean {
  if (!personne) return false;
  const saisie = personne.avsDepart || {};
  for (const cle of CLES_ANTICIPATION) {
    if (montantPositif(saisie[cle])) return true;
  }
  if ((personne.avsRentesAnticipees || []).some((ligne) => montantPositif(ligne.montantAnnuel))) {
    return true;
  }
  if (!montantPositif(saisie.mensuel65)) return false;
  const recopié = suggestionAvsDepart({
    avsMensuel: personne.avsMensuel,
    avsRentesAnticipees: personne.avsRentesAnticipees,
  }).mensuel65;
  return recopié == null || Number(saisie.mensuel65) !== Number(recopié);
}

export function analysesAvsDuDossier(
  client: PersonneAvsDepart,
  conjoint: PersonneAvsDepart | null | undefined,
  inclureConjoint: boolean,
): AnalyseAvsPersonne[] {
  const pages: AnalyseAvsPersonne[] = [];
  if (anticipationAvsRenseignee(client)) pages.push(buildAnalyseAvsPersonne(client));
  if (inclureConjoint && conjoint && anticipationAvsRenseignee(conjoint)) {
    pages.push(buildAnalyseAvsPersonne(conjoint));
  }
  return pages;
}

function courbeDe(scenario: ScenarioAvs): CourbeCumulAvs {
  const couleur =
    scenario.depart === 63
      ? COULEUR_DEPART_63
      : scenario.depart === 64
        ? COULEUR_DEPART_64
        : COULEUR_DEPART_65;
  const points: PointCumulAvs[] = [];
  for (let age = scenario.depart; age <= AVS_HORIZON_GRAPHIQUE; age += 1) {
    const cumul = cumulAvs(scenario, age);
    if (cumul == null) continue;
    points.push({ age, cumul });
  }
  return { depart: scenario.depart, couleur, points };
}

function marquesDe(scenarios: ScenarioAvs[]): MarqueEquilibreAvs[] {
  const marques: MarqueEquilibreAvs[] = [];
  for (const scenario of scenarios) {
    if (scenario.depart === 65) continue;
    const equilibre = scenario.equilibre;
    if (equilibre.kind !== "age" || equilibre.horsPeriode || equilibre.age == null) continue;
    const cumul = cumulAvs(scenario, equilibre.age);
    if (cumul == null) continue;
    marques.push({
      depart: scenario.depart,
      age: equilibre.age,
      cumul,
      etiquette: `Âge d'équilibre – Départ à ${scenario.depart} ans : ${formatAgeAnneesMois(equilibre.age)}`,
    });
  }
  return marques;
}

function ageLegalDe(personne: PersonneAvsDepart): number | null {
  if (!personne.dateNaissance || !/^\d{4}-\d{2}-\d{2}/.test(personne.dateNaissance)) {
    return null;
  }
  const civilite = personne.civilite === "Madame" ? "Madame" : "Monsieur";
  const age = getLegalRetirementAge(civilite, personne.dateNaissance);
  return Number.isFinite(age) ? age : null;
}

function texte(valeur: string | null | undefined): string {
  return String(valeur || "").trim();
}

function echap(valeur: string): string {
  return valeur
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function celluleMontant(valeur: number | null, fort = false): CelluleAvs {
  if (valeur == null) return { kind: "manquant" };
  return { kind: "montant", valeur, fort };
}

function celluleCalculee(valeur: number | null, fort = false): CelluleAvs {
  if (valeur == null) {
    return { kind: "texte", valeur: "Calcul impossible – données manquantes" };
  }
  return { kind: "montant", valeur, fort };
}

function htmlCellule(cellule: CelluleAvs): string {
  if (cellule.kind === "vide") return "—";
  if (cellule.kind === "manquant") return "À compléter";
  if (cellule.kind === "texte") {
    return cellule.fort ? `<strong>${echap(cellule.valeur)}</strong>` : echap(cellule.valeur);
  }
  const texteMontant = formatChfAvs(cellule.valeur);
  return cellule.fort ? `<strong>${echap(texteMontant)}</strong>` : echap(texteMontant);
}

function ligneTableau(libelle: string, cellules: CelluleAvs[]): string {
  return `<tr><th>${echap(libelle)}</th>${cellules
    .map((cellule) => `<td>${htmlCellule(cellule)}</td>`)
    .join("")}</tr>`;
}

export function renderAnalyseAvsHtml(model: AnalyseAvsPersonne): string {
  const [s63, s64, s65] = model.scenarios;
  const titre = model.nomComplet
    ? `Analyse AVS – ${model.nomComplet}`
    : "Analyse AVS";
  const avertissement = model.avertissementAgeLegal
    ? `<p class="avs-depart-avert">${echap(model.avertissementAgeLegal)}</p>`
    : "";
  const tableauRentes = `
    <h2 class="avs-depart-h">RENTE AVS – COMPARAISON DES ÂGES DE DÉPART</h2>
    <table class="avs-depart">
      <thead><tr>
        <th>Informations</th>
        <th>Départ à 63 ans</th>
        <th>Départ à 64 ans</th>
        <th>Départ à 65 ans</th>
      </tr></thead>
      <tbody>
        ${ligneTableau("Rente mensuelle pendant l'anticipation", [
          celluleMontant(s63.mensuelAvant),
          celluleMontant(s64.mensuelAvant),
          { kind: "vide" },
        ])}
        ${ligneTableau("Rente annuelle pendant l'anticipation (13 versements)", [
          celluleMontant(s63.annuelAvant, true),
          celluleMontant(s64.annuelAvant, true),
          { kind: "vide" },
        ])}
        ${ligneTableau("Rente mensuelle dès 65 ans", [
          celluleMontant(s63.mensuelDes65),
          celluleMontant(s64.mensuelDes65),
          celluleMontant(s65.mensuelDes65),
        ])}
        ${ligneTableau("Rente annuelle dès 65 ans (13 versements)", [
          celluleMontant(s63.annuelDes65, true),
          celluleMontant(s64.annuelDes65, true),
          celluleMontant(s65.annuelDes65, true),
        ])}
      </tbody>
    </table>`;
  const tableauAnalyse = `
    <h2 class="avs-depart-h">ANALYSE DE L'ANTICIPATION AVS</h2>
    <table class="avs-depart">
      <thead><tr>
        <th>Indicateur</th>
        <th>Départ à 63 ans</th>
        <th>Départ à 64 ans</th>
        <th>Départ à 65 ans</th>
      </tr></thead>
      <tbody>
        ${ligneTableau("Années d'anticipation", [
          { kind: "texte", valeur: "2" },
          { kind: "texte", valeur: "1" },
          { kind: "texte", valeur: "0" },
        ])}
        ${ligneTableau("Rentes reçues avant 65 ans", [
          celluleCalculee(s63.recuAvant65, true),
          celluleCalculee(s64.recuAvant65, true),
          { kind: "montant", valeur: 0, fort: true },
        ])}
        ${ligneTableau("Rente mensuelle dès 65 ans", [
          celluleMontant(s63.mensuelDes65),
          celluleMontant(s64.mensuelDes65),
          celluleMontant(s65.mensuelDes65),
        ])}
        ${ligneTableau("Rente annuelle dès 65 ans", [
          celluleMontant(s63.annuelDes65, true),
          celluleMontant(s64.annuelDes65, true),
          celluleMontant(s65.annuelDes65, true),
        ])}
        ${ligneTableau("Âge d'équilibre estimé", [
          { kind: "texte", valeur: libelleEquilibre(s63.equilibre), fort: true },
          { kind: "texte", valeur: libelleEquilibre(s64.equilibre), fort: true },
          { kind: "texte", valeur: "Référence" },
        ])}
        ${ligneTableau("Écart mensuel au départ vs départ à 65 ans", [
          celluleCalculee(s63.ecartMensuel),
          celluleCalculee(s64.ecartMensuel),
          { kind: "vide" },
        ])}
      </tbody>
    </table>`;
  return `
    <style>${STYLES}</style>
    <div class="avs-depart-page" data-avs-personne="${echap(model.nomComplet)}">
      <div class="page-title">${echap(titre)}</div>
      ${avertissement}
      ${tableauRentes}
      ${tableauAnalyse}
      ${renderGraphique(model)}
    </div>`;
}

const STYLES = `
.avs-depart-page { color: #1a1a1a; }
.avs-depart-page .page-title {
  font-size: 12.5pt; font-weight: 700; letter-spacing: 0.04em;
  margin: 0 0 8px; text-transform: uppercase;
}
.avs-depart-avert {
  margin: 0 0 8px; padding: 6px 8px; background: #fff7ed; color: #9a3412;
  font-size: 8.5pt; border: 1px solid #fdba74;
}
.avs-depart-h {
  margin: 8px 0 4px; font-size: 9pt; letter-spacing: 0.03em; color: #800000;
}
table.avs-depart { width: 100%; border-collapse: collapse; margin: 0 0 6px; }
table.avs-depart th, table.avs-depart td {
  border: 1px solid #d4d4d4; padding: 3px 5px; font-size: 8pt; text-align: right;
}
table.avs-depart th:first-child, table.avs-depart td:first-child {
  text-align: left; width: 40%;
}
table.avs-depart thead th { background: #f4ecec; color: #3a1d1d; font-weight: 650; }
.avs-depart-legend { margin: 4px 0 0; font-size: 8pt; }
.avs-depart-swatch {
  display: inline-block; width: 18px; height: 8px; margin: 0 4px 0 10px; vertical-align: middle;
}
.avs-depart-chart { width: 100%; height: auto; }
`;

function renderGraphique(model: AnalyseAvsPersonne): string {
  if (model.courbes.length === 0) {
    return `<h2 class="avs-depart-h">ÉVOLUTION DU CUMUL DES RENTES AVS</h2><p class="avs-depart-avert">Graphique non affiché : aucun scénario n'est complet.</p>`;
  }
  const largeur = 640;
  const hauteur = 210;
  const gauche = 62;
  const droite = 12;
  const haut = 18;
  const bas = 26;
  const xDe = (age: number) =>
    gauche + ((age - 63) / (AVS_HORIZON_GRAPHIQUE - 63)) * (largeur - gauche - droite);
  const yDe = (cumul: number) =>
    haut + (1 - cumul / model.yMax) * (hauteur - haut - bas);
  const ticksX = [63, 65, 70, 75, 80, 85, 90];
  const axes = `
    <line x1="${gauche}" y1="${haut}" x2="${gauche}" y2="${hauteur - bas}" stroke="#bbb" />
    <line x1="${gauche}" y1="${hauteur - bas}" x2="${largeur - droite}" y2="${hauteur - bas}" stroke="#bbb" />
    <text x="4" y="12" font-size="8" fill="#666">CHF</text>
    <text x="${gauche - 4}" y="${yDe(0) + 3}" font-size="8" fill="#666" text-anchor="end">0</text>
    <text x="${gauche - 4}" y="${yDe(model.yMax) + 3}" font-size="8" fill="#666" text-anchor="end">${echap(formatChfAvs(model.yMax).replace("CHF", "").trim())}</text>
    ${ticksX
      .map(
        (age) =>
          `<text x="${xDe(age)}" y="${hauteur - 8}" font-size="8" fill="#666" text-anchor="middle">${age}</text>`,
      )
      .join("")}`;
  const courbes = model.courbes
    .map((courbe) => {
      const points = courbe.points
        .map((point) => `${xDe(point.age).toFixed(1)},${yDe(point.cumul).toFixed(1)}`)
        .join(" ");
      return `<polyline fill="none" stroke="${courbe.couleur}" stroke-width="2.4" points="${points}" />`;
    })
    .join("");
  const marques = model.marques
    .map((marque, index) => {
      const x = xDe(marque.age);
      const y = yDe(marque.cumul);
      const decalage = index === 0 ? -8 : 14;
      return `
        <line x1="${x.toFixed(1)}" y1="${haut}" x2="${x.toFixed(1)}" y2="${hauteur - bas}" stroke="#888" stroke-dasharray="3 3" />
        <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.5" fill="#1a1a1a" />
        <text x="${x.toFixed(1)}" y="${Math.max(11, y + decalage).toFixed(1)}" font-size="8" fill="#1a1a1a" text-anchor="middle">${echap(marque.etiquette)}</text>`;
    })
    .join("");
  const legende = model.courbes
    .map(
      (courbe) =>
        `<span class="avs-depart-swatch" style="background:${courbe.couleur}"></span>Départ à ${courbe.depart} ans`,
    )
    .join("");
  return `
    <h2 class="avs-depart-h">ÉVOLUTION DU CUMUL DES RENTES AVS</h2>
    <svg class="avs-depart-chart" viewBox="0 0 ${largeur} ${hauteur}" role="img" aria-label="Évolution du cumul des rentes AVS">
      ${axes}
      ${courbes}
      ${marques}
    </svg>
    <p class="avs-depart-legend">${legende}</p>`;
}
