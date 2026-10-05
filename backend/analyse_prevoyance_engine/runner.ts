/**
 * Point d'entrée Node du moteur existant.
 * Aucun calcul n'est réécrit ici : on appelle les services du module validé.
 */
import { taxCalculationService } from "./services/TaxCalculationService";
import { retirementAnalysisService } from "./services/RetirementAnalysisService";
import { buildReportPayload } from "./report/buildReportPayload";
import { renderPrintableReportHtml } from "./pdf/renderPrintableReportHtml";
import type { AnalyseInput, AnalyseRecord } from "./types";
import { writeFileSync } from "fs";

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function main() {
  const cmd = process.argv[2];
  const raw = (await readStdin()).trim();
  const body = raw ? JSON.parse(raw) : {};

  if (cmd === "locations") {
    const locations = await taxCalculationService.searchLocation({
      search: String(body.q || ""),
      taxYear: body.taxYear ? Number(body.taxYear) : undefined,
    });
    process.stdout.write(JSON.stringify({ locations }));
    return;
  }

  if (cmd === "calculate") {
    const input = body.input as AnalyseInput;
    if (!input) throw new Error("input requis");
    const results = await retirementAnalysisService.run(input);
    process.stdout.write(JSON.stringify({ results }));
    return;
  }

  if (cmd === "html" || cmd === "pdf") {
    const record = body.record as AnalyseRecord;
    if (!record?.input) throw new Error("record requis");
    if (cmd === "html") {
      const html = renderPrintableReportHtml(buildReportPayload(record));
      process.stdout.write(html);
      return;
    }
    const outPath = process.argv[3];
    if (!outPath) throw new Error("chemin PDF requis");
    const { pdfGenerationService } = await import("./services/PdfGenerationService");
    const buf = await pdfGenerationService.generatePdfBuffer(record);
    writeFileSync(outPath, buf);
    process.stdout.write(JSON.stringify({ bytes: buf.length }));
    process.exit(0);
  }

  throw new Error(`commande inconnue: ${cmd}`);
}

main().catch((err) => {
  const message = err instanceof Error ? err.message : String(err);
  process.stderr.write(message);
  process.exit(1);
});
