import { applyNouveauPreneurNames, preneurIdentityFieldNames } from "./demandesOffres";

const schema = {
  id: "pilier3",
  fields: [
    { type: "text", name: "input_agent_prenom", label: "Prénom de l'agent" },
    { type: "text", name: "input_agent_nom", label: "Nom de l'agent" },
    { type: "section", name: "input_4", label: "Preneur d'assurance" },
    { type: "text", name: "input_45", label: "Nom" },
    { type: "text", name: "input_46", label: "Prénom" },
    { type: "text", name: "input_6", label: "Adresse postale" },
    { type: "radio", name: "input_61", label: "Y'a-t-il une deuxième personne à assurer ?" },
    { type: "text", name: "input_62", label: "Nom" },
    { type: "text", name: "input_63", label: "Prénom" },
  ],
};

describe("préremplissage du preneur pour un nouveau client", () => {
  test("cible le nom et le prénom du preneur, pas la deuxième personne ni l'agent", () => {
    expect(preneurIdentityFieldNames(schema)).toEqual({
      nom: "input_45",
      prenom: "input_46",
    });
  });

  test("recopie la saisie immédiatement, y compris quand elle est effacée", () => {
    const filled = applyNouveauPreneurNames(schema, { input_6: "Rue du Rhône" }, {
      prenom: "Cemile",
      nom: "Demirtas",
    });
    expect(filled.input_46).toBe("Cemile");
    expect(filled.input_45).toBe("Demirtas");
    expect(filled.input_6).toBe("Rue du Rhône");
    expect(filled.input_62).toBeUndefined();
    expect(filled.input_63).toBeUndefined();

    const cleared = applyNouveauPreneurNames(schema, filled, { prenom: "", nom: "Demirtas" }, [], {
      prenom: true,
      nom: true,
    });
    expect(cleared.input_46).toBe("");
    expect(cleared.input_45).toBe("Demirtas");
  });

  test("ne recopie qu'un seul champ tant que l'autre n'a pas été saisi", () => {
    const next = applyNouveauPreneurNames(schema, { input_46: "Déjà là" }, {
      prenom: "Cemile",
      nom: "",
    }, [], { prenom: true, nom: false });
    expect(next.input_46).toBe("Cemile");
    expect(next.input_45).toBeUndefined();
  });

  test("conserve un nom ou un prénom modifié dans la section preneur", () => {
    const next = applyNouveauPreneurNames(schema, {
      input_45: "Martin",
      input_46: "Cécile",
    }, {
      prenom: "Cemile",
      nom: "Demirtas",
    }, new Set(["input_46"]));
    expect(next.input_46).toBe("Cécile");
    expect(next.input_45).toBe("Demirtas");
  });

  test("laisse le payload inchangé quand les valeurs sont déjà les mêmes", () => {
    const payload = { input_45: "Demirtas", input_46: "Cemile" };
    expect(applyNouveauPreneurNames(schema, payload, {
      prenom: "Cemile",
      nom: "Demirtas",
    })).toBe(payload);
  });

  test("un changement de type efface le preneur saisi, pas l'agent ni la deuxième personne", () => {
    const next = applyNouveauPreneurNames(schema, {
      input_agent_prenom: "Léa",
      input_agent_nom: "Fictive",
      input_45: "Demirtas",
      input_46: "Cemile",
      input_6: "Rue Fictive 12",
      input_62: "Martin",
      input_63: "Alice",
    }, { prenom: "", nom: "" }, [], { prenom: true, nom: true });
    expect(next.input_46).toBe("");
    expect(next.input_45).toBe("");
    expect(next.input_agent_prenom).toBe("Léa");
    expect(next.input_agent_nom).toBe("Fictive");
    expect(next.input_62).toBe("Martin");
    expect(next.input_63).toBe("Alice");
    expect(next.input_6).toBe("Rue Fictive 12");
  });

  test("reconnaît aussi la section Situation du preneur", () => {
    const situation = {
      fields: [
        { type: "section", name: "s", label: "Situation du preneur d'assurance" },
        { type: "text", name: "input_47", label: "Prénom" },
        { type: "text", name: "input_48", label: "Nom" },
      ],
    };
    const next = applyNouveauPreneurNames(situation, {}, { prenom: "Cemile", nom: "Demirtas" });
    expect(next).toEqual({ input_47: "Cemile", input_48: "Demirtas" });
  });
});
