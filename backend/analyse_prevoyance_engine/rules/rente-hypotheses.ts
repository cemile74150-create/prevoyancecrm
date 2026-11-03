/**
 * Règles métier des hypothèses de rente (hors ESTV).
 *
 * Le revenu fiscal n'est pas le revenu encaissé :
 * - certaine : AVS + rente LPP résiduelle + 100 % des participations
 *   (la rente garantie est encaissée, elle n'entre pas dans l'impôt) ;
 * - viagère : AVS + rente LPP résiduelle + 4 % de la rente garantie
 *   + 70 % des participations.
 * La rente LPP résiduelle est imposable en totalité, comme une rente LPP.
 * L'impôt est ensuite calculé par ESTV sur ce revenu fiscal.
 *
 * Offre combinée : une seule hypothèse. AVS et LPP résiduelle une fois,
 * puis la part de chaque rente réellement versée cette année-là.
 * Un seul revenu fiscal, un seul ICC/IFD. Pas d'addition de deux colonnes.
 */

import type { RenteHypothesisColumn, RenteOffreDetail } from "../types";

export type RenteHypothesisType = "certaine" | "viagere";

export interface RevenuRenteInput {
  type: RenteHypothesisType;
  renteAvs: number;
  renteGarantie: number;
  participationExcedents: number;
  /** Part de rente LPP conservée. 100 % imposable. 0 si tout le capital est déblocable. */
  renteLppResiduelle?: number;
}

export function roundMoney(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

function n(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

/** Ce que le client encaisse : AVS + rente LPP résiduelle + rente garantie + participations. */
export function revenuBrutEncaisse(input: {
  renteAvs: number;
  renteGarantie: number;
  participationExcedents: number;
  renteLppResiduelle?: number;
}): number {
  return roundMoney(
    n(input.renteAvs) +
      n(input.renteLppResiduelle) +
      n(input.renteGarantie) +
      n(input.participationExcedents),
  );
}

/**
 * Revenu à transmettre au calculateur ESTV.
 * Ce n'est pas le revenu encaissé.
 */
export function revenuFiscalImposable(input: RevenuRenteInput): number {
  const avs = n(input.renteAvs);
  const residuelle = n(input.renteLppResiduelle);
  const participation = n(input.participationExcedents);
  if (input.type === "viagere") {
    return roundMoney(
      avs + residuelle + n(input.renteGarantie) * 0.04 + participation * 0.7,
    );
  }
  return roundMoney(avs + residuelle + participation);
}

/** Revenu net annuel = encaissé − impôt ESTV. */
export function revenuNetApresImpot(revenuBrut: number, impotEstv: number): number {
  return roundMoney(n(revenuBrut) - n(impotEstv));
}

/** Rente LPP de référence : 100 % imposable avec l'AVS (pas la règle certaine/viagère). */
export function revenuFiscalRenteLpp(renteAvs: number, renteLpp: number): number {
  return roundMoney(n(renteAvs) + n(renteLpp));
}

/**
 * Années de différé saisies. Vide, 0 ou invalide : la rente démarre tout de suite.
 * Distinct de la durée de versement d'une rente certaine.
 * Ne change pas le taux d'imposition. Il décale le premier versement.
 */
export function anneesDiffere(value: number | null | undefined): number | null {
  const years = Math.floor(Number(value));
  if (!Number.isFinite(years) || years <= 0) return null;
  return years;
}

/** Mention du tableau. Null si la rente n'est pas différée. */
export function mentionDiffere(value: number | null | undefined): string | null {
  const years = anneesDiffere(value);
  return years == null ? null : `Différé : ${years} ans`;
}

/** Note d'affichage. Ne remplit pas la durée du différé saisie. */
export const NOTE_PAX_DIFFERE =
  "Pour les contrats PAX, un différé d’un an s’applique systématiquement avant le premier versement de la rente.";

export function compagnieEstPax(name: string | null | undefined): boolean {
  return /pax/i.test(String(name || ""));
}

/**
 * Arrondi au centime, une seule fois en fin de somme.
 * L'affichage au franc se fait plus tard (formatChf).
 */
function roundCents(n: number): number {
  return Math.round((n + 1e-8) * 100) / 100;
}

export interface OffreVersement {
  type: RenteHypothesisType;
  compagnie?: string | null;
  capitalPlace?: number | null;
  dureeAnnees?: number | null;
  dureeDiffereAnnees?: number | null;
  renteGarantie: number;
  participationExcedents: number;
}

export interface OffreSaisieCommeHypothese {
  type?: RenteHypothesisType | null;
  compagnie?: string | null;
  capitalPlace?: number | null;
  dureeAnnees?: number | null;
  dureeDiffereAnnees?: number | null;
  renteGarantieAnnuelle?: number | null;
  participationExcedentsAnnuelle?: number | null;
  offres?: OffreSaisieCommeHypothese[] | null;
}

/** Une offre : les champs de l'hypothèse. Deux ou plus : le tableau `offres`. */
export function offresDeHypothese(row: OffreSaisieCommeHypothese): OffreVersement[] {
  const source =
    row.offres && row.offres.length >= 2 ? row.offres : [row];
  return source.map((offre) => ({
    type: offre.type === "viagere" ? "viagere" : "certaine",
    compagnie: offre.compagnie || "",
    capitalPlace: n(offre.capitalPlace || 0),
    dureeAnnees:
      offre.type === "viagere" ? null : offre.dureeAnnees ?? null,
    dureeDiffereAnnees: offre.dureeDiffereAnnees ?? null,
    renteGarantie: n(offre.renteGarantieAnnuelle || 0),
    participationExcedents: n(offre.participationExcedentsAnnuelle || 0),
  }));
}

/**
 * Décalage du premier versement.
 * Le champ saisi prime. S'il est vide et que la compagnie est PAX,
 * la note existante compte pour un an. Les deux ne s'additionnent pas.
 */
export function differeVersementAnnees(offre: {
  compagnie?: string | null;
  dureeDiffereAnnees?: number | null;
}): number {
  const saisi = anneesDiffere(offre.dureeDiffereAnnees);
  if (saisi != null) return saisi;
  if (compagnieEstPax(offre.compagnie)) return 1;
  return 0;
}

/** Année 1 = première année de retraite. */
export function offreVersee(offre: OffreVersement, annee: number): boolean {
  if (annee < 1) return false;
  const premiere = differeVersementAnnees(offre) + 1;
  if (annee < premiere) return false;
  if (offre.type === "viagere") return true;
  const duree = Math.floor(Number(offre.dureeAnnees));
  if (!Number.isFinite(duree) || duree <= 0) return true;
  return annee <= premiere + duree - 1;
}

/** Première année où toutes les offres sont versées. Null si elles ne se croisent pas. */
export function anneeToutesVerses(offres: OffreVersement[]): number | null {
  if (!offres.length) return null;
  for (let annee = 1; annee <= 80; annee += 1) {
    if (offres.every((offre) => offreVersee(offre, annee))) return annee;
  }
  return null;
}

export function calendriersDifferents(offres: OffreVersement[]): boolean {
  if (offres.length < 2) return false;
  const signature = (offre: OffreVersement) => {
    const start = differeVersementAnnees(offre) + 1;
    if (offre.type === "viagere") return `${start}:vie`;
    const duree = Math.floor(Number(offre.dureeAnnees));
    if (!Number.isFinite(duree) || duree <= 0) return `${start}:vie`;
    return `${start}:${duree}`;
  };
  const first = signature(offres[0]);
  return offres.some((offre) => signature(offre) !== first);
}

/** Part imposable d'une rente, sans AVS ni LPP. Pas d'arrondi. */
export function partImposableOffre(offre: {
  type: RenteHypothesisType;
  renteGarantie: number;
  participationExcedents: number;
}): number {
  const rente = n(offre.renteGarantie);
  const participation = n(offre.participationExcedents);
  if (offre.type === "viagere") return rente * 0.04 + participation * 0.7;
  return participation;
}

function offresActives(offres: OffreVersement[], annee: number): OffreVersement[] {
  return offres.filter((offre) => offreVersee(offre, annee));
}

/** AVS + LPP résiduelle une fois + parts des rentes versées cette année-là. */
export function revenuFiscalPeriode(input: {
  renteAvs: number;
  renteLppResiduelle?: number;
  offres: OffreVersement[];
  annee: number;
}): number {
  let sum = n(input.renteAvs) + n(input.renteLppResiduelle);
  for (const offre of offresActives(input.offres, input.annee)) {
    sum += partImposableOffre(offre);
  }
  return roundCents(sum);
}

/** Encaissé cette année-là : AVS + LPP résiduelle + rentes et participations versées. */
export function revenuBrutPeriode(input: {
  renteAvs: number;
  renteLppResiduelle?: number;
  offres: OffreVersement[];
  annee: number;
}): number {
  let sum = n(input.renteAvs) + n(input.renteLppResiduelle);
  for (const offre of offresActives(input.offres, input.annee)) {
    sum += n(offre.renteGarantie) + n(offre.participationExcedents);
  }
  return roundCents(sum);
}

export interface TotauxOffres {
  annee: number | null;
  capitalTotal: number;
  rentesGaranties: number;
  participations: number;
  prestationsAnnuelles: number;
}

/** Capital de toutes les offres. Rentes et participations : année où elles sont versées ensemble. */
export function totauxAnneeCommune(offres: OffreVersement[]): TotauxOffres {
  const annee = anneeToutesVerses(offres);
  const actives = annee == null ? [] : offresActives(offres, annee);
  const rentes = roundCents(
    actives.reduce((sum, offre) => sum + n(offre.renteGarantie), 0),
  );
  const participations = roundCents(
    actives.reduce((sum, offre) => sum + n(offre.participationExcedents), 0),
  );
  return {
    annee,
    capitalTotal: roundCents(
      offres.reduce((sum, offre) => sum + n(offre.capitalPlace), 0),
    ),
    rentesGaranties: rentes,
    participations,
    prestationsAnnuelles: roundCents(rentes + participations),
  };
}

export interface PeriodeVersement {
  anneeDebut: number;
  /** Dernière année incluse. Null : la période continue (rente viagère). */
  anneeFin: number | null;
  revenuBrut: number;
  revenuFiscal: number;
}

/** Découpe le versement selon le différé et la durée de chaque offre. */
export function periodesVersement(input: {
  renteAvs: number;
  renteLppResiduelle?: number;
  offres: OffreVersement[];
}): PeriodeVersement[] {
  const cuts = new Set<number>([1]);
  for (const offre of input.offres) {
    const start = differeVersementAnnees(offre) + 1;
    cuts.add(start);
    if (offre.type === "viagere") continue;
    const duree = Math.floor(Number(offre.dureeAnnees));
    if (Number.isFinite(duree) && duree > 0) cuts.add(start + duree);
  }
  const points = [...cuts].filter((year) => year >= 1).sort((a, b) => a - b);
  const segments: Array<{ debut: number; fin: number | null }> = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    segments.push({ debut: points[i], fin: points[i + 1] - 1 });
  }
  const tail = points[points.length - 1];
  if (input.offres.some((offre) => offreVersee(offre, tail)) || input.offres.length === 0) {
    segments.push({ debut: tail, fin: null });
  }
  const built = segments
    .filter((segment) => segment.fin == null || segment.fin >= segment.debut)
    .map((segment) => ({
      anneeDebut: segment.debut,
      anneeFin: segment.fin,
      revenuBrut: revenuBrutPeriode({ ...input, annee: segment.debut }),
      revenuFiscal: revenuFiscalPeriode({ ...input, annee: segment.debut }),
    }));
  const merged: PeriodeVersement[] = [];
  for (const period of built) {
    const prev = merged[merged.length - 1];
    if (
      prev &&
      prev.anneeFin != null &&
      prev.anneeFin + 1 === period.anneeDebut &&
      prev.revenuBrut === period.revenuBrut &&
      prev.revenuFiscal === period.revenuFiscal
    ) {
      prev.anneeFin = period.anneeFin;
    } else {
      merged.push({ ...period });
    }
  }
  return merged;
}

function detailOffre(offre: OffreVersement): RenteOffreDetail {
  return {
    compagnie: (offre.compagnie || "").trim(),
    type: offre.type,
    capitalPlace: n(offre.capitalPlace),
    dureeAnnees: offre.type === "certaine" ? offre.dureeAnnees ?? null : null,
    dureeDiffereAnnees: anneesDiffere(offre.dureeDiffereAnnees),
    differeVersementAnnees: differeVersementAnnees(offre),
    renteGarantie: n(offre.renteGarantie),
    participationExcedents: n(offre.participationExcedents),
  };
}

function titreOffres(details: RenteOffreDetail[], index: number): string {
  const names = details.map((detail, i) => detail.compagnie || `Offre ${i + 1}`);
  const title = names.join(" + ").trim();
  return title || `Hypothèse ${index + 1}`;
}

/**
 * Une colonne pour toute l'hypothèse. Les montants sont ceux de l'année
 * où toutes les rentes sont versées, lorsqu'une telle année existe.
 * L'impôt ESTV n'est pas appelé ici.
 */
export function buildColonneCombinee(
  rowId: string,
  index: number,
  offres: OffreVersement[],
  avs: number,
  residuelle: number,
  recommander: boolean,
): RenteHypothesisColumn {
  const annee = anneeToutesVerses(offres);
  const anneeMontants = annee ?? 1;
  const fiscal = revenuFiscalPeriode({
    renteAvs: avs,
    renteLppResiduelle: residuelle,
    offres,
    annee: anneeMontants,
  });
  const brut = revenuBrutPeriode({
    renteAvs: avs,
    renteLppResiduelle: residuelle,
    offres,
    annee: anneeMontants,
  });
  const actives = offresActives(offres, anneeMontants);
  const rentes = roundCents(
    actives.reduce((sum, offre) => sum + n(offre.renteGarantie), 0),
  );
  const participations = roundCents(
    actives.reduce((sum, offre) => sum + n(offre.participationExcedents), 0),
  );
  const details = offres.map(detailOffre);
  const titre = titreOffres(details, index);
  const capital = roundCents(
    offres.reduce((sum, offre) => sum + n(offre.capitalPlace), 0),
  );
  return {
    id: rowId || `h-${index + 1}`,
    kind: "hypothese",
    label: titre,
    compagnie: titre,
    typeLabel: details
      .map((detail) => (detail.type === "viagere" ? "Viagère" : "Certaine"))
      .join(" + "),
    capitalPlace: capital || null,
    dureeAnnees: null,
    dureeDiffereAnnees: null,
    renteAvs: avs,
    renteLppResiduelle: residuelle,
    renteGarantie: rentes,
    participationExcedents: participations,
    revenuBrutEncaisse: brut,
    revenuFiscalImposable: fiscal,
    impotEstv: null,
    revenuNetApresImpot: null,
    ecartNetAnnuelVsLpp: null,
    revenuAnnuelSurCapital:
      capital > 0 ? Math.round((brut / capital) * 10000) / 10000 : null,
    recommander,
    offres: details,
    calendriersDifferents: calendriersDifferents(offres),
    anneeCommune: annee,
  };
}
