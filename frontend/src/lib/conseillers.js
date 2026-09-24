/** Normalise la liste GET /users/conseillers (string[] ou {name, finma_number}[]).
 * Source : utilisateurs actifs CRM (même base que la page Utilisateurs).
 *
 * Comparaisons / regroupements : toujours via normalizeConseillerKey.
 * Affichage : displayConseillerName (forme lisible, canonique si fusion).
 */

function stripAccents(s) {
  return String(s || "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "");
}

/** Clé stable : trim, espaces collapsés, accents retirés, minuscules. */
export function normalizeConseillerKey(name) {
  const s = String(name || "").trim().replace(/\s+/g, " ");
  if (!s) return "";
  return stripAccents(s).toLowerCase();
}

function letterCaseFlags(s) {
  const letters = [...s].filter((c) => /\p{L}/u.test(c));
  if (!letters.length) return { allUpper: false, allLower: false };
  const allUpper = letters.every((c) => c === c.toUpperCase() && c !== c.toLowerCase());
  const allLower = letters.every((c) => c === c.toLowerCase() && c !== c.toUpperCase());
  return { allUpper, allLower };
}

function displayScore(s) {
  const words = s.split(" ").filter(Boolean);
  const allCapsWords = words.filter((w) => /\p{L}/u.test(w) && w === w.toUpperCase() && w.length > 1).length;
  const titleLike = words.filter(
    (w) => w.length > 1 && w[0] === w[0].toUpperCase() && w.slice(1) === w.slice(1).toLowerCase(),
  ).length;
  const allLowerWords = words.filter((w) => /\p{L}/u.test(w) && w === w.toLowerCase()).length;
  return [allCapsWords, -titleLike, allLowerWords, -s.length];
}

function titleWords(s) {
  return s
    .split(" ")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(" ");
}

/** Choisit un libellé lisible parmi des variantes (même personne). */
export function displayConseillerName(...candidates) {
  const cleaned = candidates
    .map((c) => String(c ?? "").trim().replace(/\s+/g, " "))
    .filter(Boolean);
  if (!cleaned.length) return "Non attribué";
  cleaned.sort((a, b) => {
    const sa = displayScore(a);
    const sb = displayScore(b);
    return sa[0] - sb[0] || sa[1] - sb[1];
  });
  let best = cleaned[0];
  const { allUpper, allLower } = letterCaseFlags(best);
  if (allUpper || allLower) best = titleWords(best);
  return best;
}

/** Déduplique une liste de noms via la clé normalisée. */
export function uniqueConseillerNames(names) {
  const byKey = new Map();
  for (const raw of names || []) {
    const cleaned = String(raw || "").trim().replace(/\s+/g, " ");
    if (!cleaned) continue;
    const key = normalizeConseillerKey(cleaned);
    if (!key) continue;
    const prev = byKey.get(key);
    byKey.set(key, prev ? displayConseillerName(prev, cleaned) : displayConseillerName(cleaned));
  }
  return [...byKey.values()].sort((a, b) => a.localeCompare(b, "fr", { sensitivity: "base" }));
}

export function parseConseillerList(data) {
  const rows = Array.isArray(data) ? data : [];
  const byKey = new Map();
  for (const row of rows) {
    let name = "";
    let finma = "";
    if (typeof row === "string") {
      name = row.trim().replace(/\s+/g, " ");
    } else {
      name = String(row?.name || row?.conseiller || "").trim().replace(/\s+/g, " ");
      finma = String(row?.finma_number || "").trim();
    }
    if (!name) continue;
    const key = normalizeConseillerKey(name);
    if (!key) continue;
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, { name: displayConseillerName(name), finma_number: finma });
    } else {
      byKey.set(key, {
        name: displayConseillerName(prev.name, name),
        finma_number: prev.finma_number || finma,
      });
    }
  }
  return [...byKey.values()];
}

export function conseillerNames(list) {
  return parseConseillerList(list).map((r) => r.name);
}

export function finmaByConseillerName(list) {
  const map = {};
  for (const row of parseConseillerList(list)) {
    map[row.name] = row.finma_number || "";
    map[normalizeConseillerKey(row.name)] = row.finma_number || "";
  }
  return map;
}

export function lookupConseillerFinma(map, name) {
  const n = String(name || "").trim().replace(/\s+/g, " ");
  if (!n || !map) return "";
  return map[n] || map[normalizeConseillerKey(n)] || "";
}
