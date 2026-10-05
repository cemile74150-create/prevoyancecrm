import type {
  AnalyseInput,
  CapitalPathFoyer,
  CapitalScenario,
  IncomeScenario,
  PersonComputed,
} from "../types";

/** Produit commercial Excel Comparatif — capital de référence. */
export const VAUDOISE_CAPITAL_REF = 500_000;

export interface ComparativeColumn {
  id: "lpp" | "vaudoise15" | "vaudoise20";
  label: string;
  renteAvs: number;
  renteLppOuCertaine: number | null;
  partImposable: number;
  impotIccIfd: number | null;
  renteNette: number | null;
  gainNetVsLpp: number | null;
}

export interface ComparativeResult {
  columns: ComparativeColumn[];
  indicateurs: {
    ameliorationRevenuNet: number | null;
    revenuNetSupplementaireAnnuel: number | null;
    economieFiscaleAnnuelle: number | null;
    gainCumul15Ans: number | null;
  };
  vaudoiseRenteManquante: boolean;
  capitalVsRente: {
    /** Capital LPP effectivement retiré (× % déblocable foyer). */
    capital65: number;
    capitalBrut65: number;
    impotCapital65: number | null;
    capitalNet65: number | null;
    renteLppResiduelle: number;
    renteTotale65: number;
    impotRevenuCouple1: number | null;
    impotRevenuCouple2: number | null;
    renteNetteEstimee: number | null;
    renteNetteCheminCapital: number | null;
  };
}

/**
 * Comparatif rente LPP vs capital / Vaudoise.
 * Chemin capital : rente résiduelle selon % déblocable + impôts Couple2.
 */
export class ComparativeAnalysisService {
  build(
    input: AnalyseInput,
    client1: PersonComputed,
    conjoint: PersonComputed | null,
    capitalScenarios: CapitalScenario[],
    incomeScenarios: IncomeScenario[],
    capitalPathFoyer?: CapitalPathFoyer | null,
  ): ComparativeResult {
    const married = input.etatCivil === "Marié(e)" && !!conjoint;
    const avs =
      client1.avsAnnuel + (married ? conjoint!.avsAnnuel : 0);
    const lppRente =
      client1.renteLpp65 + (married ? conjoint!.renteLpp65 : 0);
    const renteResiduelle =
      client1.renteLppResiduelle65 +
      (married ? conjoint!.renteLppResiduelle65 : 0);

    const couple1 = incomeScenarios.find((s) => s.foyer === "Couple1");
    const couple2 = incomeScenarios.find((s) => s.foyer === "Couple2");
    const taxLpp = couple1?.impot?.impotRevenuTotal ?? null;
    const taxCapitalPath = couple2?.impot?.impotRevenuTotal ?? null;

    const renteV15 = input.renteVaudoise15 ?? null;
    const renteV20 = input.renteVaudoise20 ?? null;
    const vaudoiseRenteManquante = renteV15 == null && renteV20 == null;

    const colLpp: ComparativeColumn = {
      id: "lpp",
      label: "Rente LPP (référence)",
      renteAvs: avs,
      renteLppOuCertaine: lppRente,
      partImposable: 1,
      impotIccIfd: taxLpp,
      renteNette:
        taxLpp == null ? null : round2(avs + lppRente - taxLpp),
      gainNetVsLpp: 0,
    };

    const col15 = buildVaudoiseCol(
      "vaudoise15",
      `Vaudoise rente temporaire (${VAUDOISE_CAPITAL_REF.toLocaleString("fr-CH")} CHF) 15 ans`,
      avs,
      renteV15,
      taxCapitalPath,
      colLpp.renteNette,
    );
    const col20 = buildVaudoiseCol(
      "vaudoise20",
      `Vaudoise rente temporaire (${VAUDOISE_CAPITAL_REF.toLocaleString("fr-CH")} CHF) 20 ans`,
      avs,
      renteV20,
      taxCapitalPath,
      colLpp.renteNette,
    );

    const cap65 = capitalScenarios.find((s) => s.age === 65);
    const renteTotale =
      client1.renteTotale65 + (married ? conjoint!.renteTotale65 : 0);

    const capitalRetire =
      capitalPathFoyer?.capitalRetireTotal ??
      client1.capitalLppRetire65 +
        (married ? conjoint!.capitalLppRetire65 : 0);
    const capitalBrut =
      capitalPathFoyer?.capitalBrutTotal ??
      client1.capitalLpp65 + (married ? conjoint!.capitalLpp65 : 0);
    const impotCapital =
      capitalPathFoyer?.impot ?? cap65?.impot ?? null;
    const capitalNet =
      capitalPathFoyer?.net ??
      (impotCapital == null
        ? null
        : round2(capitalRetire - impotCapital));

    const indicateurs = {
      ameliorationRevenuNet:
        col15.renteNette != null &&
        colLpp.renteNette != null &&
        col15.renteNette !== 0
          ? round2((col15.renteNette - colLpp.renteNette) / col15.renteNette)
          : null,
      revenuNetSupplementaireAnnuel: col15.gainNetVsLpp,
      economieFiscaleAnnuelle:
        taxLpp != null && taxCapitalPath != null
          ? round2(taxLpp - taxCapitalPath)
          : null,
      gainCumul15Ans:
        col15.gainNetVsLpp != null ? round2(col15.gainNetVsLpp * 15) : null,
    };

    return {
      columns: [colLpp, col15, col20],
      indicateurs,
      vaudoiseRenteManquante,
      capitalVsRente: {
        capital65: capitalRetire,
        capitalBrut65: capitalBrut,
        impotCapital65: impotCapital,
        capitalNet65: capitalNet,
        renteLppResiduelle: renteResiduelle,
        renteTotale65: renteTotale,
        impotRevenuCouple1: taxLpp,
        impotRevenuCouple2: taxCapitalPath,
        renteNetteEstimee:
          taxLpp == null ? null : round2(renteTotale - taxLpp),
        renteNetteCheminCapital:
          taxCapitalPath == null
            ? null
            : round2(avs + renteResiduelle - taxCapitalPath),
      },
    };
  }
}

function buildVaudoiseCol(
  id: "vaudoise15" | "vaudoise20",
  label: string,
  avs: number,
  renteCertaine: number | null,
  tax: number | null,
  renteNetteLpp: number | null,
): ComparativeColumn {
  const rente = renteCertaine ?? 0;
  const renteNette =
    tax == null || renteCertaine == null
      ? null
      : round2(avs + rente - tax);
  return {
    id,
    label,
    renteAvs: avs,
    renteLppOuCertaine: renteCertaine,
    partImposable: 0,
    impotIccIfd: tax,
    renteNette,
    gainNetVsLpp:
      renteNette != null && renteNetteLpp != null
        ? round2(renteNette - renteNetteLpp)
        : null,
  };
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const comparativeAnalysisService = new ComparativeAnalysisService();
