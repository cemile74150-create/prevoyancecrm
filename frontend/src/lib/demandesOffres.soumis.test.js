import { isSoumisCompagnie, soumisCompagnieLabel } from "./demandesOffres";

describe("soumisCompagnie helpers", () => {
  test("labels green / white", () => {
    expect(soumisCompagnieLabel(true)).toBe("🟢 Soumis à la compagnie");
    expect(soumisCompagnieLabel(false)).toBe("⚪ Non soumis à la compagnie");
    expect(soumisCompagnieLabel({ soumis: true })).toBe("🟢 Soumis à la compagnie");
    expect(soumisCompagnieLabel({ soumis: false })).toBe("⚪ Non soumis à la compagnie");
  });

  test("isSoumisCompagnie reads nested and bool", () => {
    expect(isSoumisCompagnie({ soumis: true })).toBe(true);
    expect(isSoumisCompagnie({ soumis: false })).toBe(false);
    expect(isSoumisCompagnie(true)).toBe(true);
    expect(isSoumisCompagnie(null)).toBe(false);
  });
});
