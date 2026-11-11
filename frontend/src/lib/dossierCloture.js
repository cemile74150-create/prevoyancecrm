/** Clôture dossiers + recherche / couleurs pour « Suivi de vos dossiers ». */

export const CLOTURE_MOTIF_ABOUTIE = "affaire_aboutie";
export const CLOTURE_MOTIF_NON_ABOUTIE = "affaire_non_aboutie";

export const CLOTURE_MOTIFS = [
  { value: CLOTURE_MOTIF_ABOUTIE, label: "Affaire aboutie" },
  { value: CLOTURE_MOTIF_NON_ABOUTIE, label: "Affaire non aboutie" },
];

export function todayZurichIso() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Zurich",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function normalizeClotureMotif(value) {
  if (value == null || value === "") return null;
  const raw = String(value).trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (raw === "affaire_aboutie" || raw === "aboutie") return CLOTURE_MOTIF_ABOUTIE;
  if (raw === "affaire_non_aboutie" || raw === "non_aboutie" || raw === "affaire_nonaboutie") {
    return CLOTURE_MOTIF_NON_ABOUTIE;
  }
  return null;
}

export function clotureMotifLabel(value) {
  const motif = normalizeClotureMotif(value);
  if (motif === CLOTURE_MOTIF_ABOUTIE) return "Affaire aboutie";
  if (motif === CLOTURE_MOTIF_NON_ABOUTIE) return "Affaire non aboutie";
  return "Non renseigné";
}

/** Couleur de carte Kanban pour un dossier clôturé. */
export function clotureCardClass(statut, motif) {
  if (statut !== "Clôturé") return "";
  const m = normalizeClotureMotif(motif);
  if (m === CLOTURE_MOTIF_ABOUTIE) {
    return "border-emerald-400/80 bg-emerald-50 hover:border-emerald-500 hover:bg-emerald-50";
  }
  if (m === CLOTURE_MOTIF_NON_ABOUTIE) {
    return "border-red-400/80 bg-red-50 hover:border-red-500 hover:bg-red-50";
  }
  return "border-slate-300 bg-slate-50 hover:border-slate-400";
}

export function pickGroupCloture(group) {
  const members = group?.members || [];
  let clotureDate = null;
  let clotureMotif = null;
  for (const m of members) {
    if (!clotureDate && m?.cloture_date) clotureDate = String(m.cloture_date).slice(0, 10);
    if (!clotureMotif && m?.cloture_motif) clotureMotif = normalizeClotureMotif(m.cloture_motif);
    if (clotureDate && clotureMotif) break;
  }
  return { clotureDate, clotureMotif, clotureMotifLabel: clotureMotifLabel(clotureMotif) };
}

function foldSearch(text) {
  return String(text || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

/** Recherche locale (nom, prénom, référence, ville, conseiller) — combine avec les filtres. */
export function groupMatchesSearch(group, query) {
  const q = foldSearch(query);
  if (!q) return true;
  const title = foldSearch(
    group?.type === "family"
      ? group?.dossier_label || ""
      : `${group?.members?.[0]?.prenom || ""} ${group?.members?.[0]?.nom || ""}`
  );
  const haystacks = [
    title,
    foldSearch(group?.numero_dossier),
    foldSearch(group?.ville),
    foldSearch(group?.dossier_label),
    ...(group?.members || []).flatMap((m) => [
      foldSearch(m?.prenom),
      foldSearch(m?.nom),
      foldSearch(`${m?.prenom || ""} ${m?.nom || ""}`),
      foldSearch(`${m?.nom || ""} ${m?.prenom || ""}`),
      foldSearch(m?.email),
      foldSearch(m?.telephone),
      foldSearch(m?.numero_dossier),
      foldSearch(m?.conseiller),
    ]),
  ];
  return haystacks.some((h) => h && h.includes(q));
}

/**
 * Taux = abouties / (abouties + non abouties) × 100.
 * Les clôtures « Non renseigné » sont exclues du dénominateur.
 */
export function computeTauxReussite(abouties, nonAbouties) {
  const a = Number(abouties) || 0;
  const n = Number(nonAbouties) || 0;
  const denom = a + n;
  if (denom <= 0) return null;
  return Math.round((1000 * a) / denom) / 10;
}
