/**
 * Saisie planification : rachat 3e pilier, âge de retrait LPP, rente-pont.
 * Les montants confirmés et indicatifs restent distincts.
 * Aucune durée de rente-pont n'est inventée.
 */
import { getRetirementStartDate } from "./avs-age";

export const RACHAT_ABSENT_UI =
  "Attention : aucune valeur de rachat n'a été renseignée pour la date de retrait sélectionnée. Le capital à l'échéance est utilisé à titre indicatif et peut différer du montant réellement disponible.";

export const RACHAT_ABSENT_PDF =
  "Attention : le montant du 3e pilier présenté correspond au capital à l'échéance du contrat. La valeur de rachat à la date de retrait anticipé n'a pas été communiquée. Le capital réellement disponible peut donc être différent.";

export const RENTE_PONT_CAISSE_WARNING =
  "Attention : vérifiez le règlement de la caisse de pension. Certaines caisses prévoient des restrictions sur le retrait du capital LPP lorsqu'une rente-pont est versée.";

export const PILIER_3B_NOTE =
  "3e pilier B : le capital n'est pas soumis à l'impôt séparé sur les prestations de prévoyance, sous réserve du traitement fiscal applicable au contrat.";

export interface ValeurRachatLike {
  date?: string | null;
  montant?: number | null;
}

export interface PillarCapitalLike {
  echeance?: string | null;
  montant?: number | null;
  valeursRachat?: ValeurRachatLike[] | null;
}

export type CapitalStatut = "echeance" | "rachat" | "indicatif";

export interface ResolvedPillarCapital {
  montant: number;
  statut: CapitalStatut;
  avertissement: string | null;
  avertissementPdf: string | null;
}

export function yearOfIso(iso: string | null | undefined): number | null {
  if (iso == null || !/^\d{4}/.test(String(iso))) return null;
  const year = Number(String(iso).slice(0, 4));
  return Number.isFinite(year) ? year : null;
}

export function money(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

/**
 * Capital utilisé pour un retrait de 3e pilier.
 * À l'échéance (ou après) : capital contractuel.
 * Avant l'échéance : valeur de rachat de la même année, sinon capital
 * d'échéance marqué indicatif. Jamais la valeur d'une autre année.
 */
export function resolveThirdPillarCapital(
  contract: PillarCapitalLike,
  withdrawalYear: number | null | undefined,
): ResolvedPillarCapital {
  const atMaturity = money(contract?.montant);
  const maturityYear = yearOfIso(contract?.echeance);
  const year =
    withdrawalYear == null || !Number.isFinite(Number(withdrawalYear))
      ? null
      : Number(withdrawalYear);

  if (year == null || maturityYear == null || year >= maturityYear) {
    return {
      montant: atMaturity,
      statut: "echeance",
      avertissement: null,
      avertissementPdf: null,
    };
  }

  const matches = (contract?.valeursRachat || []).filter(
    (row) => row != null && yearOfIso(row.date) === year,
  );
  if (matches.length >= 1) {
    const amounts = new Set(matches.map((row) => money(row.montant)));
    if (amounts.size === 1) {
      return {
        montant: money(matches[0].montant),
        statut: "rachat",
        avertissement: null,
        avertissementPdf: null,
      };
    }
  }

  return {
    montant: atMaturity,
    statut: "indicatif",
    avertissement: RACHAT_ABSENT_UI,
    avertissementPdf: RACHAT_ABSENT_PDF,
  };
}

export function effectiveLppWithdrawalAge(
  person: { ageRetraitLppSouhaite?: number | null } | null | undefined,
  dossierAge: number | null | undefined,
): number | null {
  const custom = person?.ageRetraitLppSouhaite;
  if (custom != null && custom !== ("" as unknown) && Number.isFinite(Number(custom))) {
    return Number(custom);
  }
  if (dossierAge != null && Number.isFinite(Number(dossierAge))) {
    return Number(dossierAge);
  }
  return null;
}

/**
 * Âge du tableau LPP dont le retrait tombe dans l'année civile demandée.
 * Par défaut 65→60. Si des âges sont fournis, seuls ceux du tableau comptent.
 * Aucun âge hors tableau : on n'invente pas une ligne.
 */
export function lppAgeForCalendarYear(
  birth: string | null | undefined,
  year: number | null | undefined,
  ages?: number[],
): number | null {
  if (!birth || !/^\d{4}-\d{2}-\d{2}/.test(String(birth))) return null;
  if (year == null || !Number.isFinite(Number(year))) return null;
  const target = Number(year);
  const list = (ages && ages.length ? ages : [65, 64, 63, 62, 61, 60])
    .map((age) => Number(age))
    .filter((age) => Number.isFinite(age));
  const unique = [...new Set(list)].sort((a, b) => b - a);
  for (const age of unique) {
    if (getRetirementStartDate(birth, age).getFullYear() === target) return age;
  }
  return null;
}

export function lppTableCapitalForYear(
  person:
    | {
        dateNaissance?: string | null;
        lpp?: Array<{ age: number; capital: number }> | null;
        lppAvoirs?: Array<{
          id: string;
          rows?: Array<{ age: number; capital: number }> | null;
        }> | null;
      }
    | null
    | undefined,
  sourceId: string | null | undefined,
  year: number,
): { age: number | null; capital: number; found: boolean } {
  if (!person) return { age: null, capital: 0, found: false };
  const rows =
    sourceId && sourceId !== "primary"
      ? person.lppAvoirs?.find((row) => row.id === sourceId)?.rows
      : person.lpp;
  const ages = (rows || [])
    .map((row) => Number(row.age))
    .filter((age) => Number.isFinite(age));
  const age = lppAgeForCalendarYear(
    person.dateNaissance,
    year,
    ages.length ? ages : undefined,
  );
  if (age == null) return { age: null, capital: 0, found: false };
  const row = lppCapitalForWithdrawalAge(rows, age);
  if (!row.found || !(row.capital > 0)) return { age, capital: 0, found: false };
  return { age, capital: row.capital, found: true };
}

/**
 * « 1re possible » retenue seulement si le tableau LPP a un capital
 * pour l'âge de cette année. Une année AVS recopiée (2034) sans ligne
 * n'est pas un choix : l'appelant revient à l'onglet LPP.
 */
export function acceptedLppScenarioYear(
  person: Parameters<typeof lppTableCapitalForYear>[0],
  item: { anneePremierePossible?: number | null; sourceId?: string | null },
): number | null {
  const year = Number(item.anneePremierePossible);
  if (!Number.isFinite(year)) return null;
  const looked = lppTableCapitalForYear(person, item.sourceId ?? null, year);
  return looked.found ? year : null;
}

export function lppCapitalForWithdrawalAge(
  rows: Array<{ age: number; capital: number }> | null | undefined,
  age: number | null,
): { capital: number; found: boolean } {
  if (age == null) {
    return { capital: 0, found: false };
  }
  const row = (rows || []).find((item) => Number(item.age) === Number(age));
  if (!row) return { capital: 0, found: false };
  return { capital: money(row.capital), found: true };
}

export interface RentePontLike {
  ageDebut?: number | null;
  ageFin?: number | null;
  montantAnnuel?: number | null;
}

/**
 * Rente-pont à un âge donné. Sans âge de fin, le montant n'est pas
 * projeté : la période ne doit pas être inventée.
 */
export function rentePontAtAge(
  bridges: RentePontLike[] | null | undefined,
  legacyAmount: number | null | undefined,
  age: number | null,
): { montant: number; aVerifier: boolean } {
  const rows = bridges || [];
  if (!rows.length) {
    return { montant: 0, aVerifier: money(legacyAmount) > 0 };
  }
  if (age == null || !Number.isFinite(age)) {
    return { montant: 0, aVerifier: true };
  }
  let total = 0;
  let aVerifier = false;
  for (const row of rows) {
    const start = row?.ageDebut == null ? null : Number(row.ageDebut);
    const end = row?.ageFin == null ? null : Number(row.ageFin);
    const amount = money(row?.montantAnnuel);
    if (
      start == null ||
      end == null ||
      !Number.isFinite(start) ||
      !Number.isFinite(end) ||
      end <= start
    ) {
      if (amount > 0 || start != null) aVerifier = true;
      continue;
    }
    if (age >= start && age < end) total += amount;
  }
  return { montant: money(total), aVerifier };
}
