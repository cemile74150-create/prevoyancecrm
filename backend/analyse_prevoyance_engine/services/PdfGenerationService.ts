import { chromium, type Browser } from "playwright";
import { PDFDocument } from "pdf-lib";
import { buildReportPayload } from "../report/buildReportPayload";
import type { ReportPayload } from "../report/ReportPayload";
import {
  buildReportPages,
  renderPrintableReportHtml,
  reportCss,
  type ReportPageKind,
} from "../pdf/renderPrintableReportHtml";
import type { AnalyseRecord } from "../types";

let browserPromise: Promise<Browser> | null = null;

async function getBrowser(): Promise<Browser> {
  if (!browserPromise) {
    browserPromise = chromium.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    });
  }
  return browserPromise;
}

/**
 * Génère un PDF A4 mixte portrait/paysage.
 * Source unique : ReportPayload (moteur) — aucun calcul métier ici.
 * Une page HTML = une page PDF (fiable pour orientation mixte).
 */
export class PdfGenerationService {
  buildPayload(record: AnalyseRecord): ReportPayload {
    return buildReportPayload(record);
  }

  renderHtml(record: AnalyseRecord): string {
    return renderPrintableReportHtml(this.buildPayload(record));
  }

  async generatePdfBuffer(record: AnalyseRecord): Promise<Buffer> {
    const payload = this.buildPayload(record);
    const pages = buildReportPages(payload);
    if (!pages.length) throw new Error("Aucune page PDF à générer.");

    const browser = await getBrowser();
    const merged = await PDFDocument.create();

    for (const spec of pages) {
      const html = wrapSinglePage(spec.html, spec.kind);
      const bytes = await this.htmlToPdf(browser, html, spec.kind);
      const doc = await PDFDocument.load(bytes);
      const copied = await merged.copyPages(doc, doc.getPageIndices());
      merged.addPage(copied[0]);
    }

    const out = await merged.save();
    return Buffer.from(out);
  }

  private async htmlToPdf(
    browser: Browser,
    html: string,
    orientation: ReportPageKind,
  ): Promise<Uint8Array> {
    const page = await browser.newPage();
    try {
      await page.setContent(html, { waitUntil: "load", timeout: 30_000 });
      await new Promise((r) => setTimeout(r, 120));
      const pdf = await page.pdf({
        format: "A4",
        landscape: orientation === "landscape",
        printBackground: true,
        preferCSSPageSize: false,
        margin: orientation === "landscape"
          ? { top: "8mm", right: "12mm", bottom: "8mm", left: "22mm" }
          : { top: "12mm", right: "12mm", bottom: "12mm", left: "22mm" },
      });
      return pdf;
    } finally {
      await page.close();
    }
  }
}

function wrapSinglePage(inner: string, kind: ReportPageKind): string {
  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Rapport</title>
<style>${reportCss(kind)}</style>
</head>
<body>
<div class="sheet sheet-${kind}">${inner}</div>
</body>
</html>`;
}

export const pdfGenerationService = new PdfGenerationService();

export async function closePdfBrowser(): Promise<void> {
  const pending = browserPromise;
  browserPromise = null;
  if (!pending) return;
  try {
    const browser = await pending;
    await browser.close();
  } catch {
    /* lancement déjà en échec */
  }
}
