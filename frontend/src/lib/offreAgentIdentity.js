/**
 * Identité AGENT DEMANDEUR — autofill + verrouillage depuis le profil session.
 * Aligné sur backend/offre_agent_identity.py (classification par label GF).
 */
import { foldLabel } from "./offreNationalitePermis";

export const MISSING_FINMA_MESSAGE =
  "Votre numéro FINMA n'est pas renseigné sur votre profil utilisateur. " +
  "Complétez-le dans Utilisateurs (ou demandez à un administrateur) avant d'envoyer une demande d'offre.";

/** @returns {"prenom"|"nom"|"email"|"finma"|"full_name"|null} */
export function classifyAgentField(label) {
  const lab = foldLabel(label)
    .replace(/[''`´]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!lab) return null;
  if (lab === "agent demandeur" || lab === "agent demandeur :" || lab === "informations sur l agent") {
    return null;
  }
  if (lab.includes("formulaire reserve")) return null;
  if (lab.includes("finma")) return "finma";
  if (lab.includes("recevrez")) return null;
  if (lab.includes("email") || lab.includes("e-mail") || lab.includes("courriel")) {
    if (lab.includes("agent") || lab.includes("votre adresse email")) return "email";
    return null;
  }
  if (lab.startsWith("id de l agent")) return null;
  if (lab.includes("prenom de l agent")) return "prenom";
  if (lab.includes("nom de l agent") && !lab.includes("prenom")) return "nom";
  if (lab.includes("prenom et nom") && lab.includes("agent")) return "full_name";
  return null;
}

export function isAgentIdentityField(field) {
  if (!field || ["section", "html", "file", "hidden"].includes(field.type)) return false;
  return classifyAgentField(field.label) != null;
}

export function agentIdentityFromUser(user) {
  if (!user) {
    return { prenom: "", nom: "", email: "", finma: "", label: "" };
  }
  let prenom = String(user.prenom || "").trim();
  let nom = String(user.nom || "").trim();
  const name = String(user.name || user.conseiller || "").trim();
  if (!prenom && !nom && name) {
    const parts = name.split(/\s+/);
    prenom = parts[0] || "";
    nom = parts.slice(1).join(" ") || "";
  }
  const email = String(user.email || "").trim();
  const finma = String(user.finma_number || "").trim();
  const label = `${prenom} ${nom}`.trim() || name;
  return { prenom, nom, email, finma, label };
}

export function schemaRequiresFinma(schema) {
  if (!schema?.fields?.length) return true; // legacy / inconnu → exiger
  let hasFinma = false;
  for (const field of schema.fields) {
    if (classifyAgentField(field?.label) === "finma") {
      hasFinma = true;
      if (field.required) return true;
    }
  }
  return hasFinma;
}

export function injectAgentIdentity(schema, values, identity, { overwrite = true } = {}) {
  const next = { ...(values || {}) };
  if (!schema?.fields?.length || !identity) return next;
  const roleValues = {
    prenom: identity.prenom || "",
    nom: identity.nom || "",
    email: identity.email || "",
    finma: identity.finma || "",
    full_name: identity.label || `${identity.prenom || ""} ${identity.nom || ""}`.trim(),
  };
  let changed = false;
  for (const field of schema.fields) {
    if (["section", "html", "file", "hidden"].includes(field?.type)) continue;
    const role = classifyAgentField(field?.label);
    if (!role) continue;
    const name = field.name || field.id;
    if (!name) continue;
    const val = roleValues[role] ?? "";
    const cur = next[name];
    const empty = cur == null || cur === "" || (Array.isArray(cur) && !cur.length);
    if (overwrite || empty) {
      if (next[name] !== val) {
        next[name] = val;
        changed = true;
      }
    }
  }
  // E-mail de réception GF
  if (identity.email) {
    for (const field of schema.fields) {
      if (["section", "html", "hidden"].includes(field?.type)) continue;
      const lab = foldLabel(field?.label);
      if (lab.includes("recevrez") && (lab.includes("email") || lab.includes("e-mail") || lab.includes("offre"))) {
        const name = field.name || field.id;
        if (!name) continue;
        const cur = next[name];
        const empty = cur == null || String(cur).trim() === "";
        if (overwrite || empty) {
          if (next[name] !== identity.email) {
            next[name] = identity.email;
            changed = true;
          }
        }
      }
    }
  }
  return changed ? next : values || {};
}

export function agentLockedFieldNames(schema) {
  const names = new Set();
  for (const field of schema?.fields || []) {
    if (!isAgentIdentityField(field)) continue;
    const name = field.name || field.id;
    if (name) names.add(name);
  }
  return names;
}

export function missingFinmaMessage(user, schema) {
  if (schema && !schemaRequiresFinma(schema)) return null;
  const finma = String(user?.finma_number || "").trim();
  if (finma) return null;
  return MISSING_FINMA_MESSAGE;
}
