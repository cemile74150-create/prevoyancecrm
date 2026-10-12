import {
  LPP_CONVERSION_RATES,
  LPP_PCT_DEBLOCABLE_DEFAULT,
  RETIREMENT_AGES,
  type LppByAge,
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
      return {
        age,
        capital: round2(existing?.capital || 0),
        rente: round2(existing?.rente || 0),
      };
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

export const lppCalculationService = new LPPCalculationService();
