import { MAX_SIGNATURE_FILES, mergeSignatureFiles, signatureEntries } from "./offreSignee";

describe("signatureEntries", () => {
  it("ignore une offre non signée", () => {
    expect(signatureEntries(null)).toEqual([]);
    expect(signatureEntries({ signee: false, commentaire: "x" })).toEqual([]);
  });

  it("liste la signature puis les compléments", () => {
    const entries = signatureEntries({
      signee: true,
      commentaire: "Signé en agence",
      signed_at: "2026-11-10T10:00:00Z",
      signed_by: "Emeric",
      documents: [{ id: "p1", original_filename: "prop.pdf" }, { id: "x1", original_filename: "id.png" }],
      complements: [
        { id: "c1", at: "2026-11-11T10:00:00Z", by: "Emeric", commentaire: "IBAN", documents: [] },
        { id: "c2", commentaire: "", documents: [] },
      ],
    });
    expect(entries.map((e) => e.key)).toEqual(["initial", "c1"]);
    expect(entries[0].documents).toHaveLength(2);
    expect(entries[0].initial).toBe(true);
    expect(entries[1].commentaire).toBe("IBAN");
  });

  it("reprend document_id des signatures anciennes", () => {
    const entries = signatureEntries({ signee: true, document_id: "old", document_category: "Proposition signée" });
    expect(entries).toHaveLength(1);
    expect(entries[0].documents[0]).toEqual({ id: "old", original_filename: "Proposition signée" });
  });
});

describe("mergeSignatureFiles", () => {
  it("évite les doublons et respecte la limite", () => {
    const a = { name: "a.pdf", size: 1 };
    const b = { name: "b.pdf", size: 2 };
    expect(mergeSignatureFiles([a], [a, b])).toEqual([a, b]);
    const many = Array.from({ length: MAX_SIGNATURE_FILES + 3 }, (_, i) => ({ name: `${i}.pdf`, size: i }));
    expect(mergeSignatureFiles([], many)).toHaveLength(MAX_SIGNATURE_FILES);
  });
});
