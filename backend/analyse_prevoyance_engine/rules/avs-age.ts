/**
 * Règles AVS centralisées (âge légal hommes / femmes / générations transitoires).
 * Source Excel : feuille AVS!A4:B8 + formule B5.
 * Configurable via ce module uniquement — ne pas disperser ailleurs.
 */

export interface FemaleLegalAgeRow {
  birthYear: number;
  legalAge: number;
}

/** Table AVS 21 — femmes générations transitoires (Excel AVS!A4:B8). */
export const FEMALE_LEGAL_AGE_TABLE: FemaleLegalAgeRow[] = [
  { birthYear: 1960, legalAge: 64 },
  { birthYear: 1961, legalAge: 64.25 },
  { birthYear: 1962, legalAge: 64.5 },
  { birthYear: 1963, legalAge: 64.75 },
  { birthYear: 1964, legalAge: 65 },
];

export const MALE_LEGAL_AGE = 65;

export type GenderCivility = "Monsieur" | "Madame";

/**
 * Âge légal Excel :
 * - Monsieur → 65 (ignore année de naissance)
 * - Madame → VLOOKUP année naissance dans table femmes
 * Pour années hors table : avant 1960 → 64 ; après 1964 → 65.
 */
export function getLegalRetirementAge(
  civilite: GenderCivility,
  birthDate: Date | string,
): number {
  if (civilite === "Monsieur") return MALE_LEGAL_AGE;

  const year =
    typeof birthDate === "string"
      ? Number(birthDate.slice(0, 4))
      : birthDate.getFullYear();

  if (!Number.isFinite(year)) return 65;

  const exact = FEMALE_LEGAL_AGE_TABLE.find((r) => r.birthYear === year);
  if (exact) return exact.legalAge;
  if (year < 1960) return 64;
  return 65;
}

/** Affichage « X ans et Y mois » comme Excel C5. */
export function formatLegalAgeLabel(legalAge: number): string {
  const years = Math.trunc(legalAge);
  const months = Math.round((legalAge - years) * 12);
  if (months === 0) return `${years} ans`;
  return `${years} ans et ${months} mois`;
}

/**
 * Date de départ = 1er jour du mois suivant l’atteinte de l’âge légal.
 * Excel : EOMONTH(DATE(YEAR+INT(age), MONTH+(age-INT)*12, DAY), 0)+1
 */
export function getRetirementStartDate(
  birthDate: Date | string,
  legalAge: number,
): Date {
  const birth =
    typeof birthDate === "string" ? parseIsoDate(birthDate) : new Date(birthDate);
  const wholeYears = Math.trunc(legalAge);
  const fracMonths = Math.round((legalAge - wholeYears) * 12);

  const y = birth.getFullYear() + wholeYears;
  const m = birth.getMonth() + fracMonths; // 0-based
  const d = birth.getDate();

  // Date d’atteinte de l’âge légal
  const reach = new Date(y, m, d);
  // Fin du mois d’atteinte
  const endOfMonth = new Date(reach.getFullYear(), reach.getMonth() + 1, 0);
  // +1 jour = 1er du mois suivant
  const start = new Date(
    endOfMonth.getFullYear(),
    endOfMonth.getMonth(),
    endOfMonth.getDate() + 1,
  );
  return start;
}

export function formatDateIso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function formatDateFr(d: Date | string): string {
  const date = typeof d === "string" ? parseIsoDate(d) : d;
  return date.toLocaleDateString("fr-CH", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}
