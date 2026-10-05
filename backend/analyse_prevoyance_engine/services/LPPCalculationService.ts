import {
  LPP_CONVERSION_RATES,
  LPP_PCT_DEBLOCABLE_DEFAULT,
  RETIREMENT_AGES,
  type LppByAge,
  type RetirementAge,
} from "../types";

/**
 * Service LPP — capitaux / rentes par âge, taux de conversion Excel,
 * et % déblocable paramétrable.
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

  /**
   * Normalise le % déblocable (0–100). Valeur absente / invalide → défaut 100.
   */
  resolvePctDeblocable(pct: number | null | undefined): number {
    if (pct == null || Number.isNaN(pct)) return LPP_PCT_DEBLOCABLE_DEFAULT;
    return Math.min(100, Math.max(0, round2(pct)));
  }

  /** Capital effectivement retiré = capital × pct/100. */
  capitalRetire(capital: number, pct: number | null | undefined): number {
    const p = this.resolvePctDeblocable(pct);
    return round2((capital || 0) * (p / 100));
  }

  /**
   * Rente résiduelle après retrait partiel = rente × (1 − pct/100).
   * 100 % → 0 ; 50 % → 50 % de la rente ; 0 % → rente entière.
   */
  renteResiduelle(rente: number, pct: number | null | undefined): number {
    const p = this.resolvePctDeblocable(pct);
    return round2((rente || 0) * (1 - p / 100));
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const lppCalculationService = new LPPCalculationService();
