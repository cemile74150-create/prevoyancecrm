/** Helpers urgence / format pour les échéances 3e pilier. */

export const URGENCY = {
  urgent: {
    id: "urgent",
    label: "Urgentes",
    short: "urgentes",
    hint: "Dans moins de 30 jours",
    maxDays: 30,
    dot: "bg-red-500",
    badge: "bg-red-100 text-red-800 border-red-200",
    row: "border-l-4 border-l-red-500",
  },
  treat: {
    id: "treat",
    label: "À traiter",
    short: "à traiter",
    hint: "Dans moins de 3 mois",
    maxDays: 90,
    dot: "bg-orange-500",
    badge: "bg-orange-100 text-orange-800 border-orange-200",
    row: "border-l-4 border-l-orange-500",
  },
  soon: {
    id: "soon",
    label: "À venir",
    short: "à venir",
    hint: "Dans moins de 6 mois",
    maxDays: 180,
    dot: "bg-amber-400",
    badge: "bg-amber-100 text-amber-900 border-amber-200",
    row: "border-l-4 border-l-amber-400",
  },
  year: {
    id: "year",
    label: "Dans l'année",
    short: "dans l'année",
    hint: "Dans moins d'un an",
    maxDays: 365,
    dot: "bg-blue-500",
    badge: "bg-blue-100 text-blue-800 border-blue-200",
    row: "border-l-4 border-l-blue-500",
  },
};

export const URGENCY_ORDER = ["urgent", "treat", "soon", "year"];

export function getDaysLeft(item) {
  if (typeof item?.days_left === "number") return item.days_left;
  const raw = item?.echeance_3p;
  if (!raw) return null;
  try {
    const due = new Date(`${String(raw).slice(0, 10)}T00:00:00`);
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    return Math.round((due - now) / (24 * 60 * 60 * 1000));
  } catch {
    return null;
  }
}

export function getUrgency(item) {
  const days = getDaysLeft(item);
  if (days == null) return null;
  if (days < 30) return URGENCY.urgent; // inclut échéances passées
  if (days < 90) return URGENCY.treat;
  if (days < 180) return URGENCY.soon;
  if (days <= 365) return URGENCY.year;
  return null;
}

export function clientLabel(item) {
  return `${item?.prenom || ""} ${item?.nom || ""}`.trim() || "—";
}

export function formatEcheanceDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(`${String(iso).slice(0, 10)}T00:00:00`).toLocaleDateString("fr-CH");
  } catch {
    return String(iso).slice(0, 10);
  }
}

export function formatDaysLeft(days) {
  if (days == null) return "";
  if (days < 0) return `Dépassée (${Math.abs(days)} j)`;
  if (days === 0) return "Aujourd'hui";
  if (days === 1) return "Demain";
  return `Dans ${days} j`;
}

/** Ne garde que les échéances à surveiller (< 1 an ou déjà passées récemment affichées par l'API). */
export function filterAlertEcheances(items) {
  return (items || []).filter((item) => {
    if (item?.alert) return true;
    const days = getDaysLeft(item);
    return days != null && days <= 365;
  });
}

export function sortByUrgency(items) {
  return [...(items || [])].sort((a, b) => {
    const da = getDaysLeft(a);
    const db = getDaysLeft(b);
    if (da == null && db == null) return 0;
    if (da == null) return 1;
    if (db == null) return -1;
    return da - db;
  });
}

export function countByUrgency(items) {
  const counts = { urgent: 0, treat: 0, soon: 0, year: 0 };
  for (const item of items || []) {
    const u = getUrgency(item);
    if (u) counts[u.id] += 1;
  }
  return counts;
}

export function matchesEcheanceSearch(item, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return true;
  const hay = [
    clientLabel(item),
    item?.company,
    item?.policy_number,
    item?.numero_dossier,
    formatEcheanceDate(item?.echeance_3p),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(q);
}

export function echeanceRowKey(item, idx) {
  return `${item.client_id || item.id}-${item.company || ""}-${item.policy_number || ""}-${item.echeance_3p || idx}`;
}
