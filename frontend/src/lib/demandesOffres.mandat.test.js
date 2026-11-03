import {
  MANDAT_GESTION_DOC_CATEGORY,
  demandeRequiresMandatGestion,
  hasMandatGestionDocument,
  isMandatGestionCategory,
  isMandatRequiredCompany,
  mandatGestionMissing,
} from "./demandesOffres";

describe("mandatGestionMissing — Allianz / Vaudoise seulement", () => {
  it("ignore les demandes sans Allianz/Vaudoise", () => {
    const demande = {
      is_professionnelle_offre: true,
      form_type: "entreprise",
      form_category: "Entreprise",
      compagnies: ["Mobilière"],
      documents: [],
    };
    expect(demandeRequiresMandatGestion(demande)).toBe(false);
    expect(mandatGestionMissing(demande, {})).toEqual([]);
  });

  it("exige document et dates si Allianz est sollicitée", () => {
    const demande = {
      is_professionnelle_offre: true,
      form_type: "entreprise",
      compagnies: ["Allianz"],
      documents: [],
    };
    expect(demandeRequiresMandatGestion(demande)).toBe(true);
    const missing = mandatGestionMissing(demande, {});
    expect(missing).toContain("Mandat de gestion (document manquant)");
    expect(missing).toContain("Dates du mandat de gestion (début et fin)");
  });

  it("détecte Vaudoise dans le payload schéma", () => {
    const demande = {
      is_professionnelle_offre: true,
      form_type: "entreprise",
      compagnies: [],
      form_payload: {},
      documents: [],
    };
    expect(
      demandeRequiresMandatGestion(demande, {
        input_99: ["Vaudoise", "Mobilière"],
      }),
    ).toBe(true);
  });

  it("n'impose rien aux particuliers même avec Vaudoise", () => {
    const demande = {
      is_professionnelle_offre: false,
      form_type: "pilier3",
      form_category: "3ème pilier",
      compagnies: ["Vaudoise"],
      documents: [],
    };
    expect(demandeRequiresMandatGestion(demande)).toBe(false);
    expect(mandatGestionMissing(demande, {})).toEqual([]);
  });

  it("rejette une durée < 1 an", () => {
    const demande = {
      is_professionnelle_offre: true,
      compagnies: ["Allianz (Romandie Courtage uniquement)"],
      documents: [{ id: "1", category: MANDAT_GESTION_DOC_CATEGORY }],
    };
    const missing = mandatGestionMissing(demande, {
      mandat_debut: "2026-01-01",
      mandat_fin: "2026-06-01",
    });
    expect(missing).toContain("Durée du mandat inférieure à 1 an");
  });

  it("accepte un mandat conforme", () => {
    const demande = {
      is_professionnelle_offre: true,
      compagnies: ["Vaudoise"],
      documents: [{ id: "1", category: "Mandat" }],
    };
    expect(
      mandatGestionMissing(demande, {
        mandat_debut: "2026-03-01",
        mandat_fin: "2027-03-01",
      }),
    ).toEqual([]);
  });

  it("reconnaît les catégories et compagnies", () => {
    expect(isMandatRequiredCompany("Allianz")).toBe(true);
    expect(isMandatRequiredCompany("Mobilière")).toBe(false);
    expect(isMandatGestionCategory("Mandat de gestion")).toBe(true);
    expect(hasMandatGestionDocument({
      documents: [{ category: "Mandat de gestion" }],
    })).toBe(true);
  });
});
