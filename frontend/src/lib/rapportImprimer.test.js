import {
  isPdfClientDocument,
  moveOrderedId,
  normalizeDocumentIds,
  reorderOrderedIds,
  sortDocumentsForRapport,
  toggleOrderedId,
} from "./rapportImprimer";

describe("rapportImprimer helpers", () => {
  test("detects pdf documents", () => {
    expect(isPdfClientDocument({ original_filename: "a.pdf" })).toBe(true);
    expect(isPdfClientDocument({ content_type: "application/pdf" })).toBe(true);
    expect(isPdfClientDocument({ original_filename: "a.docx" })).toBe(false);
  });

  test("sorts planification before offres", () => {
    const docs = [
      { id: "o", original_filename: "offre.pdf", category: "Offre" },
      { id: "p", original_filename: "plan.pdf", category: "Analyse de prévoyance" },
      { id: "c", original_filename: "cert.pdf", category: "Certificat LPP" },
    ];
    expect(sortDocumentsForRapport(docs).map((d) => d.id)).toEqual(["p", "c", "o"]);
  });

  test("toggle and reorder selection", () => {
    expect(normalizeDocumentIds(["a", "a", ""])).toEqual(["a"]);
    expect(toggleOrderedId(["a"], "b", true)).toEqual(["a", "b"]);
    expect(toggleOrderedId(["a", "b"], "a", false)).toEqual(["b"]);
    expect(moveOrderedId(["a", "b", "c"], "c", "up")).toEqual(["a", "c", "b"]);
    expect(reorderOrderedIds(["a", "b", "c"], "c", "a")).toEqual(["c", "a", "b"]);
  });
});
