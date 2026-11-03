// @ts-nocheck
"use client";

import { formatChf } from "@/analyse-prevoyance/lib/mappers";
import {
  applyResumeCapitalTax,
  buildResumePrestationsLpp,
  type ResumeAgeRow,
  type ResumeCapitalTaxLine,
  type ResumeCell,
} from "@/analyse-prevoyance/lib/resumePrestationsLpp";
import type { AnalyseInput } from "@/analyse-prevoyance/lib/types";

function cellText(cell: ResumeCell): string {
  if (cell.kind === "bar") return "";
  return cell.annual ? `${formatChf(cell.amount)}/an` : formatChf(cell.amount);
}

function ageMoney(value: number | null, annual: boolean): string {
  if (value == null) return "—";
  return annual ? `${formatChf(value)}/an` : formatChf(value);
}

function AgeTable({ rows }: { rows: ResumeAgeRow[] }) {
  if (rows.length === 0) return null;
  const range = rows.some((row) => row.renteMaximum != null);
  const pendingTax = rows.every((row) => row.impot == null);
  return (
    <div className="space-y-1 pt-2">
      <p className="text-sm font-semibold text-[#800000]">Capital disponible et rente de 58 à 65 ans</p>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[520px] text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Âge</th>
              <th className="px-3 py-2 text-left font-medium">Capital disponible</th>
              {range ? (
                <>
                  <th className="px-3 py-2 text-left font-medium">Rente minimum</th>
                  <th className="px-3 py-2 text-left font-medium">Rente maximum</th>
                </>
              ) : (
                <th className="px-3 py-2 text-left font-medium">Rente</th>
              )}
              <th className="px-3 py-2 text-left font-medium">Impôt sur le capital</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.age} className="border-t">
                <td className="px-3 py-2">{row.age} ans</td>
                <td className="px-3 py-2">{ageMoney(row.capital, false)}</td>
                {range ? (
                  <>
                    <td className="px-3 py-2">{ageMoney(row.renteMinimum, true)}</td>
                    <td className="px-3 py-2">{ageMoney(row.renteMaximum, true)}</td>
                  </>
                ) : (
                  <td className="px-3 py-2">{ageMoney(row.rente, true)}</td>
                )}
                <td className="px-3 py-2">{ageMoney(row.impot, false)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Capital LPP disponible et rente à chaque âge. L&apos;impôt est estimé sur ce capital, pour cet assuré.
        Le libre passage n&apos;est pas compris.
        {pendingTax ? " Calculez l'analyse pour afficher l'impôt." : ""}
      </p>
    </div>
  );
}

export function ResumePrestationsLppPreview({
  input,
  capitalTax,
}: {
  input: AnalyseInput;
  capitalTax?: ResumeCapitalTaxLine[] | null;
}) {
  const block = buildResumePrestationsLpp(input);
  if (!block) return null;
  applyResumeCapitalTax(block, capitalTax);
  return (
    <section className="space-y-4" data-testid="resume-prestations-lpp">
      {block.showResume ? (
      <h3 className="border-b-2 border-[#800000] pb-1 text-base font-semibold text-[#800000]">
        {block.title}
      </h3>
      ) : null}
      {block.showResume && block.tables.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucune prestation LPP saisie à 65 ans.</p>
      ) : null}
      {block.tables.map((table) => (
        <div key={table.subtitle} className="space-y-1">
          <p className="text-sm font-semibold text-[#800000]">{table.subtitle}</p>
          {block.showResume ? (
            <>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full min-w-[480px] text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      {table.headers.map((header, index) => (
                        <th key={`${header}-${index}`} className="px-3 py-2 text-left font-medium">{header}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {table.rows.map((row, index) => (
                      <tr key={`${row.label}-${index}`} className="border-t">
                        <td className="px-3 py-2">{row.label}{row.mark ? ` ${row.mark}` : ""}</td>
                        {row.cells.map((cell, cellIndex) => (
                          <td key={cellIndex} className="px-3 py-2">
                            {cell.kind === "bar" ? (
                              <span
                                className="block h-5 bg-[linear-gradient(to_bottom_right,transparent_calc(50%-0.5px),#64748b_calc(50%-0.5px),#64748b_calc(50%+0.5px),transparent_calc(50%+0.5px))]"
                                aria-label="Non applicable"
                              />
                            ) : cellText(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                    <tr className="border-t bg-muted/40 font-semibold">
                      <td className="px-3 py-2">Total</td>
                      {table.totals.map((cell, index) => (
                        <td key={index} className="px-3 py-2">
                          {cell.kind === "bar" ? "—" : cellText(cell)}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
              {table.notes.map((note) => (
                <p key={note.mark} className="text-xs text-muted-foreground">
                  {note.mark} {note.text}
                </p>
              ))}
            </>
          ) : null}
          {block.showAges ? <AgeTable rows={table.ages} /> : null}
        </div>
      ))}
    </section>
  );
}
