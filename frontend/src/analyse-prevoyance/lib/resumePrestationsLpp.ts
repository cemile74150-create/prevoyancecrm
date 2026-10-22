/**
 * Aperçu écran du résumé LPP à 65 ans.
 * Même règle que backend/analyse_prevoyance_engine/rules/resume-prestations-lpp.ts.
 */
import type {
  AnalyseInput,
  LppByAge,
  LppCaisseType,
  LppRenteUnite,
  PersonInput,
  PersonKey,
} from "@/analyse-prevoyance/lib/types";

export type ResumeCell =
  | { kind: "amount"; amount: number; annual: boolean }
  | { kind: "bar" };

export interface ResumeRow {
  label: string;
  mark: string;
  cells: ResumeCell[];
}

export interface ResumeNote {
  mark: string;
  text: string;
}

export interface ResumePersonTable {
  subtitle: string;
  headers: string[];
  rows: ResumeRow[];
  totals: ResumeCell[];
  notes: ResumeNote[];
}

const NOTE_CPEG =
  "CPEG : l'assuré peut demander au maximum 25 % de son avoir de vieillesse LPP sous forme de capital. Le solde est versé sous forme de rente de retraite.";
const NOTE_CPEV =
  "CPEV : l'assuré peut demander une partie de sa pension de retraite sous forme de capital, dans une limite de 50 % de la valeur en capital de la pension de retraite (avec un minimum de CHF 20'000). Le solde est versé sous forme de rente.";
const NOTE_RETRAITES_POPULAIRES =
  "Retraites Populaires : l'assuré peut, selon le règlement applicable, choisir de prendre tout ou partie de son avoir de vieillesse sous forme de capital, ou de le percevoir sous forme de rente.";
const MARKS = ["*", "**", "***"];

export function buildResumePrestationsLpp(
  input: Pick<AnalyseInput, "afficherResumePrestationsLpp" | "client1" | "conjoint" | "libresPassages">,
): { title: string; tables: ResumePersonTable[] } | null {
  if (!input.afficherResumePrestationsLpp) return null;
  const tables = [personTable(input.client1, "client1", input, "Assuré 1")];
  if (input.conjoint) tables.push(personTable(input.conjoint, "conjoint", input, "Assuré 2"));
  return {
    title: "Résumé des prestations deuxième pilier",
    tables: tables.filter((table) => table.rows.length > 0),
  };
}

function annual(amount: number | null | undefined, unite: LppRenteUnite | undefined): number {
  const value = Number(amount) || 0;
  return unite === "mensuel" ? Math.round(value * 12 * 100) / 100 : Math.round(value * 100) / 100;
}

function personTable(
  person: PersonInput,
  key: PersonKey,
  input: Pick<AnalyseInput, "libresPassages">,
  fallback: string,
): ResumePersonTable {
  const funds = fundLines(person);
  const range = funds.some((fund) => fund.type === "etatique");
  const notes = notesFor(funds);
  const marks = new Map(notes.map((note) => [note.institution, note.mark]));
  const rows: ResumeRow[] = funds.map((fund) => ({
    label: `LPP – ${fund.institution || "LPP"}`,
    mark: marks.get(fund.institution) || "",
    cells: range ? rangeCells(fund) : simpleCells(fund),
  }));
  for (const lp of input.libresPassages || []) {
    if (lp.titulaire !== key) continue;
    const capital = Number(lp.montant) || 0;
    if (capital === 0 && !(lp.institution || "").trim()) continue;
    rows.push({
      label: "Libre passage",
      mark: "",
      cells: range
        ? [{ kind: "amount", amount: capital, annual: false }, { kind: "bar" }, { kind: "bar" }]
        : [{ kind: "amount", amount: capital, annual: false }, { kind: "bar" }],
    });
  }
  return {
    subtitle: personSubtitle(person, fallback),
    headers: range ? ["", "Capital max", "Rente minimum", "Rente maximum"] : ["", "Capital", "Rente"],
    rows,
    totals: totalCells(rows),
    notes: notes.map(({ mark, text }) => ({ mark, text })),
  };
}

function fundLines(person: PersonInput) {
  const lines = [];
  const primary = lineFrom(person.lppInstitution || "", person.lppType, person.lppRenteUnite, person.lpp);
  if (primary) lines.push(primary);
  for (const avoir of person.lppAvoirs || []) {
    const extra = lineFrom(avoir.institution, avoir.type, avoir.renteUnite, avoir.rows);
    if (extra) lines.push(extra);
  }
  return lines;
}

function lineFrom(
  institution: string,
  type: LppCaisseType | undefined,
  unite: LppRenteUnite | undefined,
  rows: LppByAge[] | undefined,
) {
  const row = (rows || []).find((item) => item.age === 65) ?? null;
  const name = institution.trim();
  const capital = Number(row?.capital) || 0;
  const rente = Number(row?.rente) || 0;
  const reduite = Number(row?.renteReduite) || 0;
  if (!name && capital === 0 && rente === 0 && reduite === 0) return null;
  return { institution: name, type: type === "etatique" ? "etatique" as const : "classique" as const, unite, row };
}

function simpleCells(fund: NonNullable<ReturnType<typeof lineFrom>>): ResumeCell[] {
  return [
    { kind: "amount", amount: Number(fund.row?.capital) || 0, annual: false },
    { kind: "amount", amount: annual(fund.row?.rente, fund.unite), annual: true },
  ];
}

function rangeCells(fund: NonNullable<ReturnType<typeof lineFrom>>): ResumeCell[] {
  const capital: ResumeCell = { kind: "amount", amount: Number(fund.row?.capital) || 0, annual: false };
  const maximum: ResumeCell = { kind: "amount", amount: annual(fund.row?.rente, fund.unite), annual: true };
  if (fund.type !== "etatique") return [capital, { kind: "bar" }, maximum];
  const raw = fund.row?.renteReduite;
  const hasMinimum = raw != null && Number(raw) > 0;
  return [capital, hasMinimum ? { kind: "amount", amount: annual(raw, fund.unite), annual: true } : { kind: "bar" }, maximum];
}

function totalCells(rows: ResumeRow[]): ResumeCell[] {
  const width = rows[0]?.cells.length ?? 0;
  const totals: ResumeCell[] = [];
  for (let index = 0; index < width; index += 1) {
    const values = rows
      .map((row) => row.cells[index])
      .filter((cell): cell is Extract<ResumeCell, { kind: "amount" }> => cell?.kind === "amount");
    if (values.length === 0) {
      totals.push({ kind: "bar" });
      continue;
    }
    totals.push({
      kind: "amount",
      amount: values.reduce((acc, cell) => acc + cell.amount, 0),
      annual: values.some((cell) => cell.annual),
    });
  }
  return totals;
}

function notesFor(funds: Array<{ institution: string }>) {
  const notes: Array<{ institution: string; mark: string; text: string }> = [];
  const seen = new Set<string>();
  for (const fund of funds) {
    const known = knownFund(fund.institution);
    if (!known || seen.has(known.key)) continue;
    seen.add(known.key);
    notes.push({ institution: fund.institution, mark: MARKS[notes.length] || "*", text: known.text });
  }
  return notes;
}

function knownFund(institution: string): { key: string; text: string } | null {
  const name = institution.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  if (/\bcpeg\b/.test(name)) return { key: "cpeg", text: NOTE_CPEG };
  if (/\bcpev\b/.test(name)) return { key: "cpev", text: NOTE_CPEV };
  if (name.includes("retraite populaire") || name.includes("retraites populaires")) {
    return { key: "rp", text: NOTE_RETRAITES_POPULAIRES };
  }
  return null;
}

function personSubtitle(person: PersonInput, fallback: string): string {
  const nom = (person.nom || "").trim().toLocaleUpperCase("fr-CH");
  const prenom = (person.prenom || "").trim();
  return [nom, prenom].filter(Boolean).join(" ") || fallback;
}
