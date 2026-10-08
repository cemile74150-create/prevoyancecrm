import type {
  AnalyseInput,
  PersonInput,
  RenteHypothesisColumn,
  RenteHypothesisComparison,
  RenteHypothesisInput,
} from "../types";
import { taxCalculationService } from "./TaxCalculationService";
import { lppCalculationService } from "./LPPCalculationService";
import { ageRetraitePersonne } from "../rules/age-retraite";
import {
  revenuBrutEncaisse,
  revenuFiscalImposable,
  revenuFiscalRenteLpp,
  revenuNetApresImpot,
  roundMoney,
} from "../rules/rente-hypotheses";

function avsPrincipale65(person: PersonInput): number {
  if (person.avsAnnuel != null && person.avsAnnuel > 0) return person.avsAnnuel;
  return Math.round((person.avsMensuel || 0) * 12);
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

function lppRentePourAge(person: PersonInput, age: number | null): number {
  const target = age ?? 65;
  const row = (person.lpp || []).find((item) => item.age === target);
  if (row) return row.rente || 0;
  const at65 = (person.lpp || []).find((item) => item.age === 65);
  return at65?.rente || 0;
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

/** Rente LPP non retirée en capital. 100 % déblocable → 0. Couple : somme des deux assurés. */
function renteLppResiduelleFoyer(
  input: AnalyseInput,
  age1: number | null,
  age2: number | null,
  married: boolean,
): number {
  const part = (person: PersonInput, age: number | null) =>
    lppCalculationService.renteResiduelle(
      lppRentePourAge(person, age),
      person.lppPctDeblocable,
    );
  const total =
    part(input.client1, age1) +
    (married && input.conjoint ? part(input.conjoint, age2) : 0);
  return roundMoney(total);
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
    const married = input.etatCivil === "Marié(e)" && !!input.conjoint;
    const avs =
      avsPourAge(input.client1, age1) +
      (married && input.conjoint ? avsPourAge(input.conjoint, age2) : 0);
    const lpp =
      lppRentePourAge(input.client1, age1) +
      (married && input.conjoint ? lppRentePourAge(input.conjoint, age2) : 0);
    const residuelle = renteLppResiduelleFoyer(input, age1, age2, married);

    const columns: RenteHypothesisColumn[] = [];
    if (withLpp) {
      columns.push(await this.columnLpp(input, avs, lpp, age1, age2));
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

  private async columnLpp(
    input: AnalyseInput,
    avs: number,
    lpp: number,
    age1: number | null,
    age2: number | null,
  ): Promise<RenteHypothesisColumn> {
    const fiscal = revenuFiscalRenteLpp(avs, lpp);
    const brut = fiscal;
    const impot = await this.taxOn(input, fiscal, age1, age2);
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
    };
  }
}

export const renteHypothesisService = new RenteHypothesisService();
