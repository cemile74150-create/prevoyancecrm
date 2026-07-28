import { getInitialDocumentChecklistState, getNextDocumentStatus } from './documentChecklist';

describe('document checklist helpers', () => {
  it('creates an empty checklist state for every document', () => {
    const state = getInitialDocumentChecklistState(["Carte d'identité", 'Procuration']);
    expect(state).toEqual({
      "Carte d'identité": { sent: false, received: false },
      Procuration: { sent: false, received: false },
    });
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
