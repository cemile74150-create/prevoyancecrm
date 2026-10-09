import {
  desiredRetirementAgeOptions,
  formatLegalAgeLabel,
  getLegalRetirementAge,
} from "./avsAge";

describe("âge légal AVS — convention années + mois/12", () => {
  it("représente 64 ans et 9 mois par 64.75 (Madame 1963)", () => {
    expect(getLegalRetirementAge("Madame", "1963-01-20")).toBe(64.75);
    expect(formatLegalAgeLabel(64.75)).toBe("64 ans et 9 mois");
  });

  it("ajoute l'âge légal fractionnel en tête, sans dupliquer 64", () => {
    const opts = desiredRetirementAgeOptions("Madame", "1963-01-20");
    expect(opts[0]).toEqual({ value: 64.75, label: "64 ans et 9 mois" });
    expect(opts.filter((row) => row.value === 64.75)).toHaveLength(1);
    expect(opts.filter((row) => row.value === 64)).toHaveLength(1);
    expect(opts.map((row) => row.value)).toEqual([64.75, 65, 64, 63, 62, 61, 60]);
  });

  it("n'ajoute pas de doublon si l'âge légal est déjà un entier (65 ans)", () => {
    const opts = desiredRetirementAgeOptions("Monsieur", "1961-12-13");
    expect(opts.filter((row) => row.value === 65)).toHaveLength(1);
    expect(opts.map((row) => row.value)).toEqual([65, 64, 63, 62, 61, 60]);
    expect(formatLegalAgeLabel(65)).toBe("65 ans");
  });

  it("n'ajoute pas de doublon pour Madame née en 1960 (64 ans)", () => {
    const opts = desiredRetirementAgeOptions("Madame", "1960-06-01");
    expect(opts.filter((row) => row.value === 64)).toHaveLength(1);
    expect(opts[0]).toEqual({ value: 65, label: "65 ans" });
  });
});
