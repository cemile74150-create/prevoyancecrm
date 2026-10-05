// @ts-nocheck
/**
 * Dossier réel HELFER (V3_analyse_prevoyance.xlsx — Fribourg).
 * Valeurs saisies / calculées extraites de Feuille de calcul + caches PQ.
 */
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseInput,
} from "../types";

export const HELFER_EXCEL = {
  ville: "1700 Fribourg",
  taxLocationId: 170_000_000,
  taxYear: 2025,
  etatCivil: "Marié(e)" as const,
  salaireClient1: 93_925,
  salaireConjoint: 72_866,
  fortune: 0,
  /** Comparatif C11 — rente certaine Vaudoise 530k / 20 ans */
  renteVaudoise20: 23_136,
  /** Comparatif D11 — 500k / 20 ans */
  renteVaudoise15: 21_826.8,
  client1: {
    civilite: "Monsieur" as const,
    nom: "HELFER",
    prenom: "Wiliam",
    dateNaissance: "1961-12-13",
    /** Excel B5 forcé 65 (pas formule VLOOKUP) */
    ageLegalExcel: 65,
    dateDepartExcel: "2027-01-01",
    avsMensuel: 1_890,
    avsAnnuel: 24_570,
    lpp65Capital: 350_359,
    lpp65Rente: 21_024,
    /** E16 = 100 % déblocable */
    pctDeblocable: 1,
    troisiemePilier: {
      echeance: "2027-06-01",
      montant: 63_046,
      police: "1210.P0.75084712",
      prime: 2_053,
      compagnie: "Helvetia",
    },
  },
  conjoint: {
    civilite: "Madame" as const,
    nom: "HELFER",
    prenom: "Ariane",
    dateNaissance: "1963-01-20",
    /** Excel G5 forcé 65 ; AVS table → 64.75 ; H10 AVS = 2027-11-01 */
    ageLegalExcel: 65,
    dateDepartExcel: "2028-02-01",
    dateAvsExcel: "2027-11-01",
    ageLegalLabelAffiche: "64 ans et 11 mois", // I5 texte libre
    avsMensuel: 1_965,
    avsAnnuel: 25_545,
    lpp65Capital: 148_678,
    lpp65Rente: 16_057,
    /** J15 — 50 % déblocable Mme */
    pctDeblocable: 0.5,
    librePassage: 1_016.75,
    troisiemePilier: {
      echeance: "2027-01-01",
      montant: 69_454,
      police: "L501448559",
      prime: 6_000,
      compagnie: "Axa",
    },
  },
  /** Totaux Feuille de calcul */
  aggregates: {
    renteTotaleClient1: 45_594, // B29 = B12+C16
    renteTotaleConjoint: 41_602, // B30 = H16+G10*13
    renteTotaleFoyer: 87_196, // B31
    avsTotal: 50_115, // E31 = B12+G12
    salaireAvant: 166_791, // E4+E5
    lacune80: 46_236.8, // D139*80%-D140
    lacune: 79_595, // D139-D140
  },
  /** Impôts capital cachés PQ (Calcul impot Capital) */
  capitalTaxes: {
    lppClient1: { capital: 350_359, impot: 27_912 },
    lppPlus3pClient1: { capital: 632_553.75, impot: 60_647 },
    thirdPillarClient1: { capital: 63_046, impot: 1_097 },
    thirdPillarConjoint: { capital: 69_454, impot: 1_366 },
    /** Mme LPP + libre passage */
    lppConjointPlusLp: { capital: 149_694.75, impot: 5_912 },
    /** Impôt capital chemin « retraite avec capital » = J2+J7 */
    cheminCapital: { capital: 500_053.75, impot: 33_824 },
  },
  /** Impôts revenu cachés PQ */
  incomeTaxes: {
    couple1: {
      revenu1: 45_594,
      /** Cache PQ ≠ B30 feuille (41 602) — écart documenté */
      revenu2Pq: 40_941.48969250947,
      revenu2Feuille: 41_602,
      impotTotal: 10_436,
      impotFederal: 899,
      impotCanton: 5_202,
      impotCommune: 4_335,
      impotEglise: 0,
    },
    couple2: {
      revenu1: 24_570,
      /** Feuille H5 = E30+H16/2 = 33 573.5 ; cache PQ différent */
      revenu2Feuille: 33_573.5,
      revenu2Pq: 33_243.24484625473,
      impotTotal: 4_379,
      impotFederal: 197,
      impotCanton: 2_281,
      impotCommune: 1_901,
      impotEglise: 0,
    },
  },
  /** ANALYSE RETRAITE comparaison rente/capital */
  compare: {
    capitalLppBrut: 500_053.75,
    impotCapital: 33_824,
    capitalNet: 466_229.75,
    renteLppCheminRente: 37_081,
    renteLppResiduelleCapital: 8_028.5, // H16/2
    renteApresImpotRente: 76_760,
    renteApresImpotCapital: 53_764.5,
  },
  /** Evolution : I4 = salaire conjoint (≠ 0) ; L3 figé sur A2 → salaire conjoint permanent */
  evolution: {
    i4SalaireConjoint: 72_866,
    revenuAvant: 166_791,
    revenuApres2027: 118_460, // rente Mr + salaire Mme (L3 bug/formule)
    lacune90_2027: -41_044.4,
  },
} as const;

/** Payload formulaire module pour le dossier HELFER. */
export function helferAnalyseInput(): AnalyseInput {
  const base = emptyAnalyseInput();
  const x = HELFER_EXCEL;
  /**
   * Libre passage G20 = 1 016.75, titulaire conjoint.
   * Métier : % retiré = 100 % (avoir LP typiquement retiré en capital).
   * Excel J7 taxe 100 % LPP Mme + LP malgré J15=50 % — incohérence non reproduite :
   * LPP Mme reste à 50 % ; LP seul à 100 %.
   */
  const lpId = "lp-helfer-g20";
  return {
    ...base,
    villeRecherche: x.ville,
    taxLocationId: x.taxLocationId,
    taxGroupId: x.taxLocationId,
    etatCivil: x.etatCivil,
    salaireClient1: x.salaireClient1,
    salaireConjoint: x.salaireConjoint,
    fortune: x.fortune,
    taxYear: x.taxYear,
    conseillerNom: "",
    renteVaudoise20: x.renteVaudoise20,
    renteVaudoise15: x.renteVaudoise15,
    libresPassages: [
      {
        id: lpId,
        titulaire: "conjoint",
        institution: "Libre passage (Excel G20)",
        montant: x.conjoint.librePassage,
        dateRetraitPossible: x.conjoint.dateDepartExcel,
        pctRetire: 100,
      },
    ],
    withdrawalScenarios: [
      {
        id: "helfer-sc-a",
        name: "A — Regroupé (année départ Mr)",
        includeInReport: true,
        items: [
          {
            id: "a-lpp-w",
            kind: "lpp",
            titulaire: "client1",
            label: "LPP Wiliam",
            institution: "LPP",
            montantDisponible: x.client1.lpp65Capital,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2027,
            anneeDernierePossible: null,
          },
          {
            id: "a-lpp-a",
            kind: "lpp",
            titulaire: "conjoint",
            label: "LPP Ariane",
            institution: "LPP",
            montantDisponible: x.conjoint.lpp65Capital,
            pctCapital: 50,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2028,
            anneeDernierePossible: null,
          },
          {
            id: "a-lp",
            kind: "libre_passage",
            titulaire: "conjoint",
            label: "Libre passage G20",
            institution: "Libre passage (Excel G20)",
            montantDisponible: x.conjoint.librePassage,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2028,
            anneeDernierePossible: null,
            sourceId: lpId,
          },
          {
            id: "a-3p-w",
            kind: "3p",
            titulaire: "client1",
            label: "3P Helvetia",
            institution: "Helvetia",
            montantDisponible: x.client1.troisiemePilier.montant,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2027,
            anneeDernierePossible: null,
            sourceId: "3p-w",
          },
          {
            id: "a-3p-a",
            kind: "3p",
            titulaire: "conjoint",
            label: "3P Axa",
            institution: "Axa",
            montantDisponible: x.conjoint.troisiemePilier.montant,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2027,
            anneeDernierePossible: null,
            sourceId: "3p-a",
          },
        ],
      },
      {
        id: "helfer-sc-b",
        name: "B — Réparti (dates sources)",
        includeInReport: true,
        items: [
          {
            id: "b-lpp-w",
            kind: "lpp",
            titulaire: "client1",
            label: "LPP Wiliam",
            institution: "LPP",
            montantDisponible: x.client1.lpp65Capital,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2027,
            anneeDernierePossible: null,
          },
          {
            id: "b-lpp-a",
            kind: "lpp",
            titulaire: "conjoint",
            label: "LPP Ariane",
            institution: "LPP",
            montantDisponible: x.conjoint.lpp65Capital,
            pctCapital: 50,
            anneeRetraitPrevue: 2028,
            anneePremierePossible: 2028,
            anneeDernierePossible: null,
          },
          {
            id: "b-lp",
            kind: "libre_passage",
            titulaire: "conjoint",
            label: "Libre passage G20",
            institution: "Libre passage (Excel G20)",
            montantDisponible: x.conjoint.librePassage,
            pctCapital: 100,
            anneeRetraitPrevue: 2028,
            anneePremierePossible: 2028,
            anneeDernierePossible: null,
            sourceId: lpId,
          },
          {
            id: "b-3p-w",
            kind: "3p",
            titulaire: "client1",
            label: "3P Helvetia",
            institution: "Helvetia",
            montantDisponible: x.client1.troisiemePilier.montant,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2027,
            anneeDernierePossible: null,
            sourceId: "3p-w",
          },
          {
            id: "b-3p-a",
            kind: "3p",
            titulaire: "conjoint",
            label: "3P Axa",
            institution: "Axa",
            montantDisponible: x.conjoint.troisiemePilier.montant,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2027,
            anneeDernierePossible: null,
            sourceId: "3p-a",
          },
        ],
      },
      {
        id: "helfer-sc-c",
        name: "C — Personnalisé (LPP+LP sans 3P)",
        includeInReport: false,
        items: [
          {
            id: "c-lpp-w",
            kind: "lpp",
            titulaire: "client1",
            label: "LPP Wiliam",
            institution: "LPP",
            montantDisponible: x.client1.lpp65Capital,
            pctCapital: 100,
            anneeRetraitPrevue: 2027,
            anneePremierePossible: 2027,
            anneeDernierePossible: null,
          },
          {
            id: "c-lpp-a",
            kind: "lpp",
            titulaire: "conjoint",
            label: "LPP Ariane",
            institution: "LPP",
            montantDisponible: x.conjoint.lpp65Capital,
            pctCapital: 50,
            anneeRetraitPrevue: 2028,
            anneePremierePossible: 2028,
            anneeDernierePossible: null,
          },
          {
            id: "c-lp",
            kind: "libre_passage",
            titulaire: "conjoint",
            label: "Libre passage G20",
            institution: "Libre passage (Excel G20)",
            montantDisponible: x.conjoint.librePassage,
            pctCapital: 100,
            anneeRetraitPrevue: 2028,
            anneePremierePossible: 2028,
            anneeDernierePossible: null,
            sourceId: lpId,
          },
        ],
      },
    ],
    client1: {
      ...emptyPerson("Monsieur"),
      civilite: x.client1.civilite,
      nom: x.client1.nom,
      prenom: x.client1.prenom,
      dateNaissance: x.client1.dateNaissance,
      avsMensuel: x.client1.avsMensuel,
      avsAnnuel: x.client1.avsAnnuel,
      lppPctDeblocable: Math.round(x.client1.pctDeblocable * 100),
      lpp: [
        { age: 65, capital: x.client1.lpp65Capital, rente: x.client1.lpp65Rente },
        { age: 64, capital: 0, rente: 0 },
        { age: 63, capital: 0, rente: 0 },
        { age: 62, capital: 0, rente: 0 },
        { age: 61, capital: 0, rente: 0 },
        { age: 60, capital: 0, rente: 0 },
      ],
      troisiemePilier: [
        {
          id: "3p-w",
          echeance: x.client1.troisiemePilier.echeance,
          montant: x.client1.troisiemePilier.montant,
          police: x.client1.troisiemePilier.police,
          prime: x.client1.troisiemePilier.prime,
          compagnie: x.client1.troisiemePilier.compagnie,
        },
      ],
    },
    conjoint: {
      ...emptyPerson("Madame"),
      civilite: x.conjoint.civilite,
      nom: x.conjoint.nom,
      prenom: x.conjoint.prenom,
      dateNaissance: x.conjoint.dateNaissance,
      avsMensuel: x.conjoint.avsMensuel,
      avsAnnuel: x.conjoint.avsAnnuel,
      lppPctDeblocable: Math.round(x.conjoint.pctDeblocable * 100),
      lpp: [
        {
          age: 65,
          capital: x.conjoint.lpp65Capital,
          rente: x.conjoint.lpp65Rente,
        },
        { age: 64, capital: 0, rente: 0 },
        { age: 63, capital: 0, rente: 0 },
        { age: 62, capital: 0, rente: 0 },
        { age: 61, capital: 0, rente: 0 },
        { age: 60, capital: 0, rente: 0 },
      ],
      troisiemePilier: [
        {
          id: "3p-a",
          echeance: x.conjoint.troisiemePilier.echeance,
          montant: x.conjoint.troisiemePilier.montant,
          police: x.conjoint.troisiemePilier.police,
          prime: x.conjoint.troisiemePilier.prime,
          compagnie: x.conjoint.troisiemePilier.compagnie,
        },
      ],
      rentePont: 0,
    },
  };
}
