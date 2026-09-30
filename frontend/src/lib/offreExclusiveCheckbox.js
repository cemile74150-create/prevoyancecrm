/**
 * Mutual exclusion for checkbox groups with an « Aucun » (none) option.
 * Used by OffreSchemaForm when a field declares `exclusive_none`.
 */

/**
 * Toggle one option in a checkbox selection, applying exclusive-none rules.
 *
 * - Checking the exclusive value clears every other option.
 * - Checking any other option clears the exclusive value.
 * - Unchecking behaves like a normal multi-select.
 *
 * @param {string[]|null|undefined} current
 * @param {string} option
 * @param {string|null|undefined} exclusiveNone e.g. "Aucun"
 * @returns {string[]}
 */
export function toggleExclusiveCheckboxSelection(current, option, exclusiveNone) {
  const list = Array.isArray(current) ? current.slice() : [];
  const none =
    exclusiveNone != null && String(exclusiveNone).trim() !== ""
      ? String(exclusiveNone)
      : null;
  const isSelected = list.includes(option);

  if (isSelected) {
    return list.filter((x) => x !== option);
  }

  if (!none) {
    return [...list, option];
  }

  if (option === none) {
    return [none];
  }

  return [...list.filter((x) => x !== none), option];
}
