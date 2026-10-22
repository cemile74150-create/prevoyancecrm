/**
 * Comparatif d'offres de rente, hors parcours AVS / LPP.
 *
 * Cet onglet a sa propre assiette. Le rapport d'analyse
 * (revenuFiscalImposable, participation à 100 %) n'est pas modifié :
 * - certaine : 70 % de la participation aux excédents
 *   (la rente garantie est encaissée, elle n'est pas imposable) ;
 * - viagère : 4 % de la rente garantie + 100 % de la participation.
 * Pas d'AVS, pas de LPP.
 *
 * L'impôt sur la fortune d'une rente certaine suit le capital
 * qui diminue de la rente garantie chaque année. Plancher à 0.
 * Une rente viagère n'a pas de calendrier sur une durée inventée.
 */

import { roundMoney } from "./rente-hypotheses.ts";

export type OffreRenteType = "certaine" | "viagere";

export interface AssietteOffreInput {
  type: OffreRenteType;
  renteGarantie: number;
  participationExcedents: number;
}

function n(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

/** Revenu transmis à ESTV pour cet onglet. Pas d'AVS, pas de LPP. */
export function assietteOffreComparatif(input: AssietteOffreInput): number {
  const garantie = n(input.renteGarantie);
  const participation = n(input.participationExcedents);
  if (input.type === "viagere") {
    return roundMoney(garantie * 0.04 + participation);
  }
  return roundMoney(participation * 0.7);
}

/** Ce que l'offre verse : rente garantie + participation. */
export function revenuEncaisseOffre(
  renteGarantie: number,
  participationExcedents: number,
): number {
  return roundMoney(n(renteGarantie) + n(participationExcedents));
}

/**
 * Fortune imposable année par année.
 * Année 1 = capital. Chaque année suivante = fortune précédente − rente.
 * Plancher à 0. La durée doit être celle de la rente certaine.
 */
export function fortunesDecroissantes(
  capitalPlace: number,
  renteAnnuelle: number,
  dureeAnnees: number,
): number[] {
  const years = Math.floor(n(dureeAnnees));
  if (years <= 0) return [];
  const step = Math.max(0, n(renteAnnuelle));
  let fortune = Math.max(0, n(capitalPlace));
  const out: number[] = [];
  for (let i = 0; i < years; i += 1) {
    out.push(roundMoney(fortune));
    fortune = Math.max(0, roundMoney(fortune - step));
  }
  return out;
}

export const LIBELLE_ICC_ANNUEL = "ICC / IFD annuel";

export function libelleTotalIccDuree(annees: number): string {
  return `Total ICC / IFD sur ${annees} ans`;
}

export interface ImpotRevenuPdf {
  /** total = rente certaine à durée connue. annuel = viagère ou certaine sans durée. */
  mode: "total" | "annuel" | "inconnu";
  libelle: string;
  montant: number | null;
  annees: number | null;
}

/**
 * PDF du comparatif d'offres seulement.
 * Rente certaine : impôt annuel × durée, sans calendrier.
 * Rente viagère : impôt annuel, sans durée inventée.
 */
export function impotRevenuPourPdf(
  type: OffreRenteType,
  impotAnnuel: number | null | undefined,
  dureeAnnees: number | null | undefined,
): ImpotRevenuPdf {
  if (impotAnnuel == null || Number.isNaN(Number(impotAnnuel))) {
    return { mode: "inconnu", libelle: "ICC / IFD", montant: null, annees: null };
  }
  const years = Math.floor(n(Number(dureeAnnees)));
  if (type === "certaine" && years > 0) {
    return {
      mode: "total",
      libelle: libelleTotalIccDuree(years),
      montant: roundMoney(n(impotAnnuel) * years),
      annees: years,
    };
  }
  return {
    mode: "annuel",
    libelle: LIBELLE_ICC_ANNUEL,
    montant: roundMoney(n(impotAnnuel)),
    annees: null,
  };
}

/** Somme des impôts fortune annuels. Null si une année n'a pas de montant. */
export function totalImpotFortune(impots: Array<number | null | undefined>): number | null {
  if (!impots.length) return null;
  let sum = 0;
  for (const value of impots) {
    if (value == null || Number.isNaN(value)) return null;
    sum += value;
  }
  return roundMoney(sum);
}
