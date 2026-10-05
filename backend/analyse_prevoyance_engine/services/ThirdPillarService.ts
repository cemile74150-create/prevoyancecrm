import type { ThirdPillarContract } from "../types";

/**
 * Service 3e pilier — agrégation multi-contrats.
 */
export class ThirdPillarService {
  totalCapital(contracts: ThirdPillarContract[]): number {
    return round2(contracts.reduce((s, c) => s + (c.montant || 0), 0));
  }

  totalPrimes(contracts: ThirdPillarContract[]): number {
    return round2(contracts.reduce((s, c) => s + (c.prime || 0), 0));
  }

  /** Âge approximatif à l’échéance pour l’impôt capital 3P (année échéance − année naissance). */
  ageAtMaturity(
    birthDateIso: string,
    echeanceIso: string,
  ): number | null {
    if (!birthDateIso || !echeanceIso) return null;
    const by = Number(birthDateIso.slice(0, 4));
    const ey = Number(echeanceIso.slice(0, 4));
    if (!Number.isFinite(by) || !Number.isFinite(ey)) return null;
    return Math.max(55, Math.min(70, ey - by));
  }
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export const thirdPillarService = new ThirdPillarService();
