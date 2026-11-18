/** Helpers Rapport à imprimer (Planification). */

export const PLANIFICATION_VIRTUAL_PREFIX = "planif-analyse:";

export function isPdfClientDocument(doc) {
  if (!doc) return false;
  if (doc.virtual_planification || doc.is_planification) return true;
  const name = String(doc.original_filename || doc.filename || "").toLowerCase();
  const ctype = String(doc.content_type || "").toLowerCase();
  if (name.endsWith(".pdf")) return true;
  if (ctype.includes("pdf")) return true;
  if (ctype.startsWith("application/octet-stream") && doc.template_id) return true;
  return false;
}

export function isVirtualPlanificationId(id) {
  return String(id || "").startsWith(PLANIFICATION_VIRTUAL_PREFIX);
}

export function isPlanificationDocument(doc) {
  if (!doc) return false;
  if (doc.is_planification || doc.virtual_planification) return true;
  if (isVirtualPlanificationId(doc.id)) return true;
  const title = String(doc.title || "").toLowerCase();
  const filename = String(doc.original_filename || doc.filename || "").toLowerCase();
  const category = String(doc.category || "").toLowerCase();
  const checklist = String(doc.checklist_item || "").toLowerCase();
  if (title.includes("comparatif") || filename.startsWith("comparatif_rentes")) return false;
  if (title.startsWith("analyse de prévoyance") || title.startsWith("analyse de prevoyance")) return true;
  if (filename.startsWith("analyse_prevoyance")) return true;
  if (category.includes("analyse de prévoyance") || category.includes("analyse de prevoyance")) {
    return !filename.includes("comparatif");
  }
  if (checklist.includes("analyse de prévoyance") || checklist.includes("analyse de prevoyance")) {
    return !filename.includes("comparatif");
  }
  return false;
}

export function pickLatestPlanification(docs, preferredId) {
  const preferred = String(preferredId || "").trim();
  if (preferred) {
    const hit = (docs || []).find((d) => String(d?.id || "") === preferred);
    if (hit) return hit;
  }
  const plans = (docs || []).filter(isPlanificationDocument);
  if (!plans.length) return null;
  return [...plans].sort((a, b) => {
    const ca = String(a.created_at || "");
    const cb = String(b.created_at || "");
    if (ca !== cb) return ca < cb ? 1 : -1;
    return String(a.id || "") < String(b.id || "") ? 1 : -1;
  })[0];
}

const RANK_RULES = [
  [/imp[oô]t|declaration|déclaration/, 20],
  [/\bavs\b/, 30],
  [/r[eé]ponse recherche lpp|fonds de garantie/, 40],
  [/certificat lpp/, 50],
  [/\blpp\b/, 55],
  [/3e pilier|3[eè]me pilier|police 3e|\b3a\b|\b3b\b/, 60],
  [/offre/, 70],
];

function blob(doc) {
  return [
    doc?.category,
    doc?.checklist_item,
    doc?.template_id,
    doc?.original_filename,
    doc?.title,
  ]
    .map((v) => String(v || "").toLowerCase())
    .join(" ");
}

export function documentSortRank(doc) {
  const text = blob(doc);
  let rank = 900;
  for (const [re, value] of RANK_RULES) {
    if (re.test(text)) rank = Math.min(rank, value);
  }
  return [rank, String(doc?.created_at || ""), String(doc?.original_filename || doc?.id || "").toLowerCase()];
}

export function sortDocumentsForRapport(docs, preferredId) {
  const latest = pickLatestPlanification(docs, preferredId);
  const latestId = latest?.id ? String(latest.id) : "";
  const planIds = new Set(
    (docs || [])
      .filter(isPlanificationDocument)
      .map((d) => String(d.id || ""))
      .filter(Boolean),
  );
  if (latestId) planIds.add(latestId);
  const others = (docs || []).filter((d) => !planIds.has(String(d.id || "")));
  others.sort((a, b) => {
    const ra = documentSortRank(a);
    const rb = documentSortRank(b);
    for (let i = 0; i < ra.length; i += 1) {
      if (ra[i] < rb[i]) return -1;
      if (ra[i] > rb[i]) return 1;
    }
    return 0;
  });
  return latest ? [latest, ...others] : others;
}

export function normalizeDocumentIds(ids) {
  const out = [];
  const seen = new Set();
  for (const raw of ids || []) {
    const id = String(raw || "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

export function ensurePlanificationFirst(documentIds, docs, preferredId) {
  const latest = pickLatestPlanification(docs, preferredId);
  const latestId = latest?.id ? String(latest.id) : String(preferredId || "").trim();
  const planIds = new Set(
    (docs || []).filter(isPlanificationDocument).map((d) => String(d.id || "")).filter(Boolean),
  );
  if (latestId) planIds.add(latestId);
  const rest = normalizeDocumentIds(documentIds).filter(
    (id) => !planIds.has(id) && !isVirtualPlanificationId(id),
  );
  if (latestId) return [latestId, ...rest];
  return rest;
}

/** Ajoute un id en fin d'ordre s'il n'y est pas ; retire s'il est décoché. */
export function toggleOrderedId(orderedIds, docId, checked, { lockedId } = {}) {
  const id = String(docId || "").trim();
  if (!id) return normalizeDocumentIds(orderedIds);
  if (lockedId && id === String(lockedId)) {
    // Planification toujours sélectionnée.
    const current = normalizeDocumentIds(orderedIds).filter((x) => x !== id);
    return [String(lockedId), ...current];
  }
  const current = normalizeDocumentIds(orderedIds);
  if (checked) {
    if (current.includes(id)) return current;
    return [...current, id];
  }
  return current.filter((x) => x !== id);
}

export function moveOrderedId(orderedIds, docId, direction, { lockedId } = {}) {
  const ids = normalizeDocumentIds(orderedIds);
  const lock = lockedId ? String(lockedId) : "";
  const index = ids.indexOf(docId);
  if (index < 0) return ids;
  if (lock && docId === lock) return ids;
  const target = direction === "up" ? index - 1 : index + 1;
  if (target < 0 || target >= ids.length) return ids;
  if (lock && target === 0 && ids[0] === lock) return ids;
  const next = [...ids];
  const [row] = next.splice(index, 1);
  next.splice(target, 0, row);
  if (lock && next[0] !== lock) {
    const without = next.filter((x) => x !== lock);
    return [lock, ...without];
  }
  return next;
}

export function reorderOrderedIds(orderedIds, fromId, toId, { lockedId } = {}) {
  const ids = normalizeDocumentIds(orderedIds);
  const lock = lockedId ? String(lockedId) : "";
  if (lock && (fromId === lock || toId === lock)) return ids;
  const from = ids.indexOf(fromId);
  const to = ids.indexOf(toId);
  if (from < 0 || to < 0 || from === to) return ids;
  const next = [...ids];
  const [row] = next.splice(from, 1);
  next.splice(to, 0, row);
  if (lock && next[0] !== lock) {
    const without = next.filter((x) => x !== lock);
    return [lock, ...without];
  }
  return next;
}

export function rapportDownloadName(client) {
  const nom = String(client?.nom || "Client").replace(/[^A-Za-z0-9_-]+/g, "_") || "Client";
  const prenom = String(client?.prenom || "X").replace(/[^A-Za-z0-9_-]+/g, "_") || "X";
  return `Rapport_Planification_${nom}_${prenom}.pdf`;
}
