/**
 * Shared LeoSoft rule for demande d'offre schemas:
 * Nationalité = Suisse → Permis locked to « Aucun permis ».
 * Used by OffreSchemaForm so every form inherits the behaviour.
 */

/** Fold accents for label matching (prénom → prenom). */
export function foldLabel(label) {
  return String(label || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** Primary nationality field (not follow-up « Quelle est sa nationalité ? »). */
export function isPrimaryNationaliteField(field) {
  const lab = foldLabel(field?.label);
  if (!lab.includes("nationalite")) return false;
  if (lab.startsWith("quelle") || lab.includes("quelle est")) return false;
  return true;
}

/** Permis de séjour / Permis — exclude date, conduire, retrait. */
export function isPermisSejourField(field) {
  const lab = foldLabel(field?.label);
  if (!lab.includes("permis")) return false;
  if (lab.includes("conduire")) return false;
  if (lab.includes("retrait")) return false;
  if (lab.includes("date") && lab.includes("permis")) return false;
  return (
    lab === "permis" ||
    lab === "permis de sejour" ||
    lab.startsWith("permis de sejour") ||
    (lab.startsWith("permis") && !lab.includes("conduire"))
  );
}

/**
 * Pair each Nationalité with the next Permis de séjour field
 * (supports multi-assuré forms like pilier3 parent/enfant).
 */
export function findNationalitePermisPairs(fields) {
  const pairs = [];
  let pendingNat = null;
  for (const field of fields || []) {
    if (field?.type === "section" || field?.type === "html") continue;
    if (isPrimaryNationaliteField(field)) {
      pendingNat = field;
      continue;
    }
    if (pendingNat && isPermisSejourField(field)) {
      pairs.push({ nationalite: pendingNat, permis: field });
      pendingNat = null;
    }
  }
  return pairs;
}

const SWISS_NATIONALITY_VALUES = new Set(["suisse", "switzerland", "swiss"]);

export function isSwissNationality(value) {
  const v = foldLabel(value);
  if (!v) return false;
  if (SWISS_NATIONALITY_VALUES.has(v)) return true;
  // Minor variants: "Suisse (CH)", "CH - Suisse"
  if (/^suisse(\s*\(.*\))?$/.test(v)) return true;
  if (/^switzerland(\s*\(.*\))?$/.test(v)) return true;
  if (/^ch\s*[\/\-]\s*suisse$/.test(v)) return true;
  return false;
}

/** Exact option label for « Aucun permis », or literal for free-text fields. */
export function resolveAucunPermisValue(permisField) {
  const options = (permisField?.options || []).filter((o) => o != null && String(o).trim() !== "");
  const match = options.find((o) => {
    const f = foldLabel(o);
    return f === "aucun permis" || f.startsWith("aucun permis");
  });
  if (match != null) return String(match);
  // Select/radio without that option (e.g. ménage Suisse/Autre) → no fake value
  if (options.length > 0) return null;
  return "Aucun permis";
}

export function isAucunPermisValue(value, permisField) {
  const raw = value == null ? "" : String(value);
  if (!raw.trim()) return false;
  const aucun = resolveAucunPermisValue(permisField);
  if (aucun != null && raw === aucun) return true;
  const f = foldLabel(raw);
  return f === "aucun permis" || f.startsWith("aucun permis");
}

/**
 * Shared LeoSoft rule: Nationalité Suisse → Permis locked to « Aucun permis ».
 * Returns same reference when nothing changes.
 */
export function applyNationalitePermisRules(schema, values) {
  const pairs = findNationalitePermisPairs(schema?.fields || []);
  if (!pairs.length) return values;
  const next = { ...(values || {}) };
  let changed = false;
  for (const { nationalite, permis } of pairs) {
    const natName = nationalite.name || nationalite.id;
    const perName = permis.name || permis.id;
    if (!natName || !perName) continue;
    const natVal = next[natName];
    if (isSwissNationality(natVal)) {
      const target = resolveAucunPermisValue(permis);
      const desired = target != null ? target : "";
      if (String(next[perName] ?? "") !== String(desired)) {
        next[perName] = desired;
        changed = true;
      }
    } else if (natVal != null && String(natVal).trim() !== "") {
      // Foreign nationality: clear auto « Aucun permis » so user must choose
      if (isAucunPermisValue(next[perName], permis)) {
        next[perName] = "";
        changed = true;
      }
    }
  }
  return changed ? next : values;
}

export function isPermisLockedByNationalite(schema, values, fieldName) {
  if (!fieldName) return false;
  for (const { nationalite, permis } of findNationalitePermisPairs(schema?.fields || [])) {
    const perName = permis.name || permis.id;
    if (perName !== fieldName) continue;
    const natName = nationalite.name || nationalite.id;
    return isSwissNationality(values?.[natName]);
  }
  return false;
}
