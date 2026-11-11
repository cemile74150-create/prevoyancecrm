/** Helpers du fil de discussion demandes d'offres (pièces jointes). */

export const MAX_DISCUSSION_FILES = 15;
export const MAX_DISCUSSION_FILE_BYTES = 20 * 1024 * 1024;
export const DISCUSSION_ACCEPT =
  ".pdf,.png,.jpg,.jpeg,.gif,.webp,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.txt,.csv";

const ALLOWED_EXT = new Set(
  DISCUSSION_ACCEPT.split(",").map((item) => item.trim().replace(/^\./, "").toLowerCase())
);

export function fileExtension(name) {
  const base = String(name || "").split(/[/\\]/).pop() || "";
  const idx = base.lastIndexOf(".");
  return idx >= 0 ? base.slice(idx + 1).toLowerCase() : "";
}

/** Ajoute des fichiers sans doublon (nom+taille) ni dépassement de limite. */
export function mergeDiscussionFiles(current, incoming, max = MAX_DISCUSSION_FILES) {
  const list = [...(current || [])];
  const errors = [];
  (incoming || []).forEach((file) => {
    if (!file) return;
    const ext = fileExtension(file.name);
    if (!ALLOWED_EXT.has(ext)) {
      errors.push(`${file.name} : type non autorisé`);
      return;
    }
    if (typeof file.size === "number" && file.size > MAX_DISCUSSION_FILE_BYTES) {
      errors.push(`${file.name} : trop volumineux (max 20 Mo)`);
      return;
    }
    if (list.some((f) => f.name === file.name && f.size === file.size)) return;
    if (list.length >= max) {
      errors.push(`Maximum ${max} documents`);
      return;
    }
    list.push(file);
  });
  return { files: list, errors };
}

/** Envoi possible si texte non vide ou au moins une pièce. */
export function canSendDiscussion(texte, files) {
  return Boolean(String(texte || "").trim()) || (Array.isArray(files) && files.length > 0);
}
