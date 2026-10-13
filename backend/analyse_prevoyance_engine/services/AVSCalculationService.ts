import {
  formatDateIso,
  formatLegalAgeLabel,
  getLegalRetirementAge,
  getRetirementStartDate,
} from "../rules/avs-age";
import { lppCalculationService } from "./LPPCalculationService";
import type { PersonComputed, PersonInput } from "../types";

/** Rente AVS annuelle = mensuelle × 13 (13e rente), pas × 12. */
export const AVS_MENSUALITES_PAR_AN = 13;

/**
 * Service AVS — rentes et âge légal.
 * Mensuel × 13 → annuel lorsque l'annuel n'est pas déjà saisi.
 * Un annuel déjà enregistré reste prioritaire (analyses existantes).
 * Intègre le % LPP disponible pour capital retiré / rente résiduelle.
 */
export class AVSCalculationService {
  annualFromMonthly(mensuel: number): number {
    return round2(mensuel * AVS_MENSUALITES_PAR_AN);
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
    const lpp65 = lppCalculationService.getAtAge(
      lppCalculationService.normalizeRows(person.lpp || []),
      65,
    );
    const capitalLpp65 = lppCalculationService.referenceCapital(person.lpp);
    const renteLpp65 = round2(lpp65.rente || 0);
    const lppPctDeblocable = lppCalculationService.resolvePctDeblocable(
      person.lppPctDeblocable,
    );
    const capitalLppRetire65 = lppCalculationService.capitalEffectivementRetirable(
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
