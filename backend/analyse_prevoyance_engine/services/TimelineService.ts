import { personFirstName } from "../mappers";
import { anneeRetraitLibrePassage } from "../rules/libre-passage-annee";
import type { AnalyseInput, PersonComputed, WithdrawalPlanItem } from "../types";
import { librePassageRetire, normalizeThirdPillarType } from "../types";
import { lppCalculationService } from "./LPPCalculationService";

export interface TimelineEvent {
  year: number | null;
  label: string;
  amount: number;
  kind: "avs" | "lpp" | "3p" | "lp";
  person: "client1" | "conjoint";
}

export interface TimelineResult {
  events: TimelineEvent[];
  years: number[];
  byYear: Record<number, TimelineEvent[]>;
}

/**
 * Frise du scénario coché « Inclure dans le rapport ».
 * Les retraits de capitaux suivent l'année prévue de ce scénario.
 * L'AVS reste à son année de début de perception.
 */
export class TimelineService {
  build(input: AnalyseInput, client1: PersonComputed, conjoint: PersonComputed | null): TimelineResult {
    const events: TimelineEvent[] = [];
    const scenario = (input.withdrawalScenarios || []).find(
      (item) => item.includeInReport,
    );
    const items = scenario?.items || [];
    const c1 = input.client1;
    const c2 = input.conjoint;
    const who1 = personFirstName(c1, "Assuré 1");
    const who2 = personFirstName(c2, "Assuré 2");

    events.push({
      year: yearOf(client1.dateDepart),
      label: `AVS – ${who1}`,
      amount: client1.avsAnnuel,
      kind: "avs",
      person: "client1",
    });

    if (conjoint && c2) {
      events.push({
        year: yearOf(conjoint.dateDepart),
        label: `AVS – ${who2}`,
        amount: conjoint.avsAnnuel,
        kind: "avs",
        person: "conjoint",
      });
    }

    pushLpp(events, client1, who1, "client1", items);
    if (conjoint && c2) {
      pushLpp(events, conjoint, who2, "conjoint", items);
    }

    pushPillars(events, c1.troisiemePilier, "client1", who1, items);
    if (c2) {
      pushPillars(events, c2.troisiemePilier, "conjoint", who2, items);
    }

    for (const lp of input.libresPassages || []) {
      const birth =
        lp.titulaire === "conjoint"
          ? input.conjoint?.dateNaissance
          : input.client1.dateNaissance;
      const planned = items.find(
        (item) => item.kind === "libre_passage" && item.sourceId === lp.id,
      );
      const who = lp.titulaire === "conjoint" ? who2 : who1;
      events.push({
        year: planned?.anneeRetraitPrevue ?? anneeRetraitLibrePassage(lp, birth),
        label: `Libre passage – ${who} – ${lp.institution || "libre passage"}`.trim(),
        amount: librePassageRetire(lp),
        kind: "lp",
        person: lp.titulaire,
      });
    }

    const years = [
      ...new Set(
        events
          .map((e) => e.year)
          .filter((y): y is number => y != null && Number.isFinite(y)),
      ),
    ].sort((a, b) => a - b);

    const byYear: Record<number, TimelineEvent[]> = {};
    for (const y of years) {
      byYear[y] = events.filter((e) => e.year === y);
    }

    return { events, years, byYear };
  }
}

/**
 * Destin du 2e pilier d'après le % déblocable déjà résolu.
 * 100 (défaut si absent) → capital ; 0 → rente ; entre les deux → les deux.
 */
export function lppTimelineFate(
  pct: number | null | undefined,
): "Capital" | "Rente" | "Capital + rente" {
  const resolved = lppCalculationService.resolvePctDeblocable(pct);
  if (resolved >= 100) return "Capital";
  if (resolved <= 0) return "Rente";
  return "Capital + rente";
}

function pushLpp(
  events: TimelineEvent[],
  computed: PersonComputed,
  who: string,
  person: "client1" | "conjoint",
  items: WithdrawalPlanItem[],
) {
  const pct = lppCalculationService.resolvePctDeblocable(computed.lppPctDeblocable);
  const fate = lppTimelineFate(pct);
  const capital = computed.capitalLppRetire65;
  const rente = lppCalculationService.renteResiduelle(computed.renteLpp65, pct);
  if (fate === "Capital" && !(capital > 0)) return;
  if (fate === "Rente" && !(rente > 0)) return;
  if (fate === "Capital + rente" && !(capital > 0) && !(rente > 0)) return;
  const planned = findItem(items, "lpp", person);
  const year =
    fate === "Rente"
      ? yearOf(computed.dateDepart)
      : (planned?.anneeRetraitPrevue ?? yearOf(computed.dateDepart));
  events.push({
    year,
    label: `LPP – ${who} – ${fate}`,
    amount: fate === "Rente" ? rente : capital,
    kind: "lpp",
    person,
  });
}

function pushPillars(
  events: TimelineEvent[],
  contracts: AnalyseInput["client1"]["troisiemePilier"],
  person: "client1" | "conjoint",
  who: string,
  items: WithdrawalPlanItem[],
) {
  for (const contract of contracts || []) {
    if (!contract.montant && !contract.compagnie && !contract.police) continue;
    const planned = items.find(
      (item) => item.kind === "3p" && item.sourceId === contract.id,
    );
    const type = normalizeThirdPillarType(contract.type);
    const year = planned?.anneeRetraitPrevue ?? yearOf(contract.echeance);
    events.push({
      year,
      label: [type, who, contract.compagnie, contract.police]
        .filter(Boolean)
        .join(" – "),
      amount: contract.montant || 0,
      kind: "3p",
      person,
    });
  }
}

function findItem(
  items: WithdrawalPlanItem[],
  kind: WithdrawalPlanItem["kind"],
  titulaire: WithdrawalPlanItem["titulaire"],
): WithdrawalPlanItem | undefined {
  return items.find((item) => item.kind === kind && item.titulaire === titulaire);
}

function yearOf(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const y = Number(String(iso).slice(0, 4));
  return Number.isFinite(y) ? y : null;
}

export const timelineService = new TimelineService();
