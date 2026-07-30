import { DOCUMENT_CHECKLIST_ITEMS, getInitialDocumentChecklistState, getNextDocumentStatus } from './documentChecklist';

describe('document checklist helpers', () => {
  it('creates an empty checklist state for every document', () => {
    const state = getInitialDocumentChecklistState(["Carte d'identité", 'Demande LPP']);
    expect(state).toEqual({
      "Carte d'identité": { sent: false, received: false },
      "Demande LPP": { sent: false, received: false },
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

  it('merges saved checklist values when provided', () => {
    const state = getInitialDocumentChecklistState(['Procuration'], {
      Procuration: { sent: true, received: false },
    });
    expect(state.Procuration).toEqual({ sent: true, received: false });
  });

  it('keeps only sent or received active for a document', () => {
    const current = { sent: false, received: false };
    expect(getNextDocumentStatus(current, 'sent')).toEqual({ sent: true, received: false });
    expect(getNextDocumentStatus({ sent: true, received: false }, 'sent')).toEqual({ sent: false, received: false });
    expect(getNextDocumentStatus({ sent: true, received: false }, 'received')).toEqual({ sent: false, received: true });
  });
});
