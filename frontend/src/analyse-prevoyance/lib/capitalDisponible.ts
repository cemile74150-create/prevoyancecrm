/**
 * Capital déjà saisi dans le dossier : LPP retiré à l'âge du tableau,
 * libres passages et 3e piliers (montant saisi, comme le total 3e pilier du rapport).
 * Rien n'est inventé : sans montant saisi, le résultat est null et aucun avertissement n'est affiché.
 */
import { effectiveLppWithdrawalAge } from "@/analyse-prevoyance/lib/planificationSaisie";
import type { AnalyseInput, LppAvoir, LppByAge, PersonInput } from "@/analyse-prevoyance/lib/types";
import {
  LPP_PCT_DEBLOCABLE_DEFAULT,
  RETIREMENT_AGES,
  librePassageRetire,
} from "@/analyse-prevoyance/lib/types";

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function pctOf(pct: number | null | undefined): number {
  if (pct == null || Number.isNaN(Number(pct))) return LPP_PCT_DEBLOCABLE_DEFAULT;
  return Math.min(100, Math.max(0, Number(pct)));
}

function ageTableau(person: PersonInput, input: AnalyseInput): number {
  const requested = effectiveLppWithdrawalAge(
    person,
    input.ageRetraitLpp ?? input.ageRetraiteSouhaite,
  );
  if (requested != null && (RETIREMENT_AGES as readonly number[]).includes(requested)) {
    return requested;
  }
  return 65;
}

function rowAt(rows: LppByAge[] | null | undefined, age: number): LppByAge | null {
  return (rows || []).find((row) => Number(row.age) === age) ?? null;
}

function capitalAvoir(avoir: LppAvoir, personAge: number): { montant: number; connu: boolean } {
  const age =
    avoir.ageRetrait != null &&
    (RETIREMENT_AGES as readonly number[]).includes(avoir.ageRetrait)
      ? avoir.ageRetrait
      : personAge;
  const row = rowAt(avoir.rows, age);
  if (!row) return { montant: 0, connu: false };
  if (avoir.type === "etatique") {
    if (avoir.retraitEtatique === "rente_entiere") {
      return { montant: 0, connu: (row.capital || 0) > 0 };
    }
    if (
      avoir.retraitEtatique === "saisi" &&
      row.capitalSaisi != null &&
      row.renteConserveeSaisie != null
    ) {
      return { montant: round2(row.capitalSaisi), connu: row.capitalSaisi > 0 };
    }
    return { montant: round2(row.capital || 0), connu: (row.capital || 0) > 0 };
  }
  const connu = (row.capital || 0) > 0;
  return { montant: round2((row.capital || 0) * (pctOf(avoir.pctDeblocable) / 100)), connu };
}

function avoirsPersonne(person: PersonInput): LppAvoir[] {
  return [
    {
      id: "primary",
      institution: person.lppInstitution || "",
      rows: person.lpp || [],
      type: person.lppType === "etatique" ? "etatique" : "classique",
      renteUnite: person.lppRenteUnite === "mensuel" ? "mensuel" : "annuel",
      ageRetrait: null,
      retraitEtatique: person.lppRetraitEtatique || "capital_max",
      pctDeblocable: person.lppPctDeblocable,
    },
    ...(person.lppAvoirs || []),
  ];
}

export function capitalDisponibleDossier(input: AnalyseInput): number | null {
  const persons = [input.client1];
  if (input.etatCivil === "Marié(e)" && input.conjoint) persons.push(input.conjoint);
  let connu = false;
  let total = 0;
  for (const person of persons) {
    const age = ageTableau(person, input);
    for (const avoir of avoirsPersonne(person)) {
      const part = capitalAvoir(avoir, age);
      if (part.connu) connu = true;
      total += part.montant;
    }
    for (const pillar of person.troisiemePilier || []) {
      const montant = Number(pillar.montant) || 0;
      if (montant > 0) connu = true;
      total += montant;
    }
  }
  for (const lp of input.libresPassages || []) {
    const montant = librePassageRetire(lp);
    if (montant > 0) connu = true;
    total += montant;
  }
  if (!connu) return null;
  return round2(total);
}
