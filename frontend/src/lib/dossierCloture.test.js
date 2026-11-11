import {
  CLOTURE_MOTIF_ABOUTIE,
  CLOTURE_MOTIF_NON_ABOUTIE,
  clotureCardClass,
  clotureMotifLabel,
  computeTauxReussite,
  groupMatchesSearch,
  normalizeClotureMotif,
  todayZurichIso,
} from "./dossierCloture";

describe("dossierCloture", () => {
  test("todayZurichIso is YYYY-MM-DD", () => {
    expect(todayZurichIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  test("normalize and label motifs", () => {
    expect(normalizeClotureMotif("affaire_aboutie")).toBe(CLOTURE_MOTIF_ABOUTIE);
    expect(normalizeClotureMotif("Affaire non aboutie")).toBe(CLOTURE_MOTIF_NON_ABOUTIE);
    expect(clotureMotifLabel(null)).toBe("Non renseigné");
    expect(clotureMotifLabel(CLOTURE_MOTIF_ABOUTIE)).toBe("Affaire aboutie");
  });

  test("card colors for closed dossiers", () => {
    expect(clotureCardClass("Nouveau", CLOTURE_MOTIF_ABOUTIE)).toBe("");
    expect(clotureCardClass("Clôturé", CLOTURE_MOTIF_ABOUTIE)).toContain("emerald");
    expect(clotureCardClass("Clôturé", CLOTURE_MOTIF_NON_ABOUTIE)).toContain("red");
    expect(clotureCardClass("Clôturé", null)).toContain("slate");
  });

  test("taux exclut non renseigné du dénominateur", () => {
    expect(computeTauxReussite(1, 1)).toBe(50);
    expect(computeTauxReussite(0, 0)).toBeNull();
  });

  test("search matches name and reference with filters still independent", () => {
    const group = {
      type: "client",
      numero_dossier: "DOS-42",
      ville: "Lausanne",
      members: [{ prenom: "Éléonore", nom: "Dupont", conseiller: "Alberto Mendes" }],
    };
    expect(groupMatchesSearch(group, "eleonore")).toBe(true);
    expect(groupMatchesSearch(group, "DOS-42")).toBe(true);
    expect(groupMatchesSearch(group, "mendes")).toBe(true);
    expect(groupMatchesSearch(group, "genève")).toBe(false);
    expect(groupMatchesSearch(group, "")).toBe(true);
  });
});
