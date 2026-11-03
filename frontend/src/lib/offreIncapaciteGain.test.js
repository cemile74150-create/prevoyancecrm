import fs from "fs";
import path from "path";

import {
  incapaciteBlocksNext,
  isFieldVisible,
  omitIncapaciteWhenHidden,
} from "./offreIncapaciteGain";

const schema = JSON.parse(
  fs.readFileSync(
    path.resolve(__dirname, "../../../backend/offre_form_schemas/entreprise_46.json"),
    "utf8",
  ),
);
const detail = schema.fields.find((field) => field.name === "input_83");
const LABEL = "Nature de l'incapacité de gain et depuis quand ?";

describe("LPP — capacité de travail", () => {
  test("Oui masque la nature d'incapacité, Non l'affiche", () => {
    expect(detail.label).toBe(LABEL);
    expect(detail.show_when.rules).toEqual([{ field: "input_62", op: "is", value: "Non" }]);
    expect(isFieldVisible(detail, { input_62: "Oui" })).toBe(false);
    expect(isFieldVisible(detail, { input_62: "Non" })).toBe(true);
    expect(isFieldVisible(detail, {})).toBe(false);
  });

  test("une saisie puis Oui n'est pas conservée ; Non la garde", () => {
    const cleared = omitIncapaciteWhenHidden(schema, {
      input_62: "Oui",
      input_83: "dos depuis 2024",
      input_83__comment: "ancienne précision",
    });
    expect(cleared.input_83).toBe("");
    expect(cleared.input_83__comment).toBe("");

    const kept = omitIncapaciteWhenHidden(schema, {
      input_62: "Non",
      input_83: "dos depuis 2024",
    });
    expect(kept.input_83).toBe("dos depuis 2024");
  });

  test("Suivant n'est bloqué que lorsque Non est coché et que le champ est vide", () => {
    expect(incapaciteBlocksNext(schema.fields, { input_62: "Oui", input_83: "" }, 1)).toBe(false);
    expect(incapaciteBlocksNext(schema.fields, { input_62: "Oui", input_83: "dos depuis 2024" }, 1)).toBe(false);
    expect(incapaciteBlocksNext(schema.fields, { input_62: "Non", input_83: "" }, 1)).toBe(true);
    expect(incapaciteBlocksNext(schema.fields, { input_62: "Non", input_83: "   " }, 1)).toBe(true);
    expect(incapaciteBlocksNext(schema.fields, { input_62: "Non", input_83: "dos depuis 2024" }, 1)).toBe(false);
    expect(incapaciteBlocksNext(schema.fields, { input_62: "Non", input_83: "" }, 2)).toBe(false);
  });
});
