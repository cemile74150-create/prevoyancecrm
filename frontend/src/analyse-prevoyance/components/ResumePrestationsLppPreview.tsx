// @ts-nocheck
"use client";

import { formatChf } from "@/analyse-prevoyance/lib/mappers";
import {
  buildResumePrestationsLpp,
  type ResumeCell,
} from "@/analyse-prevoyance/lib/resumePrestationsLpp";
import type { AnalyseInput } from "@/analyse-prevoyance/lib/types";

function cellText(cell: ResumeCell): string {
  if (cell.kind === "bar") return "";
  return cell.annual ? `${formatChf(cell.amount)}/an` : formatChf(cell.amount);
}

export function ResumePrestationsLppPreview({ input }: { input: AnalyseInput }) {
  const block = buildResumePrestationsLpp(input);
  if (!block) return null;
  return (
    <section className="space-y-4" data-testid="resume-prestations-lpp">
      <h3 className="border-b-2 border-[#800000] pb-1 text-base font-semibold text-[#800000]">
        {block.title}
      </h3>
      {block.tables.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucune prestation LPP saisie à 65 ans.</p>
      ) : block.tables.map((table) => (
        <div key={table.subtitle} className="space-y-1">
          <p className="text-sm font-semibold text-[#800000]">{table.subtitle}</p>
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
        </div>
      ))}
    </section>
  );
}
