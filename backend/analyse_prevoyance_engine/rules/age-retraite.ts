/** Âge de retraite souhaité déjà porté par le dossier, résolu par assuré. */

export function ageRetraitePersonne(
  person: { ageRetraiteSouhaite?: number | null } | null | undefined,
  dossierAge: number | null | undefined,
): number | null {
  const own = person?.ageRetraiteSouhaite;
  if (own != null && Number.isFinite(Number(own))) return Number(own);
  if (dossierAge != null && Number.isFinite(Number(dossierAge))) return Number(dossierAge);
  return null;
}
