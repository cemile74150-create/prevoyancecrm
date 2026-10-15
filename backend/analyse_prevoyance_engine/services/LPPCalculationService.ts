import {
  LPP_CONVERSION_RATES,
  LPP_PCT_DEBLOCABLE_DEFAULT,
  RETIREMENT_AGES,
  type LppAvoirLigne,
  type LppByAge,
  type LppCaisseType,
  type LppRenteUnite,
  type LppRetraitEtatique,
  type PersonInput,
  type RetirementAge,
} from "../types";

const EPS = 0.05;

/**
 * Service LPP — capitaux / rentes par âge, taux de conversion Excel,
 * et % déblocable paramétrable.
 *
 * Règle métier (une seule application du %) :
 * 1. Capital de référence = avoir LPP total avant retrait (saisie âge 65).
 * 2. % disponible = part retirable (0–100).
 * 3. Capital effectivement retirable = référence × % / 100, UNE fois.
 * Si une valeur égale déjà ce retirable, ne pas réappliquer le %.
 * Rente résiduelle = rente totale saisie × (1 − % / 100), sur la même référence.
 */
export class LPPCalculationService {
  conversionRate(row: LppByAge): number | null {
    if (row.age === 65) {
      if (!row.capital || row.capital <= 0) return null;
      return row.rente / row.capital;
    }
    return LPP_CONVERSION_RATES[row.age];
  }

  normalizeRows(rows: LppByAge[]): LppByAge[] {
    const byAge = new Map(rows.map((r) => [r.age, r]));
    return RETIREMENT_AGES.map((age) => {
      const existing = byAge.get(age);
      const row: LppByAge = {
        age,
        capital: round2(existing?.capital || 0),
        rente: round2(existing?.rente || 0),
      };
      if (existing?.renteReduite != null) {
        row.renteReduite = round2(existing.renteReduite);
      }
      if (existing?.capitalSaisi != null) {
        row.capitalSaisi = round2(existing.capitalSaisi);
      }
      if (existing?.renteConserveeSaisie != null) {
        row.renteConserveeSaisie = round2(existing.renteConserveeSaisie);
      }
      return row;
    });
  }

  getAtAge(rows: LppByAge[], age: RetirementAge): LppByAge {
    return (
      rows.find((r) => r.age === age) ?? { age, capital: 0, rente: 0 }
    );
  }

  /** Avoir LPP total à 65 ans — base unique du % déblocable. */
  referenceCapital(rows: LppByAge[] | null | undefined): number {
    return round2(this.getAtAge(this.normalizeRows(rows || []), 65).capital);
  }

  /**
   * Normalise le % déblocable (0–100). Valeur absente / invalide → défaut 100.
   */
  resolvePctDeblocable(pct: number | null | undefined): number {
    if (pct == null || Number.isNaN(pct)) return LPP_PCT_DEBLOCABLE_DEFAULT;
    return Math.min(100, Math.max(0, round2(pct)));
  }

  /** Capital effectivement retiré = capital de référence × pct/100 (une fois). */
  capitalRetire(capital: number, pct: number | null | undefined): number {
    const p = this.resolvePctDeblocable(pct);
    return round2((capital || 0) * (p / 100));
  }

  /**
   * Retirable à partir de l’avoir total. Si `maybeAlreadyRetirable` égale déjà
   * référence × % / 100, on renvoie cette valeur — pas de second %.
   */
  capitalEffectivementRetirable(
    reference: number,
    pct: number | null | undefined,
    maybeAlreadyRetirable?: number | null,
  ): number {
    const once = this.capitalRetire(reference, pct);
    if (
      maybeAlreadyRetirable != null &&
      this.isAlreadyRetirable(maybeAlreadyRetirable, reference, pct)
    ) {
      return once;
    }
    return once;
  }

  /**
   * True si `value` est déjà le retirable (référence × % / 100) et n’est pas
   * l’avoir total. Dans ce cas un nouvel × % serait une double application.
   */
  isAlreadyRetirable(
    value: number,
    reference: number,
    pct: number | null | undefined,
  ): boolean {
    const p = this.resolvePctDeblocable(pct);
    if (p <= 0 || p >= 100) return false;
    const once = this.capitalRetire(reference, p);
    return nearlyEqual(value, once) && !nearlyEqual(value, reference);
  }

  /**
   * Rente résiduelle après retrait partiel = rente × (1 − pct/100).
   * 100 % → 0 ; 50 % → 50 % de la rente ; 0 % → rente entière.
   * `rente` = rente totale saisie sur l’avoir de référence, pas une résiduelle.
   */
  renteResiduelle(rente: number, pct: number | null | undefined): number {
    const p = this.resolvePctDeblocable(pct);
    return round2((rente || 0) * (1 - p / 100));
  }

  /**
   * Diagnostic : ne modifie aucun dossier. Signale un risque si le capital
   * saisi ressemble à un retirable déjà réduit (taux de conversion irréaliste).
   */
  diagnosePerson(person: PersonInput): LppPctDiagnostic {
    const reference = this.referenceCapital(person.lpp);
    const pct = this.resolvePctDeblocable(person.lppPctDeblocable);
    const retirableOnce = this.capitalRetire(reference, pct);
    const doublePct = this.capitalRetire(retirableOnce, pct);
    const rente = round2(this.getAtAge(this.normalizeRows(person.lpp || []), 65).rente);
    const conversionRate = reference > 0 ? rente / reference : null;
    const residualOnce = this.renteResiduelle(rente, pct);
    return {
      reference,
      pct,
      retirableOnce,
      doublePct,
      renteTotale: rente,
      renteResiduelleOnce: residualOnce,
      conversionRate,
      /**
       * À 65 ans un taux > 8 % est atypique : le capital saisi est souvent
       * déjà le retirable (cas Excel HELFER Ariane 148 678 à 50 %).
       */
      risqueCapitalDejaRetirable:
        pct > 0 &&
        pct < 100 &&
        conversionRate != null &&
        conversionRate > 0.08,
    };
  }

  /**
   * Caisse principale, puis caisses ajoutées.
   * Une planification sans lppAvoirs ne contient que la caisse principale.
   */
  listAvoirs(person: PersonInput): AvoirRef[] {
    const extras = person.lppAvoirs || [];
    return [
      {
        id: "primary",
        institution: (person.lppInstitution || "").trim(),
        rows: person.lpp || [],
        pct: person.lppPctDeblocable,
        type: person.lppType === "etatique" ? "etatique" : "classique",
        renteUnite: person.lppRenteUnite === "mensuel" ? "mensuel" : "annuel",
        ageRetrait: null,
        retraitEtatique: person.lppRetraitEtatique || "capital_max",
      },
      ...extras.map((avoir) => ({
        id: avoir.id,
        institution: (avoir.institution || "").trim(),
        rows: avoir.rows || [],
        pct: avoir.pctDeblocable,
        type: avoir.type === "etatique" ? ("etatique" as const) : ("classique" as const),
        renteUnite: avoir.renteUnite === "mensuel" ? ("mensuel" as const) : ("annuel" as const),
        ageRetrait: avoir.ageRetrait,
        retraitEtatique: avoir.retraitEtatique || "capital_max",
      })),
    ];
  }

  /**
   * Somme des caisses à un âge du tableau.
   * Une LPP classique applique son pourcentage une fois.
   * Une caisse étatique prend le capital maximal et la rente réduite saisis.
   */
  aggregateAtAge(
    person: PersonInput,
    age: RetirementAge,
  ): {
    lines: LppAvoirLigne[];
    capital: number;
    rente: number;
    capitalRetire: number;
    renteResiduelle: number;
  } {
    const lines = this.listAvoirs(person).map((avoir) => this.lineAtAge(avoir, age));
    const sum = (key: "capital" | "rente" | "capitalRetire" | "renteResiduelle") =>
      round2(lines.reduce((total, line) => total + line[key], 0));
    return {
      lines,
      capital: sum("capital"),
      rente: sum("rente"),
      capitalRetire: sum("capitalRetire"),
      renteResiduelle: sum("renteResiduelle"),
    };
  }

  /**
   * Capital retiré d'une caisse pour un scénario.
   * Sans sourceId : caisse principale, pour que les planifications déjà
   * enregistrées restent sur leur unique LPP.
   */
  capitalRetireForItem(
    person: PersonInput,
    sourceId: string | null | undefined,
    age: RetirementAge,
  ): number {
    const id = sourceId && sourceId !== "primary" ? sourceId : "primary";
    const line = this.aggregateAtAge(person, age).lines.find((row) => row.id === id);
    return line?.capitalRetire ?? 0;
  }

  private lineAtAge(avoir: AvoirRef, personAge: RetirementAge): LppAvoirLigne {
    const age = fundTableAge(avoir.ageRetrait, personAge);
    const row = this.getAtAge(this.normalizeRows(avoir.rows), age);
    if (avoir.type === "etatique") return this.etatiqueLine(avoir, row, age);
    const pct = this.resolvePctDeblocable(avoir.pct);
    return {
      id: avoir.id,
      institution: avoir.institution,
      pct,
      type: "classique",
      age,
      capital: round2(row.capital || 0),
      rente: round2(row.rente || 0),
      capitalRetire: this.capitalRetire(row.capital, pct),
      renteResiduelle: this.renteResiduelle(row.rente, pct),
    };
  }

  /**
   * Capital maximal et rente réduite.
   * La rente entière ne remplace la rente réduite que si ce scénario est choisi.
   * Un retrait saisi n'est retenu que lorsque le capital et la rente sont tous les deux écrits.
   */
  private etatiqueLine(
    avoir: AvoirRef,
    row: LppByAge,
    age: RetirementAge,
  ): LppAvoirLigne {
    const renteEntiere = lppRenteAnnuelle(row.rente, avoir.renteUnite);
    const renteReduite = lppRenteAnnuelle(row.renteReduite || 0, avoir.renteUnite);
    const capitalMax = round2(row.capital || 0);
    let capitalRetire = capitalMax;
    let renteResiduelle = renteReduite;
    if (avoir.retraitEtatique === "rente_entiere") {
      capitalRetire = 0;
      renteResiduelle = renteEntiere;
    } else if (
      avoir.retraitEtatique === "saisi" &&
      row.capitalSaisi != null &&
      row.renteConserveeSaisie != null
    ) {
      capitalRetire = round2(row.capitalSaisi);
      renteResiduelle = lppRenteAnnuelle(row.renteConserveeSaisie, avoir.renteUnite);
    }
    return {
      id: avoir.id,
      institution: avoir.institution,
      pct: 100,
      type: "etatique",
      age,
      capital: capitalMax,
      rente: renteEntiere,
      capitalRetire,
      renteResiduelle,
    };
  }
}

interface AvoirRef {
  id: string;
  institution: string;
  rows: LppByAge[];
  pct: number | null | undefined;
  type: LppCaisseType;
  renteUnite: LppRenteUnite;
  ageRetrait?: number | null;
  retraitEtatique: LppRetraitEtatique;
}

export interface LppPctDiagnostic {
  reference: number;
  pct: number;
  retirableOnce: number;
  doublePct: number;
  renteTotale: number;
  renteResiduelleOnce: number;
  conversionRate: number | null;
  risqueCapitalDejaRetirable: boolean;
}

function nearlyEqual(a: number, b: number): boolean {
  return Math.abs(round2(a) - round2(b)) <= EPS;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** Rente de caisse étatique ramenée à l'année. Un mois compte 12, pas 13. */
export function lppRenteAnnuelle(
  montant: number | null | undefined,
  unite: LppRenteUnite | null | undefined,
): number {
  const value = montant || 0;
  if (unite === "mensuel") return round2(value * 12);
  return round2(value);
}

function fundTableAge(
  fundAge: number | null | undefined,
  personAge: RetirementAge,
): RetirementAge {
  if (fundAge != null && (RETIREMENT_AGES as readonly number[]).includes(fundAge)) {
    return fundAge as RetirementAge;
  }
  return personAge;
}

/** Âge du tableau LPP (60–65). Absent ou hors tableau → 65. */
export function lppTableAge(
  personAge: number | null | undefined,
): RetirementAge {
  if (personAge != null && (RETIREMENT_AGES as readonly number[]).includes(personAge)) {
    return personAge as RetirementAge;
  }
  return 65;
}

export const lppCalculationService = new LPPCalculationService();
