// @ts-nocheck
import {
  effectiveLppWithdrawalAge,
  lppCapitalForWithdrawalAge,
  resolveThirdPillarCapital,
  yearOfIso,
} from "./planificationSaisie";
import type {
  AnalyseInput,
  CapitalKind,
  PersonComputed,
  PersonInput,
  PersonKey,
  WithdrawalPlanItem,
  WithdrawalScenario,
} from "./types";

function dossierLppAge(input: AnalyseInput): number | null {
  const age = input.ageRetraiteSouhaite ?? input.client1?.ageRetraiteSouhaite ?? null;
  return age != null && Number.isFinite(Number(age)) ? Number(age) : null;
}

function lppItem(
  id: string,
  titulaire: PersonKey,
  input: AnalyseInput,
  person: PersonInput,
  computed: PersonComputed,
): WithdrawalPlanItem {
  const age = effectiveLppWithdrawalAge(person, dossierLppAge(input));
  const row = lppCapitalForWithdrawalAge(person.lpp, age);
  const birth = yearOfIso(person.dateNaissance);
  const year =
    row.found && birth != null && age != null
      ? birth + age
      : yearOfIso(computed.dateDepart);
  const custom =
    person.ageRetraitLppSouhaite != null &&
    Number.isFinite(Number(person.ageRetraitLppSouhaite));
  return {
    id,
    kind: "lpp",
    titulaire,
    label: `LPP ${person.prenom || (titulaire === "client1" ? "assuré 1" : "Assuré 2")}`,
    institution: "LPP",
    montantDisponible: row.found ? row.capital : custom ? 0 : computed.capitalLpp65,
    pctCapital: computed.lppPctDeblocable,
    anneeRetraitPrevue: year,
    anneePremierePossible: year,
    anneeDernierePossible: null,
  };
}

function extraLppItems(
  titulaire: PersonKey,
  person: PersonInput,
  dossierAge: number | null,
): WithdrawalPlanItem[] {
  const personAge = effectiveLppWithdrawalAge(person, dossierAge);
  return (person.lppAvoirs || []).map((avoir) => {
    const age =
      avoir.ageRetrait != null && Number.isFinite(Number(avoir.ageRetrait))
        ? Number(avoir.ageRetrait)
        : personAge;
    const row = lppCapitalForWithdrawalAge(avoir.rows, age);
    const etatique = avoir.type === "etatique";
    const birth = yearOfIso(person.dateNaissance);
    const year = row.found && birth != null && age != null ? birth + age : null;
    return {
      id: `lpp-${avoir.id}`,
      kind: "lpp" as const,
      titulaire,
      label: `LPP ${avoir.institution || person.prenom || ""}`.trim(),
      institution: avoir.institution || "LPP",
      montantDisponible: row.found ? row.capital : 0,
      pctCapital: etatique ? 100 : avoir.pctDeblocable ?? 100,
      anneeRetraitPrevue: year,
      anneePremierePossible: year,
      anneeDernierePossible: null,
      sourceId: avoir.id,
    };
  });
}

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

  items.push(lppItem("lpp-client1", "client1", input, input.client1, client1));
  items.push(...extraLppItems("client1", input.client1, dossierLppAge(input)));

  if (conjoint && input.conjoint) {
    items.push(lppItem("lpp-conjoint", "conjoint", input, input.conjoint, conjoint));
    items.push(...extraLppItems("conjoint", input.conjoint, dossierLppAge(input)));
  }

  for (const lp of input.libresPassages || []) {
    items.push({
      id: `lp-${lp.id}`,
      kind: "libre_passage",
      titulaire: lp.titulaire,
      label: `Libre passage ${lp.institution || ""}`.trim(),
      institution: lp.institution || "Libre passage",
      montantDisponible: lp.montant,
      pctCapital: 100,
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
    for (const c of contracts || []) {
      const year = yearOf(c.echeance);
      const resolved = resolveThirdPillarCapital(c, year);
      if (!c.montant && !(c.valeursRachat || []).length) continue;
      items.push({
        id: `3p-${c.id}`,
        kind: "3p",
        titulaire,
        label: `${c.type === "3B" ? "3B" : "3A"} – ${prenom} – ${c.compagnie || ""} – ${c.police || ""}`.replace(/\s+–\s+$/g, "").trim(),
        institution: c.compagnie || "3e pilier",
        montantDisponible: resolved.montant,
        capitalStatut: resolved.statut,
        pctCapital: 100,
        anneeRetraitPrevue: year,
        anneePremierePossible: year,
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

export function selectedWithdrawalYear(item: {
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

export function withPillarCapital(
  input: AnalyseInput,
  item: WithdrawalPlanItem,
): WithdrawalPlanItem {
  if (item.kind !== "3p" || !item.sourceId) return item;
  const person = item.titulaire === "conjoint" ? input.conjoint : input.client1;
  const contract = person?.troisiemePilier?.find((row) => row.id === item.sourceId);
  if (!contract) return item;
  const resolved = resolveThirdPillarCapital(contract, selectedWithdrawalYear(item));
  return {
    ...item,
    montantDisponible: resolved.montant,
    capitalStatut: resolved.statut,
  };
}
