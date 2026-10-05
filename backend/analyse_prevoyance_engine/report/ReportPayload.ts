/**
 * Objet rapport unique — seule source pour preview HTML, contrôle UI et PDF.
 * Aucun calcul métier dans le rendu PDF : tout vient du moteur via ce payload.
 */

export interface ReportMoney {
  value: number | null;
  label?: string;
}

export interface ReportPersonBlock {
  displayName: string;
  civilite: string;
  dateNaissance: string | null;
  dateNaissanceLabel: string;
  salaire: number;
  ageLegalLabel: string;
  dateDepart: string;
  dateDepartLabel: string;
  avsAnnuel: number;
  capitalLpp65: number;
  renteLpp65: number;
  lppPctDeblocable: number;
  capitalLppRetire65: number;
  renteLppResiduelle65: number;
  total3ePilier: number;
  /** Somme des montants de libre passage saisis pour cette personne. */
  librePassage: number;
  hasRentePont: boolean;
  rentePont: number;
}

export interface ReportThirdPillarRow {
  personKey: "client1" | "conjoint";
  personName: string;
  compagnie: string;
  police: string;
  type: string;
  echeance: string | null;
  echeanceLabel: string;
  montant: number;
  prime: number;
  impot: number | null;
  capitalNet: number | null;
}

export interface ReportCapitalScenarioRow {
  age: number;
  capital: number;
  impot: number | null;
  net: number | null;
  rente: number;
}

export interface ReportIncomeScenarioRow {
  foyer: string;
  label: string;
  age: number;
  revenu1: number;
  revenu2: number;
  fortune: number;
  impotTotal: number | null;
  impotFederal: number | null;
  impotCanton: number | null;
  impotCommune: number | null;
}

export interface ReportEvolutionPoint {
  year: number;
  revenu: number;
  lacune90: number;
  phase: "salaire" | "transition" | "rente";
}

export interface ReportTimelineEvent {
  year: number | null;
  label: string;
  amount: number;
  kind: "avs" | "lpp" | "3p" | "lp";
}

export interface ReportVaudoiseColumn {
  id: string;
  label: string;
  capitalAffecte: number;
  renteCertaine: number;
  participationExcedents: number | null;
  partImposable: number;
  impot: number | null;
  renteNette: number | null;
  gainNetVsLpp: number | null;
  recommended?: boolean;
}

export interface ReportPayload {
  meta: {
    generatedAt: string;
    dateRapportLabel: string;
    conseillerNom: string;
    villeRecherche: string;
    etatCivil: string;
    taxLocationId: number | null;
    taxYear: number;
    isCouple: boolean;
    pageCount: number;
  };
  client1: ReportPersonBlock;
  conjoint: ReportPersonBlock | null;
  aggregates: {
    salaireAvant: number;
    revenuApres: number;
    lacune: number;
    manquePour80: number;
    tauxRemplacementReel: number;
    avsTotal: number;
    capitalLppTotal: number;
    renteLppTotal: number;
    /** Capital LPP effectivement retiré (foyer, × % déblocable). */
    capitalLppRetireTotal: number;
    /** Rente LPP résiduelle foyer après retrait partiel. */
    renteLppResiduelleTotal: number;
    total3ePilierFoyer: number;
    /** Somme des libres passages du foyer (montants saisis). */
    librePassageTotal: number;
    /** Capital 2e pilier du foyer + libre passage. Affichage du bandeau de synthèse. */
    capitalLppAvecLibrePassage: number;
    impotCapital65: number | null;
    capitalNet65: number | null;
    impotRevenuCouple1: number | null;
    impotRevenuCouple2: number | null;
    renteApresImpot: number | null;
    renteNetteCheminCapital: number | null;
  };
  capitalScenarios: ReportCapitalScenarioRow[];
  incomeScenarios: ReportIncomeScenarioRow[];
  thirdPillarRows: ReportThirdPillarRow[];
  evolution: {
    cible: number;
    salaireReference: number;
    renteReference: number;
    points: ReportEvolutionPoint[];
  };
  timeline: {
    years: number[];
    events: ReportTimelineEvent[];
    byYear: Record<number, ReportTimelineEvent[]>;
  };
  /** Page Vaudoise uniquement si au moins une rente certaine est renseignée. */
  vaudoise: {
    include: boolean;
    capitalDisponible: number;
    columns: ReportVaudoiseColumn[];
    indicateurs: {
      revenuNetSupplementaire: number | null;
      gainCumul20Ans: number | null;
      economieFiscaleAnnuelle: number | null;
    };
  } | null;
  /** Page des hypothèses de rente saisies (certaine / viagère). */
  hypothesesRente: import("../types").RenteHypothesisComparison | null;
  /**
   * Page 6 optimisation fiscale multi-années (ancien bloc commercial).
   * Remplacée à terme par `withdrawalPlanning` si scénarios saisis.
   * Absent Excel V6 → include=false tant qu’aucun scénario.
   */
  fiscalOptimization: {
    include: boolean;
    reasonHidden: string;
  };
  /**
   * Page « Planification des retraits de capitaux ».
   * include=true uniquement si ≥1 scénario a includeInReport (opt-in).
   */
  withdrawalPlanning: {
    include: boolean;
    scenarios: Array<{
      id: string;
      name: string;
      includeInReport: boolean;
      capitalRetireTotal: number;
      impotTotal: number | null;
      capitalNet: number | null;
      byYear: Array<{
        year: number;
        capitalRetire: number;
        impot: number | null;
        net: number | null;
        lines: Array<{
          titulaire: string;
          kind: string;
          label: string;
          institution: string;
          montantRetire: number;
        }>;
      }>;
      audits: Array<{
        year: number;
        titulaire: string;
        taxLocationId: number;
        etatCivil: string;
        ageAtPayment: number;
        montantSoumis: number;
        impotTotal: number | null;
        request: Record<string, unknown>;
        capitauxInclus: Array<{
          kind: string;
          label: string;
          montantRetire: number;
        }>;
        error?: string;
      }>;
    }>;
    comparisons: Array<{
      fromName: string;
      toName: string;
      deltaImpot: number | null;
      deltaCapitalNet: number | null;
      sameCapitalBase: boolean;
      warning: string | null;
    }>;
  };
  flags: {
    hasThirdPillar: boolean;
    hasRentePont: boolean;
    hasVaudoise: boolean;
    hasHypothesesRente: boolean;
    showConjoint: boolean;
    hasWithdrawalPlanning: boolean;
  };
  /** Empreinte des valeurs clés pour tests de cohérence PDF/preview. */
  coherence: {
    avsClient1: number;
    avsConjoint: number | null;
    capitalLpp65: number;
    renteLpp65: number;
    total3ePilier: number;
    lacune: number;
    salaireAvant: number;
    revenuApres: number;
    impotCapital65: number | null;
    capitalNet65: number | null;
    impotRevenuCouple1: number | null;
  };
}
