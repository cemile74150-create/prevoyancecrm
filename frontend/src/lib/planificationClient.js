/** Lien fiche client ↔ planification existante, par identifiant, pas par le nom. */

const STATUTS_ACTIFS = new Set(["brouillon", "calculee", "finalisee"]);

export function planificationsDuClient(items, clientId) {
  const id = String(clientId || "").trim();
  if (!id) return [];
  return (Array.isArray(items) ? items : []).filter((row) => row && row.clientId === id);
}

export function aUnePlanificationActive(items) {
  return (items || []).some((row) => STATUTS_ACTIFS.has(row?.status));
}

/** Retour vers l'onglet Planification de cette fiche. Null sans identifiant. */
export function ficheClientPlanificationPath(clientId) {
  const id = String(clientId || "").trim();
  if (!id) return null;
  return `/clients/${encodeURIComponent(id)}?tab=planification`;
}
