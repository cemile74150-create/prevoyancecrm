/**
 * Capacité de travail (demande d'offre LPP, schéma entreprise_46).
 *
 * Question : « Toutes les personnes assurées sont-elles en pleine capacité de travail ? »
 * - Oui : pleine capacité — masquer « Nature de l'incapacité de gain et depuis quand ? »,
 *   ne pas l'exiger, ne pas envoyer une saisie précédente.
 * - Non : afficher le champ et le rendre obligatoire (il bloque Suivant tant qu'il est vide).
 */

export const INCAPACITE_GAIN_LABEL = "Nature de l'incapacité de gain et depuis quand ?";

/** Evaluate Gravity-Forms style show_when against current values. */
export function isFieldVisible(field, values) {
  const sw = field?.show_when;
  if (!sw || !Array.isArray(sw.rules) || !sw.rules.length) return true;
  const results = sw.rules.map((rule) => {
    const raw = values?.[rule.field];
    const expected = rule.value;
    if (Array.isArray(raw)) {
      return raw.includes(expected);
    }
    const actual = raw == null ? "" : String(raw);
    if (rule.op === "isnot") return actual !== expected;
    return actual === expected;
  });
  return (sw.logic || "all") === "any" ? results.some(Boolean) : results.every(Boolean);
}

export function incapaciteField(fields) {
  return (fields || []).find((field) => (field?.label || "") === INCAPACITE_GAIN_LABEL) || null;
}

/** Efface la nature d'incapacité quand le champ est masqué (réponse Oui, ou pas encore Non). */
export function omitIncapaciteWhenHidden(schema, values) {
  const src = values || {};
  const field = incapaciteField(schema?.fields);
  if (!field || isFieldVisible(field, src)) return src;
  const name = field.name || field.id;
  if (!name) return src;
  const commentKey = `${name}__comment`;
  const hasText = String(src[name] ?? "").trim() !== "";
  const hasComment = String(src[commentKey] ?? "").trim() !== "";
  if (!hasText && !hasComment) return src;
  const next = { ...src };
  if (hasText) next[name] = "";
  if (hasComment) next[commentKey] = "";
  return next;
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
