/**
 * Comparatif d'offres de rente, hors parcours AVS / LPP.
 *
 * Même part imposable que le rapport d'analyse, sans AVS ni LPP
 * tant qu'ils ne sont pas ajoutés :
 * - certaine : 0 % de la rente garantie + 100 % de la participation
 *   (la rente garantie est encaissée, elle n'entre pas dans l'impôt) ;
 * - viagère : 4 % de la rente garantie + 70 % de la participation.
 * Pas d'AVS, pas de LPP.
 *
 * L'impôt sur le revenu de la rente est annuel. Il n'est pas
 * multiplié par la durée.
 * L'impôt sur la fortune d'une rente certaine suit le capital
 * qui diminue de la rente garantie chaque année. Plancher à 0.
 * L'impôt fortune « si capital non affecté » garde ce capital
 * constant et multiplie l'impôt d'une année par la durée saisie.
 * Une rente viagère n'a pas de durée inventée : gain net et
 * impôts fortune qui dépendent d'une durée restent vides.
 */

import { roundMoney } from "./rente-hypotheses.ts";
import type { RevenuAjouteImpot } from "../types.ts";

export type OffreRenteType = "certaine" | "viagere";

export interface AssietteOffreInput {
  type: OffreRenteType;
  renteGarantie: number;
  participationExcedents: number;
}

function n(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

/** Libellé d'une ligne ajoutée à l'impôt sur le revenu du comparatif d'offres. */
export function libelleRevenuAjoute(row: RevenuAjouteImpot): string {
  if (row.kind === "avs") return "AVS";
  if (row.kind === "lpp") return "Rente LPP";
  const label = (row.libelle || "").trim();
  return label || "Autre revenu";
}

/**
 * Somme des revenus ajoutés avec +. Le dossier (AVS saisie, LPP, fortune)
 * n'entre pas tout seul : seulement ces lignes.
 */
export function totalRevenusAjoutesImpot(
  rows: RevenuAjouteImpot[] | null | undefined,
): number {
  return roundMoney(
    (rows || []).reduce((sum, row) => sum + Math.max(0, n(row.montant)), 0),
  );
}

/** Revenu de l'offre transmis à ESTV, avant les lignes ajoutées avec +. */
export function assietteOffreComparatif(input: AssietteOffreInput): number {
  const garantie = n(input.renteGarantie);
  const participation = n(input.participationExcedents);
  if (input.type === "viagere") {
    return roundMoney(garantie * 0.04 + participation * 0.7);
  }
  return roundMoney(participation);
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

export const LIBELLE_IMPOT_RENTE_ANNUEL = "Impôt de la rente (par an)";

export interface ImpotRevenuPdf {
  /** annuel = impôt de l'année. inconnu = impôt non calculé. Jamais un total sur N ans. */
  mode: "annuel" | "inconnu";
  libelle: string;
  montant: number | null;
  annees: number | null;
}

/**
 * PDF du comparatif d'offres seulement.
 * Le montant est l'impôt annuel de la rente, certaine ou viagère.
 * La durée ne le multiplie pas : un total « sur N ans » montrait
 * l'annuel comme un cumul, ou le cumul comme s'il était l'annuel.
 */
export function impotRevenuPourPdf(
  _type: OffreRenteType,
  impotAnnuel: number | null | undefined,
  _dureeAnnees: number | null | undefined,
): ImpotRevenuPdf {
  if (impotAnnuel == null || Number.isNaN(Number(impotAnnuel))) {
    return {
      mode: "inconnu",
      libelle: LIBELLE_IMPOT_RENTE_ANNUEL,
      montant: null,
      annees: null,
    };
  }
  return {
    mode: "annuel",
    libelle: LIBELLE_IMPOT_RENTE_ANNUEL,
    montant: roundMoney(n(impotAnnuel)),
    annees: null,
  };
}

/**
 * Gain net = revenu net annuel × durée saisie − capital affecté à la rente.
 * Sans durée (viagère, ou certaine sans durée) : pas de montant.
 */
export function gainNetOffre(
  revenuNetAnnuel: number | null | undefined,
  dureeAnnees: number | null | undefined,
  capitalPlace: number | null | undefined,
): number | null {
  if (revenuNetAnnuel == null || Number.isNaN(Number(revenuNetAnnuel))) return null;
  const years = Math.floor(n(Number(dureeAnnees)));
  if (years <= 0) return null;
  return roundMoney(n(revenuNetAnnuel) * years - n(Number(capitalPlace)));
}

/**
 * Impôt fortune si le capital n'est pas affecté à la rente.
 * Fortune constante = capital affecté. Impôt ESTV d'une année (revenu 0) × durée.
 * Ce n'est pas la fortune qui diminue de la rente garantie.
 */
export function impotFortuneCapitalNonAffecte(
  impotAnnuelSurCapital: number | null | undefined,
  dureeAnnees: number | null | undefined,
): number | null {
  if (impotAnnuelSurCapital == null || Number.isNaN(Number(impotAnnuelSurCapital))) return null;
  const years = Math.floor(n(Number(dureeAnnees)));
  if (years <= 0) return null;
  return roundMoney(n(impotAnnuelSurCapital) * years);
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
