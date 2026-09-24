/** Helpers partagés pour les rappels CRM. */

export const RAPPEL_STATUT_LABEL = {
  a_faire: "À faire",
  en_attente: "En attente",
  termine: "Terminé",
  echeance_passee: "Échéance passée",
};

export const RAPPEL_STATUT_STYLE = {
  a_faire: "text-[#002FA7] bg-[#002FA7]/10 border-[#002FA7]/20",
  en_attente: "text-amber-800 bg-amber-50 border-amber-200",
  termine: "text-slate-600 bg-slate-50 border-slate-200",
  echeance_passee: "text-red-800 bg-red-50 border-red-200",
};

/** Pastilles calendrier (statut effectif). */
export const RAPPEL_CALENDAR_CHIP = {
  echeance_passee: "bg-red-100 text-red-900 border-red-200 hover:bg-red-200/80",
  a_faire: "bg-amber-100 text-amber-950 border-amber-200 hover:bg-amber-200/70",
  en_attente: "bg-[#002FA7]/10 text-[#002FA7] border-[#002FA7]/25 hover:bg-[#002FA7]/15",
  termine: "bg-emerald-100 text-emerald-900 border-emerald-200 hover:bg-emerald-200/70",
};

export const WEEKDAY_LABELS_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

/** Statut stocké en base (a_faire | en_attente | termine). */
export function rappelStoredStatut(r) {
  const raw = String(r?.statut || "").toLowerCase();
  if (raw === "en_attente") return "en_attente";
  if (raw === "termine" || r?.done) return "termine";
  if (raw === "a_faire") return "a_faire";
  return r?.done ? "termine" : "a_faire";
}

/** Datetime d'échéance locale, ou null. */
export function rappelDueDate(r) {
  const dateS = String(r?.date || "").slice(0, 10);
  if (!dateS) return null;
  const heureS = r?.heure ? String(r.heure).slice(0, 5) : "09:00";
  const dt = new Date(`${dateS}T${heureS}:00`);
  return Number.isFinite(dt.getTime()) ? dt : null;
}

/** True si échéance dépassée et rappel encore « à faire ». */
export function rappelIsOverdue(r, now = new Date()) {
  if (r?.is_echeance_passee === true) return true;
  if (rappelStoredStatut(r) !== "a_faire") return false;
  const due = rappelDueDate(r);
  if (!due) return false;
  return now.getTime() > due.getTime();
}

/** Statut affiché (inclut echeance_passee calculé automatiquement). */
export function rappelStatutEffectif(r, now = new Date()) {
  const stored = rappelStoredStatut(r);
  if (stored === "a_faire" && rappelIsOverdue(r, now)) return "echeance_passee";
  if (r?.statut_effectif === "echeance_passee") return "echeance_passee";
  return stored;
}

export function formatRappelDateFr(iso) {
  if (!iso) return "—";
  try {
    return new Date(`${String(iso).slice(0, 10)}T12:00:00`).toLocaleDateString("fr-CH");
  } catch {
    return iso;
  }
}

export function formatRappelDateTimeFr(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (!Number.isFinite(d.getTime())) return formatRappelDateFr(iso);
    return d.toLocaleString("fr-CH", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return formatRappelDateFr(iso);
  }
}

/** « 8 sept. 2026 à 09:14 » (locale fr). */
export function formatRappelCreatedAtFr(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (!Number.isFinite(d.getTime())) return "";
    const datePart = d.toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    const timePart = d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    return `${datePart} à ${timePart}`;
  } catch {
    return "";
  }
}

/** Nom affiché du créateur (legacy author inclus). */
export function rappelCreatorName(r) {
  const name = (r?.created_by_name || r?.author || "").trim();
  return name || null;
}

/** Id créateur (nouveau + legacy created_by). */
export function rappelCreatorId(r) {
  const id = (r?.created_by_user_id || r?.created_by || "").trim();
  return id || null;
}

/**
 * Ligne d'attribution : « Créé par Cemile Demirtas · le 8 sept. 2026 à 09:14 »
 * Legacy sans nom → « Créé par : inconnu » (+ date si dispo).
 */
export function formatRappelAttributionLine(r) {
  const name = rappelCreatorName(r) || "inconnu";
  const when = formatRappelCreatedAtFr(r?.created_at);
  const namePart = name === "inconnu" ? "Créé par : inconnu" : `Créé par ${name}`;
  if (!when) return namePart;
  return `${namePart} · le ${when}`;
}

/** Filtre Mes rappels côté client (legacy sans id exclus). */
export function isRappelCreatedByUser(r, accountId) {
  const me = (accountId || "").trim();
  if (!me) return false;
  return rappelCreatorId(r) === me;
}

/** Entrées d'historique e-mail / relances pour affichage. */
export function rappelEmailHistoryEntries(rappel) {
  const hist = Array.isArray(rappel?.email_history) ? [...rappel.email_history] : [];
  return hist
    .filter((h) => h && (h.sent_at || h.status))
    .sort((a, b) => String(a.sent_at || "").localeCompare(String(b.sent_at || "")));
}

export function rappelEmailHistoryLabel(entry) {
  if (!entry) return "E-mail";
  if (entry.label) return entry.label;
  if (entry.kind === "relance") {
    return entry.status === "failed" ? "Relance automatique (échec)" : "Relance automatique";
  }
  return entry.status === "failed" ? "E-mail de rappel (échec)" : "E-mail de rappel";
}

/** +N jours calendaires à partir d'une date ISO YYYY-MM-DD. */
export function addDaysIso(isoDate, days) {
  const base = String(isoDate || "").slice(0, 10);
  if (!base) return "";
  const dt = new Date(`${base}T12:00:00`);
  if (!Number.isFinite(dt.getTime())) return "";
  dt.setDate(dt.getDate() + days);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function toIsoDate(d) {
  if (!(d instanceof Date) || !Number.isFinite(d.getTime())) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseIsoDate(iso) {
  const s = String(iso || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const dt = new Date(`${s}T12:00:00`);
  return Number.isFinite(dt.getTime()) ? dt : null;
}

export function startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1, 12, 0, 0);
}

export function startOfWeekMonday(d) {
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12, 0, 0);
  const day = dt.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  dt.setDate(dt.getDate() + diff);
  return dt;
}

export function addMonths(d, n) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1, 12, 0, 0);
}

export function addDays(d, n) {
  const dt = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12, 0, 0);
  dt.setDate(dt.getDate() + n);
  return dt;
}

export function isSameDay(a, b) {
  return (
    a instanceof Date
    && b instanceof Date
    && a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
  );
}

/** Grille mois : 42 jours (6 semaines) à partir du lundi avant le 1er. */
export function buildMonthGrid(cursor) {
  const first = startOfMonth(cursor);
  const gridStart = startOfWeekMonday(first);
  const days = [];
  for (let i = 0; i < 42; i += 1) {
    const day = addDays(gridStart, i);
    days.push({
      date: day,
      iso: toIsoDate(day),
      inMonth: day.getMonth() === cursor.getMonth(),
    });
  }
  return days;
}

/** 7 jours Lun→Dim de la semaine du curseur. */
export function buildWeekDays(cursor) {
  const start = startOfWeekMonday(cursor);
  return Array.from({ length: 7 }, (_, i) => {
    const day = addDays(start, i);
    return { date: day, iso: toIsoDate(day), inMonth: true };
  });
}

export function formatPeriodTitle(cursor, mode) {
  if (mode === "day") {
    return cursor.toLocaleDateString("fr-FR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  }
  if (mode === "week") {
    const start = startOfWeekMonday(cursor);
    const end = addDays(start, 6);
    const a = start.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
    const b = end.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
    return `${a} – ${b}`;
  }
  const label = cursor.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** Map isoDate → rappels triés par heure. */
export function groupRappelsByIsoDate(rappels) {
  const map = new Map();
  for (const r of rappels || []) {
    const iso = String(r?.date || "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) continue;
    if (!map.has(iso)) map.set(iso, []);
    map.get(iso).push(r);
  }
  for (const [, list] of map) {
    list.sort((a, b) => {
      const ha = a.heure ? String(a.heure).slice(0, 5) : "99:99";
      const hb = b.heure ? String(b.heure).slice(0, 5) : "99:99";
      if (ha !== hb) return ha.localeCompare(hb);
      return String(a.id || "").localeCompare(String(b.id || ""));
    });
  }
  return map;
}

export function filterRappelsForCalendar(rappels, { statusFilter = "all", authorFilter = "all", now = new Date() } = {}) {
  return (rappels || []).filter((r) => {
    if (authorFilter && authorFilter !== "all") {
      const author = rappelCreatorName(r) || "—";
      if (author !== authorFilter) return false;
    }
    if (!statusFilter || statusFilter === "all") return true;
    const stored = rappelStoredStatut(r);
    const effectif = rappelStatutEffectif(r, now);
    if (statusFilter === "a_faire") return stored === "a_faire";
    if (statusFilter === "en_attente") return stored === "en_attente";
    if (statusFilter === "termine") return stored === "termine";
    if (statusFilter === "echeance_passee") return effectif === "echeance_passee";
    return true;
  });
}

export function uniqueRappelAuthors(rappels) {
  const set = new Set();
  for (const r of rappels || []) {
    const a = (rappelCreatorName(r) || "").trim();
    if (a) set.add(a);
  }
  return [...set].sort((x, y) => x.localeCompare(y, "fr"));
}

export function rappelCalendarLabel(r) {
  const heure = r?.heure ? String(r.heure).slice(0, 5) : "";
  const client = (r?.client_name || "Client").trim() || "Client";
  const titre = (r?.titre || "Rappel").trim() || "Rappel";
  return heure ? `${heure} · ${client} — ${titre}` : `${client} — ${titre}`;
}
