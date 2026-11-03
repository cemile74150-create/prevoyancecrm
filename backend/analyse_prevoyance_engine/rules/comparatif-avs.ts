/**
 * Comparatif AVS : âge de référence, anticipation 1 an, anticipation 2 ans.
 * Un seul calcul pour l'écran et le PDF. Les rentes mensuelles déjà saisies
 * sont la source. 1 890 CHF n'est pas une valeur par défaut.
 *
 * La 13e rente (dès janvier 2026) est inclus dans l'annuel = mensuel × 13.
 * Une année incomplète ne prend que les mois de vieillesse réellement perçus :
 * total de ces mois = mensuel × k × 13/12, soit la 13e proratisée (k/12).
 * Avant 2026, pas de 13e. Le supplément transitoire, la rente enfant et les
 * prestations exclues ne sont pas ajoutés.
 */
import {
  formatLegalAgeLabel,
  getLegalRetirementAge,
  getRetirementStartDate,
} from "./avs-age";

export const AVS_13E_DEPUIS = { annee: 2026, mois: 1 } as const;

/** Seuils du revenu annuel moyen déterminant (barème EAK / OCAS, AVS 21). */
export const AVS21_RAM_PLAFOND_BAS = 60_480;
export const AVS21_RAM_PLAFOND_MOYEN = 75_600;

export type Avs21TrancheRevenu = "bas" | "moyen" | "eleve";

/**
 * Taux favorable pour une anticipation en années entières.
 * Femmes nées de 1961 à 1969. Source : EAK, « Taux de réduction favorable
 * en cas d'anticipation de la rente ». Le supplément de rente n'y figure pas.
 * https://www.eak.admin.ch/fr/taux-de-reduction-favorable-en-cas-danticipation-de-la-rente
 */
export const AVS21_TAUX_REDUCTION_TRANSITOIRE: Record<
  1 | 2,
  Record<Avs21TrancheRevenu, number>
> = {
  1: { bas: 0, moyen: 0.025, eleve: 0.035 },
  2: { bas: 0.02, moyen: 0.045, eleve: 0.065 },
};

export const AVS21_GENERATION = { debut: 1961, fin: 1969 } as const;

/**
 * Tranche retenue uniquement quand le revenu annuel moyen n'est pas connu.
 * Ce n'est pas le barème ordinaire de 6,8 %.
 */
export const AVS21_TRANCHE_SI_REVENU_INCONNU: Avs21TrancheRevenu = "eleve";

const TAUX_ORDINAIRE: Record<1 | 2, number> = { 1: 0.068, 2: 0.136 };

export const COULEUR_SANS_ANTICIPATION = "#800000";
export const COULEUR_ANTICIPATION_1 = "#E29AAD";
export const COULEUR_ANTICIPATION_2 = "#C4A36A";

/** Le croisement est cherché jusqu'à cet âge. Au-delà : non atteint. */
export const AVS_HORIZON_ANS = 110;
export const LABEL_EQUILIBRE_NON_ATTEINT = `Non atteint avant ${AVS_HORIZON_ANS} ans`;

const COULEURS = [
  COULEUR_SANS_ANTICIPATION,
  COULEUR_ANTICIPATION_1,
  COULEUR_ANTICIPATION_2,
] as const;

const INDEX_13E = AVS_13E_DEPUIS.annee * 12 + (AVS_13E_DEPUIS.mois - 1);
const EPS = 0.5;

export interface PersonneAvsSaisie {
  prenom?: string | null;
  nom?: string | null;
  civilite?: string | null;
  dateNaissance?: string | null;
  avsMensuel?: number | null;
  avsAnnuel?: number | null;
  avsRentesAnticipees?: Array<{
    age?: number | null;
    montantAnnuel?: number | null;
  }> | null;
  /**
   * Revenu annuel moyen déterminant, seulement pour la tranche AVS 21.
   * Absent du formulaire : la tranche configurable est indiquée dans la note.
   */
  revenuAnnuelMoyen?: number | null;
}

export interface ComparatifAvsDemande {
  couple: boolean;
  personnes: PersonneAvsSaisie[];
}

export type SourceRenteAvs =
  | "reference"
  | "bareme"
  | "saisie"
  | "absente"
  | "indetermine";

export interface ComparatifAvsPersonneVue {
  prenom: string;
  nom: string;
  libelleColonne: string;
  ageReference: number | null;
  ageReferenceLabel: string | null;
}

export interface ComparatifAvsLigne {
  annees: 0 | 1 | 2;
  libelle: string;
  libelleCourbe: string;
  couleur: string;
  mensuelsExacts: Array<number | null>;
  mensuelsAffiches: Array<number | null>;
  annuelExact: number | null;
  annuelAffiche: number | null;
  equilibreLabel: string;
  ageEquilibre: number | null;
  sources: SourceRenteAvs[];
  taux: Array<number | null>;
}

export interface MoisCumulAvs {
  mois: string;
  cumul: [number, number, number];
}

export interface PointCumulAvs {
  x: number;
  y: number;
}

export interface ComparatifAvs {
  couple: boolean;
  titre: string;
  titreGraphique: string;
  personnes: ComparatifAvsPersonneVue[];
  lignes: [ComparatifAvsLigne, ComparatifAvsLigne, ComparatifAvsLigne];
  axe: "age" | "date" | "aucun";
  noteAxe: string | null;
  journal: MoisCumulAvs[];
  series: Array<{ annees: 0 | 1 | 2; couleur: string; points: PointCumulAvs[] }>;
  marques: Array<{ annees: 1 | 2; x: number; y: number; etiquette: string }>;
  xMin: number;
  xMax: number;
  yMax: number;
  note: string;
  notesComplement: string[];
}

interface RenteResolue {
  mensuelExact: number | null;
  annuelExact: number | null;
  source: SourceRenteAvs;
  taux: number | null;
  note: string | null;
}

interface PersonneResolue {
  prenom: string;
  nom: string;
  civilite: string;
  ageReference: number | null;
  idxFin: number | null;
  idxDepart: [number | null, number | null, number | null];
  rentes: [RenteResolue, RenteResolue, RenteResolue];
}

export function trancheRevenuAnnuelMoyen(ram: number): Avs21TrancheRevenu {
  if (ram <= AVS21_RAM_PLAFOND_BAS) return "bas";
  if (ram <= AVS21_RAM_PLAFOND_MOYEN) return "moyen";
  return "eleve";
}

/** Décimale inférieure : 92,568 → 92,5. Ce n'est pas l'arrondi habituel. */
export function formatAgeUneDecimale(age: number): string {
  const v = Math.floor(age * 10 + 1e-8) / 10;
  return `${v.toFixed(1).replace(".", ",")} ans`;
}

export function formatChfFranc(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("fr-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(Math.round(n));
}

export function etiquetteEquilibre(annees: 1 | 2, age: number): string {
  const duree = annees === 1 ? "1 an" : "2 ans";
  return `Âge d'équilibre — ${duree} d'anticipation : ${formatAgeUneDecimale(age)}`;
}

export function cumulAu(
  model: ComparatifAvs,
  annees: 0 | 1 | 2,
  mois: string,
): number | null {
  const row = model.journal.find((item) => item.mois === mois);
  return row ? row.cumul[annees] : null;
}

export function comparatifAvsDepuisAnalyse(input: {
  etatCivil?: string | null;
  client1: PersonneAvsSaisie;
  conjoint?: PersonneAvsSaisie | null;
}): ComparatifAvs {
  const couple = input.etatCivil === "Marié(e)" && input.conjoint != null;
  return buildComparatifAvs({
    couple,
    personnes: couple ? [input.client1, input.conjoint as PersonneAvsSaisie] : [input.client1],
  });
}

export function buildComparatifAvs(demande: ComparatifAvsDemande): ComparatifAvs {
  const couple = Boolean(demande.couple) && (demande.personnes?.length || 0) >= 2;
  const saisies = (demande.personnes || []).slice(0, couple ? 2 : 1);
  const personnes = saisies.map((saisie, index) => resoudrePersonne(saisie, index));
  const notes = new Set<string>();
  for (const personne of personnes) {
    for (const rente of personne.rentes) {
      if (rente.note) notes.add(rente.note);
    }
  }

  const horloge = personnes.find(
    (personne) => personne.ageReference != null && personne.idxDepart[0] != null,
  );
  const agesConnus = personnes
    .map((personne) => personne.ageReference)
    .filter((age): age is number => age != null);
  const memeAge =
    agesConnus.length > 0 &&
    agesConnus.every((age) => Math.abs(age - agesConnus[0]) < 1e-9);
  const ageLibelle = memeAge ? agesConnus[0] : null;
  const axe: ComparatifAvs["axe"] =
    horloge == null ? "aucun" : memeAge ? "age" : "date";

  const debuts = personnes.flatMap((personne) =>
    personne.idxDepart.filter((idx): idx is number => idx != null),
  );
  const fins = personnes
    .map((personne) => personne.idxFin)
    .filter((idx): idx is number => idx != null);
  const idxDebut = debuts.length ? Math.min(...debuts) : null;
  const idxFin = fins.length ? Math.max(...fins) : null;

  const journal: MoisCumulAvs[] = [];
  const series: ComparatifAvs["series"] = [0, 1, 2].map((annees) => ({
    annees: annees as 0 | 1 | 2,
    couleur: COULEURS[annees],
    points: [],
  }));
  const equilibres: Array<{ age: number; y: number; idx: number; frac: number } | null> = [
    null,
    null,
    null,
  ];

  const xDe = (idx: number, frac: number): number => {
    if (!horloge || horloge.ageReference == null || horloge.idxDepart[0] == null) {
      return anneeDecimale(idx) + frac / 12;
    }
    if (axe === "date") return anneeDecimale(idx) + frac / 12;
    return horloge.ageReference + (idx - horloge.idxDepart[0] + frac) / 12;
  };

  if (idxDebut != null && idxFin != null && idxFin > idxDebut) {
    const cumul: [number, number, number] = [0, 0, 0];
    const tracee = [false, false, false];
    for (let idx = idxDebut; idx < idxFin; idx += 1) {
      const avant = cumul.slice() as [number, number, number];
      for (let scenario = 0; scenario < 3; scenario += 1) {
        let ajout = 0;
        for (const personne of personnes) {
          ajout += versementPersonne(personne, scenario as 0 | 1 | 2, idx);
        }
        cumul[scenario] += ajout;
        if (!tracee[scenario] && ajout > 0) {
          series[scenario].points.push({ x: xDe(idx, 0), y: 0 });
          tracee[scenario] = true;
        }
        if (tracee[scenario]) {
          series[scenario].points.push({ x: xDe(idx, 1), y: cumul[scenario] });
        }
      }
      for (const scenario of [1, 2] as const) {
        if (equilibres[scenario]) continue;
        const menait = avant[scenario] > avant[0] + EPS;
        const rattrape = cumul[0] + EPS >= cumul[scenario];
        const close = cumul[0] - avant[0] - (cumul[scenario] - avant[scenario]);
        if (menait && rattrape && avant[scenario] > EPS && close > EPS) {
          const frac = Math.min(1, Math.max(0, (avant[scenario] - avant[0]) / close));
          equilibres[scenario] = {
            age: ageHorloge(horloge, idx, frac),
            y: avant[0] + frac * (cumul[0] - avant[0]),
            idx,
            frac,
          };
        }
      }
      journal.push({ mois: isoMois(idx), cumul: cumul.slice() as [number, number, number] });
    }
  }

  const lignes = [0, 1, 2].map((annees) =>
    ligneScenario(
      annees as 0 | 1 | 2,
      personnes,
      ageLibelle,
      equilibres[annees],
      horloge,
    ),
  ) as ComparatifAvs["lignes"];

  const marques = ([1, 2] as const)
    .filter((annees) => equilibres[annees] && lignes[annees].ageEquilibre != null)
    .map((annees) => {
      const point = equilibres[annees] as { age: number; y: number; idx: number; frac: number };
      return {
        annees,
        x: xDe(point.idx, point.frac),
        y: point.y,
        etiquette: etiquetteEquilibre(annees, point.age),
      };
    });

  const xs = series.flatMap((serie) => serie.points.map((point) => point.x));
  let xMin = 0;
  let xMax = AVS_HORIZON_ANS;
  if (axe === "age") {
    xMin = xs.length ? Math.floor(Math.min(...xs) + 1e-9) : 60;
    xMax = echelleJusqua(marques.map((marque) => marque.x), AVS_HORIZON_ANS, xMin);
  } else if (axe === "date") {
    xMin = xs.length ? Math.floor(Math.min(...xs)) : AVS_13E_DEPUIS.annee;
    const horizon = xs.length ? Math.max(...xs) : xMin + 1;
    xMax = echelleJusqua(marques.map((marque) => marque.x), horizon, xMin);
  }
  const yBrut = Math.max(
    0,
    ...series.flatMap((serie) =>
      serie.points.filter((point) => point.x <= xMax + 1e-6).map((point) => point.y),
    ),
    ...marques.map((marque) => marque.y),
  );
  const yMax = plafondAxe(yBrut);

  const titrePersonne = personnes[0];
  const nomTitre = titreIdentite(titrePersonne);
  return {
    couple,
    titre: couple ? "Synthèse pour le couple" : nomTitre ? `Synthèse AVS — ${nomTitre}` : "Synthèse AVS",
    titreGraphique: couple
      ? "Évolution du cumul des rentes AVS (couple)"
      : nomTitre
        ? `Évolution du cumul des rentes AVS — ${nomTitre}`
        : "Évolution du cumul des rentes AVS",
    personnes: personnes.map((personne, index) => ({
      prenom: personne.prenom,
      nom: personne.nom,
      libelleColonne: libelleColonne(personne, index),
      ageReference: personne.ageReference,
      ageReferenceLabel:
        personne.ageReference == null ? null : formatLegalAgeLabel(personne.ageReference),
    })),
    lignes,
    axe,
    noteAxe: noteAges(personnes, axe),
    journal,
    series,
    marques,
    xMin,
    xMax,
    yMax,
    note: "",
    notesComplement: Array.from(notes),
  };
}

/** Au moins jusqu'au plus grand âge d'équilibre, sans dépasser l'horizon. */
function echelleJusqua(equilibres: number[], horizon: number, xMin: number): number {
  const atteints = equilibres.filter((x) => Number.isFinite(x));
  const plafond = Math.max(horizon, xMin + 1);
  if (!atteints.length) return Math.min(plafond, Math.max(horizon, xMin + 1));
  const besoin = Math.max(...atteints);
  const avecMarge = Math.ceil(besoin + 1 - 1e-9);
  return Math.min(plafond, Math.max(xMin + 1, avecMarge));
}

export function renderComparatifAvsBlockHtml(model: ComparatifAvs): string {
  const headers = model.couple
    ? ["Scénario", ...model.personnes.map((personne) => personne.libelleColonne), "Total annuel", "Âge d'équilibre"]
    : ["Scénario", "Rente mensuelle", "Rente annuelle", "Âge d'équilibre"];
  const head = headers.map((label) => `<th>${esc(label)}</th>`).join("");
  const body = model.lignes
    .map((ligne) => {
      const cellules = model.couple
        ? [
            ...ligne.mensuelsAffiches.map((montant) => `<td>${formatChfFranc(montant)}</td>`),
            `<td>${formatChfFranc(ligne.annuelAffiche)}</td>`,
          ]
        : [
            `<td>${formatChfFranc(ligne.mensuelsAffiches[0] ?? null)}</td>`,
            `<td>${formatChfFranc(ligne.annuelAffiche)}</td>`,
          ];
      return `<tr><td class="lab">${esc(ligne.libelle)}</td>${cellules.join("")}<td>${esc(ligne.equilibreLabel)}</td></tr>`;
    })
    .join("");
  const axe = model.noteAxe
    ? `<p class="avs-cmp-axis">${esc(model.noteAxe)}</p>`
    : "";
  const graphique =
    model.axe === "aucun"
      ? `<p class="avs-cmp-note">Le graphique n'est pas tracé : sans date de naissance, l'âge d'équilibre ne peut pas être situé.</p>`
      : `<div class="avs-cmp-chart">${renderComparatifAvsSvg(model)}</div>`;
  return `<section class="avs-cmp" data-avs-comparatif="${model.couple ? "couple" : "seul"}" data-personnes="${model.personnes.length}">
<style>
.avs-cmp { color: #161616; font-family: Candara, Calibri, "Segoe UI", sans-serif; }
.avs-cmp-title { color: #800000; font-size: 13pt; font-weight: 700; margin: 0 0 8px; padding-bottom: 3px; border-bottom: 1.5px solid #800000; }
.avs-cmp-chart-title { text-align: center; font-size: 12pt; font-weight: 700; margin: 14px 0 4px; color: #3a3838; }
.avs-cmp-axis { text-align: center; font-size: 8.5pt; color: #595959; margin: 0 0 6px; }
.avs-cmp-table { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin: 0 0 4px; page-break-inside: avoid; break-inside: avoid; }
.avs-cmp-table th { background: #800000; color: #fff; padding: 6px 8px; font-weight: 600; text-align: center; line-height: 1.25; }
.avs-cmp-table td { padding: 6px 8px; border-bottom: 1px solid #e2e2e2; text-align: right; font-variant-numeric: tabular-nums; }
.avs-cmp-table td.lab { text-align: left; font-variant-numeric: normal; }
.avs-cmp-chart { page-break-inside: avoid; break-inside: avoid; }
.avs-cmp-svg { width: 100%; height: auto; display: block; }
.avs-cmp-note { font-size: 8.5pt; line-height: 1.4; color: #595959; margin: 8px 0 0; }
</style>
<h2 class="avs-cmp-title">${esc(model.titre)}</h2>
<table class="avs-cmp-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
<h3 class="avs-cmp-chart-title">${esc(model.titreGraphique)}</h3>
${axe}
${graphique}
</section>`;
}

export function renderComparatifAvsSvg(model: ComparatifAvs): string {
  if (model.axe === "aucun") return "";
  const W = 760;
  const H = 440;
  const padL = 74;
  const padR = 16;
  const padT = 78;
  const padB = 72;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const x0 = model.xMin;
  const x1 = model.xMax <= model.xMin ? model.xMin + 1 : model.xMax;
  const y1 = model.yMax > 0 ? model.yMax : 1;
  const xPix = (x: number) => padL + ((x - x0) / (x1 - x0)) * plotW;
  const yPix = (y: number) => padT + plotH - (Math.max(0, y) / y1) * plotH;

  const grilles: string[] = [];
  for (let i = 0; i <= 4; i += 1) {
    const valeur = (y1 * i) / 4;
    const y = yPix(valeur);
    grilles.push(
      `<line x1="${padL}" y1="${fixe(y)}" x2="${W - padR}" y2="${fixe(y)}" stroke="#e6e6e6" stroke-width="1"/>`,
      `<text x="${padL - 8}" y="${fixe(y + 3)}" text-anchor="end" font-size="9" fill="#666">${esc(formatAxe(valeur))}</text>`,
    );
  }
  const pasX = x1 - x0 > 40 ? 2 : 1;
  const xticks: string[] = [];
  for (let x = Math.ceil(x0); x <= x1 + 1e-9; x += pasX) {
    const px = xPix(x);
    xticks.push(
      `<line x1="${fixe(px)}" y1="${padT}" x2="${fixe(px)}" y2="${fixe(padT + plotH)}" stroke="#f3f3f3" stroke-width="1"/>`,
      `<text x="${fixe(px)}" y="${H - padB + 14}" text-anchor="middle" font-size="9" fill="#444">${x}</text>`,
    );
  }

  const courbes = model.series
    .map((serie) => {
      const points = serie.points.filter((point) => point.x <= x1 + 1e-6);
      if (points.length < 2) return "";
      const d = points
        .map((point, index) => `${index === 0 ? "M" : "L"}${fixe(xPix(point.x))} ${fixe(yPix(point.y))}`)
        .join(" ");
      return `<path d="${d}" fill="none" stroke="${serie.couleur}" stroke-width="2.2" stroke-linejoin="round"/>`;
    })
    .join("");

  const etiquettes = disposerEtiquettes(
    model.marques.map((marque) => ({
      x: xPix(marque.x),
      texte: marque.etiquette,
      couleur: COULEURS[marque.annees],
    })),
    W,
  );
  const marques = model.marques
    .map((marque, index) => {
      const x = xPix(marque.x);
      const y = yPix(marque.y);
      const boite = etiquettes[index];
      return `<line x1="${fixe(x)}" y1="${fixe(y)}" x2="${fixe(x)}" y2="${fixe(padT + plotH)}" stroke="${COULEURS[marque.annees]}" stroke-width="1" stroke-dasharray="3 3"/>
<circle cx="${fixe(x)}" cy="${fixe(y)}" r="4.5" fill="${COULEURS[marque.annees]}" stroke="#fff" stroke-width="1.2"/>
<rect x="${fixe(boite.x)}" y="${fixe(boite.y)}" width="${fixe(boite.w)}" height="${fixe(boite.h)}" rx="3" fill="${marque.annees === 1 ? "#F8E6EC" : "#F4E7D4"}" stroke="${COULEURS[marque.annees]}"/>
<text x="${fixe(boite.x + 6)}" y="${fixe(boite.y + 13)}" font-size="8.5" fill="#3a2218">${esc(marque.etiquette)}</text>`;
    })
    .join("");

  const legend = model.lignes
    .map((ligne, index) => {
      const x = padL + index * (plotW / 3);
      return `<line x1="${fixe(x)}" y1="${H - 16}" x2="${fixe(x + 22)}" y2="${H - 16}" stroke="${ligne.couleur}" stroke-width="3"/>
<text x="${fixe(x + 28)}" y="${H - 12}" font-size="9" fill="#333">${esc(ligne.libelleCourbe)}</text>`;
    })
    .join("");

  const axeNom = model.axe === "date" ? "Année" : "Âge";
  return `<svg class="avs-cmp-svg" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${esc(model.titreGraphique)}">
${grilles.join("")}
${xticks.join("")}
  <text x="${fixe(padL + plotW / 2)}" y="${H - padB + 30}" text-anchor="middle" font-size="10" fill="#333">${axeNom}</text>
<text x="16" y="${fixe(padT + plotH / 2)}" text-anchor="middle" font-size="10" fill="#333" transform="rotate(-90 16 ${fixe(padT + plotH / 2)})">Cumul des rentes (CHF)</text>
${courbes}
${marques}
${legend}
</svg>`;
}

function ligneScenario(
  annees: 0 | 1 | 2,
  personnes: PersonneResolue[],
  ageLibelle: number | null,
  equilibre: { age: number; y: number } | null,
  horloge: PersonneResolue | undefined,
): ComparatifAvsLigne {
  const rentes = personnes.map((personne) => personne.rentes[annees]);
  const incomplet = rentes.some((rente) => rente.annuelExact == null);
  const annuelExact = incomplet
    ? null
    : rentes.reduce((somme, rente) => somme + (rente.annuelExact || 0), 0);
  let equilibreLabel = LABEL_EQUILIBRE_NON_ATTEINT;
  let ageEquilibre: number | null = null;
  if (annees === 0) {
    equilibreLabel = "—";
  } else if (equilibre && horloge && Number.isFinite(equilibre.age)) {
    ageEquilibre = equilibre.age;
    equilibreLabel = formatAgeUneDecimale(equilibre.age);
  }
  return {
    annees,
    libelle: libelleScenario(annees, ageLibelle),
    libelleCourbe: libelleCourbe(annees, ageLibelle),
    couleur: COULEURS[annees],
    mensuelsExacts: rentes.map((rente) => rente.mensuelExact),
    mensuelsAffiches: rentes.map((rente) =>
      rente.mensuelExact == null ? null : Math.round(rente.mensuelExact),
    ),
    annuelExact,
    annuelAffiche: annuelExact == null ? null : Math.round(annuelExact),
    equilibreLabel,
    ageEquilibre,
    sources: rentes.map((rente) => rente.source),
    taux: rentes.map((rente) => rente.taux),
  };
}

function resoudrePersonne(saisie: PersonneAvsSaisie, index: number): PersonneResolue {
  const prenom = texte(saisie?.prenom);
  const nom = texte(saisie?.nom);
  const civilite = texte(saisie?.civilite);
  const ageReference = ageDeReference(civilite, saisie?.dateNaissance);
  const idxFin =
    ageReference != null && dateValide(saisie?.dateNaissance)
      ? indexMoisDate(getRetirementStartDate(String(saisie.dateNaissance), AVS_HORIZON_ANS))
      : null;
  const reference = renteDeReference(saisie);
  const rentes: PersonneResolue["rentes"] = [
    renteScenario(saisie, 0, reference, ageReference),
    renteScenario(saisie, 1, reference, ageReference),
    renteScenario(saisie, 2, reference, ageReference),
  ];
  const idxDepart = [0, 1, 2].map((annees) => {
    if (ageReference == null || !dateValide(saisie?.dateNaissance)) return null;
    if (rentes[annees].mensuelExact == null) return null;
    return indexMoisDate(
      getRetirementStartDate(String(saisie.dateNaissance), ageReference - annees),
    );
  }) as [number | null, number | null, number | null];
  void index;
  return { prenom, nom, civilite, ageReference, idxFin, idxDepart, rentes };
}

function renteScenario(
  saisie: PersonneAvsSaisie,
  annees: 0 | 1 | 2,
  reference: { mensuel: number; annuel: number } | null,
  ageReference: number | null,
): RenteResolue {
  if (annees === 0) {
    if (reference == null) {
      return vide("absente");
    }
    return {
      mensuelExact: reference.mensuel,
      annuelExact: reference.annuel,
      source: reference.annuel > 0 ? "reference" : "absente",
      taux: 0,
      note: null,
    };
  }
  const stocke =
    ageReference == null ? null : montantAnticipeStocke(saisie, ageReference - annees);
  if (stocke != null) {
    return {
      mensuelExact: stocke / 13,
      annuelExact: stocke,
      source: "saisie",
      taux: null,
      note: null,
    };
  }
  if (reference == null || reference.annuel <= 0) return vide("absente");
  const decision = deciderTaux(saisie, annees);
  if (decision.taux == null) {
    return {
      mensuelExact: null,
      annuelExact: null,
      source: "indetermine",
      taux: null,
      note: decision.note,
    };
  }
  const milli = Math.round(decision.taux * 1000);
  const mensuel = (reference.mensuel * (1000 - milli)) / 1000;
  return {
    mensuelExact: mensuel,
    annuelExact: mensuel * 13,
    source: "bareme",
    taux: decision.taux,
    note: decision.note,
  };
}

function deciderTaux(
  saisie: PersonneAvsSaisie,
  annees: 1 | 2,
): { taux: number | null; note: string | null } {
  const civilite = texte(saisie.civilite);
  const annee = anneeNaissance(saisie.dateNaissance);
  if (civilite === "Madame" && annee == null) {
    return {
      taux: null,
      note: "Date de naissance manquante pour une assurée : le taux de réduction n'est pas estimé. Le barème ordinaire de 6,8 % par année n'est pas appliqué.",
    };
  }
  if (civilite !== "Madame" && civilite !== "Monsieur") {
    return {
      taux: null,
      note: "Civilité manquante : le taux de réduction n'est pas estimé, et 6,8 % par année n'est pas appliqué.",
    };
  }
  const transitoire =
    civilite === "Madame" &&
    annee != null &&
    annee >= AVS21_GENERATION.debut &&
    annee <= AVS21_GENERATION.fin;
  if (!transitoire) return { taux: TAUX_ORDINAIRE[annees], note: null };

  const ram = nombrePositif(saisie.revenuAnnuelMoyen);
  const tranche =
    ram != null && ram > 0 ? trancheRevenuAnnuelMoyen(ram) : AVS21_TRANCHE_SI_REVENU_INCONNU;
  const taux = AVS21_TAUX_REDUCTION_TRANSITOIRE[annees][tranche];
  const taux1 = pourcent(AVS21_TAUX_REDUCTION_TRANSITOIRE[1][tranche]);
  const taux2 = pourcent(AVS21_TAUX_REDUCTION_TRANSITOIRE[2][tranche]);
  const revenu =
    ram != null && ram > 0
      ? `Revenu annuel moyen déterminant retenu pour la tranche « ${libelleTranche(tranche)} ».`
      : `Le revenu annuel moyen déterminant n'est pas dans le dossier : la tranche configurable « ${libelleTranche(tranche)} » est appliquée (${taux1} pour 1 an, ${taux2} pour 2 ans).`;
  return {
    taux,
    note: `Femme de la génération transitoire AVS 21 (née de 1961 à 1969) : la réduction n'est pas de 6,8 % par année. ${revenu} Un montant anticipé déjà saisi remplace ce calcul. Le supplément de rente transitoire n'est pas inclus.`,
  };
}

function montantAnticipeStocke(saisie: PersonneAvsSaisie, ageCible: number): number | null {
  let meilleur: { ecart: number; montant: number } | null = null;
  for (const ligne of saisie.avsRentesAnticipees || []) {
    const age = nombre(ligne?.age);
    const montant = nombrePositif(ligne?.montantAnnuel);
    if (age == null || montant == null || montant <= 0) continue;
    const ecart = Math.abs(age - ageCible);
    if (ecart > 0.51) continue;
    if (!meilleur || ecart < meilleur.ecart) meilleur = { ecart, montant };
  }
  return meilleur ? meilleur.montant : null;
}

function renteDeReference(
  saisie: PersonneAvsSaisie,
): { mensuel: number; annuel: number } | null {
  const mensuel = nombrePositif(saisie?.avsMensuel);
  const annuel = nombrePositif(saisie?.avsAnnuel);
  if (mensuel != null && mensuel > 0) return { mensuel, annuel: mensuel * 13 };
  if (annuel != null && annuel > 0) return { mensuel: annuel / 13, annuel };
  if (mensuel === 0 || annuel === 0) return { mensuel: 0, annuel: 0 };
  return null;
}

function versementPersonne(personne: PersonneResolue, scenario: 0 | 1 | 2, idx: number): number {
  const depart = personne.idxDepart[scenario];
  if (depart == null || personne.idxFin == null) return 0;
  if (idx < depart || idx >= personne.idxFin) return 0;
  const mensuel = personne.rentes[scenario].mensuelExact;
  if (mensuel == null || mensuel <= 0) return 0;
  if (idx < INDEX_13E) return mensuel;
  return (mensuel * 13) / 12;
}

function ageHorloge(
  horloge: PersonneResolue | undefined,
  idx: number,
  frac: number,
): number {
  if (!horloge || horloge.ageReference == null || horloge.idxDepart[0] == null) return Number.NaN;
  return horloge.ageReference + (idx - horloge.idxDepart[0] + frac) / 12;
}

function ageDeReference(civilite: string, dateNaissance: string | null | undefined): number | null {
  if (civilite === "Monsieur") return 65;
  if (civilite !== "Madame" || !dateValide(dateNaissance)) return null;
  return getLegalRetirementAge("Madame", String(dateNaissance));
}

function libelleScenario(annees: 0 | 1 | 2, age: number | null): string {
  if (age == null) {
    if (annees === 0) return "Âge de référence";
    return annees === 1 ? "1 an d'anticipation" : "2 ans d'anticipation";
  }
  const label = formatLegalAgeLabel(age - annees);
  if (annees === 0) return `${label} (âge de référence)`;
  return annees === 1
    ? `1 an d'anticipation (${label})`
    : `2 ans d'anticipation (${label})`;
}

function libelleCourbe(annees: 0 | 1 | 2, age: number | null): string {
  if (age == null) {
    if (annees === 0) return "Sans anticipation";
    return annees === 1 ? "1 an d'anticipation" : "2 ans d'anticipation";
  }
  if (annees === 0) return `${formatLegalAgeLabel(age)} (sans anticipation)`;
  const des = formatLegalAgeLabel(age - annees);
  return annees === 1
    ? `1 an d'anticipation (dès ${des})`
    : `2 ans d'anticipation (dès ${des})`;
}

function libelleColonne(personne: PersonneResolue, index: number): string {
  if (personne.prenom) return `Rente ${personne.prenom}`;
  if (personne.civilite === "Madame" || personne.civilite === "Monsieur") {
    return `Rente ${personne.civilite}`;
  }
  return `Rente assuré ${index + 1}`;
}

function titreIdentite(personne: PersonneResolue | undefined): string {
  if (!personne) return "";
  const nom = personne.nom.toLocaleUpperCase("fr-CH");
  return [personne.prenom, nom].filter(Boolean).join(" ");
}

function noteAges(personnes: PersonneResolue[], axe: ComparatifAvs["axe"]): string | null {
  if (axe !== "date") return null;
  const parts = personnes
    .filter((personne) => personne.ageReference != null)
    .map((personne) => {
      const qui = personne.prenom || personne.civilite || "Assuré";
      return `${qui} : ${formatLegalAgeLabel(personne.ageReference as number)}`;
    });
  return parts.length ? `Âge de référence — ${parts.join(" · ")}` : null;
}

function libelleTranche(tranche: Avs21TrancheRevenu): string {
  if (tranche === "bas") return `jusqu'à ${formatAxe(AVS21_RAM_PLAFOND_BAS)} CHF`;
  if (tranche === "moyen") {
    return `de ${formatAxe(AVS21_RAM_PLAFOND_BAS + 1)} à ${formatAxe(AVS21_RAM_PLAFOND_MOYEN)} CHF`;
  }
  return `dès ${formatAxe(AVS21_RAM_PLAFOND_MOYEN + 1)} CHF`;
}

function pourcent(taux: number): string {
  const n = Math.round(taux * 1000) / 10;
  return `${String(n).replace(".", ",")} %`;
}

function vide(source: SourceRenteAvs): RenteResolue {
  return {
    mensuelExact: source === "absente" ? 0 : null,
    annuelExact: source === "absente" ? 0 : null,
    source,
    taux: null,
    note: null,
  };
}

function disposerEtiquettes(
  items: Array<{ x: number; texte: string; couleur: string }>,
  largeur: number,
): Array<{ x: number; y: number; w: number; h: number }> {
  const boites = items.map((item, index) => {
    const w = Math.min(340, Math.max(150, Math.ceil(item.texte.length * 5.35 + 14)));
    const h = 18;
    const versLaGauche = items.length > 1 && index === items.length - 1;
    let x = items.length === 1 ? item.x - w / 2 : versLaGauche ? item.x - w - 8 : item.x + 8;
    x = Math.min(largeur - w - 4, Math.max(4, x));
    return { x, y: 14, w, h };
  });
  if (boites.length === 2 && chevauche(boites[0], boites[1])) {
    boites[0].y = 6;
    boites[1].y = 28;
  }
  return boites;
}

function chevauche(
  a: { x: number; y: number; w: number; h: number },
  b: { x: number; y: number; w: number; h: number },
): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function plafondAxe(valeur: number): number {
  if (!(valeur > 0)) return 1000;
  const cible = valeur * 1.12;
  const pow = Math.pow(10, Math.floor(Math.log10(cible)));
  const paliers = [1, 1.2, 1.4, 1.5, 1.6, 1.8, 2, 2.5, 3, 4, 5, 6, 8, 10];
  for (const palier of paliers) {
    if (palier * pow >= cible - 1e-6) return palier * pow;
  }
  return 10 * pow;
}

function anneeNaissance(date: string | null | undefined): number | null {
  if (!dateValide(date)) return null;
  const annee = Number(String(date).slice(0, 4));
  return Number.isFinite(annee) ? annee : null;
}

function dateValide(date: string | null | undefined): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(date || ""));
}

function indexMoisDate(date: Date): number {
  return date.getFullYear() * 12 + date.getMonth();
}

function isoMois(index: number): string {
  const annee = Math.floor(index / 12);
  const mois = (index % 12) + 1;
  return `${annee}-${String(mois).padStart(2, "0")}`;
}

function anneeDecimale(index: number): number {
  return Math.floor(index / 12) + (index % 12) / 12;
}

function formatAxe(n: number): string {
  return new Intl.NumberFormat("fr-CH", { maximumFractionDigits: 0 }).format(n);
}

function nombre(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function nombrePositif(value: unknown): number | null {
  const n = nombre(value);
  if (n == null) return null;
  return n < 0 ? 0 : n;
}

function texte(value: unknown): string {
  return String(value || "").trim();
}

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fixe(n: number): string {
  return n.toFixed(1);
}
