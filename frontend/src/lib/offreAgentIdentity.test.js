import {
  agentIdentityFromUser,
  agentLockedFieldNames,
  classifyAgentField,
  injectAgentIdentity,
  isAgentIdentityField,
  missingFinmaMessage,
  resolveAgentIdentity,
  viewerIsDemandeCreator,
  MISSING_FINMA_MESSAGE,
} from "./offreAgentIdentity";

const menageLike = {
  fields: [
    { name: "input_119", label: "Agent demandeur", type: "section" },
    { name: "input_120.3", label: "Prénom de l'agent", type: "text", required: true },
    { name: "input_120.6", label: "Nom de l'agent", type: "text", required: true },
    { name: "input_121", label: "Votre adresse email", type: "email", required: true },
    { name: "input_122", label: "Votre numéro FINMA", type: "text", required: true },
    {
      name: "input_26",
      label: "Vous recevrez les offres à l'adresse email suivante :",
      type: "email",
      required: true,
    },
    { name: "input_10", label: "Prénom", type: "text" },
  ],
};

describe("offreAgentIdentity", () => {
  test("classifyAgentField maps GF labels", () => {
    expect(classifyAgentField("Prénom de l'agent")).toBe("prenom");
    expect(classifyAgentField("Nom de l'agent")).toBe("nom");
    expect(classifyAgentField("Votre adresse email")).toBe("email");
    expect(classifyAgentField("Votre numéro FINMA")).toBe("finma");
    expect(classifyAgentField("Agent demandeur")).toBeNull();
    expect(
      classifyAgentField("Vous recevrez les offres à l'adresse email suivante :"),
    ).toBeNull();
    expect(classifyAgentField("Prénom")).toBeNull();
  });

  test("isAgentIdentityField / locked names", () => {
    expect(isAgentIdentityField(menageLike.fields[1])).toBe(true);
    expect(isAgentIdentityField(menageLike.fields[0])).toBe(false);
    expect(isAgentIdentityField(menageLike.fields[6])).toBe(false);
    const locked = agentLockedFieldNames(menageLike);
    expect(locked.has("input_120.3")).toBe(true);
    expect(locked.has("input_122")).toBe(true);
    expect(locked.has("input_10")).toBe(false);
    expect(locked.has("input_26")).toBe(false);
  });

  test("injectAgentIdentity autofills and overwrites spoof", () => {
    const identity = agentIdentityFromUser({
      prenom: "Alice",
      nom: "Martin",
      email: "alice@leosoft.ch",
      finma_number: "F-100",
    });
    const next = injectAgentIdentity(
      menageLike,
      {
        "input_120.3": "Hacker",
        "input_120.6": "Fake",
        "input_121": "spoof@evil.test",
        "input_122": "SPOOF",
        "input_10": "ClientPrenom",
      },
      identity,
      { overwrite: true },
    );
    expect(next["input_120.3"]).toBe("Alice");
    expect(next["input_120.6"]).toBe("Martin");
    expect(next["input_121"]).toBe("alice@leosoft.ch");
    expect(next["input_122"]).toBe("F-100");
    expect(next["input_26"]).toBe("alice@leosoft.ch");
    expect(next["input_10"]).toBe("ClientPrenom");
  });

  test("missingFinmaMessage when profile has no FINMA", () => {
    expect(missingFinmaMessage({ finma_number: "" }, menageLike)).toBe(MISSING_FINMA_MESSAGE);
    expect(missingFinmaMessage({ finma_number: "F-1" }, menageLike)).toBeNull();
    expect(missingFinmaMessage({ finma: "F-2" }, menageLike)).toBeNull();
  });

  test("admin viewing another agent's draft keeps that agent identity", () => {
    const sophieDraft = {
      created_by_account_id: "sophie-id",
      agent_prenom: "Sophie",
      agent_nom: "Masi",
      agent_email: "sophie@agencemendes.ch",
      agent_finma: "F-SOPHIE",
      agent_label: "Sophie Masi",
    };
    const admin = {
      account_id: "admin-id",
      prenom: "Cemile",
      nom: "Admin",
      email: "cemile@agencemendes.ch",
      finma_number: "F-ADMIN",
    };
    const ident = resolveAgentIdentity(sophieDraft, admin);
    expect(ident.prenom).toBe("Sophie");
    expect(ident.nom).toBe("Masi");
    expect(ident.email).toBe("sophie@agencemendes.ch");
    expect(ident.finma).toBe("F-SOPHIE");
    expect(viewerIsDemandeCreator(sophieDraft, admin)).toBe(false);
    expect(viewerIsDemandeCreator(sophieDraft, { account_id: "sophie-id" })).toBe(true);
  });

  test("resolveAgentIdentity waits for the loaded demande", () => {
    const admin = { account_id: "admin-id", prenom: "Cemile", nom: "Admin" };
    expect(resolveAgentIdentity(null, admin)).toBeNull();
  });
});
