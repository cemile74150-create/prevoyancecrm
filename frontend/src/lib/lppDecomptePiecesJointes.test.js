import {
  LPP_DECOMPTE_PIECES_JOINTES_INTRO,
  LPP_DECOMPTE_PIECES_JOINTES_ITEMS,
  LPP_DECOMPTE_PIECES_JOINTES_TITLE,
} from "./lppDecomptePiecesJointes";

describe("rappel pièces jointes Demandes LPP", () => {
  it("rappelle la réponse de caisse et la procuration, hors PDF", () => {
    expect(LPP_DECOMPTE_PIECES_JOINTES_TITLE).toBe(
      "Attention – Documents à joindre",
    );
    expect(LPP_DECOMPTE_PIECES_JOINTES_INTRO).toMatch(/joindre obligatoirement/i);
    expect(LPP_DECOMPTE_PIECES_JOINTES_ITEMS).toHaveLength(2);
    expect(LPP_DECOMPTE_PIECES_JOINTES_ITEMS[0]).toMatch(/réponse de la caisse/i);
    expect(LPP_DECOMPTE_PIECES_JOINTES_ITEMS[0]).toMatch(/surobligatoire/i);
    expect(LPP_DECOMPTE_PIECES_JOINTES_ITEMS[1]).toMatch(/procuration/i);
  });
});
