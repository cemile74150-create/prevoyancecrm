/** Année de retrait d'un libre passage.

La date saisie prime pour la frise. Sinon, année de naissance + âge de
déblocage. L'âge n'est jamais déduit de la date, ni l'inverse.
*/
export function anneeRetraitLibrePassage(
  lp: { dateRetraitPossible?: string | null; ageDeblocage?: number | null },
  dateNaissance?: string | null,
): number | null {
  const fromDate = /^(\d{4})/.exec((lp.dateRetraitPossible || "").trim());
  if (fromDate) return Number(fromDate[1]);
  const age = lp.ageDeblocage;
  if (age == null || !Number.isFinite(Number(age))) return null;
  const birth = /^(\d{4})/.exec((dateNaissance || "").trim());
  if (!birth) return null;
  return Number(birth[1]) + Number(age);
}
