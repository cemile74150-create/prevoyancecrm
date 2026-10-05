import {
  formatDateIso,
  formatLegalAgeLabel,
  getLegalRetirementAge,
  getRetirementStartDate,
} from "../rules/avs-age";
import { lppCalculationService } from "./LPPCalculationService";
import type { PersonComputed, PersonInput } from "../types";

/**
 * Service AVS — rentes et âge légal.
 * Mensuel × 13 → annuel (Excel E31 / E32).
 * Intègre le % LPP déblocable pour capital retiré / rente résiduelle.
 */
export class AVSCalculationService {
  annualFromMonthly(mensuel: number): number {
    return round2(mensuel * 13);
  }

  resolveAnnual(person: PersonInput): number {
    if (person.avsAnnuel != null && person.avsAnnuel > 0) {
      return round2(person.avsAnnuel);
    }
    return this.annualFromMonthly(person.avsMensuel || 0);
  }

  computePersonBasics(person: PersonInput): PersonComputed {
    const ageLegal = getLegalRetirementAge(person.civilite, person.dateNaissance);
    const dateDepart = getRetirementStartDate(person.dateNaissance, ageLegal);
    const avsAnnuel = this.resolveAnnual(person);
    const lpp65 = person.lpp.find((r) => r.age === 65) ?? {
      age: 65 as const,
      capital: 0,
      rente: 0,
    };
    const capitalLpp65 = round2(lpp65.capital || 0);
    const renteLpp65 = round2(lpp65.rente || 0);
    const lppPctDeblocable = lppCalculationService.resolvePctDeblocable(
      person.lppPctDeblocable,
    );
    const capitalLppRetire65 = lppCalculationService.capitalRetire(
      capitalLpp65,
      lppPctDeblocable,
    );
    const renteLppResiduelle65 = lppCalculationService.renteResiduelle(
      renteLpp65,
      lppPctDeblocable,
    );
    const total3ePilier = person.troisiemePilier.reduce(
      (s, c) => s + (c.montant || 0),
      0,
    );

    return {
      ageLegal,
      ageLegalLabel: formatLegalAgeLabel(ageLegal),
      dateDepart: formatDateIso(dateDepart),
      avsAnnuel,
      capitalLpp65,
      renteLpp65,
      lppPctDeblocable,
      capitalLppRetire65,
      renteLppResiduelle65,
      renteTotale65: round2(avsAnnuel + renteLpp65),
      total3ePilier: round2(total3ePilier),
    };
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const avsCalculationService = new AVSCalculationService();
