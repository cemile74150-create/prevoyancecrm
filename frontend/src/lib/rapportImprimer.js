/** Helpers Rapport à imprimer (Planification). */

export function isPdfClientDocument(doc) {
  if (!doc) return false;
  const name = String(doc.original_filename || doc.filename || "").toLowerCase();
  const ctype = String(doc.content_type || "").toLowerCase();
  if (name.endsWith(".pdf")) return true;
  if (ctype.includes("pdf")) return true;
  if (ctype.startsWith("application/octet-stream") && doc.template_id) return true;
  return false;
}

const RANK_RULES = [
  [/analyse de pr[eé]voyance|planification|comparatif/, 10],
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

export function sortDocumentsForRapport(docs) {
  return [...(docs || [])].sort((a, b) => {
    const ra = documentSortRank(a);
    const rb = documentSortRank(b);
    for (let i = 0; i < ra.length; i += 1) {
      if (ra[i] < rb[i]) return -1;
      if (ra[i] > rb[i]) return 1;
    }
    return 0;
  });
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

/** Ajoute un id en fin d'ordre s'il n'y est pas ; retire s'il est décoché. */
export function toggleOrderedId(orderedIds, docId, checked) {
  const id = String(docId || "").trim();
  if (!id) return normalizeDocumentIds(orderedIds);
  const current = normalizeDocumentIds(orderedIds);
  if (checked) {
    if (current.includes(id)) return current;
    return [...current, id];
  }
  return current.filter((x) => x !== id);
}

export function moveOrderedId(orderedIds, docId, direction) {
  const ids = normalizeDocumentIds(orderedIds);
  const index = ids.indexOf(docId);
  if (index < 0) return ids;
  const target = direction === "up" ? index - 1 : index + 1;
  if (target < 0 || target >= ids.length) return ids;
  const next = [...ids];
  const [row] = next.splice(index, 1);
  next.splice(target, 0, row);
  return next;
}

export function reorderOrderedIds(orderedIds, fromId, toId) {
  const ids = normalizeDocumentIds(orderedIds);
  const from = ids.indexOf(fromId);
  const to = ids.indexOf(toId);
  if (from < 0 || to < 0 || from === to) return ids;
  const next = [...ids];
  const [row] = next.splice(from, 1);
  next.splice(to, 0, row);
  return next;
}

export function rapportDownloadName(client) {
  const nom = String(client?.nom || "Client").replace(/[^A-Za-z0-9_-]+/g, "_") || "Client";
  const prenom = String(client?.prenom || "X").replace(/[^A-Za-z0-9_-]+/g, "_") || "X";
  return `Rapport_Planification_${nom}_${prenom}.pdf`;
}
