import {
  STATUTS, STATUT_COLORS, STATUT_DOT, STATUT_PRESENTE_EN_COURS, normalizeStatut,
} from './constants';

describe('statuts Kanban Dossiers Prévoyance', () => {
  it('place « Dossier présenté — en cours » entre « À présenter » et « Clôturé »', () => {
    expect(STATUTS).toEqual([
      'Nouveau',
      'Documents en attente',
      'Analyse en cours',
      'Stand-by',
      'À présenter',
      'Dossier présenté — en cours',
      'Clôturé',
    ]);
  });

  it('donne une couleur distincte au nouveau statut', () => {
    expect(STATUT_DOT[STATUT_PRESENTE_EN_COURS]).toBe('bg-teal-500');
    expect(STATUT_COLORS[STATUT_PRESENTE_EN_COURS]).toContain('teal');
    const dots = STATUTS.map((s) => STATUT_DOT[s]);
    expect(new Set(dots).size).toBe(STATUTS.length);
  });

  it('conserve la normalisation des anciens libellés', () => {
    expect(normalizeStatut(STATUT_PRESENTE_EN_COURS)).toBe(STATUT_PRESENTE_EN_COURS);
    expect(normalizeStatut('À présenter au client')).toBe('À présenter');
    expect(normalizeStatut('')).toBe('Nouveau');
  });
});
