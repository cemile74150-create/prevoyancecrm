export const DOCUMENT_CHECKLIST_ITEMS = [
  'Carte d\'identité',
  'Procuration',
  'Mandat de gestion',
  'Formulaire AVS',
  'Formulaire de recherche LPP',
  'Certificat LPP',
  'Police de 3e pilier',
  'Déclaration fiscale',
  'Formulaire de prévoyance',
  'Notes',
];

export function getInitialDocumentChecklistState(items = DOCUMENT_CHECKLIST_ITEMS) {
  return items.reduce((acc, item) => {
    acc[item] = { sent: false, pending: false, received: false };
    return acc;
  }, {});
}

export function getNextDocumentStatus(currentStatus, statusKey) {
  const nextState = { sent: false, pending: false, received: false };
  const active = currentStatus?.[statusKey];

  if (active) {
    return nextState;
  }

  nextState[statusKey] = true;
  return nextState;
}
