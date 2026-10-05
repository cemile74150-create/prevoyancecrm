// @ts-nocheck
import type {
  AnalyseInput,
  CapitalKind,
  PersonComputed,
  PersonKey,
  WithdrawalPlanItem,
  WithdrawalScenario,
} from "./types";
import { LP_PCT_RETIRE_DEFAULT } from "./types";

/**
 * Construit des items de planification par défaut à partir du dossier
 * (LPP, LP, 3P) — sans inventer de règles légales de dates.
 * Fichier sans dépendance ESTV (utilisable côté client).
 */
export function buildDefaultWithdrawalItems(
  input: AnalyseInput,
  client1: PersonComputed,
  conjoint: PersonComputed | null,
): WithdrawalPlanItem[] {
  const items: WithdrawalPlanItem[] = [];
  const yearOf = (iso: string | null | undefined) =>
    iso && /^\d{4}/.test(iso) ? Number(iso.slice(0, 4)) : null;

  items.push({
    id: "lpp-client1",
    kind: "lpp",
    titulaire: "client1",
    label: `LPP ${input.client1.prenom || "assuré 1"}`,
    institution: "LPP",
    montantDisponible: client1.capitalLpp65,
    pctCapital: client1.lppPctDeblocable,
    anneeRetraitPrevue: yearOf(client1.dateDepart),
    anneePremierePossible: yearOf(client1.dateDepart),
    anneeDernierePossible: null,
  });

  if (conjoint && input.conjoint) {
    items.push({
      id: "lpp-conjoint",
      kind: "lpp",
      titulaire: "conjoint",
      label: `LPP ${input.conjoint.prenom || "Assuré 2"}`,
      institution: "LPP",
      montantDisponible: conjoint.capitalLpp65,
      pctCapital: conjoint.lppPctDeblocable,
      anneeRetraitPrevue: yearOf(conjoint.dateDepart),
      anneePremierePossible: yearOf(conjoint.dateDepart),
      anneeDernierePossible: null,
    });
  }

  for (const lp of input.libresPassages || []) {
    items.push({
      id: `lp-${lp.id}`,
      kind: "libre_passage",
      titulaire: lp.titulaire,
      label: `Libre passage ${lp.institution || ""}`.trim(),
      institution: lp.institution || "Libre passage",
      montantDisponible: lp.montant,
      pctCapital: Number.isFinite(lp.pctRetire)
        ? lp.pctRetire
        : LP_PCT_RETIRE_DEFAULT,
      anneeRetraitPrevue: (() => {
        const fromDate = yearOf(lp.dateRetraitPossible);
        if (fromDate) return fromDate;
        if (lp.ageDeblocage == null) return null;
        const birth = yearOf(
          (lp.titulaire === "conjoint" ? input.conjoint : input.client1)
            ?.dateNaissance,
        );
        return birth == null ? null : birth + Number(lp.ageDeblocage);
      })(),
      anneePremierePossible: (() => {
        const fromDate = yearOf(lp.dateRetraitPossible);
        if (fromDate) return fromDate;
        if (lp.ageDeblocage == null) return null;
        const birth = yearOf(
          (lp.titulaire === "conjoint" ? input.conjoint : input.client1)
            ?.dateNaissance,
        );
        return birth == null ? null : birth + Number(lp.ageDeblocage);
      })(),
      anneeDernierePossible: null,
      sourceId: lp.id,
    });
  }

  const push3p = (
    titulaire: PersonKey,
    prenom: string,
    contracts: AnalyseInput["client1"]["troisiemePilier"],
  ) => {
    for (const c of contracts) {
      if (!c.montant) continue;
      items.push({
        id: `3p-${c.id}`,
        kind: "3p",
        titulaire,
        label: `${c.type === "3B" ? "3B" : "3A"} – ${prenom} – ${c.compagnie || ""} – ${c.police || ""}`.replace(/\s+–\s+$/g, "").trim(),
        institution: c.compagnie || "3e pilier",
        montantDisponible: c.montant,
        pctCapital: 100,
        anneeRetraitPrevue: yearOf(c.echeance),
        anneePremierePossible: yearOf(c.echeance),
        anneeDernierePossible: null,
        sourceId: c.id,
      });
    }
  };
  push3p(
    "client1",
    input.client1.prenom || "assuré 1",
    input.client1.troisiemePilier,
  );
  if (input.conjoint) {
    push3p(
      "conjoint",
      input.conjoint.prenom || "Assuré 2",
      input.conjoint.troisiemePilier,
    );
  }

  return items;
}

/** Duplique un scénario (nouveaux ids) sans ressaisie. */
export function duplicateWithdrawalScenario(
  sc: WithdrawalScenario,
): WithdrawalScenario {
  const suffix = Math.random().toString(36).slice(2, 7);
  return {
    id: `sc-${Date.now()}-${suffix}`,
    name: `${sc.name} (copie)`,
    includeInReport: false,
    items: sc.items.map((it) => ({
      ...it,
      id: `${it.id}-copy-${suffix}`,
    })),
  };
}

export function newEmptyScenario(name = "Nouveau scénario"): WithdrawalScenario {
  return {
    id: `sc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name,
    includeInReport: false,
    items: [],
  };
}

export function kindLabel(kind: CapitalKind): string {
  switch (kind) {
    case "lpp":
      return "LPP";
    case "libre_passage":
      return "LP";
    case "3p":
      return "3P";
    default:
      return "Autre";
  }
}
