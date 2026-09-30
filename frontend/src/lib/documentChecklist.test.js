import { DOCUMENT_CHECKLIST_ITEMS, getInitialDocumentChecklistState, getNextDocumentStatus, getCustomChecklistItems, getDemandesChecklistItems, getChecklistDisplayLabel, omitChecklistItem } from './documentChecklist';

describe('document checklist helpers', () => {
  it('creates an empty checklist state for every document', () => {
    const state = getInitialDocumentChecklistState(["Carte d'identité", 'Demande LPP']);
    expect(state).toEqual({
      "Carte d'identité": { sent: false, received: false, sent_at: null, received_at: null, effectue: false },
      "Demande LPP": { sent: false, received: false, sent_at: null, received_at: null, effectue: false },
    });
  });

  it('uses a single Demande LPP checklist item', () => {
    expect(DOCUMENT_CHECKLIST_ITEMS).toContain('Demande LPP');
    expect(DOCUMENT_CHECKLIST_ITEMS).toContain('Déclaration fiscale');
    expect(DOCUMENT_CHECKLIST_ITEMS).not.toContain('Procuration');
    expect(DOCUMENT_CHECKLIST_ITEMS).not.toContain('Formulaire Recherche LPP');
    expect(DOCUMENT_CHECKLIST_ITEMS.indexOf('Déclaration fiscale')).toBeLessThan(
      DOCUMENT_CHECKLIST_ITEMS.indexOf('Autre formulaire')
    );
  });

  it('displays renamed labels while keeping internal keys', () => {
    expect(getChecklistDisplayLabel('Demande LPP')).toBe('Recherche Fond');
    expect(getChecklistDisplayLabel('Formulaire AVS')).toBe('Projection rente AVS');
    expect(getChecklistDisplayLabel('Police 3e pilier')).toBe('Police 3e pilier');
  });

  it('merges saved checklist values when provided', () => {
    const state = getInitialDocumentChecklistState(['Procuration'], {
      Procuration: { sent: true, received: false },
    });
    expect(state.Procuration).toBeUndefined();
  });

  it('preserves effectue status for Recherche Fond', () => {
    const state = getInitialDocumentChecklistState(['Demande LPP'], {
      'Demande LPP': { sent: true, received: false, effectue: true },
    });
    expect(state['Demande LPP'].effectue).toBe(true);
    expect(state['Demande LPP'].sent).toBe(true);
  });

  it('shows custom checklist items only when linked docs exist', () => {
    const custom = getCustomChecklistItems(
      { 'Compte de libre passage': { sent: false, received: true } },
      [{ checklist_item: 'Attestation employeur', generated: false }]
    );
    expect(custom).toEqual(['Attestation employeur']);
    expect(custom).not.toContain('Compte de libre passage');

    const withFile = getCustomChecklistItems(
      { 'Compte de libre passage': { sent: false, received: false } },
      [{ checklist_item: 'Compte de libre passage', generated: false }]
    );
    expect(withFile).toContain('Compte de libre passage');

    const demandes = getDemandesChecklistItems(
      { 'Compte de libre passage': { sent: false, received: false } },
      [{ checklist_item: 'Compte de libre passage', generated: false }]
    );
    expect(demandes).toContain('Police 3e pilier');
    expect(demandes).toContain('Compte de libre passage');
    expect(demandes).not.toContain('Autre formulaire');
  });

  it('omits custom checklist keys but keeps standard ones', () => {
    const saved = {
      "Carte d'identité": { sent: true, received: false },
      Mutuelle: { sent: false, received: false },
    };
    expect(omitChecklistItem(saved, 'Mutuelle')).toEqual({
      "Carte d'identité": { sent: true, received: false },
    });
    expect(omitChecklistItem(saved, "Carte d'identité")).toEqual(saved);
  });

  it('toggles effectue independently of sent/received', () => {
    const current = { sent: true, received: false, effectue: false };
    expect(getNextDocumentStatus(current, 'effectue')).toMatchObject({
      sent: true,
      received: false,
      effectue: true,
    });
    expect(getNextDocumentStatus({ ...current, effectue: true }, 'effectue')).toMatchObject({
      effectue: false,
    });
  });

  it('keeps sent when marking received', () => {
    const next = getNextDocumentStatus({ sent: true, received: false }, 'received');
    expect(next.sent).toBe(true);
    expect(next.received).toBe(true);
  });
});
