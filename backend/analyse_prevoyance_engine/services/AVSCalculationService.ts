import {
  ageAvecAnticipationAvs,
  anticipationAvsAnnees,
  formatDateIso,
  formatLegalAgeLabel,
  getLegalRetirementAge,
  getRetirementStartDate,
  reduireAvsPourAnticipation,
} from "../rules/avs-age";
import { effectiveLppWithdrawalAge } from "../rules/planification-saisie";
import { lppCalculationService, lppTableAge } from "./LPPCalculationService";
import type { PersonComputed, PersonInput } from "../types";

export interface PersonBasicsContext {
  /**
   * Âge de l'onglet Client, repris par le retrait LPP
   * tant que l'assuré n'a pas le sien.
   */
  dossierAgeRetraite?: number | null;
  /** Âge de perception AVS saisi dans l'onglet Client. */
  agePerceptionAvs?: number | null;
}

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

  computePersonBasics(
    person: PersonInput,
    ctx?: PersonBasicsContext,
  ): PersonComputed {
    const ageLegal = getLegalRetirementAge(person.civilite, person.dateNaissance);
    const dateDepart = formatDateIso(
      getRetirementStartDate(person.dateNaissance, ageLegal),
    );
    const lppAgeRequested = effectiveLppWithdrawalAge(
      person,
      ctx?.dossierAgeRetraite,
    );
    const ageLppRetenu = lppTableAge(lppAgeRequested);
    const aggregated = lppCalculationService.aggregateAtAge(person, ageLppRetenu);
    const lppPctDeblocable = lppCalculationService.resolvePctDeblocable(
      person.lppPctDeblocable,
    );
    const ageFin = lppAgeRequested ?? ageLegal;
    const anticipation = anticipationAvsAnnees(person.anticipationAvsAnnees);
    const ageAvs =
      anticipation > 0
        ? ageAvecAnticipationAvs(ageLegal, anticipation)
        : explicitAge(ctx?.agePerceptionAvs) ?? ageLegal;
    const dateFinActivite =
      lppAgeRequested == null
        ? dateDepart
        : formatDateIso(
            getRetirementStartDate(person.dateNaissance, lppAgeRequested),
          );
    const datePerceptionAvs = formatDateIso(
      getRetirementStartDate(person.dateNaissance, ageAvs),
    );
    const pleine = this.resolveAnnual(person);
    const saisieAnticipee =
      anticipation > 0
        ? (person.avsRentesAnticipees || []).find(
            (row) => row.age === ageAvs && row.montantAnnuel > 0,
          )
        : undefined;
    const avsRetenue = saisieAnticipee
      ? round2(saisieAnticipee.montantAnnuel)
      : reduireAvsPourAnticipation(pleine, anticipation);
    const total3ePilier = person.troisiemePilier.reduce(
      (s, c) => s + (c.montant || 0),
      0,
    );

    return {
      ageLegal,
      ageLegalLabel: formatLegalAgeLabel(ageLegal),
      dateDepart,
      dateFinActivite,
      ageFinActiviteLabel: formatLegalAgeLabel(ageFin),
      datePerceptionAvs,
      agePerceptionAvsLabel:
        anticipation > 0
          ? `${formatLegalAgeLabel(ageAvs)} (anticipation ${anticipation} an${anticipation > 1 ? "s" : ""})`
          : formatLegalAgeLabel(ageAvs),
      ageLppRetenu,
      avsAnnuel: avsRetenue,
      capitalLpp65: aggregated.capital,
      renteLpp65: aggregated.rente,
      lppPctDeblocable,
      capitalLppRetire65: aggregated.capitalRetire,
      renteLppResiduelle65: aggregated.renteResiduelle,
      renteTotale65: round2(avsRetenue + aggregated.rente),
      total3ePilier: round2(total3ePilier),
      lppLignes: aggregated.lines.map((line) => ({
        ...line,
        anneeRetrait: anneeRetraitLigne(
          person.dateNaissance,
          line.age ?? ageLppRetenu,
        ),
      })),
    };
  }
}

function anneeRetraitLigne(birth: string, age: number): number | null {
  if (!birth || !/^\d{4}-\d{2}-\d{2}/.test(birth)) return null;
  const year = getRetirementStartDate(birth, age).getFullYear();
  return Number.isFinite(year) ? year : null;
}

function explicitAge(value: number | null | undefined): number | null {
  if (value == null || Number.isNaN(value) || value <= 0) return null;
  return value;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const avsCalculationService = new AVSCalculationService();
