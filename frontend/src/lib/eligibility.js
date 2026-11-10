export function foldSearch(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function filterListsByName(lists, query) {
  const q = foldSearch(query);
  if (!q) return lists || [];
  return (lists || []).filter((l) => foldSearch(l.name).includes(q));
}

export function setListChecked(lists, listId, checked) {
  return (lists || []).map((l) => (l.id === listId ? { ...l, checked } : l));
}

export function eligibilityErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (!err?.response) return "Connexion au serveur impossible. Réessayez.";
  return fallback;
}

export function clientCountLabel(count) {
  const n = Number(count) || 0;
  return `${n} client${n > 1 ? "s" : ""}`;
}
