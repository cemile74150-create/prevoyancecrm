/**
 * Résumé des prestations LPP à 65 ans, pour la planification seulement.
 * Les montants sont ceux de la ligne d'âge 65. Aucun barème de caisse n'est recalculé.
 */
import { formatChf } from "../mappers";
import { lppRenteAnnuelle } from "../services/LPPCalculationService";
import type {
  AnalyseInput,
  LppByAge,
  LppCaisseType,
  LppRenteUnite,
  PersonInput,
  PersonKey,
} from "../types";

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

export interface ResumePrestationsLpp {
  title: "Résumé des prestations deuxième pilier";
  tables: ResumePersonTable[];
}

const NOTE_CPEG =
  "CPEG : l'assuré peut demander au maximum 25 % de son avoir de vieillesse LPP sous forme de capital. Le solde est versé sous forme de rente de retraite.";
const NOTE_CPEV =
  "CPEV : l'assuré peut demander une partie de sa pension de retraite sous forme de capital, dans une limite de 50 % de la valeur en capital de la pension de retraite (avec un minimum de CHF 20'000). Le solde est versé sous forme de rente.";
const NOTE_RETRAITES_POPULAIRES =
  "Retraites Populaires : l'assuré peut, selon le règlement applicable, choisir de prendre tout ou partie de son avoir de vieillesse sous forme de capital, ou de le percevoir sous forme de rente.";

const MARKS = ["*", "**", "***"];

interface FundLine {
  institution: string;
  type: LppCaisseType;
  unite: LppRenteUnite | undefined;
  row: LppByAge | null;
}

export function buildResumePrestationsLpp(
  input: Pick<AnalyseInput, "afficherResumePrestationsLpp" | "client1" | "conjoint" | "libresPassages">,
): ResumePrestationsLpp | null {
  if (!input.afficherResumePrestationsLpp) return null;
  const tables = [
    personTable(input.client1, "client1", input, "Assuré 1"),
  ];
  if (input.conjoint) {
    tables.push(personTable(input.conjoint, "conjoint", input, "Assuré 2"));
  }
  return {
    title: "Résumé des prestations deuxième pilier",
    tables: tables.filter((table) => table.rows.length > 0),
  };
}

export function renderResumePrestationsLppHtml(block: ResumePrestationsLpp): string {
  const tables = block.tables.map((table) => renderTable(table)).join("");
  return `<section class="lpp-resume" data-block="resume-prestations-lpp">
  <div class="lpp-resume-title">${esc(block.title)}</div>
  ${tables || `<p class="lpp-resume-note">Aucune prestation LPP saisie à 65 ans.</p>`}
</section>`;
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
  const markByInstitution = new Map(notes.map((note) => [note.institution, note.mark]));
  const rows: ResumeRow[] = funds.map((fund) => ({
    label: `LPP – ${fund.institution || "LPP"}`,
    mark: markByInstitution.get(fund.institution) || "",
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
        ? [amount(capital, false), { kind: "bar" }, { kind: "bar" }]
        : [amount(capital, false), { kind: "bar" }],
    });
  }
  const headers = range
    ? ["", "Capital max", "Rente minimum", "Rente maximum"]
    : ["", "Capital", "Rente"];
  return {
    subtitle: personSubtitle(person, fallback),
    headers,
    rows,
    totals: totalCells(rows),
    notes: notes.map(({ mark, text }) => ({ mark, text })),
  };
}

function fundLines(person: PersonInput): FundLine[] {
  const lines: FundLine[] = [];
  const primary = lineFrom(
    person.lppInstitution || "",
    person.lppType,
    person.lppRenteUnite,
    person.lpp,
  );
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
): FundLine | null {
  const row = (rows || []).find((item) => item.age === 65) ?? null;
  const name = institution.trim();
  const capital = Number(row?.capital) || 0;
  const rente = Number(row?.rente) || 0;
  const reduite = Number(row?.renteReduite) || 0;
  if (!name && capital === 0 && rente === 0 && reduite === 0) return null;
  return {
    institution: name,
    type: type === "etatique" ? "etatique" : "classique",
    unite,
    row,
  };
}

function simpleCells(fund: FundLine): ResumeCell[] {
  return [
    amount(Number(fund.row?.capital) || 0, false),
    amount(lppRenteAnnuelle(fund.row?.rente, fund.unite), true),
  ];
}

function rangeCells(fund: FundLine): ResumeCell[] {
  const capital = amount(Number(fund.row?.capital) || 0, false);
  const maximum = amount(lppRenteAnnuelle(fund.row?.rente, fund.unite), true);
  if (fund.type !== "etatique") {
    return [capital, { kind: "bar" }, maximum];
  }
  const minimumRaw = fund.row?.renteReduite;
  const minimum = lppRenteAnnuelle(minimumRaw, fund.unite);
  const hasMinimum = minimumRaw != null && Number(minimumRaw) > 0;
  return [capital, hasMinimum ? amount(minimum, true) : { kind: "bar" }, maximum];
}

function amount(value: number, annual: boolean): ResumeCell {
  return { kind: "amount", amount: value, annual };
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
    const sum = values.reduce((acc, cell) => acc + cell.amount, 0);
    totals.push({ kind: "amount", amount: sum, annual: values.some((cell) => cell.annual) });
  }
  return totals;
}

function notesFor(funds: FundLine[]): Array<{ institution: string; mark: string; text: string }> {
  const notes: Array<{ institution: string; mark: string; text: string }> = [];
  const seen = new Set<string>();
  for (const fund of funds) {
    const known = knownFund(fund.institution);
    if (!known || seen.has(known.key)) continue;
    seen.add(known.key);
    notes.push({
      institution: fund.institution,
      mark: MARKS[notes.length] || "*".repeat(notes.length + 1),
      text: known.text,
    });
  }
  return notes;
}

function knownFund(institution: string): { key: string; text: string } | null {
  const name = institution
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
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
  const label = [nom, prenom].filter(Boolean).join(" ");
  return label || fallback;
}

function renderTable(table: ResumePersonTable): string {
  const head = table.headers
    .map((header, index) => `<th class="${index === 0 ? "lab" : "val"}">${esc(header)}</th>`)
    .join("");
  const body = table.rows
    .map((row) => {
      const label = `${esc(row.label)}${row.mark ? ` ${esc(row.mark)}` : ""}`;
      const cells = row.cells.map((cell) => renderCell(cell)).join("");
      return `<tr><td class="lab">${label}</td>${cells}</tr>`;
    })
    .join("");
  const totals = table.totals.map((cell) => renderCell(cell)).join("");
  const notes = table.notes
    .map((note) => `<p class="lpp-resume-note">${esc(note.mark)} ${esc(note.text)}</p>`)
    .join("");
  return `<p class="lpp-resume-name">${esc(table.subtitle)}</p>
  <table class="data lpp-resume">
    <tr>${head}</tr>
    ${body}
    <tr class="total"><td class="lab">Total</td>${totals}</tr>
  </table>
  ${notes}`;
}

function renderCell(cell: ResumeCell | undefined): string {
  if (!cell || cell.kind === "bar") return `<td class="val cell-bar"></td>`;
  const text = cell.annual ? `${formatChf(cell.amount)}/an` : formatChf(cell.amount);
  return `<td class="val">${esc(text)}</td>`;
}

function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
