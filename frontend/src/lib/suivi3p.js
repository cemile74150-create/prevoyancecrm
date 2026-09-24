/** Constantes & helpers UI pour le module Suivi 3e Pilier */
import { formatDateFr, toIsoDate, toSwissDate } from "@/lib/dates";

export { formatDateFr, toIsoDate, toSwissDate };
export const SUIVI_3P_STATUTS = [
  "À analyser",
  "Analyse en cours",
  "Offre envoyée",
  "Signé",
  "Refusé",
  "Sans suite",
];

export const SUIVI_3P_STATUT_STYLE = {
  "À analyser": "bg-slate-500/10 text-slate-700 ring-1 ring-inset ring-slate-500/20",
  "Analyse en cours": "bg-sky-500/10 text-sky-800 ring-1 ring-inset ring-sky-500/25",
  "Offre envoyée": "bg-amber-500/10 text-amber-800 ring-1 ring-inset ring-amber-500/25",
  Signé: "bg-emerald-500/10 text-emerald-800 ring-1 ring-inset ring-emerald-500/25",
  Refusé: "bg-rose-500/10 text-rose-800 ring-1 ring-inset ring-rose-500/25",
  "Sans suite": "bg-zinc-500/10 text-zinc-600 ring-1 ring-inset ring-zinc-500/20",
};

export const SUIVI_3P_GEO_OPTIONS = [
  { id: "all", label: "Tous" },
  { id: "frontaliers", label: "Suivi 3P – Frontaliers" },
  { id: "suisses", label: "Suivi 3P – Suisses" },
];

export const SUIVI_3P_GEO_STYLE = {
  Frontalier: "bg-orange-500/10 text-orange-900 ring-1 ring-inset ring-orange-500/25",
  Suisse: "bg-[#002FA7]/10 text-[#002FA7] ring-1 ring-inset ring-[#002FA7]/25",
};

export function formatChf(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(n);
}

/** Colonnes disponibles pour l'export Excel Suivi 3P */
export const SUIVI_3P_EXPORT_COLUMNS = [
  { key: "conseiller", label: "Conseiller / Agent" },
  { key: "client", label: "Nom et prénom du client" },
  { key: "gain_fiscal", label: "Gain fiscal proposé (CHF)" },
  { key: "conjoint", label: "Nom et prénom du conjoint" },
  { key: "telephone", label: "Téléphone" },
  { key: "email", label: "E-mail" },
  { key: "date_courrier", label: "Date d'envoi du courrier" },
  { key: "statut", label: "Statut du suivi" },
  { key: "date_suivi", label: "Date du prochain suivi / échéance" },
  { key: "notes", label: "Commentaire / note" },
];

export const DEFAULT_SUIVI_3P_EXPORT_COLUMN_KEYS = SUIVI_3P_EXPORT_COLUMNS.map((c) => c.key);
