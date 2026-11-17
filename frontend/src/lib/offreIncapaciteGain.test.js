import fs from "fs";
import path from "path";

import {
  incapaciteBlocksNext,
  isFieldVisible,
  isRenderableField,
  isSectionVisible,
  omitHiddenFieldValues,
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

  test("réouverture sans réponse parent ne détruit pas une valeur déjà enregistrée", () => {
    const reopened = omitIncapaciteWhenHidden(schema, {
      input_83: "dos depuis 2024",
    });
    expect(reopened.input_83).toBe("dos depuis 2024");
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

describe("show_when générique", () => {
  test("omitHiddenFieldValues efface seulement si le parent a répondu", () => {
    const cleared = omitHiddenFieldValues(schema, {
      input_62: "Oui",
      input_83: "dos depuis 2024",
    });
    expect(cleared.input_83).toBe("");

    const preserved = omitHiddenFieldValues(schema, {
      input_83: "dos depuis 2024",
    });
    expect(preserved.input_83).toBe("dos depuis 2024");
  });

  test("opérateurs numériques > et <", () => {
    const field = {
      name: "input_x",
      show_when: { logic: "all", rules: [{ field: "input_n", op: ">", value: "500000" }] },
    };
    expect(isFieldVisible(field, { input_n: "600000" })).toBe(true);
    expect(isFieldVisible(field, { input_n: "400000" })).toBe(false);
    expect(isFieldVisible(field, { input_n: "" })).toBe(false);
  });

  test("section sans enfant visible est masquée", () => {
    const fields = [
      { name: "input_a", type: "radio", options: ["Oui", "Non"], page: 1 },
      { name: "sec", type: "section", label: "Suite", page: 1 },
      {
        name: "input_b",
        type: "text",
        page: 1,
        show_when: { logic: "all", rules: [{ field: "input_a", op: "is", value: "Oui" }] },
      },
      { name: "sec2", type: "section", label: "Autre", page: 1 },
      { name: "input_c", type: "text", page: 1 },
    ];
    const sec = fields[1];
    expect(isSectionVisible(sec, fields, { input_a: "Non" })).toBe(false);
    expect(isSectionVisible(sec, fields, { input_a: "Oui" })).toBe(true);
    expect(isRenderableField(sec, fields, { input_a: "Non" })).toBe(false);
    expect(isRenderableField(fields[4], fields, {})).toBe(true);
  });
});
