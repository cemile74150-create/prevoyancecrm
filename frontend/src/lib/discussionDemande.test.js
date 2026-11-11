import fs from "fs";
import path from "path";
import {
  DISCUSSION_ACCEPT,
  MAX_DISCUSSION_FILES,
  canSendDiscussion,
  fileExtension,
  mergeDiscussionFiles,
} from "./discussionDemande";

const root = path.resolve(__dirname, "..");
const src = (rel) => fs.readFileSync(path.join(root, rel), "utf8");

describe("discussionDemande helpers", () => {
  it("valide l'envoi texte ou pièces", () => {
    expect(canSendDiscussion("", [])).toBe(false);
    expect(canSendDiscussion("  ", [])).toBe(false);
    expect(canSendDiscussion("Bonjour", [])).toBe(true);
    expect(canSendDiscussion("", [{ name: "a.pdf", size: 1 }])).toBe(true);
  });

  it("filtre types, taille et doublons", () => {
    expect(fileExtension("Scan.PDF")).toBe("pdf");
    const a = { name: "a.pdf", size: 10 };
    const b = { name: "b.png", size: 20 };
    const first = mergeDiscussionFiles([], [a, a, b]);
    expect(first.files).toEqual([a, b]);
    expect(first.errors).toEqual([]);

    const bad = mergeDiscussionFiles([], [{ name: "x.exe", size: 1 }]);
    expect(bad.files).toEqual([]);
    expect(bad.errors[0]).toMatch(/type non autorisé/);

    const huge = mergeDiscussionFiles([], [{ name: "big.pdf", size: 21 * 1024 * 1024 }]);
    expect(huge.files).toEqual([]);
    expect(huge.errors[0]).toMatch(/volumineux/);

    const many = Array.from({ length: MAX_DISCUSSION_FILES + 2 }, (_, i) => ({
      name: `${i}.pdf`,
      size: i,
    }));
    const capped = mergeDiscussionFiles([], many);
    expect(capped.files).toHaveLength(MAX_DISCUSSION_FILES);
    expect(capped.errors.some((e) => /Maximum/.test(e))).toBe(true);
  });

  it("UI fil expose trombone, accept et téléchargement", () => {
    const ui = src("components/DiscussionDemande.js");
    expect(ui).toMatch(/Paperclip/);
    expect(ui).toMatch(/discussion-joindre/);
    expect(ui).toMatch(/DISCUSSION_ACCEPT/);
    expect(ui).toMatch(/openAuthenticatedBlob/);
    expect(ui).toMatch(/demandes-offres\/documents\/\$\{/);
    expect(ui).toMatch(/FormData/);
    expect(ui).toMatch(/discussion-pj-pending/);
    expect(ui).toMatch(/discussion-message-docs/);
    expect(DISCUSSION_ACCEPT).toContain(".pdf");
  });
});
