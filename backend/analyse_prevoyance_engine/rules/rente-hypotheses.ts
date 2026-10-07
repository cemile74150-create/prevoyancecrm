/**
 * Règles métier des hypothèses de rente (hors ESTV).
 *
 * Le revenu fiscal n'est pas le revenu encaissé :
 * - certaine : AVS + rente LPP résiduelle + 70 % des participations
 *   (la rente garantie n'est pas imposable) ;
 * - viagère : AVS + rente LPP résiduelle + 4 % de la rente garantie
 *   + 70 % des participations.
 * La rente LPP résiduelle est imposable en totalité, comme une rente LPP.
 * L'impôt est ensuite calculé par ESTV sur ce revenu fiscal.
 */

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
  const participation = n(input.participationExcedents) * 0.7;
  if (input.type === "viagere") {
    return roundMoney(avs + residuelle + n(input.renteGarantie) * 0.04 + participation);
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
