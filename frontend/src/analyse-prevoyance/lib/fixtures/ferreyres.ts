// @ts-nocheck
/**
 * Valeurs de référence extraites de l’inventaire / cache Excel Ferreyres.
 * Fortune Couple1 : colonne G vide dans tblRevenus → somme PQ = 0.
 */
export const FERREYRES = {
  ville: "1313 Ferreyres",
  taxLocationId: 131300000,
  taxYear: 2025,
  etatCivil: "Marié(e)" as const,
  confession: 5,
  fortuneCouple1: 0,
  capitalTaxes: [
    { age: 65, capital: 1_081_456, impot: 93_864 },
    { age: 64, capital: 1_021_035, impot: 88_151 },
    { age: 63, capital: 955_233, impot: 81_924 },
    { age: 62, capital: 891_807, impot: 75_779 },
    { age: 61, capital: 830_667, impot: 69_805 },
    { age: 60, capital: 771_897, impot: 64_065 },
  ],
  thirdPillar: { capital: 170_000, age: 64, impot: 8_259 },
  couple1: {
    revenu1: 82_213,
    revenu2: 24_570,
    age1: 65,
    age2: 65,
    fortune: 0,
    impotRevenuTotal: 16_789,
    impotFederal: 1_736,
    impotCanton: 9_964,
    impotCommune: 5_089,
    impotEglise: 0,
  },
  /** Décomposition AVS/LPP cohérente avec cache Couple1/Couple2. */
  revenues: {
    avsClient1: 24_895,
    avsConjoint: 24_570,
    lppClient1: 82_213 - 24_895, // 57318
    lppConjoint: 0,
  },
};
