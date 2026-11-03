import {
  ageAvecAnticipationAvs,
  anticipationAvsAnnees,
  formatDateIso,
  formatLegalAgeLabel,
  getLegalRetirementAge,
  getRetirementStartDate,
} from "../rules/avs-age";
import { effectiveLppWithdrawalAge } from "../rules/planification-saisie";
import { avertissementLppAge, lppCalculationService, lppTableAge } from "./LPPCalculationService";
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
    const lppAvertissement = avertissementLppAge(person, lppAgeRequested);
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
    const active = renteAvsDejaPercue(person);
    const pleine = this.resolveAnnual(person);
    // L'anticipation décale seulement la date. Le montant saisi reste la
    // référence : ni la réduction de 6,8 % par an, ni une ligne anticipée
    // ne remplacent « AVS estimée ».
    const avsReference = person.avsDejaActive
      ? active
        ? this.annualFromMonthly(active.mensuel)
        : 0
      : pleine;
    const dateAvs = person.avsDejaActive
      ? active?.date || ""
      : datePerceptionAvs;
    const libelleAvs = person.avsDejaActive
      ? active
        ? "AVS déjà active"
        : "AVS déjà active — date ou montant manquant"
      : anticipation > 0
        ? `${formatLegalAgeLabel(ageAvs)} (anticipation ${anticipation} an${anticipation > 1 ? "s" : ""})`
        : formatLegalAgeLabel(ageAvs);
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
      datePerceptionAvs: dateAvs || undefined,
      agePerceptionAvsLabel: libelleAvs,
      ageLppRetenu: ageLppRetenu ?? undefined,
      avsDejaActive: Boolean(person.avsDejaActive),
      lppAvertissement,
      avsAnnuel: avsReference,
      capitalLpp65: aggregated.capital,
      renteLpp65: aggregated.rente,
      lppPctDeblocable,
      capitalLppRetire65: aggregated.capitalRetire,
      renteLppResiduelle65: aggregated.renteResiduelle,
      renteTotale65: round2(avsReference + aggregated.rente),
      total3ePilier: round2(total3ePilier),
      lppLignes: aggregated.lines.map((line) => ({
        ...line,
        anneeRetrait: anneeRetraitLigne(
          person.dateNaissance,
          line.age ?? ageLppRetenu ?? ageFin,
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

/** Rente déjà versée : date saisie et mensuel × 13, sans seconde rente à l'âge légal. */
function renteAvsDejaPercue(
  person: PersonInput,
): { date: string; mensuel: number } | null {
  if (!person.avsDejaActive) return null;
  const date = String(person.dateDebutRenteAvs || "");
  if (!/^\d{4}-\d{2}-\d{2}/.test(date)) return null;
  const mensuel = Number(person.renteAvsPercueMensuelle);
  if (!Number.isFinite(mensuel) || mensuel <= 0) return null;
  return { date, mensuel };
}

function explicitAge(value: number | null | undefined): number | null {
  if (value == null || Number.isNaN(value) || value <= 0) return null;
  return value;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const avsCalculationService = new AVSCalculationService();
