/** Règles d'affichage des demandes de complément. Le serveur reste la source de vérité. */

export const MAX_COMPLEMENT_FILES = 15;

export function pendingComplementCount(demande) {
  const explicit = Number(demande?.nb_complements_en_attente);
  if (Number.isFinite(explicit) && explicit >= 0) return explicit;
  return (demande?.notes_externes || []).filter((note) => note?.complement?.status === "en_attente").length;
}

export function replyBlockReason(note, text, files) {
  if (!note?.can_reply || note?.complement?.status !== "en_attente") {
    return "Réponse non autorisée";
  }
  const comment = String(text || "").trim();
  const count = Array.isArray(files) ? files.length : 0;
  if (comment.length > 8000) return "La réponse est trop longue";
  if (count > MAX_COMPLEMENT_FILES) return `Maximum ${MAX_COMPLEMENT_FILES} documents`;
  if (note.complement?.type === "document" && count < 1) {
    return "Ajoutez au moins un document";
  }
  if (note.complement?.type === "information" && !comment && count < 1) {
    return "Saisissez une réponse ou joignez un document";
  }
  return "";
}

export function withoutFileAt(files, index) {
  return (files || []).filter((_, i) => i !== index);
}

export function replaceFileAt(files, index, file) {
  return (files || []).map((item, i) => (i === index ? file : item));
}

export function appendFiles(files, incoming, max = MAX_COMPLEMENT_FILES) {
  const next = [...(files || [])];
  Array.from(incoming || []).forEach((file) => {
    if (file && next.length < max) next.push(file);
  });
  return next;
}

export function offreNotificationPath(notification, { fromGestion = false } = {}) {
  if (!notification?.demande_id) return null;
  const params = new URLSearchParams();
  if (fromGestion) params.set("from", "gestion");
  if (notification.complement_id) params.set("complement", notification.complement_id);
  const query = params.toString();
  return `/demandes-offres/${notification.demande_id}${query ? `?${query}` : ""}`;
}
