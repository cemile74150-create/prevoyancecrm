/**
 * Tableau comparatif d'offres de rente pour l'onglet dédié.
 * ESTV est appelé sur l'offre seule (revenu) puis sur la fortune seule.
 * Le comparatif du rapport d'analyse n'emprunte pas ce service.
 */
import type { AnalyseInput, RenteHypothesisInput } from "../types";
import { ageRetraitePersonne } from "../rules/age-retraite";
import {
  assietteOffreComparatif,
  fortunesDecroissantes,
  gainNetOffre,
  impotFortuneCapitalNonAffecte,
  libelleRevenuAjoute,
  revenuEncaisseOffre,
  totalImpotFortune,
  totalRevenusAjoutesImpot,
  type OffreRenteType,
} from "../rules/comparatif-rente-offre";
import { roundMoney } from "../rules/rente-hypotheses";
import {
  taxCalculationService,
  type DetailedTaxParams,
} from "./TaxCalculationService";

/** Au-delà, le calendrier ESTV est tronqué pour rester exploitable. */
export const DUREE_FORTUNE_MAX = 40;

export interface FortuneAnnee {
  annee: number;
  fortune: number;
  impotFortune: number | null;
}

export interface ComparatifOffreColumn {
  id: string;
  label: string;
  compagnie: string | null;
  type: OffreRenteType;
  typeLabel: string;
  capitalPlace: number;
  dureeAnnees: number | null;
  renteGarantie: number;
  participationExcedents: number;
  revenuEncaisse: number;
  partImposable: number;
  impotRevenu: number | null;
  revenuNet: number | null;
  /** Revenu net annuel × durée saisie − capital. Null sans durée. */
  gainNet: number | null;
  recommander: boolean;
  /** Null pour une viagère, ou une certaine sans durée. */
  fortuneAnnees: FortuneAnnee[] | null;
  totalImpotFortune: number | null;
  /**
   * Impôt ESTV sur le capital affecté, fortune constante, × durée saisie.
   * Null sans durée. Ce n'est pas le total de la fortune décroissante.
   */
  impotFortuneSiNonAffecte: number | null;
  dureeFortune: number | null;
}

export interface RevenuAjouteAffiche {
  libelle: string;
  montant: number;
}

export interface ComparatifRenteOffreResult {
  columns: ComparatifOffreColumn[];
  /** Mêmes montants pour chaque offre : ils entrent dans l'impôt sur le revenu. */
  revenusAjoutes: RevenuAjouteAffiche[];
  anneesAffichees: number;
  avertissement: string | null;
}

export interface TaxClient {
  calculateDetailedTaxes(
    params: DetailedTaxParams & { foyer?: string },
  ): Promise<{ impotRevenuTotal: number }>;
}

function n(value: unknown): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function offerUsable(row: RenteHypothesisInput): boolean {
  return Boolean(
    (row.compagnie || "").trim() ||
      n(row.capitalPlace) ||
      n(row.renteGarantieAnnuelle) ||
      n(row.participationExcedentsAnnuelle),
  );
}

function offerType(row: RenteHypothesisInput): OffreRenteType {
  return row.type === "viagere" ? "viagere" : "certaine";
}

function resolvedAge(
  person: { ageRetraiteSouhaite?: number | null } | null | undefined,
  dossierAge: number | null | undefined,
): number {
  const age = ageRetraitePersonne(person, dossierAge);
  if (age != null && age > 0) return Math.round(age);
  return 65;
}

async function mapPool<T, R>(
  items: T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const out: R[] = new Array(items.length);
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next;
      next += 1;
      out[index] = await fn(items[index], index);
    }
  });
  await Promise.all(workers);
  return out;
}

export class ComparatifRenteOffreService {
  constructor(private tax: TaxClient = taxCalculationService) {}

  async build(input: AnalyseInput): Promise<ComparatifRenteOffreResult> {
    const hypotheses = (input.renteHypotheses || []).filter(offerUsable);
    const revenusAjoutes = (input.revenusAjoutesImpot || [])
      .map((row) => ({
        libelle: libelleRevenuAjoute(row),
        montant: roundMoney(Math.max(0, n(row.montant))),
      }))
      .filter((row) => row.montant > 0);
    const extra = totalRevenusAjoutesImpot(input.revenusAjoutesImpot);
    if (!input.taxLocationId || !hypotheses.length) {
      return { columns: [], revenusAjoutes, anneesAffichees: 0, avertissement: null };
    }

    const married = input.etatCivil === "Marié(e)";
    const age1 = resolvedAge(input.client1, input.ageRetraiteSouhaite);
    const age2 = married
      ? resolvedAge(input.conjoint, input.ageRetraiteSouhaite)
      : 0;
    const warnings: string[] = [];
    const cache = new Map<string, number>();

    const taxAt = async (
      revenue: number,
      fortune: number,
      age: number,
      foyer: string,
    ): Promise<number | null> => {
      if (revenue <= 0 && fortune <= 0) return 0;
      const key = `${foyer}|${revenue}|${fortune}|${age}`;
      const hit = cache.get(key);
      if (hit != null) return hit;
      try {
        const result = await this.tax.calculateDetailedTaxes({
          foyer,
          taxLocationId: input.taxLocationId as number,
          relationship: married ? 2 : 1,
          age1: age,
          age2: married ? age2 : 0,
          revenue1: revenue,
          revenue2: 0,
          fortune,
          taxYear: input.taxYear,
        });
        const amount = roundMoney(n(result.impotRevenuTotal));
        cache.set(key, amount);
        return amount;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (!warnings.includes(message)) warnings.push(message);
        return null;
      }
    };

    const columns: ComparatifOffreColumn[] = [];
    for (const [index, row] of hypotheses.entries()) {
      columns.push(await this.column(row, index, age1, extra, taxAt, warnings));
    }
    const anneesAffichees = columns.reduce(
      (max, col) => Math.max(max, col.fortuneAnnees?.length || 0),
      0,
    );
    return {
      columns,
      revenusAjoutes,
      anneesAffichees,
      avertissement: warnings[0] || null,
    };
  }

  private async column(
    row: RenteHypothesisInput,
    index: number,
    age1: number,
    extraRevenue: number,
    taxAt: (
      revenue: number,
      fortune: number,
      age: number,
      foyer: string,
    ) => Promise<number | null>,
    warnings: string[],
  ): Promise<ComparatifOffreColumn> {
    const type = offerType(row);
    const garantie = n(row.renteGarantieAnnuelle);
    const participation = n(row.participationExcedentsAnnuelle);
    const capital = n(row.capitalPlace);
    const partImposable = assietteOffreComparatif({
      type,
      renteGarantie: garantie,
      participationExcedents: participation,
    });
    const revenuEncaisse = revenuEncaisseOffre(garantie, participation);
    const impotRevenu = await taxAt(
      roundMoney(partImposable + extraRevenue),
      0,
      age1,
      "comparatif-offre-revenu",
    );
    const company = (row.compagnie || "").trim();
    const revenuNet = impotRevenu == null ? null : roundMoney(revenuEncaisse - impotRevenu);

    let fortuneAnnees: FortuneAnnee[] | null = null;
    let total: number | null = null;
    let dureeFortune: number | null = null;
    let gainNet: number | null = null;
    let impotFortuneSiNonAffecte: number | null = null;
    if (type === "certaine" && row.dureeAnnees != null && n(row.dureeAnnees) > 0) {
      const asked = Math.floor(n(row.dureeAnnees));
      const duree = Math.min(asked, DUREE_FORTUNE_MAX);
      if (asked > DUREE_FORTUNE_MAX) {
        warnings.push(
          `Le calendrier de fortune décroissante est limité à ${DUREE_FORTUNE_MAX} ans. L'impôt fortune si le capital n'est pas affecté utilise la durée saisie (${asked} ans).`,
        );
      }
      const fortunes = fortunesDecroissantes(capital, garantie, duree);
      const impots = await mapPool(fortunes, 4, (fortune, yearIndex) =>
        taxAt(0, fortune, Math.min(age1 + yearIndex, 100), "comparatif-offre-fortune"),
      );
      fortuneAnnees = fortunes.map((fortune, yearIndex) => ({
        annee: yearIndex + 1,
        fortune,
        impotFortune: impots[yearIndex],
      }));
      total = totalImpotFortune(impots);
      dureeFortune = duree;
      // Durée saisie du contrat, y compris au-delà du calendrier plafonné.
      // L'année 1 est déjà l'impôt ESTV sur le capital entier (revenu 0, âge de retraite).
      gainNet = gainNetOffre(revenuNet, asked, capital);
      impotFortuneSiNonAffecte = impotFortuneCapitalNonAffecte(
        fortuneAnnees[0]?.impotFortune ?? null,
        asked,
      );
    }

    return {
      id: row.id || `offre-${index + 1}`,
      label: company || `Offre ${index + 1}`,
      compagnie: company || null,
      type,
      typeLabel: type === "viagere" ? "Rente viagère" : "Rente certaine",
      capitalPlace: capital,
      dureeAnnees: type === "viagere" ? null : row.dureeAnnees ?? null,
      renteGarantie: garantie,
      participationExcedents: participation,
      revenuEncaisse,
      partImposable,
      impotRevenu,
      revenuNet,
      gainNet,
      recommander: Boolean(row.recommander),
      fortuneAnnees,
      totalImpotFortune: total,
      impotFortuneSiNonAffecte,
      dureeFortune,
    };
  }
}

export const comparatifRenteOffreService = new ComparatifRenteOffreService();
