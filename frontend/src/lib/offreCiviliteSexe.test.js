import {
  applyCiviliteSexeRules,
  civiliteForGender,
  findCiviliteSexePairs,
  genderKeyFromValue,
  normalizeCrmCiviliteSexe,
  sexeForGender,
  syncLegacyCiviliteSexe,
} from "./offreCiviliteSexe";
import { prefillSchemaPayloadFromClient } from "./demandesOffres";

const pilierSchema = {
  id: "pilier3",
  fields: [
    { type: "section", name: "s1", label: "Preneur d'assurance" },
    { type: "radio", name: "input_100", label: "Civilité", options: ["Madame", "Monsieur"] },
    { type: "text", name: "input_45", label: "Nom" },
    { type: "text", name: "input_46", label: "Prénom" },
    { type: "select", name: "input_47", label: "Sexe", options: ["Masculin", "Féminin"] },
    { type: "radio", name: "input_200", label: "Civilité", options: ["Madame", "Monsieur"] },
    { type: "select", name: "input_201", label: "Sexe", options: ["Masculin", "Féminin"] },
  ],
};

describe("genderKeyFromValue", () => {
  test.each([
    ["Monsieur", "M"],
    ["Madame", "F"],
    ["Homme", "M"],
    ["Femme", "F"],
    ["Masculin", "M"],
    ["Féminin", "F"],
    ["", null],
    ["Autre", null],
  ])("%s → %s", (value, expected) => {
    expect(genderKeyFromValue(value)).toBe(expected);
  });
});

describe("sync civilité → sexe (schéma Masculin/Féminin)", () => {
  test("détecte les paires Civilité + Sexe", () => {
    expect(findCiviliteSexePairs(pilierSchema.fields)).toHaveLength(2);
  });

  test("Monsieur → Masculin et Madame → Féminin", () => {
    const fromMr = applyCiviliteSexeRules(pilierSchema, { input_100: "Monsieur" }, {
      sourceFieldName: "input_100",
    });
    expect(fromMr.input_47).toBe("Masculin");

    const fromMme = applyCiviliteSexeRules(pilierSchema, { input_100: "Madame" }, {
      sourceFieldName: "input_100",
    });
    expect(fromMme.input_47).toBe("Féminin");
  });

  test("Sexe → Civilité en sens inverse", () => {
    const next = applyCiviliteSexeRules(pilierSchema, { input_47: "Féminin" }, {
      sourceFieldName: "input_47",
    });
    expect(next.input_100).toBe("Madame");
  });

  test("fillMissingOnly ne corrige pas une incohérence déjà saisie", () => {
    const payload = { input_100: "Monsieur", input_47: "Féminin" };
    expect(applyCiviliteSexeRules(pilierSchema, payload, { fillMissingOnly: true })).toBe(payload);
  });

  test("comble le sexe manquant depuis la civilité au chargement", () => {
    const next = applyCiviliteSexeRules(pilierSchema, { input_100: "Madame" }, {
      fillMissingOnly: true,
    });
    expect(next.input_47).toBe("Féminin");
  });
});

describe("préremplissage client existant", () => {
  test("Homme CRM → Monsieur + Masculin sur le schéma compagnie", () => {
    const next = prefillSchemaPayloadFromClient(pilierSchema, {}, {
      sexe: "Homme",
      prenom: "Alessandro",
      nom: "COLLORA",
    });
    expect(next.input_100).toBe("Monsieur");
    expect(next.input_47).toBe("Masculin");
    expect(next.input_46).toBe("Alessandro");
    expect(next.input_45).toBe("COLLORA");
  });

  test("ne réécrit pas une civilité déjà saisie (overwrite false)", () => {
    const next = prefillSchemaPayloadFromClient(
      pilierSchema,
      { input_100: "Madame", input_47: "Féminin" },
      { sexe: "Homme" },
      { overwrite: false },
    );
    expect(next.input_100).toBe("Madame");
    expect(next.input_47).toBe("Féminin");
  });

  test("normalizeCrmCiviliteSexe mappe Homme vers les vocabulaires demandés", () => {
    const mapped = normalizeCrmCiviliteSexe(
      { sexe: "Homme" },
      ["Madame", "Monsieur"],
      ["Masculin", "Féminin"],
    );
    expect(mapped).toEqual({
      civilite: "Monsieur",
      sexe: "Masculin",
      gender: "M",
    });
  });
});

describe("wizard legacy Homme/Femme", () => {
  test("Monsieur → Homme et Homme → Monsieur", () => {
    expect(syncLegacyCiviliteSexe("Monsieur", "", "civilite")).toEqual({
      civilite: "Monsieur",
      sexe: "Homme",
    });
    expect(syncLegacyCiviliteSexe("", "Femme", "sexe")).toEqual({
      civilite: "Madame",
      sexe: "Femme",
    });
  });

  test("helpers exposent les libellés attendus", () => {
    expect(civiliteForGender("M", ["Madame", "Monsieur"])).toBe("Monsieur");
    expect(sexeForGender("F", ["Homme", "Femme"])).toBe("Femme");
    expect(sexeForGender("F", ["Masculin", "Féminin"])).toBe("Féminin");
  });
});
