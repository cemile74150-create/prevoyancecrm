import { normalizeConseillerKey, uniqueConseillerNames } from "./conseillers";

export const NON_ATTRIBUE = "Non attribué";

/** Conseillers distincts d'un dossier Kanban (famille = membres pouvant différer). */
export function groupConseillers(group) {
  return uniqueConseillerNames((group?.members || []).map((m) => m?.conseiller));
}

export function groupMatchesConseiller(group, selected) {
  const wanted = String(selected || "").trim();
  if (!wanted || wanted === "all") return true;
  const names = groupConseillers(group);
  if (wanted === NON_ATTRIBUE) return names.length === 0;
  const key = normalizeConseillerKey(wanted);
  return names.some((n) => normalizeConseillerKey(n) === key);
}

/** Options du filtre : conseillers actifs + conseillers présents sur les dossiers (legacy / inactifs). */
export function kanbanConseillerOptions(activeNames, groups) {
  const present = (groups || []).flatMap(groupConseillers);
  return uniqueConseillerNames([...(activeNames || []), ...present]);
}

export function sameConseiller(a, b) {
  return normalizeConseillerKey(a) === normalizeConseillerKey(b);
}
