export const MAX_SIGNATURE_FILES = 15;

function cleanDocs(list) {
  return (Array.isArray(list) ? list : []).filter((doc) => doc && doc.id);
}

/**
 * Entrées affichables d'une signature : la signature initiale puis chaque complément,
 * dans l'ordre chronologique. Les signatures anciennes n'ont que `document_id`.
 */
export function signatureEntries(signature) {
  if (!signature || !signature.signee) return [];
  const out = [];
  let initialDocs = cleanDocs(signature.documents);
  if (!initialDocs.length && signature.document_id) {
    initialDocs = [{ id: signature.document_id, original_filename: signature.document_category || "Proposition signée" }];
  }
  const initialComment = String(signature.commentaire || "").trim();
  if (initialComment || initialDocs.length) {
    out.push({
      key: "initial",
      initial: true,
      at: signature.signed_at || signature.recorded_at || null,
      by: signature.signed_by || signature.recorded_by || "",
      commentaire: initialComment,
      documents: initialDocs,
    });
  }
  (Array.isArray(signature.complements) ? signature.complements : []).forEach((item, index) => {
    if (!item || typeof item !== "object") return;
    const commentaire = String(item.commentaire || "").trim();
    const documents = cleanDocs(item.documents);
    if (!commentaire && !documents.length) return;
    out.push({
      key: item.id || `complement-${index}`,
      initial: false,
      at: item.at || null,
      by: item.by || "",
      commentaire,
      documents,
    });
  });
  return out;
}

/** Ajoute des fichiers sans doublon (même nom + taille) et sans dépasser la limite. */
export function mergeSignatureFiles(current, incoming, max = MAX_SIGNATURE_FILES) {
  const list = [...(current || [])];
  (incoming || []).forEach((file) => {
    if (!file) return;
    if (list.some((f) => f.name === file.name && f.size === file.size)) return;
    if (list.length < max) list.push(file);
  });
  return list;
}
