// Congés & absences : mêmes règles que backend/leaves.py.
// Dates civiles « AAAA-MM-JJ » calculées en UTC pour éviter tout décalage de fuseau.

export const LEAVE_TYPES = [
  { id: "paid", label: "Congés payés" },
  { id: "unpaid", label: "Congé sans solde" },
  { id: "other", label: "Autre absence" },
];

export const STATUS_META = {
  pending: { label: "En attente", className: "bg-amber-50 text-amber-800 border-amber-200" },
  approved: { label: "Validée", className: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  rejected: { label: "Refusée", className: "bg-red-50 text-red-700 border-red-200" },
  cancelled: { label: "Annulée", className: "bg-slate-100 text-slate-600 border-slate-200" },
  cancellation_requested: { label: "Annulation demandée", className: "bg-violet-50 text-violet-800 border-violet-200" },
};

export const DAY_PART_LABELS = { full: "Journée entière", morning: "Matin", afternoon: "Après-midi" };

export const EVENT_LABELS = {
  created: "Demande déposée",
  approved: "Validée",
  rejected: "Refusée",
  cancelled: "Annulée par le collaborateur",
  cancellation_requested: "Annulation demandée",
  cancellation_accepted: "Annulation acceptée",
  cancellation_refused: "Annulation refusée",
};

export const CALCULATION_NOTE =
  "Durée indicative : jours ouvrés du lundi au vendredi, samedis et dimanches exclus. "
  + "Les jours fériés et les horaires individuels ne sont pas pris en compte.";

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function parseIsoDate(iso) {
  const m = ISO_RE.exec(String(iso || "").slice(0, 10));
  if (!m) return null;
  const t = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const d = new Date(t);
  if (d.getUTCMonth() !== Number(m[2]) - 1) return null;
  return d;
}

export function toIso(d) {
  return d.toISOString().slice(0, 10);
}

function addDays(d, n) {
  return new Date(d.getTime() + n * 86400000);
}

function isWorkingDay(d) {
  const wd = d.getUTCDay();
  return wd !== 0 && wd !== 6;
}

export function computeWorkingDays(startIso, endIso, startPart = "full", endPart = "full") {
  const start = parseIsoDate(startIso);
  const end = parseIsoDate(endIso);
  if (!start || !end || end < start) return 0;
  if (startIso === endIso) {
    if (!isWorkingDay(start)) return 0;
    return startPart === "full" ? 1 : 0.5;
  }
  let total = 0;
  for (let d = start; d <= end; d = addDays(d, 1)) {
    if (isWorkingDay(d)) total += 1;
  }
  if (startPart === "afternoon" && isWorkingDay(start)) total -= 0.5;
  if (endPart === "morning" && isWorkingDay(end)) total -= 0.5;
  return total;
}

/** Erreur de saisie à afficher, ou "" si la demande peut partir. */
export function validateLeaveForm({ leaveType, startDate, endDate, startPart, endPart }) {
  if (!leaveType) return "Choisissez un type d'absence.";
  const start = parseIsoDate(startDate);
  const end = parseIsoDate(endDate);
  if (!start) return "Indiquez la date de début.";
  if (!end) return "Indiquez la date de fin.";
  if (end < start) return "La date de fin doit être égale ou postérieure à la date de début.";
  if (startDate !== endDate) {
    if (startPart === "morning") return "Le premier jour ne peut commencer que le matin (journée entière) ou l'après-midi.";
    if (endPart === "afternoon") return "Le dernier jour ne peut se terminer que le soir (journée entière) ou à midi.";
  }
  if (computeWorkingDays(startDate, endDate, startPart, startDate === endDate ? startPart : endPart) <= 0) {
    return "La période choisie ne contient aucun jour ouvré (lundi à vendredi).";
  }
  return "";
}

export function formatDateFr(iso) {
  const m = ISO_RE.exec(String(iso || "").slice(0, 10));
  return m ? `${m[3]}.${m[2]}.${m[1]}` : "—";
}

export function formatDateTimeFr(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("fr-CH", { dateStyle: "short", timeStyle: "short" });
}

export function formatDays(n) {
  const v = Number(n) || 0;
  return `${String(v).replace(".", ",")} j`;
}

export function periodLabel(item) {
  if (!item) return "—";
  const sp = item.start_day_part || "full";
  const ep = item.end_day_part || "full";
  if (item.start_date === item.end_date) {
    return sp === "full" ? formatDateFr(item.start_date) : `${formatDateFr(item.start_date)} (${DAY_PART_LABELS[sp].toLowerCase()})`;
  }
  const from = `${formatDateFr(item.start_date)}${sp === "afternoon" ? " (après-midi)" : ""}`;
  const to = `${formatDateFr(item.end_date)}${ep === "morning" ? " (matin)" : ""}`;
  return `${from} → ${to}`;
}

export function leaveErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return fallback;
}

export function newClientRequestId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `req-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function currentMonth(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function shiftMonth(month, delta) {
  const [y, m] = month.split("-").map(Number);
  const idx = y * 12 + (m - 1) + delta;
  return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2, "0")}`;
}

export function monthLabel(month) {
  const d = parseIsoDate(`${month}-01`);
  if (!d) return month;
  const label = d.toLocaleDateString("fr-CH", { month: "long", year: "numeric", timeZone: "UTC" });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

/** Semaines lundi → dimanche couvrant le mois. */
export function monthGrid(month) {
  const first = parseIsoDate(`${month}-01`);
  if (!first) return [];
  const offset = (first.getUTCDay() + 6) % 7;
  let d = addDays(first, -offset);
  const weeks = [];
  for (let w = 0; w < 6; w += 1) {
    const days = [];
    for (let i = 0; i < 7; i += 1) {
      const iso = toIso(d);
      days.push({ iso, day: d.getUTCDate(), inMonth: iso.slice(0, 7) === month, weekend: i >= 5 });
      d = addDays(d, 1);
    }
    weeks.push(days);
    if (toIso(d).slice(0, 7) !== month) break;
  }
  return weeks;
}

/** Absences présentes ce jour-là, avec la demi-journée concernée. */
export function entriesForDay(items, iso) {
  return (items || [])
    .filter((e) => e.start_date <= iso && e.end_date >= iso)
    .map((e) => {
      let part = "full";
      if (e.start_date === e.end_date) part = e.start_day_part || "full";
      else if (iso === e.start_date && e.start_day_part === "afternoon") part = "afternoon";
      else if (iso === e.end_date && e.end_day_part === "morning") part = "morning";
      return { ...e, part };
    });
}

export function yearOptions(years, now = new Date()) {
  const y = now.getFullYear();
  return Array.from(new Set([y + 1, y, y - 1, ...(years || [])])).sort((a, b) => b - a);
}
