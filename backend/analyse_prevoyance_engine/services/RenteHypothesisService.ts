import type {
  AnalyseInput,
  PersonComputed,
  PersonInput,
  RenteHypothesisColumn,
  RenteHypothesisComparison,
  RenteHypothesisInput,
} from "../types";
import { avsCalculationService } from "./AVSCalculationService";
import { taxCalculationService } from "./TaxCalculationService";
import { ageRetraitePersonne } from "../rules/age-retraite";
import {
  revenuBrutEncaisse,
  revenuFiscalImposable,
  revenuFiscalRenteLpp,
  revenuNetApresImpot,
  roundMoney,
} from "../rules/rente-hypotheses";

function avsPrincipale65(person: PersonInput): number {
  return avsCalculationService.resolveAnnual(person);
}

/** AVS utilisée pour un âge : anticipée si saisie, sinon la rente à 65 ans. */
export function avsPourAge(person: PersonInput, age: number | null): number {
  if (age != null && age !== 65) {
    const hit = (person.avsRentesAnticipees || []).find(
      (row) => row.age === age && row.montantAnnuel > 0,
    );
    if (hit) return hit.montantAnnuel;
  }
  return avsPrincipale65(person);
}

/**
 * Mêmes pensions que les lignes imprimées et que le scénario Couple1 :
 * AVS retenue, rente LPP entière à l'âge de retrait LPP, résiduelle selon le %.
 * Une rente d'un autre âge du tableau n'est pas ajoutée.
 */
function pensionsImprimees(input: AnalyseInput): {
  client1: PersonComputed;
  conjoint: PersonComputed | null;
} {
  const client1 = avsCalculationService.computePersonBasics(input.client1, {
    dossierAgeRetraite: ageRetraitePersonne(
      input.client1,
      input.ageRetraiteSouhaite,
    ),
  });
  const conjoint =
    input.etatCivil === "Marié(e)" && input.conjoint
      ? avsCalculationService.computePersonBasics(input.conjoint, {
          dossierAgeRetraite: ageRetraitePersonne(
            input.conjoint,
            input.ageRetraiteSouhaite,
          ),
        })
      : null;
  return { client1, conjoint };
}

function hypothesisUsable(row: RenteHypothesisInput): boolean {
  return Boolean(
    (row.compagnie || "").trim() ||
      row.capitalPlace ||
      row.renteGarantieAnnuelle ||
      row.participationExcedentsAnnuelle,
  );
}

function typeLabel(type: RenteHypothesisInput["type"]): string {
  return type === "viagere" ? "Viagère" : "Certaine";
}

/**
 * Comparatif des offres de rente. Chaque colonne a son impôt ESTV
 * calculé sur le revenu fiscal, pas sur le revenu encaissé.
 */
export class RenteHypothesisService {
  async build(
    input: AnalyseInput,
  ): Promise<RenteHypothesisComparison | null> {
    const hypotheses = (input.renteHypotheses || []).filter(hypothesisUsable);
    const withLpp = Boolean(input.comparerAvecRenteLpp);
    if (!hypotheses.length && !withLpp) return null;

    const age1 = ageRetraitePersonne(input.client1, input.ageRetraiteSouhaite);
    const age2 = input.conjoint
      ? ageRetraitePersonne(input.conjoint, input.ageRetraiteSouhaite)
      : null;
    const { client1, conjoint } = pensionsImprimees(input);
    const avs = roundMoney(client1.avsAnnuel + (conjoint?.avsAnnuel ?? 0));
    const lpp = roundMoney(client1.renteLpp65 + (conjoint?.renteLpp65 ?? 0));
    const residuelle = roundMoney(
      client1.renteLppResiduelle65 + (conjoint?.renteLppResiduelle65 ?? 0),
    );

    const columns: RenteHypothesisColumn[] = [];
    if (withLpp) {
      columns.push(
        await this.columnLpp(
          input,
          avs,
          lpp,
          client1.renteTotale65,
          conjoint?.renteTotale65 ?? 0,
        ),
      );
    }
    for (const [index, row] of hypotheses.entries()) {
      columns.push(await this.columnOffre(input, row, index, avs, residuelle, age1, age2));
    }

    const lppNet = columns.find((col) => col.kind === "lpp")?.revenuNetApresImpot;
    if (withLpp && lppNet != null) {
      for (const col of columns) {
        if (col.kind === "lpp" || col.revenuNetApresImpot == null) continue;
        col.ecartNetAnnuelVsLpp =
          Math.round((col.revenuNetApresImpot - lppNet) * 100) / 100;
      }
    }

    return {
      ageRetraite: age1,
      comparerAvecRenteLpp: withLpp,
      columns,
    };
  }

  private async taxOn(
    input: AnalyseInput,
    revenuFiscal: number,
    age1: number | null,
    age2: number | null,
  ): Promise<number | null> {
    if (!input.taxLocationId || revenuFiscal <= 0) return null;
    const married = input.etatCivil === "Marié(e)";
    const resolved1 = age1 ?? 65;
    const resolved2 = age2 ?? resolved1;
    try {
      const tax = await taxCalculationService.calculateDetailedTaxes({
        foyer: "hypothese-rente",
        taxLocationId: input.taxLocationId,
        relationship: married ? 2 : 1,
        age1: resolved1,
        age2: married ? resolved2 : 0,
        revenue1: revenuFiscal,
        revenue2: 0,
        fortune: input.fortune || 0,
        taxYear: input.taxYear,
      });
      return tax.impotRevenuTotal;
    } catch {
      return null;
    }
  }

  /**
   * Même assiette et même appel ESTV que Couple1 (revenu partagé, âge 65).
   * Le total imposable reste AVS + rente LPP entière imprimée.
   */
  private async taxLikeCouple1(
    input: AnalyseInput,
    revenue1: number,
    revenue2: number,
  ): Promise<number | null> {
    const total = roundMoney(revenue1 + revenue2);
    if (!input.taxLocationId || total <= 0) return null;
    const married = input.etatCivil === "Marié(e)";
    try {
      const tax = await taxCalculationService.calculateDetailedTaxes({
        foyer: "hypothese-rente",
        taxLocationId: input.taxLocationId,
        relationship: married ? 2 : 1,
        age1: 65,
        age2: married ? 65 : 0,
        revenue1,
        revenue2: married ? revenue2 : 0,
        fortune: input.fortune || 0,
        taxYear: input.taxYear,
      });
      return tax.impotRevenuTotal;
    } catch {
      return null;
    }
  }

  private async columnLpp(
    input: AnalyseInput,
    avs: number,
    lpp: number,
    revenue1: number,
    revenue2: number,
  ): Promise<RenteHypothesisColumn> {
    const fiscal = revenuFiscalRenteLpp(avs, lpp);
    const brut = fiscal;
    const impot = await this.taxLikeCouple1(input, revenue1, revenue2);
    return {
      id: "lpp",
      kind: "lpp",
      label: "Rente LPP (réf.)",
      compagnie: null,
      typeLabel: "LPP",
      capitalPlace: null,
      dureeAnnees: null,
      renteAvs: avs,
      renteLppResiduelle: null,
      renteGarantie: lpp,
      participationExcedents: 0,
      revenuBrutEncaisse: brut,
      revenuFiscalImposable: fiscal,
      impotEstv: impot,
      revenuNetApresImpot: impot == null ? null : revenuNetApresImpot(brut, impot),
      ecartNetAnnuelVsLpp: null,
      revenuAnnuelSurCapital: null,
    };
  }

  private async columnOffre(
    input: AnalyseInput,
    row: RenteHypothesisInput,
    index: number,
    avs: number,
    renteLppResiduelle: number,
    age1: number | null,
    age2: number | null,
  ): Promise<RenteHypothesisColumn> {
    const garantie = row.renteGarantieAnnuelle || 0;
    const participation = row.participationExcedentsAnnuelle || 0;
    const fiscal = revenuFiscalImposable({
      type: row.type,
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle,
    });
    const brut = revenuBrutEncaisse({
      renteAvs: avs,
      renteGarantie: garantie,
      participationExcedents: participation,
      renteLppResiduelle,
    });
    const impot = await this.taxOn(input, fiscal, age1, age2);
    const capital = row.capitalPlace || 0;
    return {
      id: row.id || `h-${index + 1}`,
      kind: "hypothese",
      label: (row.compagnie || "").trim() || `Hypothèse ${index + 1}`,
      compagnie: (row.compagnie || "").trim() || null,
      typeLabel: typeLabel(row.type),
      capitalPlace: capital || null,
      dureeAnnees: row.type === "certaine" ? row.dureeAnnees : null,
      renteAvs: avs,
      renteLppResiduelle,
      renteGarantie: garantie,
      participationExcedents: participation,
      revenuBrutEncaisse: brut,
      revenuFiscalImposable: fiscal,
      impotEstv: impot,
      revenuNetApresImpot: impot == null ? null : revenuNetApresImpot(brut, impot),
      ecartNetAnnuelVsLpp: null,
      revenuAnnuelSurCapital:
        capital > 0 ? Math.round((brut / capital) * 10000) / 10000 : null,
      // Recopie du flag conseiller uniquement — aucun recalcul LPP / fiscal.
      recommander: Boolean(row.recommander),
    };
  }
}

export const renteHypothesisService = new RenteHypothesisService();
