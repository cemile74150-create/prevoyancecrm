import type { PersonInput } from "../types";

/** True si au moins une ligne LPP (historique ou caisse) a un capital ou une rente. */
export function personHasLppSaisie(person: PersonInput | null | undefined): boolean {
  if (!person) return false;
  const rows = [
    ...(person.lpp || []),
    ...(person.lppAvoirs || []).flatMap((avoir) => avoir.rows || []),
  ];
  return rows.some((row) => Number(row.capital || 0) > 0 || Number(row.rente || 0) > 0);
}
