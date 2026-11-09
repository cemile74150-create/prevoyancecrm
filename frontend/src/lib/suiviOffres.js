/**
 * Suivi des offres : attribution, statut de traitement, statut commercial.
 *
 * Les compteurs et les étiquettes de chaque demande (`pilotage_tags`) sont
 * calculés par l'API (/demandes-offres/pilotage). Ce module ne refait aucun
 * calcul d'indicateur : il affiche et filtre sur ces étiquettes.
 */

export const NON_ATTRIBUE = "non_attribue";
export const NON_ATTRIBUE_LABEL = "Non attribué";

export const TRAITEMENT_ORDER = [
  "en_attente",
  "en_cours",
  "attente_compagnie",
  "relance",
  "offres_partielles",
  "offre_transmise",
];

export const TRAITEMENT_STYLE = {
  en_attente: "bg-blue-50 text-blue-900 ring-1 ring-inset ring-blue-200",
  en_cours: "bg-orange-50 text-orange-900 ring-1 ring-inset ring-orange-200",
  attente_compagnie: "bg-yellow-50 text-yellow-900 ring-1 ring-inset ring-yellow-300",
  relance: "bg-violet-50 text-violet-900 ring-1 ring-inset ring-violet-200",
  offres_partielles: "bg-teal-50 text-teal-900 ring-1 ring-inset ring-teal-200",
  offre_transmise: "bg-emerald-50 text-emerald-900 ring-1 ring-inset ring-emerald-200",
};

export const COMMERCIAL_ORDER = ["transmise_client", "signee", "non_signee", "non_renseigne"];

export const COMMERCIAL_LABELS = {
  non_renseigne: "Statut non renseigné",
  transmise_client: "Offre transmise au client",
  signee: "Offre signée",
  non_signee: "Offre non signée",
};

export const COMMERCIAL_STYLE = {
  non_renseigne: "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200",
  transmise_client: "bg-indigo-50 text-indigo-900 ring-1 ring-inset ring-indigo-200",
  signee: "bg-emerald-100 text-emerald-900 ring-1 ring-inset ring-emerald-300",
  non_signee: "bg-rose-50 text-rose-800 ring-1 ring-inset ring-rose-200",
};

/** Couleur du bouton d'ouverture, d'après `bouton_traiter.couleur` fourni par l'API. */
export const BOUTON_TRAITER_CLASS = {
  bleu: "bg-[#002FA7] text-white hover:bg-[#00237d]",
  orange: "bg-orange-500 text-white hover:bg-orange-600",
  jaune: "bg-yellow-400 text-slate-900 hover:bg-yellow-500",
  violet: "bg-violet-600 text-white hover:bg-violet-700",
  turquoise: "bg-teal-600 text-white hover:bg-teal-700",
  vert: "bg-emerald-600 text-white hover:bg-emerald-700",
  gris: "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50",
};

export function boutonTraiter(row) {
  const b = row?.bouton_traiter;
  if (b?.label) return { label: b.label, className: BOUTON_TRAITER_CLASS[b.couleur] || BOUTON_TRAITER_CLASS.gris };
  return { label: "Voir", className: BOUTON_TRAITER_CLASS.gris };
}

export function commercialCode(row) {
  return row?.statut_commercial || "non_renseigne";
}

export function commercialLabel(row) {
  return row?.statut_commercial_label || COMMERCIAL_LABELS[commercialCode(row)];
}

export function gestionnaireLabel(row) {
  return row?.gestionnaire_nom || NON_ATTRIBUE_LABEL;
}

export function hasTag(row, tag) {
  return Array.isArray(row?.pilotage_tags) && row.pilotage_tags.includes(tag);
}

/** Cartes du tableau de bord général (B3), dans l'ordre du cahier des charges. */
export const CARTES_GLOBALES = [
  { tag: "soumises", label: "Total des demandes soumises" },
  { tag: "non_attribuees", label: "Demandes non attribuées", tone: "border-amber-300 bg-amber-50" },
  { tag: "attribuees", label: "Demandes attribuées" },
  { tag: "en_cours_global", label: "Dossiers en cours" },
  { tag: "termines", label: "Dossiers terminés" },
  { tag: "en_retard", label: "Dossiers en retard", tone: "border-red-200 bg-red-50" },
];

/** Indicateurs commerciaux (A3). */
export const CARTES_COMMERCIALES = [
  { tag: "transmises_client", label: "Offres transmises au client" },
  { tag: "attente_decision", label: "En attente de décision du client" },
  { tag: "commercial:signee", label: "Offres signées" },
  { tag: "commercial:non_signee", label: "Offres non signées" },
  { tag: "commercial:non_renseigne", label: "Statuts commerciaux non renseignés" },
];

/** Colonnes du tableau « Répartition et activité des gestionnaires d'offres » (B4). */
export const REPARTITION_COLUMNS = [
  { key: "nom", label: "Gestionnaire" },
  { key: "attribues", label: "Attribués", tag: null },
  { key: "en_cours", label: "En cours", tag: "traitement:en_cours" },
  { key: "attente_compagnie", label: "En attente compagnie", tag: "attente_compagnie_ou_relance" },
  { key: "transmis_agent", label: "Transmis à l'agent", tag: "traitement:offre_transmise" },
  { key: "signes", label: "Signés", tag: "commercial:signee" },
  { key: "non_signes", label: "Non signés", tag: "commercial:non_signee" },
  { key: "en_retard", label: "En retard", tag: "en_retard" },
];

/** Colonnes du tableau détaillé (B5), dans l'ordre demandé. */
export const DETAIL_COLUMNS = [
  "Réf. OFF",
  "Agent demandeur",
  "Gestionnaire attribué",
  "Date de soumission",
  "Date RDV client",
  "Type d'offre",
  "Compagnie(s)",
  "Statut traitement",
  "Statut commercial",
  "Jours",
  "Priorité / Urgence",
  "Dernière action",
  "Actions",
];

export const DECISION_COLUMNS = [
  "Réf. OFF",
  "Client",
  "Agent",
  "Date de transmission des documents",
  "Jours écoulés",
  "Statut commercial",
  "Rappel envoyé",
];

/** Colonnes de la file d'attribution sous le tableau B4 (dossiers non attribués). */
export const A_ATTRIBUER_COLUMNS = [
  "Réf. OFF",
  "Agent demandeur",
  "Date de soumission",
  "Date RDV client",
  "Type d'offre",
  "Compagnie(s)",
  "Statut traitement",
  "Jours",
  "Priorité / Urgence",
  "Actions",
];

/** Le filtre « En attente compagnie » du tableau B4 inclut les dossiers relancés. */
export function matchTag(row, tag) {
  if (!tag) return true;
  if (tag === "attente_compagnie_ou_relance") {
    return hasTag(row, "traitement:attente_compagnie") || hasTag(row, "traitement:relance");
  }
  return hasTag(row, tag);
}

export const FILTRES_VIDES = {
  tag: null,
  gestionnaire: "all",
  agent: "all",
  type: "all",
  compagnie: "all",
  traitement: "all",
  commercial: "all",
  priorite: "all",
};

function compagniesDe(row) {
  const list = [
    ...(Array.isArray(row?.compagnies) ? row.compagnies : []),
    ...(Array.isArray(row?.offres) ? row.offres.map((o) => o?.compagnie) : []),
  ].map((c) => String(c || "").trim()).filter(Boolean);
  return [...new Set(list)];
}

/** Filtres cumulables du tableau détaillé. La période est appliquée par l'API. */
export function filtrerDetail(rows, filtres = FILTRES_VIDES) {
  const f = { ...FILTRES_VIDES, ...(filtres || {}) };
  return (rows || []).filter((row) => {
    if (!hasTag(row, "soumises")) return false;
    if (f.tag && !matchTag(row, f.tag)) return false;
    if (f.gestionnaire !== "all") {
      if (f.gestionnaire === NON_ATTRIBUE) {
        if (row?.gestionnaire_id) return false;
      } else if (row?.gestionnaire_id !== f.gestionnaire) return false;
    }
    if (f.agent !== "all" && (row?.agent_label || "") !== f.agent) return false;
    if (f.type !== "all" && (row?.form_type || "") !== f.type) return false;
    if (f.compagnie !== "all" && !compagniesDe(row).some((c) => c.toLowerCase() === f.compagnie.toLowerCase())) {
      return false;
    }
    if (f.traitement !== "all" && row?.statut_traitement !== f.traitement) return false;
    if (f.commercial !== "all" && commercialCode(row) !== f.commercial) return false;
    if (f.priorite !== "all") {
      if (f.priorite === "urgence_agent") {
        if (!row?.urgente) return false;
      } else if ((row?.priorite || "normal") !== f.priorite) return false;
    }
    return true;
  });
}

export function filtresActifs(filtres) {
  const f = { ...FILTRES_VIDES, ...(filtres || {}) };
  return Object.keys(FILTRES_VIDES).some((key) => f[key] !== FILTRES_VIDES[key]);
}

/** Demandes soumises sans gestionnaire, plus anciennes en premier (file d'attribution). */
export function listerNonAttribuees(rows) {
  const list = filtrerDetail(rows, { ...FILTRES_VIDES, gestionnaire: NON_ATTRIBUE });
  return [...list].sort((a, b) => {
    const da = String(a?.date_envoi || "");
    const db = String(b?.date_envoi || "");
    if (da !== db) return da.localeCompare(db);
    return String(a?.numero || "").localeCompare(String(b?.numero || ""), "fr");
  });
}

/** Tri du tableau B4 : la ligne « Non attribué » reste toujours en dernier. */
export function trierRepartition(lignes, key = "attribues", direction = "desc") {
  const items = [...(lignes || [])];
  const unassigned = items.filter((l) => l.id === NON_ATTRIBUE);
  const others = items.filter((l) => l.id !== NON_ATTRIBUE);
  const sign = direction === "asc" ? 1 : -1;
  others.sort((a, b) => {
    if (key === "nom") return sign * String(a.nom || "").localeCompare(String(b.nom || ""), "fr");
    const d = (Number(a[key]) || 0) - (Number(b[key]) || 0);
    if (d !== 0) return sign * d;
    return String(a.nom || "").localeCompare(String(b.nom || ""), "fr");
  });
  return [...others, ...unassigned];
}

export const STATS_MENSUELLES_MOIS = [6, 12];

export const STATS_MENSUELLES_SERIES = [
  { key: "recues", label: "Offres reçues", color: "#002FA7" },
  { key: "signees", label: "Offres signées", color: "#10b981" },
  { key: "non_signees", label: "Offres non signées", color: "#f43f5e" },
];

/** Paramètres de /demandes-offres/pilotage/mensuel : mêmes filtres que le pilotage. */
export function statsMensuellesParams({
  mois = 6, periode = "all", dateDe = "", dateA = "", conseiller = "all", filtres = FILTRES_VIDES, perimetre,
} = {}) {
  const f = { ...FILTRES_VIDES, ...(filtres || {}) };
  const params = { mois: STATS_MENSUELLES_MOIS.includes(Number(mois)) ? Number(mois) : 6, periode: periode || "all" };
  if (params.periode === "custom") {
    if (dateDe) params.date_de = dateDe;
    if (dateA) params.date_a = dateA;
  }
  if (perimetre) params.perimetre = perimetre;
  if (conseiller && conseiller !== "all") params.conseiller = conseiller;
  if (f.gestionnaire !== "all") params.gestionnaire = f.gestionnaire;
  if (f.type !== "all") params.form_type = f.type;
  if (f.compagnie !== "all") params.compagnie = f.compagnie;
  return params;
}

export function statsMensuellesVides(data) {
  const mois = Array.isArray(data?.mois) ? data.mois : [];
  return !mois.some((m) => STATS_MENSUELLES_SERIES.some((s) => Number(m?.[s.key]) > 0));
}

export function tauxSignatureLabel(taux) {
  return taux === null || taux === undefined ? "—" : `${String(taux).replace(".", ",")} %`;
}
