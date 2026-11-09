/**
 * Transmettre une offre : deux formulaires distincts.
 * - Réponses compagnies : compagnie, date de réception, N variantes (Offre, CGA, Autre document).
 * - Traitement : compagnie, date, Offre / CGA / Autre document, commentaire (sans variantes).
 */

export const PARCOURS_REPONSES = "reponses_compagnies";
export const PARCOURS_TRAITEMENT = "traitement";
export const MAX_VARIANTES = 20;

export const VARIANTE_PIECES = [
  { id: "offre", label: "Offre", required: true },
  { id: "cga", label: "CGA", required: true },
  { id: "autre", label: "Autre document", required: false },
];

export const PARCOURS_FIELDS = {
  [PARCOURS_REPONSES]: ["compagnie", "date_reception", "nb_variantes", "variantes"],
  [PARCOURS_TRAITEMENT]: ["compagnie", "date_reception", "offre", "cga", "autre", "commentaire"],
};

export function newClientToken() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `tok-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Vide = 1. Retourne null si la saisie n'est pas un entier positif. */
export function parseNbVariantes(raw) {
  const text = String(raw ?? "").trim();
  if (!text) return 1;
  if (!/^\d+$/.test(text)) return null;
  const n = Number(text);
  if (n < 1 || n > MAX_VARIANTES) return null;
  return n;
}

export function emptyVariante() {
  return { offre: [], cga: [], autre: [] };
}

export function variantesFichiersCount(variante) {
  return VARIANTE_PIECES.reduce((sum, piece) => sum + ((variante?.[piece.id] || []).length), 0);
}

/**
 * Nouveau tableau de variantes pour `n`. Augmenter conserve les fichiers ;
 * diminuer retire les dernières variantes et indique les fichiers perdus.
 */
export function resizeVariantes(variantes, n) {
  const current = Array.isArray(variantes) ? variantes : [];
  const next = current.slice(0, n);
  while (next.length < n) next.push(emptyVariante());
  const removed = current.slice(n);
  const fichiersPerdus = removed.reduce((sum, v) => sum + variantesFichiersCount(v), 0);
  return { variantes: next, fichiersPerdus, variantesRetirees: removed.length };
}

export function variantesManquantes(variantes) {
  const missing = [];
  (variantes || []).forEach((variante, i) => {
    VARIANTE_PIECES.filter((p) => p.required).forEach((piece) => {
      if (!(variante?.[piece.id] || []).length) missing.push(`Variante ${i + 1} : ${piece.label}`);
    });
  });
  return missing;
}

/** Pièces obligatoires manquantes pour le parcours Traitement (sans préfixe Variante). */
export function traitementManquantes(pieces) {
  return VARIANTE_PIECES
    .filter((piece) => piece.required && !(pieces?.[piece.id] || []).length)
    .map((piece) => piece.label);
}

export function variantesFormData({ compagnie, dateReception, variantes, clientToken }) {
  const fd = new FormData();
  fd.append("compagnie", compagnie);
  fd.append("date_reception", dateReception);
  fd.append("nb_variantes", String(variantes.length));
  fd.append("parcours", PARCOURS_REPONSES);
  if (clientToken) fd.append("client_token", clientToken);
  variantes.forEach((variante, i) => {
    VARIANTE_PIECES.forEach((piece) => {
      (variante[piece.id] || []).forEach((file) => fd.append(`variante_${i + 1}_${piece.id}`, file));
    });
  });
  return fd;
}

export function traitementFormData({ compagnie, dateReception, pieces, commentaire, clientToken }) {
  const fd = new FormData();
  fd.append("compagnie", compagnie);
  fd.append("date_reception", dateReception);
  fd.append("parcours", PARCOURS_TRAITEMENT);
  if ((commentaire || "").trim()) fd.append("commentaires", commentaire.trim());
  if (clientToken) fd.append("client_token", clientToken);
  VARIANTE_PIECES.forEach((piece) => {
    (pieces?.[piece.id] || []).forEach((file) => fd.append(piece.id, file));
  });
  return fd;
}

/** Documents d'une réponse compagnie regroupés par transmission puis par variante. */
export function documentsParVariante(card) {
  const docs = Array.isArray(card?.documents) ? card.documents : [];
  const groups = [];
  const byKey = new Map();
  docs.forEach((doc) => {
    const variante = Number(doc?.variante) || 0;
    const key = variante ? `${doc.transmission_id || ""}:${variante}` : "sans";
    if (!byKey.has(key)) {
      const group = { key, variante, transmissionId: doc.transmission_id || null, documents: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    byKey.get(key).documents.push(doc);
  });
  return groups;
}

export const URGENCE_DELAI_24H = "moins_24h";

export function urgenceDelaiLabel(demande) {
  return demande?.urgence_delai === URGENCE_DELAI_24H ? "À traiter en moins de 24 heures" : "";
}

/** Message affiché après une transmission, d'après l'état calculé par l'API. */
export function messageTransmission(data) {
  if (data?.transmission_deja_enregistree) return "Transmission déjà enregistrée";
  const t = data?.transmission;
  if (t?.etat === "partielle") {
    return `Offres partiellement transmises à l'agent (${t.nb_transmises}/${t.nb_sollicitees} compagnies)`;
  }
  return "Offres transmises à l'agent";
}

/** Refus explicite : case 24 h non cochée ou motif vide. */
export function urgenceRefus({ delai24h, motif }) {
  if (!delai24h) return "Cochez « Demande à traiter sous moins de 24 h » pour confirmer l'urgence.";
  if (!String(motif || "").trim()) return "Le motif de l'urgence est obligatoire.";
  return "";
}

/** Bouton « Signaler une erreur » : fond blanc, texte foncé, bordure discrète. */
export const SIGNALER_ERREUR_CLASS = "w-full justify-start bg-white text-slate-900 border border-slate-300 hover:bg-slate-50";

export const FILE_COLUMNS = [
  "Agent", "Client", "Type", "Date création", "Date envoi", "RDV client",
  "Compagnies", "Statut traitement", "Statut commercial", "Soumis cie.", "Dernière action", "Jours", "Priorité", "Action",
];

/** Demande urgente posée par l'agent (badge URGENT), distincte de la priorité système. */
export function isUrgenceAgent(row) {
  return Boolean(row?.urgente);
}

function prioRankFile(priorite) {
  if (priorite === "urgent") return 0;
  if (priorite === "surveiller") return 1;
  return 2;
}

/**
 * File à traiter : l'urgence agent passe avant tout le monde,
 * même si la colonne Priorité affiche « Normal ».
 * Ensuite priorité système, puis dernière mise à jour.
 */
export function sortFileATraiter(rows) {
  return [...(rows || [])].sort((a, b) => {
    const urgent = Number(isUrgenceAgent(b)) - Number(isUrgenceAgent(a));
    if (urgent !== 0) return urgent;
    const d = prioRankFile(a?.priorite) - prioRankFile(b?.priorite);
    if (d !== 0) return d;
    return String(b?.updated_at || "").localeCompare(String(a?.updated_at || ""));
  });
}

/** Garde l'ordre relatif dans chaque groupe, mais place toutes les urgences agent en tête. */
export function urgentesAgentEnTete(rows) {
  const urgent = [];
  const autres = [];
  for (const row of rows || []) {
    (isUrgenceAgent(row) ? urgent : autres).push(row);
  }
  return urgent.concat(autres);
}
