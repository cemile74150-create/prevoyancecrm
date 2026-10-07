import type { AnalyseInput, Civilite, EtatCivil } from "./types";

export function genderFromCivilite(c: Civilite): number {
  return c === "Monsieur" ? 1 : 2;
}

export function relationshipFromEtat(e: EtatCivil): number {
  return e === "Marié(e)" ? 2 : 1;
}

export function formatChf(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(n);
}

export function formatPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-CH", {
    style: "percent",
    maximumFractionDigits: 2,
  }).format(n);
}

export function personDisplayName(
  p: AnalyseInput["client1"] | null | undefined,
): string {
  if (!p) return "—";
  const name = `${p.prenom || ""} ${p.nom || ""}`.trim();
  return name || "—";
}

/** Prénom saisi. S'il manque, on garde le libellé neutre déjà utilisé. */
export function personFirstName(
  person: { prenom?: string | null } | null | undefined,
  fallback: string,
): string {
  const prenom = (person?.prenom || "").trim();
  return prenom || fallback;
}
