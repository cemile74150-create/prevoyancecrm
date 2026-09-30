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

/** Libellés affichés (clés internes inchangées pour conserver les données existantes). */
export const CHECKLIST_DISPLAY_LABELS = {
  'Demande LPP': 'Recherche Fond',
  'Formulaire AVS': 'Projection rente AVS',
};

export function getChecklistDisplayLabel(documentName) {
  return CHECKLIST_DISPLAY_LABELS[documentName] || documentName;
}

/** Anciens libellés fusionnés dans Demande LPP — ne pas traiter comme types custom. */
const LEGACY_LPP_ALIASES = new Set(['Procuration', 'Formulaire Recherche LPP']);

const STANDARD_SET = new Set(DOCUMENT_CHECKLIST_ITEMS);

/**
 * Pour ajouter un type de document standard au dossier :
 * 1) Ajouter le libellé ici (avant « Autre formulaire » de préférence)
 * 2) Redéployer — Envoyé / Reçu / upload multi-PDF suivent automatiquement
 *
 * Types ad hoc par client : bouton « Ajouter un fichier » → intitulé → nouvelle ligne.
 */

export function isStandardChecklistItem(name) {
  return STANDARD_SET.has(name);
}

export function getStandardChecklistItems() {
  return DOCUMENT_CHECKLIST_ITEMS.filter((item) => item !== 'Autre formulaire');
}

/**
 * Types de documents personnalisés (hors liste standard), dérivés des documents
 * déjà liés. Une ligne custom sans fichier n'est pas affichée.
 */
export function getCustomChecklistItems(savedChecklist = {}, docs = []) {
  const fromDocs = (docs || [])
    .filter((d) => !d?.generated)
    .map((d) => d.checklist_item || d.category)
    .filter(
      (k) =>
        k &&
        k !== "Autre" &&
        k !== "Autre formulaire" &&
        !STANDARD_SET.has(k) &&
        !LEGACY_LPP_ALIASES.has(k)
    );

  const seen = new Set();
  const custom = [];
  for (const name of fromDocs) {
    const key = String(name).trim();
    if (!key || seen.has(key)) continue;
    // Conservé si présent dans la checklist sauvegardée (même sans fichier)
    // uniquement lorsqu'un fichier existe — source de vérité = docs.
    seen.add(key);
    custom.push(key);
  }
  custom.sort((a, b) => a.localeCompare(b, "fr"));
  return custom;
}

/** Retire une clé custom de la checklist (ne touche pas aux types standard). */
export function omitChecklistItem(savedChecklist = {}, documentName) {
  if (!documentName || isStandardChecklistItem(documentName) || documentName === "Autre formulaire") {
    return { ...(savedChecklist || {}) };
  }
  const next = { ...(savedChecklist || {}) };
  delete next[documentName];
  return next;
}

/** Lignes affichées dans Demandes : standard + custom (sans Autre formulaire). */
export function getDemandesChecklistItems(savedChecklist = {}, docs = []) {
  return [...getStandardChecklistItems(), ...getCustomChecklistItems(savedChecklist, docs)];
}

export function getInitialDocumentChecklistState(items = DOCUMENT_CHECKLIST_ITEMS, saved = {}) {
  const allItems = [...new Set([...(items || []), ...Object.keys(saved || {})])];
  return allItems.reduce((acc, item) => {
    if (LEGACY_LPP_ALIASES.has(item)) return acc;
    const existing = saved?.[item];
    acc[item] = {
      sent: Boolean(existing?.sent),
      received: Boolean(existing?.received),
      sent_at: existing?.sent_at || null,
      received_at: existing?.received_at || null,
      // Recherche Fond (Demande LPP) : À effectuer / Effectué
      effectue: Boolean(existing?.effectue),
    };
    return acc;
  }, {});
}

/**
 * Envoyé et Reçu sont indépendants (comme le suivi LPP par caisse).
 * Cocher Reçu ne décoche pas Envoyé.
 * effectue : statut À effectuer / Effectué (Recherche Fond).
 */
export function getNextDocumentStatus(currentStatus, statusKey) {
  const nextState = {
    sent: Boolean(currentStatus?.sent),
    received: Boolean(currentStatus?.received),
    sent_at: currentStatus?.sent_at || null,
    received_at: currentStatus?.received_at || null,
    effectue: Boolean(currentStatus?.effectue),
  };
  const turningOn = !Boolean(currentStatus?.[statusKey]);
  nextState[statusKey] = turningOn;

  if (statusKey === "sent") {
    if (turningOn) {
      nextState.sent_at = nextState.sent_at || new Date().toISOString();
    } else {
      nextState.sent_at = null;
    }
  }
  if (statusKey === "received") {
    if (turningOn) {
      nextState.received_at = new Date().toISOString();
      // Cohérence : une réponse reçue implique un envoi
      if (!nextState.sent) {
        nextState.sent = true;
        nextState.sent_at = nextState.sent_at || new Date().toISOString();
      }
    } else {
      nextState.received_at = null;
    }
  }
  if (statusKey === "effectue") {
    nextState.effectue = turningOn;
  }
  return nextState;
}
