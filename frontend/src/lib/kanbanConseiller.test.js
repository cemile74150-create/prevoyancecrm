import {
  NON_ATTRIBUE,
  groupConseillers,
  groupMatchesConseiller,
  kanbanConseillerOptions,
  sameConseiller,
} from "./kanbanConseiller";

const solo = (conseiller) => ({ members: [{ id: "a", conseiller }] });
const famille = (c1, c2) => ({ members: [{ id: "a", conseiller: c1 }, { id: "b", conseiller: c2 }] });

describe("groupConseillers", () => {
  test("retourne le prénom + nom du conseiller", () => {
    expect(groupConseillers(solo("Cemile Yilmaz"))).toEqual(["Cemile Yilmaz"]);
  });

  test("dédoublonne une famille suivie par le même conseiller (casse / accents)", () => {
    expect(groupConseillers(famille("Cémile Yilmaz", "cemile yilmaz"))).toHaveLength(1);
  });

  test("liste les deux conseillers si les conjoints diffèrent", () => {
    expect(groupConseillers(famille("Jean Dupont", "Anna Rossi"))).toEqual(["Anna Rossi", "Jean Dupont"]);
  });

  test("vide si aucun conseiller", () => {
    expect(groupConseillers(solo("  "))).toEqual([]);
    expect(groupConseillers({})).toEqual([]);
  });
});

describe("groupMatchesConseiller", () => {
  test("sans filtre ou « all » : tout passe", () => {
    expect(groupMatchesConseiller(solo(""), null)).toBe(true);
    expect(groupMatchesConseiller(solo("Jean Dupont"), "all")).toBe(true);
  });

  test("filtre insensible à la casse et aux accents", () => {
    expect(groupMatchesConseiller(solo("Cémile Yilmaz"), "cemile yilmaz")).toBe(true);
    expect(groupMatchesConseiller(solo("Jean Dupont"), "Cemile Yilmaz")).toBe(false);
  });

  test("famille : correspond si l'un des membres est suivi par le conseiller", () => {
    expect(groupMatchesConseiller(famille("Jean Dupont", "Anna Rossi"), "Anna Rossi")).toBe(true);
  });

  test("Non attribué : uniquement les dossiers sans conseiller", () => {
    expect(groupMatchesConseiller(solo(""), NON_ATTRIBUE)).toBe(true);
    expect(groupMatchesConseiller(solo("Jean Dupont"), NON_ATTRIBUE)).toBe(false);
  });
});

describe("kanbanConseillerOptions", () => {
  test("fusionne conseillers actifs et conseillers présents sur les dossiers, triés et sans doublon", () => {
    const options = kanbanConseillerOptions(
      ["Jean Dupont", "Cemile Yilmaz"],
      [solo("JEAN DUPONT"), solo("Ancien Conseiller"), solo("")],
    );
    expect(options).toEqual(["Ancien Conseiller", "Cemile Yilmaz", "Jean Dupont"]);
  });

  test("sameConseiller compare via la clé normalisée", () => {
    expect(sameConseiller("Cémile  Yilmaz", "cemile yilmaz")).toBe(true);
  });
});
