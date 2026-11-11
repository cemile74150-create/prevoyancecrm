/**
 * Contrôle d'accès par domaine e-mail (module Congés & absences).
 * Règle : e-mail normalisé (trim + minuscules) se termine par « @ » + domaine.
 * Miroir backend : backend/email_domain_access.py — garder les deux alignés.
 */

export const LEAVES_EMAIL_DOMAIN = "agencemendes.ch";

export function normalizeEmail(value) {
  return String(value || "").trim().toLowerCase();
}

/** True si l'e-mail (après normalisation) se termine par « @domain ». */
export function emailEndsWithDomain(email, domain = LEAVES_EMAIL_DOMAIN) {
  const normalized = normalizeEmail(email);
  const domainNorm = String(domain || "").trim().toLowerCase().replace(/^@/, "");
  if (!normalized || !domainNorm) return false;
  return normalized.endsWith(`@${domainNorm}`);
}

export function canAccessLeavesModule(user, domain = LEAVES_EMAIL_DOMAIN) {
  return emailEndsWithDomain(user?.email, domain);
}
