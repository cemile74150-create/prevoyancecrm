import { formatDateFr } from "../rules/avs-age";
import { personDisplayName } from "../mappers";
import type { AnalyseRecord } from "../types";
import { librePassageRetire, normalizeThirdPillarType } from "../types";
import type {
  ReportPayload,
  ReportPersonBlock,
  ReportThirdPillarRow,
  ReportVaudoiseColumn,
} from "./ReportPayload";

const FISCAL_OPT_HIDDEN_REASON =
  "Page 6 « Optimisation fiscale des retraits » absente du classeur Excel V6 " +
  "(aucune feuille / formule multi-années pour scénario HELFER). " +
  "Le PDF de référence V3 contient ce bloc commercial, mais les impôts capital " +
  "par année fiscale distincte (retraits échelonnés) ne sont pas calculables " +
  "sans inventer des appels ESTV non présents dans Excel. Bloc masqué jusqu’à " +
  "disponibilité des règles métier exactes.";

/**
 * Construit l’objet rapport unique à partir des résultats moteur.
 * Aucun calcul métier nouveau — agrégation / formatage uniquement.
 */
export function buildReportPayload(record: AnalyseRecord): ReportPayload {
  const { input, results } = record;
  if (!results) {
    throw new Error("Impossible de construire le rapport sans résultats calculés.");
  }

  const isCouple =
    input.etatCivil === "Marié(e)" && !!input.conjoint && !!results.conjoint;

  const client1 = buildPersonBlock(
    input.client1,
    results.client1,
    input.salaireClient1,
    sumLibrePassage(input, "client1"),
  );
  const conjoint = isCouple
    ? buildPersonBlock(
        input.conjoint!,
        results.conjoint!,
        input.salaireConjoint,
        sumLibrePassage(input, "conjoint"),
      )
    : null;

  const couple1 = results.incomeScenarios.find((s) => s.foyer === "Couple1");
  const couple2 = results.incomeScenarios.find((s) => s.foyer === "Couple2");
  const path = results.capitalPathFoyer;
  const cap65 = results.capitalScenarios.find((s) => s.age === 65);

  const avsTotal = client1.avsAnnuel + (conjoint?.avsAnnuel ?? 0);
  const capitalLppTotal = client1.capitalLpp65 + (conjoint?.capitalLpp65 ?? 0);
  const renteLppTotal = client1.renteLpp65 + (conjoint?.renteLpp65 ?? 0);
  const capitalLppRetireTotal =
    path?.capitalRetireTotal ??
    client1.capitalLppRetire65 + (conjoint?.capitalLppRetire65 ?? 0);
  const renteLppResiduelleTotal =
    path?.renteResiduelleTotal ??
    client1.renteLppResiduelle65 + (conjoint?.renteLppResiduelle65 ?? 0);
  const total3ePilierFoyer =
    client1.total3ePilier + (conjoint?.total3ePilier ?? 0);
  const librePassageTotal = round2(
    client1.librePassage + (conjoint?.librePassage ?? 0),
  );
  const librePassageRetireTotal =
    path?.librePassageRetireTotal ??
    round2(
      (input.libresPassages || []).reduce(
        (sum, lp) => sum + librePassageRetire(lp),
        0,
      ),
    );
  const lppRetireSeul =
    path?.lppRetireTotal ??
    round2(client1.capitalLppRetire65 + (conjoint?.capitalLppRetire65 ?? 0));
  const capitalLppAvecLibrePassage = round2(
    lppRetireSeul + librePassageRetireTotal,
  );

  const impotRevenuCouple1 = couple1?.impot?.impotRevenuTotal ?? null;
  const impotRevenuCouple2 = couple2?.impot?.impotRevenuTotal ?? null;
  const impotCapital65 = path?.impot ?? cap65?.impot ?? null;
  const capitalNet65 =
    path?.net ??
    (impotCapital65 == null
      ? null
      : round2(capitalLppRetireTotal - impotCapital65));

  const renteApresImpot =
    impotRevenuCouple1 == null
      ? null
      : round2(avsTotal + renteLppTotal - impotRevenuCouple1);
  const renteNetteCheminCapital =
    impotRevenuCouple2 == null
      ? null
      : round2(avsTotal + renteLppResiduelleTotal - impotRevenuCouple2);

  const thirdPillarRows = buildThirdPillarRows(record, isCouple);
  const hasThirdPillar = thirdPillarRows.length > 0;
  const hasRentePont =
    (input.client1.rentePont ?? 0) > 0 ||
    (input.conjoint?.rentePont ?? 0) > 0;

  const vaudoise = buildVaudoise(record, {
    avsTotal,
    renteLppTotal,
    impotRevenuCouple1,
    impotRevenuCouple2,
    capitalDispo: capitalLppTotal + total3ePilierFoyer,
  });

  const fiscalOptimization = {
    include: false as const,
    reasonHidden: FISCAL_OPT_HIDDEN_REASON,
  };

  const wp = results.withdrawalPlanning;
  const reportScenarioIds = new Set(
    (input.withdrawalScenarios || [])
      .filter((s) => s.includeInReport)
      .map((s) => s.id),
  );
  const reportScenarios = (wp?.scenarios ?? []).filter((s) =>
    reportScenarioIds.has(s.scenarioId),
  );
  const hasWithdrawalPlanning = reportScenarios.length > 0;
  const withdrawalPlanning = {
    include: hasWithdrawalPlanning,
    scenarios: reportScenarios.map((s) => ({
      id: s.scenarioId,
      name: s.scenarioName,
      includeInReport: true,
      capitalRetireTotal: s.capitalRetireTotal,
      impotTotal: s.impotTotal,
      capitalNet: s.capitalNet,
      byYear: s.byYear.map((y) => ({
        year: y.year,
        capitalRetire: y.capitalRetire,
        impot: y.impot,
        net: y.net ?? null,
        lines: (y.lines || []).map((l) => ({
          titulaire: l.titulaire,
          kind: l.kind,
          label: l.label,
          institution: l.institution || "",
          montantRetire: l.montantRetire,
          contratType: l.contratType ?? null,
          exonere: !!l.exonere,
        })),
      })),
      audits: s.audits.map((a) => ({
        year: a.year,
        titulaire: a.titulaire,
        taxLocationId: a.taxLocationId,
        etatCivil: a.etatCivil,
        ageAtPayment: a.ageAtPayment,
        montantSoumis: a.montantSoumis,
        impotTotal: a.impotTotal,
        request: a.request || {},
        capitauxInclus: a.capitauxInclus,
        error: a.error,
      })),
    })),
    comparisons: (wp?.comparisons ?? [])
      .filter(
        (c) =>
          reportScenarioIds.has(c.fromId) && reportScenarioIds.has(c.toId),
      )
      .map((c) => ({
        fromName: c.fromName,
        toName: c.toName,
        deltaImpot: c.deltaImpot,
        deltaCapitalNet: c.deltaCapitalNet,
        sameCapitalBase: c.sameCapitalBase,
        warning: c.warning,
      })),
    strategyScenarioId:
      wp?.strategyScenarioId && reportScenarioIds.has(wp.strategyScenarioId)
        ? wp.strategyScenarioId
        : null,
    sameYearReference: wp?.sameYearReference
      ? {
          year: wp.sameYearReference.year,
          capitalRetire: wp.sameYearReference.capitalRetire,
          impotTotal: wp.sameYearReference.impotTotal,
          capitalNet: wp.sameYearReference.capitalNet,
        }
      : null,
    economieFiscale:
      wp?.strategyScenarioId && reportScenarioIds.has(wp.strategyScenarioId)
        ? (wp.economieFiscale ?? null)
        : null,
  };

  // Pages : 1 cover, 2 agency, 3 bilan, 4 compare — puis conditionnels
  let pageCount = 4;
  if (hasThirdPillar) {
    pageCount += Math.max(1, Math.ceil(thirdPillarRows.length / 8));
  }
  // fiscalOptimization never included for now
  if (hasWithdrawalPlanning) {
    const yearRows = withdrawalPlanning.scenarios.reduce(
      (n, s) => n + s.byYear.length,
      0,
    );
    pageCount += withdrawalPlanningSheetCount(
      withdrawalPlanning.scenarios.length,
      yearRows,
      withdrawalPlanning.comparisons.length > 0,
    );
  }
  pageCount += 1; // frise always
  if (vaudoise?.include) pageCount += 1;
  const hypothesesRente =
    results.renteHypotheses &&
    results.renteHypotheses.columns.some((col) => col.kind === "hypothese")
      ? results.renteHypotheses
      : null;
  if (hypothesesRente) pageCount += 1;

  const evo = results.evolution;
  const timeline = results.timeline;

  const generatedAt = new Date().toISOString();

  return {
    meta: {
      generatedAt,
      dateRapportLabel: formatDateFr(new Date()),
      conseillerNom: input.conseillerNom || "",
      villeRecherche: input.villeRecherche,
      etatCivil: input.etatCivil,
      taxLocationId: results.taxLocation?.TaxLocationID ?? input.taxLocationId,
      taxYear: input.taxYear,
      isCouple,
      pageCount,
    },
    client1,
    conjoint,
    aggregates: {
      salaireAvant: results.lacune.salaireAvant,
      revenuApres: results.lacune.revenuApres,
      lacune: results.lacune.lacune,
      manquePour80: results.lacune.manquePour80,
      tauxRemplacementReel: results.lacune.tauxRemplacementReel,
      avsTotal,
      capitalLppTotal,
      renteLppTotal,
      capitalLppRetireTotal,
      renteLppResiduelleTotal,
      total3ePilierFoyer,
      librePassageTotal,
      capitalLppAvecLibrePassage,
      impotCapital65,
      capitalNet65,
      impotRevenuCouple1,
      impotRevenuCouple2,
      renteApresImpot,
      renteNetteCheminCapital,
    },
    capitalScenarios: results.capitalScenarios.map((s) => ({
      age: s.age,
      capital: s.capital,
      impot: s.impot,
      net: s.net,
      rente: s.rente,
    })),
    incomeScenarios: results.incomeScenarios.map((s) => ({
      foyer: s.foyer,
      label: s.label,
      age: s.age,
      revenu1: s.revenu1,
      revenu2: s.revenu2,
      fortune: s.fortune,
      impotTotal: s.impot?.impotRevenuTotal ?? null,
      impotFederal: s.impot?.impotFederal ?? null,
      impotCanton: s.impot?.impotCanton ?? null,
      impotCommune: s.impot?.impotCommune ?? null,
    })),
    thirdPillarRows,
    evolution: {
      cible: evo?.cibleRemplacement ?? 0.9,
      salaireReference: evo?.salaireReference ?? results.lacune.salaireAvant,
      renteReference: evo?.renteReference ?? results.lacune.revenuApres,
      points: (evo?.rows ?? []).map((r) => ({
        year: r.year,
        revenu: r.revenu,
        lacune90: r.lacune90,
        phase: r.phase,
      })),
    },
    timeline: {
      years: timeline?.years ?? [],
      events: (timeline?.events ?? []).map((e) => ({
        year: e.year,
        label: e.label,
        amount: e.amount,
        kind: e.kind,
      })),
      byYear: Object.fromEntries(
        Object.entries(timeline?.byYear ?? {}).map(([y, evs]) => [
          y,
          evs.map((e) => ({
            year: e.year,
            label: e.label,
            amount: e.amount,
            kind: e.kind,
          })),
        ]),
      ),
    },
    vaudoise,
    hypothesesRente,
    fiscalOptimization,
    withdrawalPlanning,
    flags: {
      hasThirdPillar,
      hasRentePont,
      hasVaudoise: !!vaudoise?.include,
      hasHypothesesRente: !!hypothesesRente,
      showConjoint: isCouple,
      hasWithdrawalPlanning,
    },
    coherence: {
      avsClient1: client1.avsAnnuel,
      avsConjoint: conjoint?.avsAnnuel ?? null,
      capitalLpp65: capitalLppRetireTotal,
      renteLpp65: renteLppTotal,
      total3ePilier: total3ePilierFoyer,
      lacune: results.lacune.lacune,
      salaireAvant: results.lacune.salaireAvant,
      revenuApres: results.lacune.revenuApres,
      impotCapital65,
      capitalNet65,
      impotRevenuCouple1,
    },
  };
}

function sumLibrePassage(
  input: AnalyseRecord["input"],
  titulaire: "client1" | "conjoint",
): number {
  return round2(
    (input.libresPassages || [])
      .filter((lp) => lp.titulaire === titulaire)
      .reduce((sum, lp) => sum + (Number(lp.montant) || 0), 0),
  );
}

/**
 * Découpe la page de planification pour garder une typographie lisible.
 * Deux scénarios courts tiennent ensemble ; au-delà, un scénario par page.
 * Les écarts vont sur une page suivante.
 */
export function withdrawalPlanningSheetCount(
  scenarioCount: number,
  yearRowCount: number,
  _hasComparisons: boolean,
): number {
  if (scenarioCount <= 0) return 0;
  void yearRowCount;
  return 1;
}

function buildPersonBlock(
  person: AnalyseRecord["input"]["client1"],
  computed: NonNullable<AnalyseRecord["results"]>["client1"],
  salaire: number,
  librePassage: number,
): ReportPersonBlock {
  return {
    displayName: personDisplayName(person),
    civilite: person.civilite,
    dateNaissance: person.dateNaissance || null,
    dateNaissanceLabel: person.dateNaissance
      ? formatDateFr(person.dateNaissance)
      : "—",
    salaire,
    ageLegalLabel: computed.ageLegalLabel,
    dateDepart: computed.dateDepart,
    dateDepartLabel: formatDateFr(computed.dateDepart),
    avsAnnuel: computed.avsAnnuel,
    capitalLpp65: computed.capitalLpp65,
    renteLpp65: computed.renteLpp65,
    lppPctDeblocable: computed.lppPctDeblocable,
    capitalLppRetire65: computed.capitalLppRetire65,
    renteLppResiduelle65: computed.renteLppResiduelle65,
    total3ePilier: computed.total3ePilier,
    librePassage,
    hasRentePont: (person.rentePont ?? 0) > 0,
    rentePont: person.rentePont ?? 0,
  };
}

function buildThirdPillarRows(
  record: AnalyseRecord,
  isCouple: boolean,
): ReportThirdPillarRow[] {
  const { input, results } = record;
  const rows: ReportThirdPillarRow[] = [];
  const lines = results?.thirdPillarLines || [];

  const push = (
    personKey: "client1" | "conjoint",
    personName: string,
    contracts: AnalyseRecord["input"]["client1"]["troisiemePilier"],
  ) => {
    for (const c of contracts) {
      if (!c.montant && !c.compagnie && !c.police) continue;
      const type = normalizeThirdPillarType(c.type);
      const line = lines.find(
        (item) => item.contractId === c.id && item.personKey === personKey,
      );
      const exonere = type === "3B";
      const impot = exonere ? null : (line?.impot ?? null);
      const montant = c.montant || 0;
      rows.push({
        personKey,
        personName,
        compagnie: c.compagnie || "—",
        police: c.police || "—",
        type,
        echeance: c.echeance || null,
        echeanceLabel: c.echeance ? formatDateFr(c.echeance) : "—",
        montant,
        prime: c.prime || 0,
        impot,
        exonere,
        capitalNet: exonere
          ? montant
          : (line?.capitalNet ?? (impot != null ? round2(montant - impot) : null)),
      });
    }
  };

  push("client1", personDisplayName(input.client1), input.client1.troisiemePilier);
  if (isCouple && input.conjoint) {
    push(
      "conjoint",
      personDisplayName(input.conjoint),
      input.conjoint.troisiemePilier,
    );
  }
  return rows;
}

function buildVaudoise(
  record: AnalyseRecord,
  ctx: {
    avsTotal: number;
    renteLppTotal: number;
    impotRevenuCouple1: number | null;
    impotRevenuCouple2: number | null;
    capitalDispo: number;
  },
): ReportPayload["vaudoise"] {
  const r15 = record.input.renteVaudoise15 ?? null;
  const r20 = record.input.renteVaudoise20 ?? null;
  if (r15 == null && r20 == null) {
    return {
      include: false,
      capitalDisponible: ctx.capitalDispo,
      columns: [],
      indicateurs: {
        revenuNetSupplementaire: null,
        gainCumul20Ans: null,
        economieFiscaleAnnuelle: null,
      },
    };
  }

  const taxLpp = ctx.impotRevenuCouple1;
  const taxV = ctx.impotRevenuCouple2;
  const netteLpp =
    taxLpp == null ? null : round2(ctx.avsTotal + ctx.renteLppTotal - taxLpp);

  const columns: ReportVaudoiseColumn[] = [
    {
      id: "lpp",
      label: "Rente LPP (réf.)",
      capitalAffecte: 0,
      renteCertaine: 0,
      participationExcedents: null,
      partImposable: 1,
      impot: taxLpp,
      renteNette: netteLpp,
      gainNetVsLpp: 0,
    },
  ];

  if (r20 != null) {
    const nette =
      taxV == null ? null : round2(ctx.avsTotal + r20 - taxV);
    columns.push({
      id: "vaudoise20",
      label: "Vaudoise 530k / 20 ans",
      capitalAffecte: 530_000,
      renteCertaine: r20,
      participationExcedents: null,
      partImposable: 0,
      impot: taxV,
      renteNette: nette,
      gainNetVsLpp:
        nette != null && netteLpp != null ? round2(nette - netteLpp) : null,
      recommended: true,
    });
  }
  if (r15 != null) {
    const nette =
      taxV == null ? null : round2(ctx.avsTotal + r15 - taxV);
    columns.push({
      id: "vaudoise15",
      label: "Vaudoise 500k / 15 ans",
      capitalAffecte: 500_000,
      renteCertaine: r15,
      participationExcedents: null,
      partImposable: 0,
      impot: taxV,
      renteNette: nette,
      gainNetVsLpp:
        nette != null && netteLpp != null ? round2(nette - netteLpp) : null,
    });
  }

  const recommended = columns.find((c) => c.recommended) || columns[1];
  return {
    include: true,
    capitalDisponible: ctx.capitalDispo,
    columns,
    indicateurs: {
      revenuNetSupplementaire: recommended?.gainNetVsLpp ?? null,
      gainCumul20Ans:
        recommended?.gainNetVsLpp != null
          ? round2(recommended.gainNetVsLpp * 20)
          : null,
      economieFiscaleAnnuelle:
        taxLpp != null && taxV != null ? round2(taxLpp - taxV) : null,
    },
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export { FISCAL_OPT_HIDDEN_REASON };
