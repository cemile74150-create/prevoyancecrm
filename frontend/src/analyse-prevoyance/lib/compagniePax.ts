/** Note d'affichage. Ne remplit pas le champ « Durée du différé ». */
export const NOTE_PAX_DIFFERE =
  "Pour les contrats PAX, un différé d’un an s’applique systématiquement avant le premier versement de la rente.";

export function compagnieEstPax(name: string | null | undefined): boolean {
  return /pax/i.test(String(name || ""));
}
