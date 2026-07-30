export const DOCUMENT_CHECKLIST_ITEMS = [
  'Carte d\'identité',
  'Demande LPP',
  'Mandat de gestion',
  'Formulaire AVS',
  'Certificat LPP',
  'Police 3e pilier',
  'Déclaration fiscale',
  'Autre formulaire',
];

/**
 * Pour ajouter un type de document au dossier :
 * 1) Ajouter le libellé ici (avant « Autre formulaire » de préférence)
 * 2) Redéployer — Envoyé / Reçu / upload multi-PDF suivent automatiquement
 *
 * Pas besoin de modifier ClientDetail.js pour une nouvelle catégorie standard.
 */
export function getInitialDocumentChecklistState(items = DOCUMENT_CHECKLIST_ITEMS, saved = {}) {
  return items.reduce((acc, item) => {
    const existing = saved?.[item];
    acc[item] = {
      sent: Boolean(existing?.sent),
      received: Boolean(existing?.received),
    };
    return acc;
  }, {});
}

export function getNextDocumentStatus(currentStatus, statusKey) {
  const nextState = { sent: false, received: false };
  const active = currentStatus?.[statusKey];

  if (active) {
    return nextState;
  }

  nextState[statusKey] = true;
  return nextState;
}
