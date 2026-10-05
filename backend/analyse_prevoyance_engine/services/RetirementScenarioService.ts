import type {
  AnalyseInput,
  CapitalKind,
  CapitalPathFoyer,
  CapitalScenario,
  IncomeScenario,
  PersonComputed,
  PersonKey,
  RetirementAge,
  WithdrawalPlanningResult,
  WithdrawalScenario,
  WithdrawalScenarioResult,
  WithdrawalTaxAudit,
} from "../types";
import {
  RETIREMENT_AGES,
  librePassageRetire,
  normalizeThirdPillarType,
  type ThirdPillarType,
} from "../types";
import { areScenariosComparable } from "../withdrawalPlanUtils";
import { lppCalculationService } from "./LPPCalculationService";
import { taxCalculationService } from "./TaxCalculationService";
import { genderFromCivilite, relationshipFromEtat } from "../mappers";

/**
 * Scénarios capital + rente + chemin foyer (LPP % + libre passage).
 * Agrégation fiscale chemin capital : une ESTV par personne (LPP retiré + LP retiré).
 */
export class RetirementScenarioService {
  async buildCapitalScenarios(
    input: AnalyseInput,
    taxGroupId: number,
  ): Promise<CapitalScenario[]> {
    const relationship = relationshipFromEtat(input.etatCivil);
    const gender = genderFromCivilite(input.client1.civilite);
    const rows = lppCalculationService.normalizeRows(input.client1.lpp);
    const pct = lppCalculationService.resolvePctDeblocable(
      input.client1.lppPctDeblocable,
    );

    const scenarios: CapitalScenario[] = [];

    for (const age of RETIREMENT_AGES) {
      const row = lppCalculationService.getAtAge(rows, age);
      const capitalBrut = row.capital;
      const capital = lppCalculationService.capitalRetire(capitalBrut, pct);
      const renteTotale = row.rente;
      const rente = lppCalculationService.renteResiduelle(renteTotale, pct);
      const taux = lppCalculationService.conversionRate(row);
      const base: CapitalScenario = {
        age,
        capital,
        capitalBrut,
        rente,
        renteTotale,
        pctDeblocable: pct,
        tauxConversion: taux,
        impot: null,
        net: null,
      };

      if (!capital || capital <= 0) {
        scenarios.push({
          ...base,
          error:
            capitalBrut > 0 && pct === 0
              ? "0 % déblocable — pas d’appel ESTV capital"
              : "Capital nul — pas d’appel ESTV",
        });
        continue;
      }

      try {
        const tax = await taxCalculationService.calculateCapitalTax({
          ageAtPayment: age,
          capital,
          gender,
          relationship,
          taxGroupId,
          taxYear: input.taxYear,
        });
        scenarios.push({
          ...base,
          impot: tax.impotTotal,
          net: round2(capital - tax.impotTotal),
          taxAudit: tax,
        });
      } catch (e) {
        scenarios.push({
          ...base,
          error: e instanceof Error ? e.message : "Erreur ESTV capital",
        });
      }
    }

    return scenarios;
  }

  /**
   * Chemin capital foyer : LPP retirée + LP retiré, ESTV **agrégée par personne**
   * (pas somme d’impôts contrat par contrat). Ne reproduit pas Excel J7 (100 % LPP Mme).
   */
  async buildCapitalPathFoyer(
    input: AnalyseInput,
    client1: PersonComputed,
    conjoint: PersonComputed | null,
    taxGroupId: number,
  ): Promise<CapitalPathFoyer> {
    const relationship = relationshipFromEtat(input.etatCivil);
    const isMarried = relationship === 2 && !!conjoint;
    const lps = input.libresPassages || [];

    const lpRetireFor = (titulaire: PersonKey) =>
      round2(
        lps
          .filter((lp) => lp.titulaire === titulaire)
          .reduce((s, lp) => s + librePassageRetire(lp), 0),
      );
    const lpBrutFor = (titulaire: PersonKey) =>
      round2(
        lps
          .filter((lp) => lp.titulaire === titulaire)
          .reduce((s, lp) => s + (lp.montant || 0), 0),
      );

    const c1Lp = lpRetireFor("client1");
    const c1LpBrut = lpBrutFor("client1");
    const c1 = {
      capitalBrut: round2(client1.capitalLpp65 + c1LpBrut),
      lppRetire: client1.capitalLppRetire65,
      lpRetire: c1Lp,
      capitalRetire: round2(client1.capitalLppRetire65 + c1Lp),
      renteResiduelle: client1.renteLppResiduelle65,
      impot: null as number | null,
    };

    let c2: CapitalPathFoyer["conjoint"] = null;

    if (c1.capitalRetire > 0) {
      try {
        const tax = await taxCalculationService.calculateCapitalTax({
          ageAtPayment: 65,
          capital: c1.capitalRetire,
          gender: genderFromCivilite(input.client1.civilite),
          relationship,
          taxGroupId,
          taxYear: input.taxYear,
        });
        c1.impot = tax.impotTotal;
      } catch {
        c1.impot = null;
      }
    }

    if (isMarried && conjoint && input.conjoint) {
      const c2Lp = lpRetireFor("conjoint");
      const c2LpBrut = lpBrutFor("conjoint");
      c2 = {
        capitalBrut: round2(conjoint.capitalLpp65 + c2LpBrut),
        lppRetire: conjoint.capitalLppRetire65,
        lpRetire: c2Lp,
        capitalRetire: round2(conjoint.capitalLppRetire65 + c2Lp),
        renteResiduelle: conjoint.renteLppResiduelle65,
        impot: null,
      };
      if (c2.capitalRetire > 0) {
        try {
          const tax = await taxCalculationService.calculateCapitalTax({
            ageAtPayment: 65,
            capital: c2.capitalRetire,
            gender: genderFromCivilite(input.conjoint.civilite),
            relationship,
            taxGroupId,
            taxYear: input.taxYear,
          });
          c2.impot = tax.impotTotal;
        } catch {
          c2.impot = null;
        }
      }
    }

    const capitalBrutTotal = round2(c1.capitalBrut + (c2?.capitalBrut ?? 0));
    const capitalRetireTotal = round2(
      c1.capitalRetire + (c2?.capitalRetire ?? 0),
    );
    const lppRetireTotal = round2(c1.lppRetire + (c2?.lppRetire ?? 0));
    const librePassageRetireTotal = round2(c1.lpRetire + (c2?.lpRetire ?? 0));
    const renteResiduelleTotal = round2(
      c1.renteResiduelle + (c2?.renteResiduelle ?? 0),
    );
    const impotParts = [c1.impot, c2?.impot].filter(
      (x): x is number => x != null,
    );
    const impot =
      impotParts.length > 0
        ? round2(impotParts.reduce((s, n) => s + n, 0))
        : capitalRetireTotal > 0
          ? null
          : 0;
    const net = impot == null ? null : round2(capitalRetireTotal - impot);

    return {
      capitalBrutTotal,
      capitalRetireTotal,
      lppRetireTotal,
      librePassageRetireTotal,
      renteResiduelleTotal,
      impot,
      net,
      client1: c1,
      conjoint: c2,
    };
  }

  async buildIncomeScenarios(
    input: AnalyseInput,
    client1: PersonComputed,
    conjoint: PersonComputed | null,
    taxLocationId: number,
  ): Promise<IncomeScenario[]> {
    const relationship = relationshipFromEtat(input.etatCivil);
    const isMarried = relationship === 2 && !!conjoint;
    const fortuneBase = Number.isFinite(input.fortune) ? input.fortune : 0;

    const defs: Array<{
      foyer: string;
      label: string;
      age: number;
      revenu1: number;
      revenu2: number;
      fortune: number;
    }> = [
      {
        foyer: "Couple1",
        label: "Rente totale AVS + LPP (65)",
        age: 65,
        revenu1: client1.renteTotale65,
        revenu2: isMarried ? conjoint!.renteTotale65 : 0,
        fortune: fortuneBase,
      },
      {
        foyer: "Couple2",
        label: "Chemin capital : AVS + rente LPP résiduelle",
        age: 65,
        revenu1: round2(client1.avsAnnuel + client1.renteLppResiduelle65),
        revenu2: isMarried
          ? round2(conjoint!.avsAnnuel + conjoint!.renteLppResiduelle65)
          : 0,
        fortune: fortuneBase,
      },
    ];

    const agesLpp: RetirementAge[] = [64, 63, 62, 61, 60];
    agesLpp.forEach((age, idx) => {
      const row = lppCalculationService.getAtAge(input.client1.lpp, age);
      defs.push({
        foyer: `Couple${idx + 3}`,
        label: `AVS + LPP âge ${age}${age === 63 ? " (fortune=0)" : ""}`,
        age,
        revenu1: round2(client1.avsAnnuel + (row.rente || 0)),
        revenu2: isMarried ? conjoint!.avsAnnuel : 0,
        fortune: age === 63 ? 0 : fortuneBase,
      });
    });

    const results: IncomeScenario[] = [];
    for (const def of defs) {
      try {
        const impot = await taxCalculationService.calculateDetailedTaxes({
          foyer: def.foyer,
          taxLocationId,
          relationship,
          age1: def.age,
          age2: isMarried ? def.age : 0,
          revenue1: def.revenu1,
          revenue2: def.revenu2,
          fortune: def.fortune,
          taxYear: input.taxYear,
        });
        results.push({ ...def, impot });
      } catch (e) {
        results.push({
          ...def,
          impot: null,
          error: e instanceof Error ? e.message : "Erreur ESTV revenu",
        });
      }
    }
    return results;
  }
}

/**
 * Service planification multi-scénarios.
 * Agrégation fiscale : **personne + année fiscale** → un appel ESTV
 * (somme des capitaux retirés), jamais somme d’impôts unitaires.
 */
export class WithdrawalPlanningService {
  async run(
    input: AnalyseInput,
    client1: PersonComputed,
    conjoint: PersonComputed | null,
    taxGroupId: number,
  ): Promise<WithdrawalPlanningResult | null> {
    const scenarios = input.withdrawalScenarios || [];
    if (!scenarios.length) return null;

    const relationship = relationshipFromEtat(input.etatCivil);
    const results: WithdrawalScenarioResult[] = [];

    for (const sc of scenarios) {
      results.push(
        await this.evaluateScenario(
          input,
          sc,
          client1,
          conjoint,
          taxGroupId,
          relationship,
        ),
      );
    }

    const comparisons: WithdrawalPlanningResult["comparisons"] = [];
    for (let i = 0; i < results.length; i++) {
      for (let j = i + 1; j < results.length; j++) {
        const a = results[i];
        const b = results[j];
        const { sameCapitalBase, warning } = areScenariosComparable(
          a.capitalRetireTotal,
          b.capitalRetireTotal,
        );
        comparisons.push({
          fromId: a.scenarioId,
          toId: b.scenarioId,
          fromName: a.scenarioName,
          toName: b.scenarioName,
          deltaImpot:
            a.impotTotal != null && b.impotTotal != null
              ? round2(b.impotTotal - a.impotTotal)
              : null,
          deltaCapitalNet:
            a.capitalNet != null && b.capitalNet != null
              ? round2(b.capitalNet - a.capitalNet)
              : null,
          sameCapitalBase,
          warning,
        });
      }
    }

    return { scenarios: results, comparisons };
  }

  private async evaluateScenario(
    input: AnalyseInput,
    sc: WithdrawalScenario,
    client1: PersonComputed,
    conjoint: PersonComputed | null,
    taxGroupId: number,
    relationship: number,
  ): Promise<WithdrawalScenarioResult> {
    // Group by titulaire + year
    type Line = {
      kind: CapitalKind;
      label: string;
      institution: string;
      montantRetire: number;
      exonere: boolean;
      contratType: ThirdPillarType | null;
    };
    type Bucket = {
      year: number;
      titulaire: PersonKey;
      items: Line[];
    };
    const buckets = new Map<string, Bucket>();

    for (const item of sc.items) {
      if (item.anneeRetraitPrevue == null) continue;
      const holder =
        item.titulaire === "client1" ? input.client1 : input.conjoint;
      const pct =
        item.kind === "lpp" && holder
          ? lppCalculationService.resolvePctDeblocable(holder.lppPctDeblocable)
          : Math.min(100, Math.max(0, item.pctCapital || 0));
      const montantRetire = round2((item.montantDisponible || 0) * (pct / 100));
      if (montantRetire <= 0) continue;
      const contratType = thirdPillarTypeForItem(input, item);
      const exonere = item.kind === "3p" && contratType === "3B";
      const key = `${item.titulaire}|${item.anneeRetraitPrevue}`;
      const cur = buckets.get(key) || {
        year: item.anneeRetraitPrevue,
        titulaire: item.titulaire,
        items: [],
      };
      cur.items.push({
        kind: item.kind,
        label: item.label,
        institution: item.institution || "",
        montantRetire,
        exonere,
        contratType,
      });
      buckets.set(key, cur);
    }

    const audits: WithdrawalTaxAudit[] = [];
    let capitalRetireTotal = 0;
    let impotTotalAcc = 0;
    let impotOk = true;
    const byYearMap = new Map<
      number,
      {
        capitalRetire: number;
        impot: number | null;
        lines: WithdrawalScenarioResult["byYear"][0]["lines"];
      }
    >();

    for (const bucket of [...buckets.values()].sort(
      (a, b) => a.year - b.year || a.titulaire.localeCompare(b.titulaire),
    )) {
      const capitalAll = round2(
        bucket.items.reduce((s, i) => s + i.montantRetire, 0),
      );
      const montantSoumis = round2(
        bucket.items
          .filter((i) => !i.exonere)
          .reduce((s, i) => s + i.montantRetire, 0),
      );
      capitalRetireTotal = round2(capitalRetireTotal + capitalAll);

      const yearEntry = byYearMap.get(bucket.year) || {
        capitalRetire: 0,
        impot: 0 as number | null,
        lines: [],
      };
      for (const it of bucket.items) {
        yearEntry.lines.push({
          titulaire: bucket.titulaire,
          kind: it.kind,
          label: it.label,
          institution: it.institution,
          montantRetire: it.montantRetire,
          contratType: it.contratType,
          exonere: it.exonere,
        });
      }
      yearEntry.capitalRetire = round2(
        yearEntry.capitalRetire + capitalAll,
      );
      if (montantSoumis <= 0) {
        if (yearEntry.impot == null) yearEntry.impot = 0;
        byYearMap.set(bucket.year, yearEntry);
        audits.push({
          scenarioId: sc.id,
          scenarioName: sc.name,
          year: bucket.year,
          titulaire: bucket.titulaire,
          taxLocationId: input.taxLocationId || taxGroupId,
          etatCivil: input.etatCivil,
          gender: genderFromCivilite(
            (bucket.titulaire === "client1" ? input.client1 : input.conjoint)
              ?.civilite || "Monsieur",
          ),
          relationship,
          ageAtPayment: 65,
          capitauxInclus: [],
          montantSoumis: 0,
          request: {},
          response: null,
          impotTotal: 0,
        });
        continue;
      }

      const person =
        bucket.titulaire === "client1" ? input.client1 : input.conjoint;
      if (!person) {
        audits.push({
          scenarioId: sc.id,
          scenarioName: sc.name,
          year: bucket.year,
          titulaire: bucket.titulaire,
          taxLocationId: input.taxLocationId || 0,
          etatCivil: input.etatCivil,
          gender: 1,
          relationship,
          ageAtPayment: 65,
          capitauxInclus: bucket.items.filter((item) => !item.exonere).map(({ kind, label, montantRetire }) => ({
            kind,
            label,
            montantRetire,
          })),
          montantSoumis,
          request: {},
          response: null,
          impotTotal: null,
          error: "Titulaire conjoint absent",
        });
        impotOk = false;
        byYearMap.set(bucket.year, yearEntry);
        continue;
      }

      const ageAtPayment = ageInYear(
        person.dateNaissance,
        bucket.year,
        bucket.titulaire === "client1"
          ? client1.ageLegal
          : (conjoint?.ageLegal ?? 65),
      );
      const gender = genderFromCivilite(person.civilite);

      try {
        const tax = await taxCalculationService.calculateCapitalTax({
          ageAtPayment,
          capital: montantSoumis,
          gender,
          relationship,
          taxGroupId,
          taxYear: input.taxYear,
        });
        audits.push({
          scenarioId: sc.id,
          scenarioName: sc.name,
          year: bucket.year,
          titulaire: bucket.titulaire,
          taxLocationId: input.taxLocationId || taxGroupId,
          etatCivil: input.etatCivil,
          gender,
          relationship,
          ageAtPayment,
          capitauxInclus: bucket.items.filter((item) => !item.exonere).map(({ kind, label, montantRetire }) => ({
            kind,
            label,
            montantRetire,
          })),
          montantSoumis,
          request: tax.request,
          response: tax.response,
          impotTotal: tax.impotTotal,
        });
        impotTotalAcc = round2(impotTotalAcc + tax.impotTotal);
        yearEntry.impot = round2((yearEntry.impot || 0) + tax.impotTotal);
        byYearMap.set(bucket.year, yearEntry);
      } catch (e) {
        impotOk = false;
        yearEntry.impot = null;
        byYearMap.set(bucket.year, yearEntry);
        audits.push({
          scenarioId: sc.id,
          scenarioName: sc.name,
          year: bucket.year,
          titulaire: bucket.titulaire,
          taxLocationId: input.taxLocationId || taxGroupId,
          etatCivil: input.etatCivil,
          gender,
          relationship,
          ageAtPayment,
          capitauxInclus: bucket.items.filter((item) => !item.exonere).map(({ kind, label, montantRetire }) => ({
            kind,
            label,
            montantRetire,
          })),
          montantSoumis,
          request: {},
          response: null,
          impotTotal: null,
          error: e instanceof Error ? e.message : "Erreur ESTV",
        });
      }
    }

    const impotTotal = impotOk ? impotTotalAcc : null;
    return {
      scenarioId: sc.id,
      scenarioName: sc.name,
      includeInReport: !!sc.includeInReport,
      capitalRetireTotal,
      impotTotal,
      capitalNet:
        impotTotal == null ? null : round2(capitalRetireTotal - impotTotal),
      audits,
      byYear: [...byYearMap.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([year, v]) => ({
          year,
          capitalRetire: v.capitalRetire,
          impot: v.impot,
          net:
            v.impot == null ? null : round2(v.capitalRetire - v.impot),
          lines: v.lines,
        })),
    };
  }
}

function thirdPillarTypeForItem(
  input: AnalyseInput,
  item: { kind: string; sourceId?: string },
): ThirdPillarType | null {
  if (item.kind !== "3p") return null;
  const contracts = [
    ...(input.client1.troisiemePilier || []),
    ...(input.conjoint?.troisiemePilier || []),
  ];
  const found = item.sourceId
    ? contracts.find((contract) => contract.id === item.sourceId)
    : undefined;
  return normalizeThirdPillarType(found?.type);
}

function ageInYear(
  birthIso: string,
  year: number,
  fallback: number,
): number {
  if (!birthIso || !/^\d{4}/.test(birthIso)) {
    return Math.round(fallback) || 65;
  }
  const by = Number(birthIso.slice(0, 4));
  const age = year - by;
  return Math.min(70, Math.max(55, age));
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const retirementScenarioService = new RetirementScenarioService();
export const withdrawalPlanningService = new WithdrawalPlanningService();

