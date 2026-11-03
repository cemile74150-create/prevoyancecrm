/**
 * Même calendrier que backend/analyse_prevoyance_engine/rules/rente-hypotheses.ts.
 * Sert au récap de l'étape Hypothèses. L'affichage au franc se fait à la fin.
 */
import { compagnieEstPax } from "@/analyse-prevoyance/lib/compagniePax";
import type {
  RenteHypothesisInput,
  RenteHypothesisType,
  RenteOffreSaisie,
} from "@/analyse-prevoyance/lib/types";

export interface TotauxOffres {
  annee: number | null;
  capitalTotal: number;
  rentesGaranties: number;
  participations: number;
  prestationsAnnuelles: number;
}

function n(value: number | null | undefined): number {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function roundCents(value: number): number {
  return Math.round((value + 1e-8) * 100) / 100;
}

export function anneesDiffere(value: number | null | undefined): number | null {
  const years = Math.floor(Number(value));
  if (!Number.isFinite(years) || years <= 0) return null;
  return years;
}

export function differeVersementAnnees(offre: {
  compagnie?: string | null;
  dureeDiffereAnnees?: number | null;
}): number {
  const saisi = anneesDiffere(offre.dureeDiffereAnnees);
  if (saisi != null) return saisi;
  if (compagnieEstPax(offre.compagnie)) return 1;
  return 0;
}

export function offreVersee(
  offre: RenteOffreSaisie,
  annee: number,
): boolean {
  if (annee < 1) return false;
  const premiere = differeVersementAnnees(offre) + 1;
  if (annee < premiere) return false;
  if (offre.type === "viagere") return true;
  const duree = Math.floor(Number(offre.dureeAnnees));
  if (!Number.isFinite(duree) || duree <= 0) return true;
  return annee <= premiere + duree - 1;
}

export function anneeToutesVerses(offres: RenteOffreSaisie[]): number | null {
  if (!offres.length) return null;
  for (let annee = 1; annee <= 80; annee += 1) {
    if (offres.every((offre) => offreVersee(offre, annee))) return annee;
  }
  return null;
}

export function offresDeHypothese(row: RenteHypothesisInput): RenteOffreSaisie[] {
  if (row.offres && row.offres.length >= 2) return row.offres;
  return [
    {
      id: `${row.id}-offre`,
      type: row.type,
      compagnie: row.compagnie,
      capitalPlace: row.capitalPlace,
      dureeAnnees: row.type === "viagere" ? null : row.dureeAnnees,
      dureeDiffereAnnees: row.dureeDiffereAnnees ?? null,
      renteGarantieAnnuelle: row.renteGarantieAnnuelle,
      participationExcedentsAnnuelle: row.participationExcedentsAnnuelle,
    },
  ];
}

export function titreOffre(offre: RenteOffreSaisie, index: number): string {
  const type = offre.type === "viagere" ? "Rente viagère" : "Rente certaine";
  return `Offre ${index + 1} — ${type}`;
}

export function totauxAnneeCommune(offres: RenteOffreSaisie[]): TotauxOffres {
  const annee = anneeToutesVerses(offres);
  const actives = annee == null ? [] : offres.filter((offre) => offreVersee(offre, annee));
  const rentes = roundCents(
    actives.reduce((sum, offre) => sum + n(offre.renteGarantieAnnuelle), 0),
  );
  const participations = roundCents(
    actives.reduce((sum, offre) => sum + n(offre.participationExcedentsAnnuelle), 0),
  );
  return {
    annee,
    capitalTotal: roundCents(
      offres.reduce((sum, offre) => sum + n(offre.capitalPlace), 0),
    ),
    rentesGaranties: rentes,
    participations,
    prestationsAnnuelles: roundCents(rentes + participations),
  };
}

export function commitOffres(
  row: RenteHypothesisInput,
  offres: RenteOffreSaisie[],
): RenteHypothesisInput {
  const first = offres[0];
  const base: RenteHypothesisInput = {
    ...row,
    type: first?.type || row.type,
    compagnie: first?.compagnie ?? "",
    capitalPlace: first?.capitalPlace || 0,
    dureeAnnees: first?.type === "certaine" ? first.dureeAnnees : null,
    dureeDiffereAnnees: first?.dureeDiffereAnnees ?? null,
    renteGarantieAnnuelle: first?.renteGarantieAnnuelle || 0,
    participationExcedentsAnnuelle: first?.participationExcedentsAnnuelle || 0,
  };
  if (offres.length < 2) {
    const { offres: _ignored, ...single } = base;
    return single;
  }
  return { ...base, offres };
}

export function emptyOffre(type: RenteHypothesisType = "certaine"): RenteOffreSaisie {
  return {
    id: `ro-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    type,
    compagnie: "",
    capitalPlace: 0,
    dureeAnnees: null,
    dureeDiffereAnnees: null,
    renteGarantieAnnuelle: 0,
    participationExcedentsAnnuelle: 0,
  };
}
