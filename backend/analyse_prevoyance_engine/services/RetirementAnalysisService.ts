import type {
  AnalyseInput,
  AnalyseResults,
  LacuneResult,
  ThirdPillarLineResult,
} from "../types";
import { normalizeThirdPillarType } from "../types";
import { avsCalculationService } from "./AVSCalculationService";
import { taxCalculationService } from "./TaxCalculationService";
import { thirdPillarService } from "./ThirdPillarService";
import { timelineService } from "./TimelineService";
import { postRetirementEvolutionService } from "./PostRetirementEvolutionService";
import { comparativeAnalysisService } from "./ComparativeAnalysisService";
import { renteHypothesisService } from "./RenteHypothesisService";
import {
  retirementScenarioService,
  withdrawalPlanningService,
} from "./RetirementScenarioService";
import { genderFromCivilite, relationshipFromEtat } from "../mappers";

/**
 * Orchestrateur d’analyse — calcule AVS/LPP/3P, lacune, scénarios + ESTV,
 * frise, évolution 90 %, comparatif.
 */
export class RetirementAnalysisService {
  async run(input: AnalyseInput): Promise<AnalyseResults> {
    const errors: string[] = [];
    const client1 = avsCalculationService.computePersonBasics(input.client1);
    const conjoint =
      input.etatCivil === "Marié(e)" && input.conjoint
        ? avsCalculationService.computePersonBasics(input.conjoint)
        : null;

    const lacune = this.computeLacune(
      input,
      client1.renteTotale65,
      conjoint?.renteTotale65 ?? 0,
    );

    let taxLocation = null;
    let taxLocationId = input.taxLocationId;
    let taxGroupId = input.taxGroupId ?? input.taxLocationId;

    if ((!taxLocationId || !taxGroupId) && input.villeRecherche.trim()) {
      try {
        const locs = await taxCalculationService.searchLocation({
          search: input.villeRecherche.trim(),
          taxYear: input.taxYear,
        });
        if (locs[0]) {
          taxLocation = locs[0];
          taxLocationId = locs[0].TaxLocationID;
          taxGroupId = locs[0].TaxLocationID;
        } else {
          errors.push(`Aucune commune trouvée pour « ${input.villeRecherche} »`);
        }
      } catch (e) {
        errors.push(
          e instanceof Error
            ? `Recherche commune ESTV : ${e.message}`
            : "Recherche commune ESTV échouée",
        );
      }
    } else if (taxLocationId) {
      taxLocation = {
        TaxLocationID: taxLocationId,
        City: input.villeRecherche,
      };
    }

    let capitalScenarios = [] as AnalyseResults["capitalScenarios"];
    let capitalPathFoyer = null as AnalyseResults["capitalPathFoyer"];
    let withdrawalPlanning = null as AnalyseResults["withdrawalPlanning"];
    let incomeScenarios = [] as AnalyseResults["incomeScenarios"];
    let thirdPillarTax = null as AnalyseResults["thirdPillarTax"];
    const thirdPillarLines: ThirdPillarLineResult[] = [];

    if (taxGroupId && taxLocationId) {
      capitalScenarios = await retirementScenarioService.buildCapitalScenarios(
        input,
        taxGroupId,
      );
      capitalPathFoyer = await retirementScenarioService.buildCapitalPathFoyer(
        input,
        client1,
        conjoint,
        taxGroupId,
      );
      incomeScenarios = await retirementScenarioService.buildIncomeScenarios(
        input,
        client1,
        conjoint,
        taxLocationId,
      );
      if ((input.withdrawalScenarios || []).length > 0) {
        try {
          withdrawalPlanning = await withdrawalPlanningService.run(
            input,
            client1,
            conjoint,
            taxGroupId,
          );
        } catch (e) {
          errors.push(
            e instanceof Error
              ? `Planification retraits : ${e.message}`
              : "Planification retraits échouée",
          );
        }
      }

      await this.taxThirdPillarContracts(
        input,
        taxGroupId,
        thirdPillarLines,
        errors,
      );
    } else if (!errors.length) {
      errors.push(
        "TaxLocationID manquant — sélectionnez une commune fiscale avant de calculer les impôts.",
      );
    }

    for (const s of capitalScenarios) {
      if (s.error) errors.push(`Capital âge ${s.age} : ${s.error}`);
    }
    for (const s of incomeScenarios) {
      if (s.error) errors.push(`${s.foyer} : ${s.error}`);
    }

    const timeline = timelineService.build(input, client1, conjoint);
    const evolution = postRetirementEvolutionService.build(
      input,
      client1,
      conjoint,
    );
    const comparative = comparativeAnalysisService.build(
      input,
      client1,
      conjoint,
      capitalScenarios,
      incomeScenarios,
      capitalPathFoyer,
    );

    let renteHypotheses = null as AnalyseResults["renteHypotheses"];
    try {
      renteHypotheses = await renteHypothesisService.build(input);
    } catch (e) {
      errors.push(
        e instanceof Error
          ? `Hypothèses de rente : ${e.message}`
          : "Hypothèses de rente échouées",
      );
    }

    return {
      computedAt: new Date().toISOString(),
      client1,
      conjoint,
      lacune,
      capitalScenarios,
      capitalPathFoyer,
      withdrawalPlanning,
      incomeScenarios,
      thirdPillarTax,
      thirdPillarLines,
      taxLocation,
      timeline,
      evolution,
      comparative,
      renteHypotheses,
      errors,
    };
  }

  /**
   * Un impôt ESTV par contrat 3A. Les 3B restent au patrimoine, sans appel ESTV.
   */
  private async taxThirdPillarContracts(
    input: AnalyseInput,
    taxGroupId: number,
    lines: ThirdPillarLineResult[],
    errors: string[],
  ): Promise<void> {
    const people: Array<{
      key: ThirdPillarLineResult["personKey"];
      person: AnalyseInput["client1"];
    }> = [{ key: "client1", person: input.client1 }];
    if (input.etatCivil === "Marié(e)" && input.conjoint) {
      people.push({ key: "conjoint", person: input.conjoint });
    }
    const relationship = relationshipFromEtat(input.etatCivil);

    for (const { key, person } of people) {
      for (const contract of person.troisiemePilier || []) {
        if (!contract.montant && !contract.compagnie && !contract.police) {
          continue;
        }
        const type = normalizeThirdPillarType(contract.type);
        const montant = contract.montant || 0;
        if (type === "3B") {
          lines.push({
            contractId: contract.id,
            personKey: key,
            type,
            montant,
            impot: null,
            exonere: true,
            capitalNet: montant,
          });
          continue;
        }
        if (!(montant > 0)) {
          lines.push({
            contractId: contract.id,
            personKey: key,
            type,
            montant,
            impot: null,
            exonere: false,
            capitalNet: montant,
          });
          continue;
        }
        const age =
          thirdPillarService.ageAtMaturity(
            person.dateNaissance,
            contract.echeance,
          ) ?? 65;
        try {
          const tax = await taxCalculationService.calculateCapitalTax({
            ageAtPayment: age,
            capital: montant,
            gender: genderFromCivilite(person.civilite),
            relationship,
            taxGroupId,
            taxYear: input.taxYear,
          });
          lines.push({
            contractId: contract.id,
            personKey: key,
            type,
            montant,
            impot: tax.impotTotal,
            exonere: false,
            capitalNet: round2(montant - tax.impotTotal),
          });
        } catch (e) {
          errors.push(
            e instanceof Error
              ? `Impôt 3e pilier ${contract.police || contract.compagnie || contract.id} : ${e.message}`
              : "Impôt 3e pilier échoué",
          );
          lines.push({
            contractId: contract.id,
            personKey: key,
            type,
            montant,
            impot: null,
            exonere: false,
            capitalNet: montant,
          });
        }
      }
    }
  }

  /**
   * Lacune Excel ANALYSE RETRAITE D140–D144 (cible 80 %).
   */
  computeLacune(
    input: AnalyseInput,
    renteClient1: number,
    renteConjoint: number,
  ): LacuneResult {
    const salaireAvant =
      input.salaireClient1 +
      (input.etatCivil === "Marié(e)" ? input.salaireConjoint : 0) +
      (input.autresRevenus || 0);
    const revenuApres = renteClient1 + renteConjoint;
    const lacune = round2(salaireAvant - revenuApres);
    const manquePour80 = round2(salaireAvant * 0.8 - revenuApres);
    const tauxRemplacementReel =
      salaireAvant > 0 ? round2(revenuApres / salaireAvant) : 0;

    return {
      salaireAvant: round2(salaireAvant),
      revenuApres: round2(revenuApres),
      lacune,
      manquePour80,
      tauxRemplacementCible: 0.8,
      tauxRemplacementReel,
    };
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const retirementAnalysisService = new RetirementAnalysisService();
