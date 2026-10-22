import type { AnalyseInput, PersonComputed } from "../types";

export interface EvolutionYearRow {
  year: number;
  revenu: number;
  lacune90: number;
  phase: "salaire" | "transition" | "rente";
}

export interface EvolutionResult {
  /** Objectif Excel Evolution : 90 % du salaire avant retraite. */
  cibleRemplacement: number;
  salaireReference: number;
  renteReference: number;
  dateDepart1: string;
  dateDepart2: string | null;
  rows: EvolutionYearRow[];
}

/**
 * Évolution après retraite — formules Excel feuille homonyme.
 * Cible lacune : 90 % (C = revenu − salaires×90 % si pas en phase salaire pure).
 *
 * Le graphique du rapport additionne l'AVS et la rente LPP complète
 * des deux assurés, avant tout retrait en capital.
 * Chaque assuré passe du salaire à cette rente à sa propre date de fin
 * d'activité, pas au 1er janvier de l'année ni à la date AVS de l'autre.
 * Le pourcentage déblocable reste utilisé par la planification, les offres
 * et les comparaisons, pas par ces barres.
 */
export class PostRetirementEvolutionService {
  build(
    input: AnalyseInput,
    client1: PersonComputed,
    conjoint: PersonComputed | null,
    options?: { startYear?: number; endYear?: number },
  ): EvolutionResult {
    const married = input.etatCivil === "Marié(e)" && !!conjoint;
    const salaire1 = input.salaireClient1 || 0;
    const salaire2 = married ? input.salaireConjoint || 0 : 0;
    const rente1 = client1.renteTotale65;
    const rente2 = married ? conjoint!.renteTotale65 : 0;
    const salaireReference = round2(salaire1 + salaire2);
    const renteReference = round2(rente1 + rente2);

    const dep1 = activityEnd(client1);
    const dep2 =
      conjoint && input.etatCivil === "Marié(e)"
        ? activityEnd(conjoint)
        : null;

    const startYear =
      options?.startYear ??
      Math.min(dep1.getFullYear() - 2, new Date().getFullYear());
    const endYear =
      options?.endYear ??
      Math.max(dep1.getFullYear(), dep2?.getFullYear() ?? 0) + 15;

    const rows: EvolutionYearRow[] = [];
    for (let year = startYear; year <= endYear; year++) {
      const part1 = personYearIncome(year, dep1, salaire1, rente1);
      const part2 = dep2
        ? personYearIncome(year, dep2, salaire2, rente2)
        : { revenu: 0, phase: "rente" as const };
      const revenu = round2(part1.revenu + part2.revenu);
      const pureSalaire = revenu === salaireReference && salaireReference > 0;
      const lacune90 = pureSalaire
        ? 0
        : round2(revenu - salaireReference * 0.9);
      const phase = dep2 ? combinePhase(part1.phase, part2.phase) : part1.phase;
      rows.push({ year, revenu, lacune90, phase });
    }

    return {
      cibleRemplacement: 0.9,
      salaireReference,
      renteReference,
      dateDepart1: client1.dateFinActivite || client1.dateDepart,
      dateDepart2: conjoint
        ? conjoint.dateFinActivite || conjoint.dateDepart
        : null,
      rows,
    };
  }
}

type YearPhase = "salaire" | "transition" | "rente";

/**
 * Fin d'activité réelle (jour, mois, année). Le départ AVS légal
 * ne remplace cette date que lorsqu'elle n'a pas été calculée.
 */
function activityEnd(person: PersonComputed): Date {
  return parseIso(person.dateFinActivite || person.dateDepart);
}

function combinePhase(a: YearPhase, b: YearPhase): YearPhase {
  return a === b ? a : "transition";
}

/**
 * Salaire pendant les mois jusqu'à la fin d'activité comprise.
 * La rente (AVS + LPP) commence le mois suivant, pas le 1er janvier.
 * 1er février : janvier et février au salaire, mars à décembre en rente.
 * 1er janvier : janvier au salaire, février à décembre en rente.
 * Après le 1er du mois, les jours restants du mois suivant sont encore
 * du salaire, au prorata du jour.
 */
function personYearIncome(
  year: number,
  depart: Date,
  salaire: number,
  rente: number,
): { revenu: number; phase: YearPhase } {
  const yDep = depart.getFullYear();
  const mDep = depart.getMonth() + 1; // 1-12
  const dDep = depart.getDate() || 1;
  if (year < yDep) return { revenu: salaire, phase: "salaire" };
  if (year > yDep) return { revenu: rente, phase: "rente" };
  const daysInMonth = new Date(yDep, mDep, 0).getDate();
  const day = Math.min(Math.max(dDep, 1), daysInMonth);
  const salaryMonths = Math.min(12, mDep + (day <= 1 ? 0 : (day - 1) / daysInMonth));
  const pensionMonths = 12 - salaryMonths;
  if (salaryMonths <= 0) return { revenu: round2(rente), phase: "rente" };
  if (pensionMonths <= 0) return { revenu: round2(salaire), phase: "salaire" };
  const revenu = (salaire * salaryMonths + rente * pensionMonths) / 12;
  return { revenu: round2(revenu), phase: "transition" };
}

function parseIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const postRetirementEvolutionService =
  new PostRetirementEvolutionService();
