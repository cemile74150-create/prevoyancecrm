import { personFirstName } from "../mappers";
import { anneeRetraitLibrePassage } from "../rules/libre-passage-annee";
import {
  acceptedLppScenarioYear,
  effectiveLppWithdrawalAge,
  lppCapitalForWithdrawalAge,
  resolveThirdPillarCapital,
} from "../rules/planification-saisie";
import type { AnalyseInput, PersonComputed, PersonInput, WithdrawalPlanItem } from "../types";
import { librePassageRetire, normalizeThirdPillarType } from "../types";
import { scenarioWithdrawalYear } from "../withdrawalPlanUtils";
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
 * Le retrait LPP suit la date de l'onglet LPP.
 * L'AVS suit l'anticipation choisie dans l'onglet AVS.
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
      year: yearOf(client1.datePerceptionAvs || (client1.avsDejaActive ? "" : client1.dateDepart)),
      label: client1.avsDejaActive ? `AVS déjà active – ${who1}` : `AVS – ${who1}`,
      amount: client1.avsAnnuel,
      kind: "avs",
      person: "client1",
    });

    if (conjoint && c2) {
      events.push({
        year: yearOf(
          conjoint.datePerceptionAvs || (conjoint.avsDejaActive ? "" : conjoint.dateDepart),
        ),
        label: conjoint.avsDejaActive ? `AVS déjà active – ${who2}` : `AVS – ${who2}`,
        amount: conjoint.avsAnnuel,
        kind: "avs",
        person: "conjoint",
      });
    }

    const dossierAge = input.ageRetraiteSouhaite ?? c1.ageRetraiteSouhaite ?? null;
    pushLpp(events, client1, c1, dossierAge, who1, "client1", items);
    if (conjoint && c2) {
      pushLpp(events, conjoint, c2, dossierAge, who2, "conjoint", items);
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
        year: (planned ? scenarioWithdrawalYear(planned) : null) ?? anneeRetraitLibrePassage(lp, birth),
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

function lppEventYear(
  computed: PersonComputed,
  personInput: PersonInput,
  person: "client1" | "conjoint",
  fate: "Capital" | "Rente" | "Capital + rente",
  items: WithdrawalPlanItem[],
): number | null {
  const explicitLppAge =
    personInput.ageRetraitLppSouhaite != null &&
    Number.isFinite(Number(personInput.ageRetraitLppSouhaite));
  const profilAge =
    personInput.ageRetraiteSouhaite != null &&
    Number.isFinite(Number(personInput.ageRetraiteSouhaite));
  const tabYear = yearOf(computed.dateFinActivite);
  const legalYear = yearOf(computed.dateDepart);
  const planned = items.find((item) => item.kind === "lpp" && item.titulaire === person);
  const chosen = planned ? acceptedLppScenarioYear(personInput, planned) : null;
  const override = chosen != null && chosen !== tabYear ? chosen : null;
  const plannedYear = planned ? scenarioWithdrawalYear(planned) : null;
  return (
    override ??
    (explicitLppAge || profilAge || fate === "Rente"
      ? (tabYear ?? legalYear)
      : (plannedYear ?? tabYear ?? legalYear))
  );
}

function lppComponentLabel(who: string, institution: string, component: string): string {
  const parts = ["LPP", who];
  if (institution) parts.push(institution);
  parts.push(component);
  return parts.join(" – ");
}

/** Une caisse : capital, rente réduite, ou les deux. Une rente seule reste « Rente ». */
function pushLppComponents(
  events: TimelineEvent[],
  who: string,
  person: "client1" | "conjoint",
  institution: string,
  capital: number,
  rente: number,
  year: number | null,
) {
  if (capital > 0 && rente > 0) {
    events.push({
      year,
      label: lppComponentLabel(who, institution, "Capital"),
      amount: capital,
      kind: "lpp",
      person,
    });
    events.push({
      year,
      label: lppComponentLabel(who, institution, "Rente réduite"),
      amount: rente,
      kind: "lpp",
      person,
    });
    return;
  }
  if (capital > 0) {
    events.push({
      year,
      label: lppComponentLabel(who, institution, "Capital"),
      amount: capital,
      kind: "lpp",
      person,
    });
    return;
  }
  if (rente > 0) {
    events.push({
      year,
      label: lppComponentLabel(who, institution, "Rente"),
      amount: rente,
      kind: "lpp",
      person,
    });
  }
}

function pushLpp(
  events: TimelineEvent[],
  computed: PersonComputed,
  personInput: PersonInput,
  dossierAge: number | null,
  who: string,
  person: "client1" | "conjoint",
  items: WithdrawalPlanItem[],
) {
  const lines = (computed.lppLignes || []).filter(
    (line) => (line.capitalRetire || 0) > 0 || (line.renteResiduelle || 0) > 0,
  );
  if (lines.length > 0) {
    const multiple = lines.length > 1;
    lines.forEach((line, index) => {
      const capital = line.capitalRetire || 0;
      const rente = line.renteResiduelle || 0;
      const fate: "Capital" | "Rente" | "Capital + rente" =
        capital > 0 && rente > 0 ? "Capital + rente" : capital > 0 ? "Capital" : "Rente";
      let institution = (line.institution || "").trim();
      if (!institution && multiple) institution = `Caisse ${index + 1}`;
      const ownYear =
        line.anneeRetrait != null &&
        line.age != null &&
        computed.ageLppRetenu != null &&
        line.age !== computed.ageLppRetenu
          ? line.anneeRetrait
          : lppEventYear(computed, personInput, person, fate, items);
      pushLppComponents(events, who, person, institution, capital, rente, ownYear);
    });
    return;
  }

  const pct = lppCalculationService.resolvePctDeblocable(computed.lppPctDeblocable);
  const fate = lppTimelineFate(pct);
  const age = effectiveLppWithdrawalAge(personInput, dossierAge);
  const row = lppCapitalForWithdrawalAge(personInput.lpp, age);
  const custom =
    personInput.ageRetraitLppSouhaite != null &&
    Number.isFinite(Number(personInput.ageRetraitLppSouhaite));
  const capital = row.found
    ? lppCalculationService.capitalRetire(row.capital, pct)
    : custom
      ? 0
      : computed.capitalLppRetire65;
  const rente = computed.renteLppResiduelle65;
  if (fate === "Capital" && !(capital > 0)) return;
  if (fate === "Rente" && !(rente > 0)) return;
  if (fate === "Capital + rente" && !(capital > 0) && !(rente > 0)) return;
  const year = lppEventYear(computed, personInput, person, fate, items);
  if (fate === "Capital + rente") {
    pushLppComponents(events, who, person, "", capital, rente, year);
    return;
  }
  pushLppComponents(
    events,
    who,
    person,
    "",
    fate === "Rente" ? 0 : capital,
    fate === "Rente" ? rente : 0,
    year,
  );
}

function pushPillars(
  events: TimelineEvent[],
  contracts: AnalyseInput["client1"]["troisiemePilier"],
  person: "client1" | "conjoint",
  who: string,
  items: WithdrawalPlanItem[],
) {
  for (const contract of contracts || []) {
    const hasRachat = (contract.valeursRachat || []).length > 0;
    if (!contract.montant && !hasRachat && !contract.compagnie && !contract.police) continue;
    const planned = items.find(
      (item) => item.kind === "3p" && item.sourceId === contract.id,
    );
    const type = normalizeThirdPillarType(contract.type);
    const year = (planned ? scenarioWithdrawalYear(planned) : null) ?? yearOf(contract.echeance);
    const resolved = resolveThirdPillarCapital(contract, year);
    const suffix = resolved.statut === "indicatif" ? " – montant indicatif" : "";
    events.push({
      year,
      label: [type, who, contract.compagnie, contract.police]
        .filter(Boolean)
        .join(" – ") + suffix,
      amount: resolved.montant,
      kind: "3p",
      person,
    });
  }
}

function yearOf(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const y = Number(String(iso).slice(0, 4));
  return Number.isFinite(y) ? y : null;
}

export const timelineService = new TimelineService();
