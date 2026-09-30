import React, { useId, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { displayConseillerName, normalizeConseillerKey } from "@/lib/conseillers";

/**
 * Champ conseiller : suggestions (datalist) + saisie libre d'un nouveau nom.
 */
export default function ConseillerCombobox({
  value = "",
  onChange,
  options = [],
  placeholder = "Choisir ou saisir un nom…",
  disabled = false,
  className,
  onKeyDown,
  onBlur,
  "data-testid": testId = "client-field-conseiller",
}) {
  const listId = useId();
  const uniqueOptions = useMemo(() => {
    const byKey = new Map();
    for (const raw of options) {
      const name = String(raw || "").trim().replace(/\s+/g, " ");
      if (!name) continue;
      const key = normalizeConseillerKey(name);
      if (!key) continue;
      const prev = byKey.get(key);
      byKey.set(key, prev ? displayConseillerName(prev, name) : displayConseillerName(name));
    }
    return [...byKey.values()].sort((a, b) => a.localeCompare(b, "fr", { sensitivity: "base" }));
  }, [options]);

  return (
    <>
      <Input
        list={listId}
        data-testid={testId}
        value={value ?? ""}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        className={cn(className)}
        onChange={(e) => onChange?.(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={onBlur}
      />
      <datalist id={listId}>
        {uniqueOptions.map((name) => (
          <option key={normalizeConseillerKey(name) || name} value={name} />
        ))}
      </datalist>
    </>
  );
}
