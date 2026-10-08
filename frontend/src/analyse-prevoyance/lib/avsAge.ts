/**
 * Même table que backend/analyse_prevoyance_engine/rules/avs-age.ts.
 * Affichage immédiat dans le formulaire, sans lancer le calcul général.
 */

export interface FemaleLegalAgeRow {
  birthYear: number;
  legalAge: number;
}

export const FEMALE_LEGAL_AGE_TABLE: FemaleLegalAgeRow[] = [
  { birthYear: 1960, legalAge: 64 },
  { birthYear: 1961, legalAge: 64.25 },
  { birthYear: 1962, legalAge: 64.5 },
  { birthYear: 1963, legalAge: 64.75 },
  { birthYear: 1964, legalAge: 65 },
];

export const MALE_LEGAL_AGE = 65;

export function getLegalRetirementAge(
  civilite: string,
  birthDate: string,
): number {
  if (civilite === "Monsieur") return MALE_LEGAL_AGE;
  const year = Number(String(birthDate || "").slice(0, 4));
  if (!Number.isFinite(year)) return 65;
  const exact = FEMALE_LEGAL_AGE_TABLE.find((row) => row.birthYear === year);
  if (exact) return exact.legalAge;
  if (year < 1960) return 64;
  return 65;
}

export function formatLegalAgeLabel(legalAge: number): string {
  const years = Math.trunc(legalAge);
  const months = Math.round((legalAge - years) * 12);
  if (months === 0) return `${years} ans`;
  return `${years} ans et ${months} mois`;
}

export function legalAgeLabel(civilite: string, birthDate: string): string {
  if (!birthDate) return "—";
  return formatLegalAgeLabel(getLegalRetirementAge(civilite, birthDate));
}
