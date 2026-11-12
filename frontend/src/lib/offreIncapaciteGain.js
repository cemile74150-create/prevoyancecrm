/**
 * Capacité de travail (demande d'offre LPP, schéma entreprise_46) +
 * moteur générique de visibilité Gravity Forms (`show_when`).
 *
 * Question : « Toutes les personnes assurées sont-elles en pleine capacité de travail ? »
 * - Oui : pleine capacité — masquer « Nature de l'incapacité de gain et depuis quand ? »,
 *   ne pas l'exiger, ne pas envoyer une saisie précédente.
 * - Non : afficher le champ et le rendre obligatoire (il bloque Suivant tant qu'il est vide).
 */

const FIELD_COMMENT_SUFFIX = "__comment";

export const INCAPACITE_GAIN_LABEL = "Nature de l'incapacité de gain et depuis quand ?";

function parentAnswered(raw) {
  if (Array.isArray(raw)) return raw.length > 0;
  return raw != null && String(raw).trim() !== "";
}

function parseRuleNumber(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const text = String(value).trim().replace(/'/g, "").replace(/\s/g, "").replace(",", ".");
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

function ruleMatches(rule, values) {
  const raw = values?.[rule.field];
  const expected = rule.value;
  const op = rule.op || "is";
  if (op === ">" || op === "<" || op === ">=" || op === "<=") {
    const leftRaw = Array.isArray(raw) ? raw[0] : raw;
    const left = parseRuleNumber(leftRaw);
    const right = parseRuleNumber(expected);
    if (left == null || right == null) return false;
    if (op === ">") return left > right;
    if (op === "<") return left < right;
    if (op === ">=") return left >= right;
    return left <= right;
  }
  if (Array.isArray(raw)) return raw.includes(expected);
  const actual = raw == null ? "" : String(raw);
  if (op === "isnot") return actual !== expected;
  return actual === expected;
}

/** Evaluate Gravity-Forms style show_when against current values. */
export function isFieldVisible(field, values) {
  const sw = field?.show_when;
  if (!sw || !Array.isArray(sw.rules) || !sw.rules.length) return true;
  const results = sw.rules.map((rule) => ruleMatches(rule, values));
  return (sw.logic || "all") === "any" ? results.some(Boolean) : results.every(Boolean);
}

/** True when every show_when parent has an explicit answer (safe to clear children). */
export function showWhenParentsAnswered(field, values) {
  const rules = field?.show_when?.rules;
  if (!Array.isArray(rules) || !rules.length) return false;
  return rules.every((rule) => parentAnswered(values?.[rule.field]));
}

/**
 * Section headers without their own show_when stay visible only if at least one
 * following non-section field on the same page is visible.
 */
export function isSectionVisible(sectionField, fields, values) {
  if (!isFieldVisible(sectionField, values)) return false;
  const list = fields || [];
  const idx = list.indexOf(sectionField);
  if (idx < 0) return true;
  const page = sectionField.page || 1;
  let sawChild = false;
  for (let i = idx + 1; i < list.length; i += 1) {
    const field = list[i];
    if ((field.page || 1) !== page) break;
    if (field.type === "section") break;
    if (field.type === "html" || field.type === "hidden") continue;
    sawChild = true;
    if (isFieldVisible(field, values)) return true;
  }
  // No interactive children → keep section if its own show_when passed.
  return !sawChild;
}

/** Field should be rendered (respects show_when + empty sections). */
export function isRenderableField(field, fields, values) {
  if ((field?.type || "") === "section") {
    return isSectionVisible(field, fields, values);
  }
  return isFieldVisible(field, values);
}

export function incapaciteField(fields) {
  return (fields || []).find((field) => (field?.label || "") === INCAPACITE_GAIN_LABEL) || null;
}

function isEmptyValue(val) {
  if (val == null) return true;
  if (typeof val === "string") return !val.trim();
  if (Array.isArray(val)) return val.length === 0;
  return false;
}

/**
 * Clear values of fields hidden by an explicit parent answer.
 * Does not wipe saved answers when parents are still empty (réouverture dossier).
 */
export function omitHiddenFieldValues(schema, values) {
  const src = values || {};
  const fields = schema?.fields || [];
  if (!fields.length) return src;
  let next = null;
  for (const field of fields) {
    const type = field?.type || "text";
    if (type === "section" || type === "html" || type === "hidden") continue;
    if (isFieldVisible(field, src)) continue;
    if (!showWhenParentsAnswered(field, src)) continue;
    const name = field.name || field.id;
    if (!name) continue;
    const commentKey = `${name}${FIELD_COMMENT_SUFFIX}`;
    const hasText = !isEmptyValue(src[name]);
    const hasComment = !isEmptyValue(src[commentKey]);
    if (!hasText && !hasComment) continue;
    if (!next) next = { ...src };
    if (hasText) next[name] = Array.isArray(src[name]) ? [] : "";
    if (hasComment) next[commentKey] = "";
  }
  return next || src;
}

/** Efface la nature d'incapacité quand le champ est masqué par une réponse explicite. */
export function omitIncapaciteWhenHidden(schema, values) {
  return omitHiddenFieldValues(schema, values);
}

/** Bloque Suivant seulement si Non est coché et que la nature d'incapacité est vide. */
export function incapaciteBlocksNext(fields, values, page) {
  const field = incapaciteField(fields);
  if (!field?.required) return false;
  if ((field.page || 1) !== page) return false;
  if (!isFieldVisible(field, values || {})) return false;
  const name = field.name || field.id;
  return String((values || {})[name] ?? "").trim() === "";
}
