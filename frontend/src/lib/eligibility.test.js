import {
  clientCountLabel,
  eligibilityErrorMessage,
  filterListsByName,
  setListChecked,
} from "./eligibility";

const LISTS = [
  { id: "a", name: "Placement à tranche", checked: false },
  { id: "b", name: "Retraite populaire – rente viagère à taux réduit", checked: true },
];

describe("eligibility helpers", () => {
  it("filters lists by name without accents or case", () => {
    expect(filterListsByName(LISTS, "VIAGERE").map((l) => l.id)).toEqual(["b"]);
    expect(filterListsByName(LISTS, "placement a").map((l) => l.id)).toEqual(["a"]);
    expect(filterListsByName(LISTS, "  ")).toEqual(LISTS);
    expect(filterListsByName(LISTS, "rien")).toEqual([]);
  });

  it("toggles one list and can roll back", () => {
    const checked = setListChecked(LISTS, "a", true);
    expect(checked.map((l) => l.checked)).toEqual([true, true]);
    expect(LISTS[0].checked).toBe(false);
    expect(setListChecked(checked, "a", false)).toEqual(LISTS);
  });

  it("uses the server message, then a network message, then the fallback", () => {
    expect(eligibilityErrorMessage({ response: { data: { detail: "Refusé" } } }, "x")).toBe("Refusé");
    expect(eligibilityErrorMessage(new Error("Network Error"), "x")).toBe("Connexion au serveur impossible. Réessayez.");
    expect(eligibilityErrorMessage({ response: { status: 500, data: {} } }, "Échec")).toBe("Échec");
  });

  it("labels client counts", () => {
    expect(clientCountLabel(0)).toBe("0 client");
    expect(clientCountLabel(1)).toBe("1 client");
    expect(clientCountLabel(12)).toBe("12 clients");
  });
});
