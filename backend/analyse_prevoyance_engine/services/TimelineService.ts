import type { AnalyseInput, PersonComputed } from "../types";
import { anneeRetraitLibrePassage } from "../rules/libre-passage-annee";

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
 * Frise chronologique — logique Excel Feuille de calcul A36:C47
 * + regroupement par années uniques (Frise Chronologique).
 */
export class TimelineService {
  build(input: AnalyseInput, client1: PersonComputed, conjoint: PersonComputed | null): TimelineResult {
    const events: TimelineEvent[] = [];
    const c1 = input.client1;
    const c2 = input.conjoint;

    events.push({
      year: yearOf(client1.dateDepart),
      label: `AVS - ${c1.prenom || "assuré 1"}`,
      amount: client1.avsAnnuel,
      kind: "avs",
      person: "client1",
    });

    if (conjoint && c2) {
      events.push({
        year: yearOf(conjoint.dateDepart),
        label: `AVS - ${c2.prenom || "Assuré 2"}`,
        amount: conjoint.avsAnnuel,
        kind: "avs",
        person: "conjoint",
      });
    }

    events.push({
      year: yearOf(client1.dateDepart),
      label: `LPP - ${c1.prenom || "assuré 1"}`,
      amount: client1.capitalLpp65,
      kind: "lpp",
      person: "client1",
    });

    if (conjoint && c2) {
      events.push({
        year: yearOf(conjoint.dateDepart),
        label: `LPP - ${c2.prenom || "Assuré 2"}`,
        amount: conjoint.capitalLpp65,
        kind: "lpp",
        person: "conjoint",
      });
    }

    for (const t of c1.troisiemePilier) {
      if (!t.echeance) continue;
      events.push({
        year: yearOf(t.echeance),
        label: `3P - ${c1.prenom || "assuré 1"} - ${t.compagnie || ""} ${t.police || ""}`.trim(),
        amount: t.montant || 0,
        kind: "3p",
        person: "client1",
      });
    }

    if (c2) {
      for (const t of c2.troisiemePilier) {
        if (!t.echeance) continue;
        events.push({
          year: yearOf(t.echeance),
          label: `3P - ${c2.prenom || "Assuré 2"} - ${t.compagnie || ""} ${t.police || ""}`.trim(),
          amount: t.montant || 0,
          kind: "3p",
          person: "conjoint",
        });
      }
    }

    for (const lp of input.libresPassages || []) {
      const person =
        lp.titulaire === "client1"
          ? c1
          : c2;
      const prenom =
        lp.titulaire === "client1"
          ? c1.prenom || "assuré 1"
          : c2?.prenom || "Assuré 2";
      if (!person && lp.titulaire === "conjoint") continue;
      const birth =
        lp.titulaire === "conjoint"
          ? input.conjoint?.dateNaissance
          : input.client1.dateNaissance;
      const ageLabel =
        lp.ageDeblocage != null && Number.isFinite(Number(lp.ageDeblocage))
          ? ` · déblocage ${lp.ageDeblocage} ans`
          : "";
      events.push({
        year: anneeRetraitLibrePassage(lp, birth),
        label: `LP - ${prenom} - ${lp.institution || "libre passage"}${ageLabel}`.trim(),
        amount: lp.montant || 0,
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

function yearOf(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const y = Number(String(iso).slice(0, 4));
  return Number.isFinite(y) ? y : null;
}

export const timelineService = new TimelineService();
