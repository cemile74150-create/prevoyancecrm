import {
  ensurePlanificationFirst,
  isPdfClientDocument,
  isPlanificationDocument,
  moveOrderedId,
  normalizeDocumentIds,
  pickLatestPlanification,
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

  test("identifies planification and ignores comparatif", () => {
    expect(
      isPlanificationDocument({
        title: "Analyse de prévoyance",
        original_filename: "Analyse_prevoyance_Dupont.pdf",
        category: "Analyse de prévoyance",
      }),
    ).toBe(true);
    expect(
      isPlanificationDocument({
        title: "Comparatif des rentes",
        original_filename: "Comparatif_rentes_Dupont.pdf",
        category: "Analyse de prévoyance",
      }),
    ).toBe(false);
  });

  test("keeps only latest planification first without duplicates", () => {
    const docs = [
      {
        id: "old",
        original_filename: "Analyse_prevoyance_old.pdf",
        title: "Analyse de prévoyance",
        category: "Analyse de prévoyance",
        created_at: "2026-01-01T10:00:00+00:00",
      },
      {
        id: "new",
        original_filename: "Analyse_prevoyance_new.pdf",
        title: "Analyse de prévoyance",
        category: "Analyse de prévoyance",
        created_at: "2026-11-18T10:00:00+00:00",
      },
      { id: "o", original_filename: "offre.pdf", category: "Offre", created_at: "2026-02-01" },
      { id: "c", original_filename: "cert.pdf", category: "Certificat LPP", created_at: "2026-02-02" },
    ];
    expect(pickLatestPlanification(docs).id).toBe("new");
    expect(sortDocumentsForRapport(docs).map((d) => d.id)).toEqual(["new", "c", "o"]);
    expect(ensurePlanificationFirst(["o", "old", "c"], docs)).toEqual(["new", "o", "c"]);
  });

  test("prefers planification linked from Planifications sub-tab", () => {
    const linked = {
      id: "linked-pdf",
      original_filename: "scan.pdf",
      title: "Document",
      category: "Autre",
      is_planification: true,
      created_at: "2026-01-01",
    };
    const otherPlan = {
      id: "heuristic",
      original_filename: "Analyse_prevoyance_x.pdf",
      title: "Analyse de prévoyance",
      category: "Analyse de prévoyance",
      created_at: "2026-12-01",
    };
    const docs = [otherPlan, linked, { id: "o", original_filename: "offre.pdf", category: "Offre" }];
    expect(pickLatestPlanification(docs, "linked-pdf").id).toBe("linked-pdf");
    expect(sortDocumentsForRapport(docs, "linked-pdf").map((d) => d.id)[0]).toBe("linked-pdf");
    expect(ensurePlanificationFirst(["o", "heuristic"], docs, "linked-pdf")).toEqual([
      "linked-pdf",
      "o",
    ]);
  });

  test("toggle and reorder keep planification locked first", () => {
    expect(normalizeDocumentIds(["a", "a", ""])).toEqual(["a"]);
    expect(toggleOrderedId(["a"], "b", true)).toEqual(["a", "b"]);
    expect(toggleOrderedId(["plan", "b"], "plan", false, { lockedId: "plan" })).toEqual(["plan", "b"]);
    expect(moveOrderedId(["plan", "a", "b"], "b", "up", { lockedId: "plan" })).toEqual(["plan", "b", "a"]);
    expect(moveOrderedId(["plan", "a", "b"], "plan", "down", { lockedId: "plan" })).toEqual([
      "plan",
      "a",
      "b",
    ]);
    expect(reorderOrderedIds(["plan", "a", "b"], "b", "a", { lockedId: "plan" })).toEqual([
      "plan",
      "b",
      "a",
    ]);
  });
});
