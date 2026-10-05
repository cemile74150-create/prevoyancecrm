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
 * Excel strict : `Evolution après retraite!I4 = 0` (salaire conjoint forcé à 0).
 * Le salaire conjoint saisi ailleurs dans le formulaire est **ignoré** pour cette série.
 */
export class PostRetirementEvolutionService {
  build(
    input: AnalyseInput,
    client1: PersonComputed,
    conjoint: PersonComputed | null,
    options?: { startYear?: number; endYear?: number },
  ): EvolutionResult {
    const salaire1 = input.salaireClient1 || 0;
    /** Excel I4 = 0 — ne pas utiliser input.salaireConjoint. */
    const salaire2 = 0;
    const rente1 = client1.renteTotale65;
    const rente2 = conjoint?.renteTotale65 ?? 0;
    const salaireReference = round2(salaire1 + salaire2);
    const renteReference = round2(rente1 + rente2);

    const dep1 = parseIso(client1.dateDepart);
    const dep2 =
      conjoint && input.etatCivil === "Marié(e)"
        ? parseIso(conjoint.dateDepart)
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
      const phase =
        part1.phase === "transition" || part2.phase === "transition"
          ? "transition"
          : part1.phase === "salaire" || part2.phase === "salaire"
            ? "salaire"
            : "rente";
      rows.push({ year, revenu, lacune90, phase });
    }

    return {
      cibleRemplacement: 0.9,
      salaireReference,
      renteReference,
      dateDepart1: client1.dateDepart,
      dateDepart2: conjoint?.dateDepart ?? null,
      rows,
    };
  }
}

function personYearIncome(
  year: number,
  depart: Date,
  salaire: number,
  rente: number,
): { revenu: number; phase: "salaire" | "transition" | "rente" } {
  const yDep = depart.getFullYear();
  const mDep = depart.getMonth() + 1; // 1-12
  if (year < yDep) return { revenu: salaire, phase: "salaire" };
  if (year > yDep) return { revenu: rente, phase: "rente" };
  // Année de transition : prorata Excel
  // salaire*(MONTH-1)/12 + rente*(13-MONTH)/12
  const revenu =
    (salaire * (mDep - 1)) / 12 + (rente * (13 - mDep)) / 12;
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
