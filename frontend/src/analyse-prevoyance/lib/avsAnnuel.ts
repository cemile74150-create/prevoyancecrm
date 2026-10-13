/** Rente AVS annuelle = mensuelle × 13 (13e rente), pas × 12. */
export const AVS_MENSUALITES_PAR_AN = 13;

export function avsAnnuelFromMensuel(mensuel: number): number {
  return Math.round((mensuel || 0) * AVS_MENSUALITES_PAR_AN);
}
