/**
 * Sync Civilité ↔ Sexe for demande d'offre schemas and legacy wizard.
 * CRM stores Homme/Femme; company forms often use Monsieur/Madame + Masculin/Féminin.
 */

import { foldLabel } from "./offreNationalitePermis";

const MALE_TOKENS = new Set([
  "monsieur", "mr", "m", "homme", "masculin", "male", "h",
]);
const FEMALE_TOKENS = new Set([
  "madame", "mme", "mlle", "mademoiselle", "femme", "feminin", "female", "f",
]);

const CIVILITE_MALE_PREFS = ["Monsieur", "M.", "Mr"];
const CIVILITE_FEMALE_PREFS = ["Madame", "Mme", "Mlle"];
const SEXE_MALE_PREFS = ["Masculin", "Homme", "M", "Male"];
const SEXE_FEMALE_PREFS = ["Féminin", "Femme", "F", "Female"];

/** @returns {"M"|"F"|null} */
export function genderKeyFromValue(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const folded = foldLabel(raw).replace(/\./g, "").replace(/\s+/g, "");
  if (!folded) return null;
  if (MALE_TOKENS.has(folded)) return "M";
  if (FEMALE_TOKENS.has(folded)) return "F";
  if (folded.includes("masculin") || folded === "homme") return "M";
  if (folded.includes("feminin") || folded === "femme") return "F";
  if (folded.startsWith("monsieur") || folded === "mr") return "M";
  if (folded.startsWith("madame") || folded.startsWith("mme")) return "F";
  return null;
}

function optionList(fieldOrOptions) {
  if (Array.isArray(fieldOrOptions)) {
    return fieldOrOptions.filter((o) => o != null && String(o).trim() !== "").map(String);
  }
  return (fieldOrOptions?.options || [])
    .filter((o) => o != null && String(o).trim() !== "")
    .map(String);
}

function pickPreferred(options, prefs) {
  if (!options.length) return prefs[0] || "";
  for (const pref of prefs) {
    const hit = options.find((o) => foldLabel(o) === foldLabel(pref));
    if (hit) return hit;
  }
  for (const pref of prefs) {
    const key = genderKeyFromValue(pref);
    const hit = options.find((o) => genderKeyFromValue(o) === key);
    if (hit) return hit;
  }
  return options[0] || prefs[0] || "";
}

/** Resolve a Monsieur/Madame (or schema option) for a gender key. */
export function civiliteForGender(gender, fieldOrOptions) {
  if (gender !== "M" && gender !== "F") return "";
  const options = optionList(fieldOrOptions);
  const prefs = gender === "M" ? CIVILITE_MALE_PREFS : CIVILITE_FEMALE_PREFS;
  return pickPreferred(options.length ? options : prefs, prefs);
}

/** Resolve Homme/Femme or Masculin/Féminin for a gender key. */
export function sexeForGender(gender, fieldOrOptions) {
  if (gender !== "M" && gender !== "F") return "";
  const options = optionList(fieldOrOptions);
  const prefs = gender === "M" ? SEXE_MALE_PREFS : SEXE_FEMALE_PREFS;
  return pickPreferred(options.length ? options : prefs, prefs);
}

/** Map any CRM / form gender token onto a field's option list. */
export function matchGenderOption(value, fieldOrOptions, kind = "auto") {
  const gender = genderKeyFromValue(value);
  if (!gender) return "";
  if (kind === "civilite") return civiliteForGender(gender, fieldOrOptions);
  if (kind === "sexe") return sexeForGender(gender, fieldOrOptions);
  const options = optionList(fieldOrOptions);
  if (!options.length) {
    return kind === "civilite"
      ? civiliteForGender(gender, [])
      : sexeForGender(gender, []);
  }
  // Prefer civilité-style options when present, else sexe-style.
  const looksCivilite = options.some((o) => {
    const f = foldLabel(o);
    return f.includes("monsieur") || f.includes("madame") || f === "m." || f === "mme";
  });
  return looksCivilite
    ? civiliteForGender(gender, options)
    : sexeForGender(gender, options);
}

export function isCiviliteField(field) {
  const lab = foldLabel(field?.label);
  if (!lab) return false;
  if (lab.startsWith("civilite") || lab === "titre") return true;
  return false;
}

export function isSexeField(field) {
  const lab = foldLabel(field?.label);
  return lab === "sexe";
}

/**
 * Pair each Civilité with the next Sexe field (multi-assuré forms).
 */
export function findCiviliteSexePairs(fields) {
  const pairs = [];
  let pending = null;
  for (const field of fields || []) {
    if (field?.type === "section" || field?.type === "html") continue;
    if (isCiviliteField(field)) {
      pending = field;
      continue;
    }
    if (pending && isSexeField(field)) {
      pairs.push({ civilite: pending, sexe: field });
      pending = null;
    }
  }
  return pairs;
}

/**
 * Sync Civilité → Sexe (and Sexe → Civilité when source is sexe or fill-missing).
 * @param {{ sourceFieldName?: string|null, fillMissingOnly?: boolean }} [opts]
 */
export function applyCiviliteSexeRules(schema, values, opts = {}) {
  const { sourceFieldName = null, fillMissingOnly = false } = opts;
  const pairs = findCiviliteSexePairs(schema?.fields || []);
  if (!pairs.length) return values;
  const next = { ...(values || {}) };
  let changed = false;

  for (const { civilite, sexe } of pairs) {
    const civName = civilite.name || civilite.id;
    const sexName = sexe.name || sexe.id;
    if (!civName || !sexName) continue;

    const civVal = next[civName];
    const sexVal = next[sexName];
    const civGender = genderKeyFromValue(civVal);
    const sexGender = genderKeyFromValue(sexVal);
    const civEmpty = civVal == null || String(civVal).trim() === "";
    const sexEmpty = sexVal == null || String(sexVal).trim() === "";

    const sourceIsCiv = sourceFieldName === civName;
    const sourceIsSex = sourceFieldName === sexName;
    const fillBoth = !sourceFieldName;

    if (sourceIsCiv || (fillBoth && civGender && (sexEmpty || sexGender !== civGender))) {
      if (civGender && (!fillMissingOnly || sexEmpty)) {
        const desired = sexeForGender(civGender, sexe);
        if (desired && String(next[sexName] ?? "") !== desired) {
          next[sexName] = desired;
          changed = true;
        }
      }
      continue;
    }

    if (sourceIsSex || (fillBoth && sexGender && civEmpty)) {
      if (sexGender && (!fillMissingOnly || civEmpty)) {
        const desired = civiliteForGender(sexGender, civilite);
        if (desired && String(next[civName] ?? "") !== desired) {
          next[civName] = desired;
          changed = true;
        }
      }
    }
  }

  return changed ? next : values;
}

/**
 * Normalize CRM civilite/sexe onto schema option vocabularies before writing.
 */
export function normalizeCrmCiviliteSexe(client, civiliteField, sexeField) {
  const rawCiv = client?.civilite || "";
  const rawSex = client?.sexe || "";
  const gender =
    genderKeyFromValue(rawCiv)
    || genderKeyFromValue(rawSex)
    || null;
  return {
    civilite: gender
      ? civiliteForGender(gender, civiliteField || CIVILITE_MALE_PREFS.concat(CIVILITE_FEMALE_PREFS))
      : "",
    sexe: gender
      ? sexeForGender(gender, sexeField || SEXE_MALE_PREFS.concat(SEXE_FEMALE_PREFS))
      : "",
    gender,
  };
}

/** Legacy wizard: Homme/Femme + Monsieur/Madame. */
export function syncLegacyCiviliteSexe(civilite, sexe, changed = "civilite") {
  if (changed === "civilite") {
    const g = genderKeyFromValue(civilite);
    if (!g) return { civilite, sexe };
    return { civilite, sexe: sexeForGender(g, ["Homme", "Femme"]) };
  }
  if (changed === "sexe") {
    const g = genderKeyFromValue(sexe);
    if (!g) return { civilite, sexe };
    return { civilite: civiliteForGender(g, ["Monsieur", "Madame"]), sexe };
  }
  const g = genderKeyFromValue(civilite) || genderKeyFromValue(sexe);
  if (!g) return { civilite, sexe };
  return {
    civilite: civiliteForGender(g, ["Monsieur", "Madame"]),
    sexe: sexeForGender(g, ["Homme", "Femme"]),
  };
}
