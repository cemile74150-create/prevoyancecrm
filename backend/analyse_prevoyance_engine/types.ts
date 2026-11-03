/** Types du module Analyse de prévoyance (saisie manuelle, sans CRM). */

export type Civilite = "Monsieur" | "Madame";
export type EtatCivil = "Personne vivant seule" | "Marié(e)";

export const RETIREMENT_AGES = [65, 64, 63, 62, 61, 60, 59, 58] as const;
export type RetirementAge = (typeof RETIREMENT_AGES)[number];

/** Taux de conversion LPP Excel (64→60 fixes ; 65, 59 et 58 = rente saisie). */
export const LPP_CONVERSION_RATES: Record<RetirementAge, number | null> = {
  65: null,
  64: 0.052,
  63: 0.051,
  62: 0.05,
  61: 0.049,
  60: 0.048,
  59: null,
  58: null,
};

export const TAX_YEAR_DEFAULT = 2025;
/** Confession hardcodée comme dans le Power Query Excel. */
export const CONFESSION_DEFAULT = 5;

export type LppCaisseType = "classique" | "etatique";
export type LppRenteUnite = "mensuel" | "annuel";
/**
 * Scénario capital d'une caisse étatique.
 * capital_max : capital maximum et rente réduite saisis.
 * rente_entiere : aucun capital, rente entière conservée.
 * saisi : capital et rente écrits pour cet âge, sans formule.
 */
export type LppRetraitEtatique = "capital_max" | "rente_entiere" | "saisi";

export interface LppByAge {
  age: RetirementAge;
  /** Classique : avoir. Étatique : capital maximum retirable. */
  capital: number;
  /** Classique : rente annuelle. Étatique : rente entière. */
  rente: number;
  /** Caisse étatique : rente réduite si le capital maximum est retiré. */
  renteReduite?: number;
  /** Retrait inférieur au maximum, saisi pour cet âge. */
  capitalSaisi?: number | null;
  /** Rente conservée saisie pour cet âge. */
  renteConserveeSaisie?: number | null;
}

/**
 * Caisse LPP supplémentaire. La caisse principale reste dans PersonInput.lpp
 * pour que les dossiers déjà enregistrés se relisent sans transformation.
 */
export interface LppAvoir {
  id: string;
  institution: string;
  rows: LppByAge[];
  /** Absent = LPP classique, y compris les dossiers déjà enregistrés. */
  type?: LppCaisseType;
  /** Unité de saisie des rentes étatique. Le moteur convertit le mois en année. */
  renteUnite?: LppRenteUnite;
  /**
   * Âge de retrait de cette caisse. Vide = âge de retrait LPP de l'assuré.
   */
  ageRetrait?: number | null;
  /** Scénario capital. Ignoré pour une LPP classique. Défaut capital_max. */
  retraitEtatique?: LppRetraitEtatique;
  /** % disponible propre à cette caisse (0–100). Défaut 100. Classique seulement. */
  pctDeblocable?: number;
}

/** Une caisse après application de sa règle, à l'âge retenu. */
export interface LppAvoirLigne {
  id: string;
  institution: string;
  /** Classique : % disponible. Étatique : 100, le montant est déjà le capital retenu. */
  pct: number;
  type?: LppCaisseType;
  age?: number;
  anneeRetrait?: number | null;
  capital: number;
  /** Rente entière annuelle (scénario 100 % rente). */
  rente: number;
  capitalRetire: number;
  /** Classique : rente × (1 − %). Étatique : rente réduite annuelle. */
  renteResiduelle: number;
}

/** 3A imposable au retrait ; 3B exonéré dans cette analyse. Absent = 3A. */
export type ThirdPillarType = "3A" | "3B";

export function normalizeThirdPillarType(value: unknown): ThirdPillarType {
  const raw = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "");
  return raw === "3B" ? "3B" : "3A";
}

export interface ValeurRachat {
  id?: string;
  date?: string | null;
  montant?: number | null;
}

export interface RentePontInput {
  id?: string;
  ageDebut?: number | null;
  ageFin?: number | null;
  montantAnnuel?: number | null;
}

export interface ThirdPillarContract {
  id: string;
  echeance: string; // ISO date
  montant: number;
  police: string;
  prime: number;
  compagnie: string;
  /** Obligatoire à la saisie. Les dossiers anciens sans type restent des 3A. */
  type?: ThirdPillarType;
  valeursRachat?: ValeurRachat[];
}

export interface ThirdPillarLineResult {
  contractId: string;
  personKey: PersonKey;
  type: ThirdPillarType;
  montant: number;
  impot: number | null;
  exonere: boolean;
  capitalNet: number;
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
  capitalStatut?: "echeance" | "rachat" | "indicatif";
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

/** Une rente dans une hypothèse. Même champs que l'hypothèse à une seule offre. */
export interface RenteOffreSaisie {
  id: string;
  type: RenteHypothesisType;
  compagnie: string;
  capitalPlace: number;
  /** Durée en années — rente certaine uniquement. */
  dureeAnnees: number | null;
  dureeDiffereAnnees?: number | null;
  renteGarantieAnnuelle: number;
  participationExcedentsAnnuelle: number;
}

/** Offre de rente saisie par le conseiller (pas un barème). */
export interface RenteHypothesisInput {
  id: string;
  type: RenteHypothesisType;
  compagnie: string;
  capitalPlace: number;
  /** Durée en années — rente certaine uniquement. */
  dureeAnnees: number | null;
  /**
   * Différé en années, rente certaine ou viagère.
   * Vide, 0 ou absent : la rente démarre tout de suite.
   * Distinct de {@link dureeAnnees}.
   */
  dureeDiffereAnnees?: number | null;
  renteGarantieAnnuelle: number;
  participationExcedentsAnnuelle: number;
  /**
   * Case conseiller « Inclure / Recommander ».
   * Seule une offre cochée reçoit le cadre vert PDF.
   * Absent / false : pas de recommandation automatique.
   * Reste au niveau de l'hypothèse, y compris si plusieurs offres y sont réunies.
   */
  recommander?: boolean;
  /**
   * Deux offres ou plus dans la même hypothèse.
   * Absent, vide ou une seule entrée : les champs ci-dessus restent l'offre unique
   * déjà enregistrée. On ne les recopie pas dans ce tableau.
   */
  offres?: RenteOffreSaisie[];
}

/** Détail d'une offre dans une colonne combinée. Le différé PAX implicite n'est pas recopié dans dureeDiffereAnnees. */
export interface RenteOffreDetail {
  compagnie: string;
  type: RenteHypothesisType;
  capitalPlace: number;
  dureeAnnees: number | null;
  dureeDiffereAnnees: number | null;
  /** Années avant le premier versement : champ saisi, ou 1 an si la note PAX s'applique. */
  differeVersementAnnees: number;
  renteGarantie: number;
  participationExcedents: number;
}

export interface RenteHypothesisColumn {
  id: string;
  kind: "lpp" | "hypothese";
  label: string;
  compagnie: string | null;
  typeLabel: string;
  capitalPlace: number | null;
  dureeAnnees: number | null;
  /** Différé recopié de la saisie. Null : pas de mention dans le tableau. */
  dureeDiffereAnnees?: number | null;
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
  /** Recopie du flag conseiller — pas un choix automatique au revenu max. */
  recommander?: boolean;
  /** Présent seulement si l'hypothèse réunit au moins deux offres. Une colonne. */
  offres?: RenteOffreDetail[];
  /** Les calendriers de versement ne coïncident pas. */
  calendriersDifferents?: boolean;
  /**
   * Année 1 = première année de retraite.
   * Année où toutes les offres de la colonne sont versées ensemble.
   */
  anneeCommune?: number | null;
}

export interface RenteHypothesisComparison {
  ageRetraite: number | null;
  comparerAvecRenteLpp: boolean;
  columns: RenteHypothesisColumn[];
}

/**
 * Cinq rentes mensuelles saisies pour le comparatif 63 / 64 / 65.
 * Null = champ vidé. Absent = pas encore saisi (un repli fiable peut s'afficher).
 */
export interface AvsDepartSaisie {
  mensuel63Avant65?: number | null;
  mensuel63Des65?: number | null;
  mensuel64Avant65?: number | null;
  mensuel64Des65?: number | null;
  mensuel65?: number | null;
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
  /** Comparatif individuel 63 / 64 / 65. N'alimente pas le reste du rapport. */
  avsDepart?: AvsDepartSaisie;
  /**
   * Anticipation choisie pour l'étude : 0 = âge de référence, 1 ou 2 ans.
   * Au-delà de 2 ans n'est pas accepté.
   */
  anticipationAvsAnnees?: 0 | 1 | 2;
  /** La rente AVS est déjà versée. La date et le montant mensuel font foi. */
  avsDejaActive?: boolean;
  /** Date réelle de début de perception, ISO. Indépendante de la fin d'activité. */
  dateDebutRenteAvs?: string | null;
  /** Montant mensuel effectivement perçu. L'annuel = ce montant × 13, une fois. */
  renteAvsPercueMensuelle?: number | null;
  lpp: LppByAge[];
  /**
   * % du capital LPP disponible / déblocable en capital (0–100).
   * Saisie libre (100, 50, 25, …). Défaut {@link LPP_PCT_DEBLOCABLE_DEFAULT}.
   * `lpp[].capital` = avoir total avant retrait. Le % s’applique UNE fois :
   * retirable = avoir × pct/100. Ne pas stocker le retirable dans capital.
   */
  lppPctDeblocable?: number;
  /** Nom de la caisse principale. Vide sur les dossiers déjà enregistrés. */
  lppInstitution?: string;
  /** Absent = LPP classique. */
  lppType?: LppCaisseType;
  lppRenteUnite?: LppRenteUnite;
  lppRetraitEtatique?: LppRetraitEtatique;
  /** Caisses ajoutées. Absent ou vide = la seule caisse historique. */
  lppAvoirs?: LppAvoir[];
  troisiemePilier: ThirdPillarContract[];
  /** Rente pont historique. Les saisies nouvelles passent par rentePonts. */
  rentePont?: number;
  rentePonts?: RentePontInput[];
  /** Âge de retrait LPP personnalisé. Absent : âge de l'onglet Client. */
  ageRetraitLppSouhaite?: number | null;
  /**
   * Âge de retraite souhaité de cet assuré (début des rentes).
   * Absent : on reprend l'âge du dossier, pour les analyses déjà enregistrées.
   */
  ageRetraiteSouhaite?: number | null;
}

export type RevenuAjouteImpotKind = "avs" | "lpp" | "autre";

/** Ligne ajoutée avec + dans l'impôt sur le revenu du comparatif d'offres. */
export interface RevenuAjouteImpot {
  id: string;
  kind: RevenuAjouteImpotKind;
  /** Utilisé quand kind vaut « autre ». */
  libelle?: string;
  montant: number;
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
  /**
   * Comparatif d'offres seulement. Ces montants s'ajoutent à l'assiette
   * de l'impôt sur le revenu de chaque offre. Le rapport de planification
   * ne les lit pas.
   */
  revenusAjoutesImpot?: RevenuAjouteImpot[];
  /**
   * Résumé des prestations à 65 ans, à l'écran et dans le PDF.
   * Absent ou false : ce résumé est masqué. N'agit pas sur le tableau 60–65.
   */
  afficherResumePrestationsLpp?: boolean;
  /**
   * Prestations retraite disponibles de 60 à 65 ans, à l'écran et dans le PDF.
   * Absent ou false : ce tableau est masqué. N'agit pas sur le résumé à 65 ans.
   */
  afficherTableauAgesLpp?: boolean;
  /**
   * Tableau d'anticipation AVS (3 scénarios, âge d'équilibre, graphique) dans le PDF.
   * Absent ou false : la page n'est pas dans le PDF. L'écran de planification ne l'affiche pas.
   */
  afficherTableauAnticipationAvs?: boolean;
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
  /** Rente AVS annuelle de référence : montant saisi, pas la rente réduite. */
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
  /** Date de fin d'activité. Égale à dateDepart tant qu'aucun âge LPP n'est saisi. */
  dateFinActivite?: string;
  ageFinActiviteLabel?: string;
  /** Date de retrait AVS. Égale à dateDepart tant que l'onglet Client n'a pas d'âge. */
  datePerceptionAvs?: string;
  agePerceptionAvsLabel?: string;
  /** Âge du tableau LPP utilisé pour les totaux (58–65). Absent si l'âge n'a pas de ligne. */
  ageLppRetenu?: RetirementAge;
  /** La rente AVS est déjà en cours : une seule rente, depuis datePerceptionAvs. */
  avsDejaActive?: boolean;
  /** Montant d'un autre âge non repris. Vide si la ligne de l'âge choisi est utilisable. */
  lppAvertissement?: string | null;
  /** Détail par caisse. Une seule ligne classique = la caisse historique. */
  lppLignes?: LppAvoirLigne[];
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
      contratType?: ThirdPillarType | null;
      exonere?: boolean;
    }>;
  }>;
}

/**
 * Référence « tout retirer la même année fiscale ».
 * Les 3B sont dans le capital affiché et absents des appels ESTV.
 */
export interface WithdrawalSameYearReference {
  /** Année fiscale unique retenue pour cette référence. */
  year: number;
  /** Scénario coché dont les capitaux ont été regroupés (aucun mélange). */
  sourceScenarioId: string;
  capitalRetire: number;
  impotTotal: number | null;
  capitalNet: number | null;
  audits: WithdrawalTaxAudit[];
}

export interface WithdrawalPlanningResult {
  scenarios: WithdrawalScenarioResult[];
  /**
   * Scénario coché affiché comme stratégie préparée.
   * S'il y en a plusieurs : celui qui a le plus d'années fiscales.
   */
  strategyScenarioId: string | null;
  sameYearReference: WithdrawalSameYearReference | null;
  /**
   * Impôt de la référence même année − impôt de la stratégie.
   * Null si un des deux impôts ESTV manque. ≤ 0 : pas de gain à afficher.
   */
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
  /** Une ligne par contrat saisi. Les 3B n'ont pas d'appel ESTV. */
  thirdPillarLines?: ThirdPillarLineResult[];
  taxLocation: TaxLocation | null;
  timeline?: import("./services/TimelineService").TimelineResult;
  evolution?: import("./services/PostRetirementEvolutionService").EvolutionResult;
  comparative?: import("./services/ComparativeAnalysisService").ComparativeResult;
  renteHypotheses?: RenteHypothesisComparison | null;
  /**
   * Impôt sur le capital LPP disponible à chaque âge du résumé (60–65).
   * Un assuré à la fois. Absent tant que le résumé n'est pas calculé.
   */
  resumeCapitalTax?: Array<{
    personKey: PersonKey;
    age: number;
    capital: number;
    impot: number | null;
  }>;
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
    anticipationAvsAnnees: 0,
    lpp: emptyLppRows(),
    lppPctDeblocable: LPP_PCT_DEBLOCABLE_DEFAULT,
    lppInstitution: "",
    lppType: "classique",
    lppRenteUnite: "annuel",
    lppRetraitEtatique: "capital_max",
    lppAvoirs: [],
    troisiemePilier: [],
    rentePont: 0,
    rentePonts: [],
    ageRetraitLppSouhaite: null,
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
    afficherResumePrestationsLpp: false,
    afficherTableauAgesLpp: false,
    afficherTableauAnticipationAvs: false,
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
