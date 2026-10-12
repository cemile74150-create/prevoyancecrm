import {
  ANALYSE_STEPS,
  NON_RENSEIGNE,
  adjacentStep,
  autosaveLabel,
  buildDossierRecap,
  isStepComplete,
  recommendedHypothesisId,
  withSingleRecommander,
} from "./analyseWizard";
import { emptyAnalyseInput, emptyPerson } from "./types";

function coupleInput() {
  const input = emptyAnalyseInput();
  input.etatCivil = "Marié(e)";
  input.client1 = {
    ...emptyPerson("Monsieur"),
    prenom: "Jean",
    nom: "Demo",
    dateNaissance: "1960-03-15",
    avsMensuel: 2_000,
    avsMontantIssuSimulation: true,
    lpp: emptyPerson("Monsieur").lpp.map((row) =>
      row.age === 65 ? { ...row, capital: 400_000, rente: 20_000 } : row,
    ),
  };
  input.conjoint = {
    ...emptyPerson("Madame"),
    prenom: "Marie",
    nom: "Demo",
    dateNaissance: "1962-07-20",
    avsMensuel: 1_500,
  };
  input.villeRecherche = "1003 Lausanne";
  input.fortune = 50_000;
  input.withdrawalScenarios = [
    { id: "sc-a", name: "A regroupé", items: [], includeInReport: true },
  ];
  input.renteHypotheses = [
    {
      id: "h1",
      type: "certaine",
      compagnie: "Vaudoise",
      capitalPlace: 530_000,
      dureeAnnees: 20,
      renteGarantieAnnuelle: 23_000,
      participationExcedentsAnnuelle: 7_000,
      recommander: false,
    },
  ];
  return input;
}

describe("parcours 9 étapes", () => {
  it("expose les 9 étapes dans l'ordre demandé", () => {
    expect(ANALYSE_STEPS.map((s) => `${s.n} ${s.label}`)).toEqual([
      "1 Client",
      "2 Assuré 2",
      "3 AVS",
      "4 LPP",
      "5 3e piliers",
      "6 Libres passages",
      "7 Retraits/Fiscalité",
      "8 Fortune",
      "9 Hypothèses",
    ]);
  });

  it("changer d'étape ne mute pas la saisie", () => {
    const input = coupleInput();
    const snapshot = JSON.stringify(input);
    expect(adjacentStep("client", 1)).toBe("assure2");
    expect(adjacentStep("hypotheses", 1)).toBe("hypotheses");
    expect(adjacentStep("client", -1)).toBe("client");
    expect(JSON.stringify(input)).toBe(snapshot);
  });

  it("toutes les étapes restent adressables, couple ou seul", () => {
    const seul = emptyAnalyseInput();
    for (const step of ANALYSE_STEPS) {
      expect(typeof isStepComplete(step.id, seul)).toBe("boolean");
      expect(typeof isStepComplete(step.id, coupleInput())).toBe("boolean");
    }
    expect(isStepComplete("assure2", seul)).toBe(false);
    expect(isStepComplete("assure2", coupleInput())).toBe(true);
    expect(isStepComplete("avs", coupleInput())).toBe(true);
  });
});

describe("autosave et récap", () => {
  it("n'affiche Enregistré / En cours / Erreur qu'après un vrai statut", () => {
    expect(autosaveLabel("idle")).toBe("");
    expect(autosaveLabel("saving")).toBe("En cours");
    expect(autosaveLabel("saved")).toBe("Enregistré");
    expect(autosaveLabel("error")).toBe("Erreur");
  });

  it("récap couple vs seul, sans montant fictif", () => {
    const vide = buildDossierRecap(emptyAnalyseInput(), null, "idle");
    expect(vide.nom).toBe(NON_RENSEIGNE);
    expect(vide.conjoint).toBe(NON_RENSEIGNE);
    expect(vide.avsMensuelle).toBe(NON_RENSEIGNE);
    expect(vide.lppTotal).toBe(NON_RENSEIGNE);
    expect(vide.communeCanton).toBe(NON_RENSEIGNE);

    const couple = buildDossierRecap(coupleInput(), { status: "brouillon" }, "saved");
    expect(couple.nom).toBe("Jean Demo");
    expect(couple.conjoint).toBe("Marie Demo");
    expect(couple.communeCanton).toBe("1003 Lausanne");
    expect(couple.statut).toBe("Enregistré");
    expect(couple.scenario).toBe("A regroupé");
    expect(couple.avsMensuelle).not.toBe(NON_RENSEIGNE);
    expect(couple.lppTotal).not.toBe(NON_RENSEIGNE);
  });

  it("conserve la case AVS simulation dans le state de saisie", () => {
    const input = coupleInput();
    expect(input.client1.avsMontantIssuSimulation).toBe(true);
    adjacentStep("avs", 1);
    expect(input.client1.avsMontantIssuSimulation).toBe(true);
  });
});

describe("recommandation conseiller", () => {
  it("une seule case Recommander à la fois, pas le revenu max auto", () => {
    const rows = [
      { id: "a", recommander: false },
      { id: "b", recommander: false },
    ];
    expect(recommendedHypothesisId(rows)).toBe(null);
    const onlyB = withSingleRecommander(rows, "b", true);
    expect(recommendedHypothesisId(onlyB)).toBe("b");
    const none = withSingleRecommander(onlyB, "b", false);
    expect(recommendedHypothesisId(none)).toBe(null);
    const onlyA = withSingleRecommander(onlyB, "a", true);
    expect(onlyA.find((r) => r.id === "a").recommander).toBe(true);
    expect(onlyA.find((r) => r.id === "b").recommander).toBe(false);
  });
});
