export const PDF_NEED_CALCULATE =
  "Calculez l'analyse avant de générer le PDF.";

export const PDF_STALE_WARNING =
  "Le formulaire a changé depuis le dernier calcul. Le PDF reprend le dernier calcul. Recalculez pour le mettre à jour.";

export const PDF_POPUP_BLOCKED =
  "Le navigateur a bloqué l'ouverture du PDF. Autorisez les pop-ups pour ce site.";

/**
 * Le PDF est toujours produit côté serveur à partir du dernier calcul.
 * Un formulaire un peu différent ne doit pas avaler le clic.
 */
export function planAnalysePdf({ hasId, hasResults, isCurrent }) {
  if (!hasId || !hasResults) {
    return { allow: false, message: PDF_NEED_CALCULATE, tone: "error" };
  }
  if (!isCurrent) {
    return { allow: true, message: PDF_STALE_WARNING, tone: "warning" };
  }
  return { allow: true, message: null, tone: null };
}

export function openAnalysePdfWindow(openWindow, url) {
  const popup = openWindow(url, "_blank", "noopener");
  if (popup) return true;
  if (typeof document === "undefined") return false;
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  return true;
}
