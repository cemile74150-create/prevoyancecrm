import {
  COMPAGNIES_DEFAUT,
  AUTRE_COMPAGNIE_VALUE,
  compagniesEnregistrementOffre,
  documentsForGeneralList,
  resolveCompagnieSaisie,
} from "./demandesOffres";

describe("documentsForGeneralList", () => {
  const demande = {
    documents: [
      { id: "offre-vd", category: "Offre compagnie", original_filename: "Vaudoise.pdf" },
      { id: "offre-axa", category: "Offre compagnie", original_filename: "AXA.pdf" },
      { id: "mandat", category: "Mandat", original_filename: "Vaudoise.pdf" },
      { id: "piece", category: "Pièce jointe", original_filename: "identite.pdf" },
      { id: "orpheline", category: "Offre compagnie", original_filename: "non-rattachee.pdf" },
    ],
    reponses_compagnies: [
      {
        compagnie: "Vaudoise",
        documents: [{ id: "offre-vd", category: "Offre compagnie", original_filename: "Vaudoise.pdf" }],
      },
      {
        compagnie: "AXA",
        documents: [{ id: "offre-axa", category: "Offre compagnie", original_filename: "AXA.pdf" }],
      },
    ],
  };

  test("retire les offres compagnie déjà affichées sur les cartes, pas les autres pièces", () => {
    const ids = documentsForGeneralList(demande).map((d) => d.id);
    expect(ids).toEqual(["mandat", "piece", "orpheline"]);
  });

  test("ne filtre pas par nom de fichier", () => {
    const kept = documentsForGeneralList(demande).find((d) => d.id === "mandat");
    expect(kept.original_filename).toBe("Vaudoise.pdf");
  });

  test("laisse la liste intacte sans cartes compagnie", () => {
    const ids = documentsForGeneralList({
      documents: demande.documents,
      reponses_compagnies: [],
    }).map((d) => d.id);
    expect(ids).toEqual(["offre-vd", "offre-axa", "mandat", "piece", "orpheline"]);
  });
});

describe("COMPAGNIES_DEFAUT", () => {
  test("inclut Rentes Genevoises sans retirer les compagnies existantes", () => {
    expect(COMPAGNIES_DEFAUT).toContain("Rentes Genevoises");
    expect(COMPAGNIES_DEFAUT).toEqual(expect.arrayContaining([
      "PAX", "Helvetia", "Swiss Life", "AXA", "Vaudoise", "Smile Direct",
    ]));
    expect(COMPAGNIES_DEFAUT).not.toContain("GVB");
  });
});

describe("compagnies d'enregistrement", () => {
  test("place les compagnies de la demande en premier et ignore Envoi du formulaire", () => {
    const options = compagniesEnregistrementOffre({
      compagnies_enregistrement: ["GVB", "Helvetia", "Axa", "Envoi du formulaire", "GVB"],
    });
    expect(options).toEqual(["GVB", "Helvetia", "Axa"]);
  });

  test("rattache une saisie libre au libellé déjà proposé", () => {
    const options = ["GVB", "Helvetia", "Axa"];
    expect(resolveCompagnieSaisie("gvb", "", options)).toBe("GVB");
    expect(resolveCompagnieSaisie(AUTRE_COMPAGNIE_VALUE, "  Helvetia ", options)).toBe("Helvetia");
    expect(resolveCompagnieSaisie(AUTRE_COMPAGNIE_VALUE, "Envoi du formulaire", options)).toBe("");
    expect(resolveCompagnieSaisie(AUTRE_COMPAGNIE_VALUE, "Rouky", options)).toBe("Rouky");
  });
});
