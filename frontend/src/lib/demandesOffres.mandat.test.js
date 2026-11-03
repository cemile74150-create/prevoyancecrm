import {
  MANDAT_GESTION_DOC_CATEGORY,
  hasMandatGestionDocument,
  isMandatGestionCategory,
  mandatGestionMissing,
} from "./demandesOffres";

describe("mandatGestionMissing", () => {
  it("ignore les demandes sans flag pro", () => {
    expect(mandatGestionMissing({ form_type: "pilier3" }, {})).toEqual([]);
  });

  it("exige document et dates pour une demande pro", () => {
    const demande = { requires_mandat_gestion: true, documents: [] };
    const missing = mandatGestionMissing(demande, {});
    expect(missing).toContain("Mandat de gestion (document manquant)");
    expect(missing).toContain("Dates du mandat de gestion (début et fin)");
  });

  it("rejette une durée < 1 an", () => {
    const demande = {
      requires_mandat_gestion: true,
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
      requires_mandat_gestion: true,
      documents: [{ id: "1", category: "Mandat" }],
    };
    const missing = mandatGestionMissing(demande, {
      mandat_debut: "2026-03-01",
      mandat_fin: "2027-03-01",
    });
    expect(missing).toEqual([]);
  });

  it("reconnaît les catégories mandat", () => {
    expect(isMandatGestionCategory("Mandat de gestion")).toBe(true);
    expect(isMandatGestionCategory("Mandat")).toBe(true);
    expect(isMandatGestionCategory("Pièce jointe")).toBe(false);
    expect(hasMandatGestionDocument({
      documents: [{ category: "Mandat de gestion" }],
    })).toBe(true);
  });
});
