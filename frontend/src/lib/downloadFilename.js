/** Helpers pour le nom de fichier au téléchargement (pas de clés de stockage). */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Détecte un nom opaque (UUID / clé S3), pas le nom enregistré à l'upload.
 */
export function looksLikeOpaqueStorageName(name) {
  const base = String(name || "")
    .trim()
    .replace(/\\/g, "/")
    .split("/")
    .pop() || "";
  const stem = base.replace(/\.[^.]+$/, "");
  if (!stem) return true;
  if (UUID_RE.test(stem)) return true;
  if (/^[0-9a-f]{32}$/i.test(stem)) return true;
  return false;
}

/**
 * Lit filename / filename* depuis Content-Disposition.
 */
export function filenameFromContentDisposition(header, fallback) {
  const cd = header || "";
  const star = /filename\*=(?:UTF-8''|utf-8'')([^;]+)/i.exec(cd);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"+|"+$/g, ""));
    } catch {
      return star[1].trim();
    }
  }
  const plain = /filename="((?:\\.|[^"\\])*)"|filename=([^";]+)/i.exec(cd);
  if (plain) {
    return (plain[1] != null ? plain[1].replace(/\\"/g, '"') : plain[2]).trim();
  }
  return fallback;
}

/**
 * Choisit le nom de téléchargement : nom enregistré (UI) en priorité,
 * puis Content-Disposition, en rejetant les UUID / clés de stockage.
 */
export function pickDownloadFilename(headerName, preferred, fallback = "document.pdf") {
  const preferredClean = String(preferred || "").trim();
  const headerClean = String(headerName || "").trim();
  const fb = String(fallback || "document.pdf").trim() || "document.pdf";

  if (preferredClean && !looksLikeOpaqueStorageName(preferredClean)) {
    return preferredClean;
  }
  if (headerClean && !looksLikeOpaqueStorageName(headerClean)) {
    return headerClean;
  }
  if (preferredClean) return preferredClean;
  if (headerClean) return headerClean;
  return fb;
}
