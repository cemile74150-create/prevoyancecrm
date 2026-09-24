/**
 * Gestion des conflits de doublon client (HTTP 409 CLIENT_DUPLICATE).
 */

export const DUPLICATE_CLIENT_MESSAGE =
  "Ce client existe déjà dans Leosoft. La création d'un nouveau profil est impossible. Veuillez utiliser le dossier existant.";

/**
 * @param {unknown} err — erreur axios
 * @returns {{ isDuplicate: boolean, message: string, existing: object|null, matches: object[] }}
 */
export function parseClientDuplicateError(err) {
  const detail = err?.response?.data?.detail;
  const status = err?.response?.status;

  if (status === 409 && detail && typeof detail === "object" && !Array.isArray(detail)) {
    const existing = detail.existing || null;
    const matches = Array.isArray(detail.matches) ? detail.matches : existing ? [existing] : [];
    return {
      isDuplicate: detail.code === "CLIENT_DUPLICATE" || Boolean(existing?.id),
      message: detail.message || DUPLICATE_CLIENT_MESSAGE,
      existing,
      matches,
    };
  }

  if (typeof detail === "string" && /existe déjà|doublon|duplicate/i.test(detail)) {
    return { isDuplicate: true, message: detail, existing: null, matches: [] };
  }

  const fallback =
    (typeof detail === "string" && detail) ||
    err?.message ||
    "Erreur lors de l'enregistrement";
  return { isDuplicate: false, message: fallback, existing: null, matches: [] };
}

export function clientDossierPath(existing) {
  if (!existing?.id) return "/clients";
  return `/clients/${existing.id}`;
}
