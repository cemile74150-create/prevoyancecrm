/** Helpers documents client (PDF vs Word). */

export function isWordDocument(doc) {
  if (!doc) return false;
  const name = String(doc.original_filename || doc.filename || "").toLowerCase();
  const ctype = String(doc.content_type || "").toLowerCase();
  return name.endsWith(".docx") || ctype.includes("wordprocessingml") || ctype.includes("msword");
}

/** Lettre AVS (et docs avec .docx compagnon) : téléchargement Word disponible. */
export function hasWordDownload(doc) {
  if (!doc) return false;
  if (doc.has_word_download || doc.docx_filename) return true;
  if (String(doc.template_id || "") === "lettre_avs") return true;
  return isWordDocument(doc);
}

/** Nom affiché dans les listes (sans extension technique pour la lettre AVS). */
export function documentDisplayName(doc) {
  const raw = (doc?.original_filename || doc?.title || "Document").trim();
  if (String(doc?.template_id || "") === "lettre_avs" || hasWordDownload(doc)) {
    return raw.replace(/\.(docx|pdf)$/i, "");
  }
  return raw;
}

/**
 * Même mécanisme que le formulaire rente future : blob PDF inline dans un nouvel onglet.
 * (La lettre AVS est stockée en PDF pour ce viewer ; le Word se télécharge à part.)
 */
export function openClientDocument(doc, openBlob) {
  if (!doc?.id) return Promise.resolve();
  return openBlob(`/documents/${doc.id}/download`);
}

export function wordDownloadPath(doc) {
  if (!doc?.id) return null;
  if (doc.has_word_download || doc.docx_filename || String(doc.template_id || "") === "lettre_avs") {
    return `/documents/${doc.id}/download-word`;
  }
  if (isWordDocument(doc)) {
    return `/documents/${doc.id}/download?download=1`;
  }
  return null;
}

export function wordDownloadFilename(doc) {
  if (doc?.docx_filename) return doc.docx_filename;
  const stem = documentDisplayName(doc) || "document";
  return stem.toLowerCase().endsWith(".docx") ? stem : `${stem}.docx`;
}
