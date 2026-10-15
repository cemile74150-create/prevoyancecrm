import { formatChf } from "./mappers";
import type {
  AnalyseInput,
  AnalyseRecord,
  PersonInput,
  RenteHypothesisInput,
} from "./types";

export const NON_RENSEIGNE = "Non renseigné";

export const AUTOSAVE_LABEL = {
  saving: "En cours",
  saved: "Enregistré",
  error: "Erreur",
} as const;

export type AutosavePhase = keyof typeof AUTOSAVE_LABEL | "idle";

export type AnalyseStepId =
  | "client"
  | "assure2"
  | "avs"
  | "lpp"
  | "piliers3"
  | "libresPassages"
  | "retraits"
  | "fortune"
  | "hypotheses";

export interface AnalyseStepDef {
  id: AnalyseStepId;
  n: number;
  label: string;
}

/** 8 étapes du parcours. La fortune reste dans le dossier, hors de ce flux. */
export const ANALYSE_STEPS: AnalyseStepDef[] = [
  { id: "client", n: 1, label: "Client" },
  { id: "assure2", n: 2, label: "Assuré 2" },
  { id: "avs", n: 3, label: "AVS" },
  { id: "lpp", n: 4, label: "LPP" },
  { id: "piliers3", n: 5, label: "3e piliers" },
  { id: "libresPassages", n: 6, label: "Libres passages" },
  { id: "retraits", n: 7, label: "Retraits/Fiscalité" },
  { id: "hypotheses", n: 8, label: "Hypothèses" },
];

export function autosaveLabel(phase: AutosavePhase): string {
  if (phase === "idle") return "";
  return AUTOSAVE_LABEL[phase];
}

export function adjacentStep(
  currentId: AnalyseStepId,
  dir: -1 | 1,
): AnalyseStepId {
  const i = ANALYSE_STEPS.findIndex((s) => s.id === currentId);
  const next = i + dir;
  if (next < 0 || next >= ANALYSE_STEPS.length) return currentId;
  return ANALYSE_STEPS[next].id;
}

function filledText(value: string | null | undefined): boolean {
  return Boolean(String(value || "").trim());
}

function positiveMoney(value: number | null | undefined): boolean {
  return Number(value || 0) > 0;
}

function lppCapital65(person: PersonInput | null | undefined): number {
  if (!person?.lpp) return 0;
  const row = person.lpp.find((r) => r.age === 65);
  return Number(row?.capital || 0);
}

function lppHasSaisie(person: PersonInput | null | undefined): boolean {
  const rows = [
    ...(person?.lpp || []),
    ...(person?.lppAvoirs || []).flatMap((avoir) => avoir.rows || []),
  ];
  return rows.some((row) => positiveMoney(row.capital) || positiveMoney(row.rente));
}

function pillarTotal(person: PersonInput | null | undefined): number {
  return (person?.troisiemePilier || []).reduce(
    (sum, c) => sum + Number(c.montant || 0),
    0,
  );
}

function personLabel(person: PersonInput | null | undefined): string {
  if (!person) return "";
  return `${person.prenom || ""} ${person.nom || ""}`.trim();
}

function moneyOrUnspecified(value: number | null | undefined): string {
  if (!positiveMoney(value)) return NON_RENSEIGNE;
  return formatChf(value);
}

function textOrUnspecified(value: string | null | undefined): string {
  return filledText(value) ? String(value).trim() : NON_RENSEIGNE;
}

export function isStepComplete(
  stepId: AnalyseStepId,
  input: AnalyseInput,
): boolean {
  const married = input.etatCivil === "Marié(e)";
  switch (stepId) {
    case "client":
      return (
        filledText(input.client1.prenom) ||
        filledText(input.client1.nom) ||
        filledText(input.client1.dateNaissance) ||
        filledText(input.villeRecherche)
      );
    case "assure2":
      return (
        married &&
        Boolean(input.conjoint) &&
        (filledText(input.conjoint?.prenom) ||
          filledText(input.conjoint?.nom) ||
          filledText(input.conjoint?.dateNaissance))
      );
    case "avs":
      return (
        positiveMoney(input.client1.avsMensuel) ||
        positiveMoney(input.client1.avsAnnuel) ||
        (married &&
          (positiveMoney(input.conjoint?.avsMensuel) ||
            positiveMoney(input.conjoint?.avsAnnuel)))
      );
    case "lpp":
      return lppHasSaisie(input.client1) || (married && lppHasSaisie(input.conjoint));
    case "piliers3":
      return (
        (input.client1.troisiemePilier || []).length > 0 ||
        (input.conjoint?.troisiemePilier || []).length > 0
      );
    case "libresPassages":
      return (input.libresPassages || []).length > 0;
    case "retraits":
      return (input.withdrawalScenarios || []).length > 0;
    case "fortune":
      return positiveMoney(input.fortune) || positiveMoney(input.autresRevenus);
    case "hypotheses":
      return (
        Boolean(input.comparerAvecRenteLpp) ||
        (input.renteHypotheses || []).some(hypothesisFilled)
      );
    default:
      return false;
  }
}

export function hypothesisFilled(row: RenteHypothesisInput): boolean {
  return Boolean(
    filledText(row.compagnie) ||
      positiveMoney(row.capitalPlace) ||
      positiveMoney(row.renteGarantieAnnuelle) ||
      positiveMoney(row.participationExcedentsAnnuelle),
  );
}

/** Une seule offre recommandée : cocher A décoche B. */
export function withSingleRecommander(
  rows: RenteHypothesisInput[],
  id: string,
  checked: boolean,
): RenteHypothesisInput[] {
  return rows.map((row) => ({
    ...row,
    recommander: checked && row.id === id,
  }));
}

export function recommendedHypothesisId(
  rows: RenteHypothesisInput[] | null | undefined,
): string | null {
  const hit = (rows || []).find((row) => row.recommander);
  return hit?.id ?? null;
}

export interface DossierRecap {
  nom: string;
  conjoint: string;
  communeCanton: string;
  avsMensuelle: string;
  lppTotal: string;
  piliers3: string;
  libresPassages: string;
  scenario: string;
  statut: string;
}

export function recordStatusLabel(status: string | null | undefined): string {
  if (status === "brouillon") return "Brouillon";
  if (status === "calculee") return "Calculée";
  if (status === "finalisee") return "Finalisée";
  if (status === "annulee") return "Annulée";
  return NON_RENSEIGNE;
}

export function buildDossierRecap(
  input: AnalyseInput,
  record: AnalyseRecord | null,
  autosavePhase: AutosavePhase,
  canton?: string | null,
): DossierRecap {
  const married = input.etatCivil === "Marié(e)";
  const lpp =
    lppCapital65(input.client1) +
    (married ? lppCapital65(input.conjoint) : 0);
  const p3 =
    pillarTotal(input.client1) + (married ? pillarTotal(input.conjoint) : 0);
  const lp = (input.libresPassages || []).reduce(
    (sum, item) => sum + Number(item.montant || 0),
    0,
  );
  const avsMensuel =
    Number(input.client1.avsMensuel || 0) +
    (married ? Number(input.conjoint?.avsMensuel || 0) : 0);
  const included = (input.withdrawalScenarios || []).find(
    (s) => s.includeInReport,
  );
  const firstScenario = (input.withdrawalScenarios || [])[0];
  const commune = filledText(input.villeRecherche)
    ? filledText(canton)
      ? `${input.villeRecherche.trim()} · ${String(canton).trim()}`
      : input.villeRecherche.trim()
    : "";
  const auto = autosaveLabel(autosavePhase);
  return {
    nom: textOrUnspecified(personLabel(input.client1)),
    conjoint: married
      ? textOrUnspecified(personLabel(input.conjoint))
      : NON_RENSEIGNE,
    communeCanton: textOrUnspecified(commune),
    avsMensuelle: moneyOrUnspecified(avsMensuel),
    lppTotal: moneyOrUnspecified(lpp),
    piliers3: moneyOrUnspecified(p3),
    libresPassages: moneyOrUnspecified(lp),
    scenario: textOrUnspecified(included?.name || firstScenario?.name),
    statut: auto || recordStatusLabel(record?.status),
  };
}

export function signedDeltaLabel(
  value: number | null | undefined,
  { asGain = false }: { asGain?: boolean } = {},
): { text: string; kind: "plus" | "minus" | "zero" | "na" } {
  if (value == null || Number.isNaN(value)) {
    return { text: "—", kind: "na" };
  }
  if (value === 0) {
    return { text: formatChf(0), kind: "zero" };
  }
  if (value > 0) {
    return { text: `+${formatChf(value)}`, kind: "plus" };
  }
  if (asGain) {
    return { text: "—", kind: "na" };
  }
  return { text: `−${formatChf(Math.abs(value))}`, kind: "minus" };
}
