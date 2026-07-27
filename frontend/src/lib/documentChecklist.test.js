import { getInitialDocumentChecklistState, getNextDocumentStatus } from './documentChecklist';

describe('document checklist helpers', () => {
  it('creates an empty checklist state for every document', () => {
    const state = getInitialDocumentChecklistState([{ id: 'carte-identite' }, { id: 'procuration' }]);
    expect(state).toEqual({
      'carte-identite': { sent: false, pending: false, received: false },
      procuration: { sent: false, pending: false, received: false },
    });
  });

  it('keeps only the selected status active for a document', () => {
    const current = { sent: false, pending: false, received: false };
    expect(getNextDocumentStatus(current, 'sent')).toEqual({ sent: true, pending: false, received: false });
    expect(getNextDocumentStatus({ sent: true, pending: false, received: false }, 'sent')).toEqual({ sent: false, pending: false, received: false });
  });
});
