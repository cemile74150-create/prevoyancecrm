// @ts-nocheck
/** Types du module Analyse de prévoyance (saisie manuelle, sans CRM). */

export type Civilite = "Monsieur" | "Madame";
export type EtatCivil = "Personne vivant seule" | "Marié(e)";

export const RETIREMENT_AGES = [65, 64, 63, 62, 61, 60] as const;
export type RetirementAge = (typeof RETIREMENT_AGES)[number];

/** Taux de conversion LPP Excel (64→60 fixes ; 65 = rente/capital). */
export const LPP_CONVERSION_RATES: Record<RetirementAge, number | null> = {
  65: null,
  64: 0.052,
  63: 0.051,
  62: 0.05,
  61: 0.049,
  60: 0.048,
};

export const TAX_YEAR_DEFAULT = 2025;
/** Confession hardcodée comme dans le Power Query Excel. */
export const CONFESSION_DEFAULT = 5;

export interface LppByAge {
  age: RetirementAge;
  capital: number;
  rente: number;
}

export type ThirdPillarType = "3A" | "3B";

export interface ThirdPillarContract {
  id: string;
  echeance: string; // ISO date
  montant: number;
  police: string;
  prime: number;
  compagnie: string;
  /** 3A imposable, 3B exonéré. Absent = 3A pour les dossiers déjà enregistrés. */
  type?: ThirdPillarType;
}

export type PersonKey = "client1" | "conjoint";

/** Avoir de libre passage (0..N). */
export interface LibrePassageAsset {
  id: string;
  titulaire: PersonKey;
  institution: string;
  montant: number;
  /** Date / période possible de retrait (ISO ou vide). Distincte de l'âge. */
  dateRetraitPossible: string;
  /**
   * Âge de déblocage / retrait prévu. Distinct de la date :
   * les deux peuvent être saisis, aucun n'écrase l'autre.
   */
  ageDeblocage?: number | null;
  /**
   * Conservé pour les dossiers déjà enregistrés.
   * Le formulaire affiche 100 % fixe : le calcul utilise toujours 100 %.
   */
  pctRetire: number;
}

export type CapitalKind = "lpp" | "libre_passage" | "3p" | "autre";

/** Ligne de planification d’un capital (scénario de retraits). */
export interface WithdrawalPlanItem {
  id: string;
  kind: CapitalKind;
  titulaire: PersonKey;
  label: string;
  /** Institution / compagnie (affichage tableau). */
  institution: string;
  montantDisponible: number;
  pctCapital: number;
  /** Échéance / disponibilité du contrat d'origine. Non modifiée dans le tableau. */
  anneeRetraitPrevue: number | null;
  /**
   * Année de retrait du scénario (« 1re possible »).
   * C'est cette année qui alimente les calculs, la projection et le PDF.
   * Vide : on relit l'année prévue pour que les scénarios déjà enregistrés restent lisibles.
   */
  anneePremierePossible: number | null;
  /** Saisie libre conseiller — pas de règle légale inventée. */
  anneeDernierePossible: number | null;
  /** Lien optionnel vers id source (contrat 3P, LP, …). */
  sourceId?: string;
}

/** Scénario nommé de retraits (A regroupé, B réparti, C perso…). */
export interface WithdrawalScenario {
  id: string;
  name: string;
  items: WithdrawalPlanItem[];
  /**
   * Opt-in PDF : seuls les scénarios cochés apparaissent dans le rapport.
   * Défaut false — ne pas inclure automatiquement tous les scénarios de travail.
   */
  includeInReport: boolean;
}

/** Message si comparaison fiscale sur bases de capital différentes. */
export const WITHDRAWAL_COMPARE_WARNING =
  "Les scénarios ne portent pas sur le même montant de capital et ne sont donc pas directement comparables fiscalement.";

/** Défaut % LPP déblocable en capital si non saisi (Excel E16 souvent 100 %). */
export const LPP_PCT_DEBLOCABLE_DEFAULT = 100;
/** Défaut % libre passage retiré si non saisi. */
export const LP_PCT_RETIRE_DEFAULT = 100;

export interface AvsRenteAnticipee {
  id: string;
  /** Âge de perception, distinct de l'âge de retraite souhaité. */
  age: number;
  montantAnnuel: number;
}

export type RenteHypothesisType = "certaine" | "viagere";

/** Offre de rente saisie par le conseiller (pas un barème). */
export interface RenteHypothesisInput {
  id: string;
  type: RenteHypothesisType;
  compagnie: string;
  capitalPlace: number;
  /** Durée en années — rente certaine uniquement. */
  dureeAnnees: number | null;
  renteGarantieAnnuelle: number;
  participationExcedentsAnnuelle: number;
}

export interface RenteHypothesisColumn {
  id: string;
  kind: "lpp" | "hypothese";
  label: string;
  compagnie: string | null;
  typeLabel: string;
  capitalPlace: number | null;
  dureeAnnees: number | null;
  renteAvs: number;
  /**
   * Rente LPP conservée parce que le capital n'est pas déblocable à 100 %.
   * Null sur la colonne de référence, qui garde la rente LPP entière.
   */
  renteLppResiduelle: number | null;
  renteGarantie: number;
  participationExcedents: number;
  revenuBrutEncaisse: number;
  revenuFiscalImposable: number;
  impotEstv: number | null;
  revenuNetApresImpot: number | null;
  /** Uniquement si la colonne LPP est la référence. */
  ecartNetAnnuelVsLpp: number | null;
  /** Revenu encaissé / capital placé. Ce n'est pas un gain en capital. */
  revenuAnnuelSurCapital: number | null;
}

export interface RenteHypothesisComparison {
  ageRetraite: number | null;
  comparerAvecRenteLpp: boolean;
  columns: RenteHypothesisColumn[];
}

export interface PersonInput {
  civilite: Civilite;
  nom: string;
  prenom: string;
  dateNaissance: string; // ISO date
  avsMensuel: number;
  /**
   * Rente AVS à 65 ans, annuelle. Si renseignée, prioritaire
   * comme dans Excel B12 / H12. Les rentes 63/64 ne sont pas déduites.
   */
  avsAnnuel?: number | null;
  /**
   * Case conseiller : le montant AVS saisi vient d'une simulation ACOR.
   * Absent / false sur les dossiers déjà enregistrés — pas de mention PDF.
   */
  avsMontantIssuSimulation?: boolean;
  /** Rentes AVS anticipées saisies explicitement (63, 64, …). */
  avsRentesAnticipees?: AvsRenteAnticipee[];
  lpp: LppByAge[];
  /**
   * % du capital LPP disponible / déblocable en capital (0–100).
   * Saisie libre (100, 50, 25, …). Défaut {@link LPP_PCT_DEBLOCABLE_DEFAULT}.
   * Capital retiré = capital × pct/100 ; solde → rente résiduelle.
   */
  lppPctDeblocable?: number;
  troisiemePilier: ThirdPillarContract[];
  /** Rente pont (conjoint, colonne J Excel) — optionnel. */
  rentePont?: number;
  /**
   * Âge de retraite souhaité de cet assuré (début des rentes).
   * Absent : on reprend l'âge du dossier, pour les analyses déjà enregistrées.
   */
  ageRetraiteSouhaite?: number | null;
}

export interface AnalyseInput {
  villeRecherche: string;
  taxLocationId: number | null;
  taxGroupId: number | null;
  etatCivil: EtatCivil;
  salaireClient1: number;
  salaireConjoint: number;
  fortune: number;
  /** Autres revenus annuels (hors salaire) — option conseiller. */
  autresRevenus?: number;
  taxYear: number;
  client1: PersonInput;
  conjoint: PersonInput | null;
  conseillerNom?: string;
  /**
   * Âge de retraite souhaité (63, 64, 65…). Null = âge applicable au dossier.
   * Distinct de la fin d'activité, de la perception AVS et du retrait LPP.
   */
  ageRetraiteSouhaite?: number | null;
  ageFinActivite?: number | null;
  agePerceptionAvs?: number | null;
  ageRetraitLpp?: number | null;
  /** Colonne de référence « Rente LPP » dans le comparatif d'hypothèses. */
  comparerAvecRenteLpp?: boolean;
  renteHypotheses?: RenteHypothesisInput[];
  /**
   * Rente certaine Vaudoise annuelle (Excel Comparatif C5/D5 vides dans le fichier).
   * Optionnel — si omis, comparatif Vaudoise partiel (fiscal seulement).
   */
  renteVaudoise15?: number | null;
  renteVaudoise20?: number | null;
  /** Avoirs de libre passage (0..N). */
  libresPassages: LibrePassageAsset[];
  /**
   * Scénarios de planification des retraits de capitaux.
   * Page PDF uniquement si ≥1 scénario a includeInReport=true.
   */
  withdrawalScenarios: WithdrawalScenario[];
}

export interface TaxLocation {
  TaxLocationID: number;
  CantonID?: number;
  BfsID?: number;
  BfsName?: string;
  ZipCode?: string;
  City?: string;
  Canton?: string;
}

export interface CapitalTaxResult {
  age: number;
  capital: number;
  gender: number;
  relationship: number;
  taxGroupId: number;
  taxYear: number;
  taxCity: number;
  taxCanton: number;
  taxFed: number;
  taxChurch: number;
  impotTotal: number;
  request: Record<string, unknown>;
  response: unknown;
}

export interface IncomeTaxResult {
  foyer: string;
  age: number;
  taxLocationId: number;
  taxYear: number;
  revenu1: number;
  revenu2: number;
  fortune: number;
  impotRevenuTotal: number;
  impotFederal: number;
  impotCanton: number;
  impotCommune: number;
  impotEglise: number;
  request: Record<string, unknown>;
  response: unknown;
}

export interface PersonComputed {
  ageLegal: number;
  ageLegalLabel: string;
  dateDepart: string;
  avsAnnuel: number;
  /** Capital LPP total à 65 (saisie). */
  capitalLpp65: number;
  /** Rente LPP totale à 65 si tout en rente (saisie). */
  renteLpp65: number;
  /** % déblocable appliqué (0–100). */
  lppPctDeblocable: number;
  /** Capital effectivement retiré = capitalLpp65 × pct/100. */
  capitalLppRetire65: number;
  /** Rente LPP résiduelle après retrait partiel = renteLpp65 × (1 − pct/100). */
  renteLppResiduelle65: number;
  /** Chemin rente : AVS + rente LPP totale. */
  renteTotale65: number;
  total3ePilier: number;
}

export interface LacuneResult {
  salaireAvant: number;
  revenuApres: number;
  lacune: number;
  manquePour80: number;
  tauxRemplacementCible: number;
  tauxRemplacementReel: number;
}

export interface CapitalScenario {
  age: RetirementAge;
  /** Capital soumis à ESTV = capital saisi × % déblocable client 1. */
  capital: number;
  /** Capital LPP brut saisi (avant % déblocable). */
  capitalBrut: number;
  /** Rente LPP résiduelle après retrait partiel. */
  rente: number;
  /** Rente LPP totale saisie (chemin rente). */
  renteTotale: number;
  pctDeblocable: number;
  tauxConversion: number | null;
  impot: number | null;
  net: number | null;
  taxAudit?: CapitalTaxResult;
  error?: string;
}

/**
 * Chemin « retraite avec capital » au niveau foyer :
 * LPP retirées (× %) + libres passages retirés (× %) ; ESTV agrégé par personne.
 */
export interface CapitalPathFoyer {
  capitalBrutTotal: number;
  capitalRetireTotal: number;
  lppRetireTotal: number;
  librePassageRetireTotal: number;
  renteResiduelleTotal: number;
  impot: number | null;
  net: number | null;
  client1: {
    capitalBrut: number;
    capitalRetire: number;
    lppRetire: number;
    lpRetire: number;
    renteResiduelle: number;
    impot: number | null;
  };
  conjoint: {
    capitalBrut: number;
    capitalRetire: number;
    lppRetire: number;
    lpRetire: number;
    renteResiduelle: number;
    impot: number | null;
  } | null;
}

/** Audit d’un appel ESTV capital (agrégat personne × année). */
export interface WithdrawalTaxAudit {
  scenarioId: string;
  scenarioName: string;
  year: number;
  titulaire: PersonKey;
  taxLocationId: number;
  etatCivil: EtatCivil;
  gender: number;
  relationship: number;
  ageAtPayment: number;
  capitauxInclus: Array<{
    kind: CapitalKind;
    label: string;
    montantRetire: number;
  }>;
  montantSoumis: number;
  request: Record<string, unknown>;
  response: unknown;
  impotTotal: number | null;
  error?: string;
}

export interface WithdrawalScenarioResult {
  scenarioId: string;
  scenarioName: string;
  includeInReport: boolean;
  capitalRetireTotal: number;
  impotTotal: number | null;
  capitalNet: number | null;
  audits: WithdrawalTaxAudit[];
  byYear: Array<{
    year: number;
    capitalRetire: number;
    impot: number | null;
    net: number | null;
    lines: Array<{
      titulaire: PersonKey;
      kind: CapitalKind;
      label: string;
      institution: string;
      montantRetire: number;
      contratType?: "3A" | "3B" | null;
      exonere?: boolean;
    }>;
  }>;
}

/**
 * Référence « tout retirer la même année fiscale ».
 * Les 3B restent dans le capital affiché et ne partent pas vers l'ESTV.
 */
export interface WithdrawalSameYearReference {
  year: number;
  sourceScenarioId: string;
  capitalRetire: number;
  impotTotal: number | null;
  capitalNet: number | null;
  audits: WithdrawalTaxAudit[];
}

export interface WithdrawalPlanningResult {
  scenarios: WithdrawalScenarioResult[];
  strategyScenarioId: string | null;
  sameYearReference: WithdrawalSameYearReference | null;
  /** Impôt même année − impôt de la stratégie. ≤ 0 : pas un gain. */
  economieFiscale: number | null;
  /** Écarts d’impôt entre scénarios (sans qualifier « meilleur »). */
  comparisons: Array<{
    fromId: string;
    toId: string;
    fromName: string;
    toName: string;
    deltaImpot: number | null;
    deltaCapitalNet: number | null;
    /** true si capitalRetireTotal identique (base comparable). */
    sameCapitalBase: boolean;
    warning: string | null;
  }>;
}

export interface IncomeScenario {
  foyer: string;
  label: string;
  age: number;
  revenu1: number;
  revenu2: number;
  fortune: number;
  impot: IncomeTaxResult | null;
  error?: string;
}

export interface AnalyseResults {
  computedAt: string;
  client1: PersonComputed;
  conjoint: PersonComputed | null;
  lacune: LacuneResult;
  capitalScenarios: CapitalScenario[];
  /** Agrégat foyer chemin capital (LPP × % + LP × %, ESTV). */
  capitalPathFoyer?: CapitalPathFoyer | null;
  /** Planification multi-scénarios des retraits (si saisie). */
  withdrawalPlanning?: WithdrawalPlanningResult | null;
  incomeScenarios: IncomeScenario[];
  thirdPillarTax?: CapitalTaxResult | null;
  taxLocation: TaxLocation | null;
  timeline?: Record<string, unknown>;
  evolution?: Record<string, unknown>;
  comparative?: Record<string, unknown>;
  renteHypotheses?: RenteHypothesisComparison | null;
  errors: string[];
}

export type AnalyseStatus = "brouillon" | "calculee" | "finalisee";

export interface AnalyseRecord {
  id: string;
  createdAt: string;
  updatedAt: string;
  /** Lien client mock / Try Live (pas CRM prod). */
  clientId: string | null;
  /** Statut workflow hub. */
  status: AnalyseStatus;
  input: AnalyseInput;
  results: AnalyseResults | null;
}


export function emptyLppRows(): LppByAge[] {
  return RETIREMENT_AGES.map((age) => ({ age, capital: 0, rente: 0 }));
}

export function emptyPerson(civilite: Civilite = "Monsieur"): PersonInput {
  return {
    civilite,
    nom: "",
    prenom: "",
    dateNaissance: "",
    avsMensuel: 0,
    avsAnnuel: null,
    avsMontantIssuSimulation: false,
    avsRentesAnticipees: [],
    lpp: emptyLppRows(),
    lppPctDeblocable: LPP_PCT_DEBLOCABLE_DEFAULT,
    troisiemePilier: [],
    rentePont: 0,
  };
}

export function emptyAnalyseInput(): AnalyseInput {
  return {
    villeRecherche: "",
    taxLocationId: null,
    taxGroupId: null,
    etatCivil: "Personne vivant seule",
    salaireClient1: 0,
    salaireConjoint: 0,
    fortune: 0,
    autresRevenus: 0,
    taxYear: TAX_YEAR_DEFAULT,
    client1: emptyPerson("Monsieur"),
    conjoint: null,
    conseillerNom: "",
    renteVaudoise15: null,
    renteVaudoise20: null,
    ageRetraiteSouhaite: null,
    ageFinActivite: null,
    agePerceptionAvs: null,
    ageRetraitLpp: null,
    comparerAvecRenteLpp: false,
    renteHypotheses: [],
    libresPassages: [],
    withdrawalScenarios: [],
  };
}

export function emptyLibrePassage(
  titulaire: PersonKey = "client1",
): LibrePassageAsset {
  return {
    id: `lp-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    titulaire,
    institution: "",
    montant: 0,
    dateRetraitPossible: "",
    ageDeblocage: null,
    pctRetire: LP_PCT_RETIRE_DEFAULT,
  };
}

/** Montant LP retiré. Le pourcentage disponible est fixe à 100 %. */
export function librePassageRetire(lp: LibrePassageAsset): number {
  return Math.round((lp.montant || 0) * 100) / 100;
}
