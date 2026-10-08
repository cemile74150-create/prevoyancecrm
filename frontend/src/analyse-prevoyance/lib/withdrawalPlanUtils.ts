// @ts-nocheck
/**
 * Utilitaires purs planification retraits (testables, sans ESTV).
 */
import type {
  WithdrawalPlanItem,
  WithdrawalScenarioResult,
} from "./types";
import { WITHDRAWAL_COMPARE_WARNING } from "./types";

/**
 * Année de retrait du scénario.
 * « 1re possible » si elle est saisie, sinon l'année prévue
 * pour relire un scénario déjà enregistré.
 */
export function scenarioWithdrawalYear(item: {
  anneePremierePossible?: number | null;
  anneeRetraitPrevue?: number | null;
}): number | null {
  if (item.anneePremierePossible != null && Number.isFinite(Number(item.anneePremierePossible))) {
    return Number(item.anneePremierePossible);
  }
  if (item.anneeRetraitPrevue != null && Number.isFinite(Number(item.anneeRetraitPrevue))) {
    return Number(item.anneeRetraitPrevue);
  }
  return null;
}

/** Montant effectivement retiré d’une ligne. */
export function itemMontantRetire(item: WithdrawalPlanItem): number {
  const pct = Math.min(100, Math.max(0, item.pctCapital || 0));
  return Math.round((item.montantDisponible || 0) * (pct / 100) * 100) / 100;
}

/** Total capital retiré d’un scénario (somme lignes avec année). */
export function scenarioCapitalRetireTotal(
  items: WithdrawalPlanItem[],
): number {
  return Math.round(
    items
      .filter((i) => scenarioWithdrawalYear(i) != null)
      .reduce((s, i) => s + itemMontantRetire(i), 0) * 100,
  ) / 100;
}

/**
 * Comparabilité fiscale : même montant total retiré.
 * Tolérance 0,01 CHF (arrondis).
 */
export function areScenariosComparable(
  capitalA: number,
  capitalB: number,
  tolerance = 0.01,
): { sameCapitalBase: boolean; warning: string | null } {
  const same = Math.abs(capitalA - capitalB) <= tolerance;
  return {
    sameCapitalBase: same,
    warning: same ? null : WITHDRAWAL_COMPARE_WARNING,
  };
}

/** Vue calendrier : lignes par année à partir des items (avant ESTV). */
export function buildCalendarPreview(items: WithdrawalPlanItem[]): Array<{
  year: number;
  lines: Array<{
    titulaire: string;
    kind: string;
    label: string;
    institution: string;
    montantRetire: number;
  }>;
  totalRetire: number;
}> {
  const byYear = new Map<
    number,
    Array<{
      titulaire: string;
      kind: string;
      label: string;
      institution: string;
      montantRetire: number;
    }>
  >();

  for (const it of items) {
    const year = scenarioWithdrawalYear(it);
    if (year == null) continue;
    const montant = itemMontantRetire(it);
    if (montant <= 0) continue;
    const list = byYear.get(year) || [];
    list.push({
      titulaire: it.titulaire,
      kind: it.kind,
      label: it.label,
      institution: it.institution || "",
      montantRetire: montant,
    });
    byYear.set(year, list);
  }

  return [...byYear.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([year, lines]) => ({
      year,
      lines,
      totalRetire:
        Math.round(lines.reduce((s, l) => s + l.montantRetire, 0) * 100) / 100,
    }));
}

/** Enrichit le calendrier avec impôts ESTV d’un résultat scénario. */
export function mergeCalendarWithResult(
  items: WithdrawalPlanItem[],
  result: WithdrawalScenarioResult | null | undefined,
): Array<{
  year: number;
  lines: Array<{
    titulaire: string;
    kind: string;
    label: string;
    institution: string;
    montantRetire: number;
  }>;
  totalRetire: number;
  impot: number | null;
  net: number | null;
}> {
  const preview = buildCalendarPreview(items);
  return preview.map((y) => {
    const yr = result?.byYear.find((b) => b.year === y.year);
    return {
      ...y,
      impot: yr?.impot ?? null,
      net:
        yr?.net ??
        (yr?.impot != null
          ? Math.round((y.totalRetire - yr.impot) * 100) / 100
          : null),
    };
  });
}
