export const STATUTS = [
  "Nouveau",
  "Documents en attente",
  "Analyse en cours",
  "Stand-by",
  "À présenter",
  "Clôturé",
];

/** Mappe les anciens libellés vers le workflow simplifié. */
export const STATUT_LEGACY_MAP = {
  "Documents demandés": "Documents en attente",
  "Documents reçus": "Analyse en cours",
  "Rapport en préparation": "Analyse en cours",
  "À présenter au client": "À présenter",
};

export function normalizeStatut(statut) {
  if (!statut) return "Nouveau";
  if (STATUTS.includes(statut)) return statut;
  return STATUT_LEGACY_MAP[statut] || statut;
}

/** Types de documents 3e pilier (alignés backend). */
export const DOCUMENT_TYPES_3P = [
  "Police 3a",
  "Police 3b",
  "Valeur de rachat",
  "Valeur de libération",
  "Résiliation",
  "Rachat",
  "Libre passage",
  "Ordre de paiement",
  "Autre document",
];

export const NO_EXPIRY_DOC_TYPES_3P = new Set(["Résiliation", "Rachat", "Libre passage"]);

export const STATUT_COLORS = {
  "Nouveau": "bg-emerald-100 text-emerald-800 border-emerald-200",
  "Documents en attente": "bg-amber-100 text-amber-800 border-amber-200",
  "Analyse en cours": "bg-blue-100 text-blue-800 border-blue-200",
  "Stand-by": "bg-orange-100 text-orange-800 border-orange-200",
  "À présenter": "bg-purple-100 text-purple-800 border-purple-200",
  "Clôturé": "bg-slate-100 text-slate-700 border-slate-200",
  // Compat anciens libellés encore présents en cache
  "Documents demandés": "bg-amber-100 text-amber-800 border-amber-200",
  "Documents reçus": "bg-blue-100 text-blue-800 border-blue-200",
  "Rapport en préparation": "bg-blue-100 text-blue-800 border-blue-200",
  "À présenter au client": "bg-purple-100 text-purple-800 border-purple-200",
};

export const STATUT_DOT = {
  "Nouveau": "bg-emerald-500",
  "Documents en attente": "bg-amber-500",
  "Analyse en cours": "bg-blue-500",
  "Stand-by": "bg-orange-500",
  "À présenter": "bg-purple-500",
  "Clôturé": "bg-slate-500",
  "Documents demandés": "bg-amber-500",
  "Documents reçus": "bg-blue-500",
  "Rapport en préparation": "bg-blue-500",
  "À présenter au client": "bg-purple-500",
};

export const DOC_CATEGORIES = [
  "Certificat LPP",
  "Déclaration d'impôt",
  "Déclaration fiscale",
  "Pièce d'identité",
  "Fiches de salaire",
  "Contrats",
  "Procuration",
  "Formulaire AVS",
  "Formulaire de recherche LPP",
  "Police 3e pilier",
  "Autre",
];
