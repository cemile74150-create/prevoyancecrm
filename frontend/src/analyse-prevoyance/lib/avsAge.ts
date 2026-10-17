/**
 * Même table que backend/analyse_prevoyance_engine/rules/avs-age.ts.
 * Affichage immédiat dans le formulaire, sans lancer le calcul général.
 *
 * Convention numérique (identique au moteur) : années + mois/12
 * ex. 64 ans et 9 mois → 64.75, 64 ans et 3 mois → 64.25.
 */

import { RETIREMENT_AGES } from "./types";

export interface FemaleLegalAgeRow {
  birthYear: number;
  legalAge: number;
}

export interface DesiredRetirementAgeOption {
  value: number;
  label: string;
}

export const FEMALE_LEGAL_AGE_TABLE: FemaleLegalAgeRow[] = [
  { birthYear: 1960, legalAge: 64 },
  { birthYear: 1961, legalAge: 64.25 },
  { birthYear: 1962, legalAge: 64.5 },
  { birthYear: 1963, legalAge: 64.75 },
  { birthYear: 1964, legalAge: 65 },
];

export const MALE_LEGAL_AGE = 65;

export const AVS_ANTICIPATION_MAX_ANNEES = 2;
export const AVS_REDUCTION_PAR_ANNEE = 0.068;

export function anticipationAvsAnnees(value: unknown): 0 | 1 | 2 {
  const years = Number(value);
  if (years === 1 || years === 2) return years;
  return 0;
}

export function ageAvecAnticipationAvs(legalAge: number, years: 0 | 1 | 2): number {
  return Math.round((legalAge - years) * 100) / 100;
}

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

/**
 * Liste « Âge de retraite souhaité » : années entières 65→60, plus l'âge
 * légal AVS de cette personne s'il n'est pas déjà un entier de la liste.
 * L'âge légal fractionnel est en tête (après « Âge applicable au dossier »).
 */
export function desiredRetirementAgeOptions(
  civilite: string,
  birthDate: string,
): DesiredRetirementAgeOption[] {
  const integers: DesiredRetirementAgeOption[] = RETIREMENT_AGES.map((age) => ({
    value: age,
    label: `${age} ans`,
  }));
  if (!birthDate) return integers;

  const legalAge = getLegalRetirementAge(civilite, birthDate);
  if (RETIREMENT_AGES.some((age) => age === legalAge)) return integers;

  return [
    { value: legalAge, label: formatLegalAgeLabel(legalAge) },
    ...integers,
  ];
}

/** 1er jour du mois suivant l'atteinte de l'âge. Même règle que le moteur. */
export function getRetirementStartDate(birthDate: string, age: number): Date {
  const [y, m, d] = String(birthDate).split("-").map(Number);
  const birth = new Date(y, (m || 1) - 1, d || 1);
  const wholeYears = Math.trunc(age);
  const fracMonths = Math.round((age - wholeYears) * 12);
  const reach = new Date(
    birth.getFullYear() + wholeYears,
    birth.getMonth() + fracMonths,
    birth.getDate(),
  );
  const endOfMonth = new Date(reach.getFullYear(), reach.getMonth() + 1, 0);
  return new Date(
    endOfMonth.getFullYear(),
    endOfMonth.getMonth(),
    endOfMonth.getDate() + 1,
  );
}

export function formatDateCh(date: Date): string {
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${day}.${month}.${date.getFullYear()}`;
}

export function lppWithdrawalDate(
  birth: string | null | undefined,
  age: number | null | undefined,
): Date | null {
  if (!birth || !/^\d{4}-\d{2}-\d{2}/.test(birth)) return null;
  if (age == null || !Number.isFinite(Number(age))) return null;
  const date = getRetirementStartDate(birth, Number(age));
  return Number.isFinite(date.getTime()) ? date : null;
}
