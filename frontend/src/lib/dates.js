/**
 * Dates UI suisses (jj.mm.aaaa) ↔ stockage ISO (yyyy-mm-dd).
 * Accepte aussi les séparateurs / et - en saisie.
 *
 * Important : toSwissDate ne doit JAMAIS étendre une année à 2 chiffres
 * (ex. « 20 » → « 2020 ») — cela casse la saisie progressive (15.06.20…2018).
 * L'expansion yy → 19xx/20xx n'a lieu que dans toIsoDate (stockage / blur).
 *
 * Réparation : une ancienne saisie live avait préfixé « 20 » à une année
 * déjà (ou devenue) à 4 chiffres → 201971 / 202026. On retire ce préfixe.
 */

function pad2(n) {
  return String(n).padStart(2, "0");
}

/**
 * Corrige une année mangled « 20 » + AAAA (6 chiffres) → AAAA.
 * Ex. 201971 → 1971, 202026 → 2026. Laisse 4 chiffres intacts (2020, 1971…).
 */
export function repairMangledYear(y) {
  const s = String(y ?? "").trim();
  if (!/^20\d{4}$/.test(s)) return s;
  const rest = s.slice(2);
  const n = Number(rest);
  if (n >= 1000 && n <= 2100) return rest;
  return s;
}

/** yy → 19yy / 20yy (seuil 30, convention CRM). Uniquement pour conversion ISO. */
function expandShortYear(y) {
  const s = repairMangledYear(y);
  if (s.length !== 2) return s;
  return `${Number(s) <= 30 ? "20" : "19"}${s}`;
}

/**
 * Affichage / saisie : jj.mm.aaaa (chaîne vide si absente).
 * Ne force jamais une année à 4 chiffres à partir de 2 chiffres partiels.
 * Répare les années déjà mangled (6 chiffres type 201971).
 */
export function toSwissDate(value) {
  if (value == null || value === "") return "";
  const raw = String(value).trim();
  if (!raw) return "";

  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[3]}.${iso[2]}.${iso[1]}`;

  // Année mangled 6 chiffres : 10.02.201971 → 10.02.1971
  const mangled = raw.match(/^(\d{1,2})[./-](\d{1,2})[./-](20\d{4})$/);
  if (mangled) {
    const [, d, m, y] = mangled;
    const fixed = repairMangledYear(y);
    if (fixed !== y) return `${pad2(d)}.${pad2(m)}.${fixed}`;
  }

  const dmy = raw.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$/);
  if (dmy) {
    const [, d, m, y] = dmy;
    // Pas d'expansion ici : « 15.06.20 » reste « 15.06.20 » pendant la frappe.
    return `${pad2(d)}.${pad2(m)}.${y}`;
  }

  return raw;
}

/** Affichage libellé : jj.mm.aaaa ou "—". Normalise via ISO si possible. */
export function formatDateFr(value) {
  if (value == null || value === "") return "—";
  const iso = toIsoDate(value);
  if (iso) return toSwissDate(iso);
  return toSwissDate(value) || "—";
}

/** Stockage CRM / matching : yyyy-mm-dd (chaîne vide si absente ou invalide). */
export function toIsoDate(value) {
  if (value == null || value === "") return "";
  const raw = String(value).trim();
  if (!raw) return "";

  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;

  // Accepte aussi année mangled 6 chiffres avant normalisation
  const dmy = raw.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{2,6})$/);
  if (!dmy) return "";
  let [, d, m, y] = dmy;
  y = expandShortYear(y);
  const dd = Number(d);
  const mm = Number(m);
  const yy = Number(y);
  if (!(mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31 && yy >= 1000 && yy <= 9999)) return "";
  return `${String(yy).padStart(4, "0")}-${pad2(mm)}-${pad2(dd)}`;
}

/**
 * Normalise une saisie date au blur : jj.mm.aaaa si parseable, sinon brut.
 * Accepte années réelles (2010, 2018, …) sans plancher artificiel 2020.
 * Répare les années mangled (201971 → 1971).
 */
export function normalizeSwissDateInput(value) {
  if (value == null || value === "") return "";
  const raw = String(value).trim();
  if (!raw) return "";
  const iso = toIsoDate(raw);
  if (iso) return toSwissDate(iso);
  return toSwissDate(raw) || raw;
}
