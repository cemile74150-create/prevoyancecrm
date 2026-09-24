import React, { useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import { normalizeSwissDateInput, toSwissDate } from "@/lib/dates";
import {
  applyNationalitePermisRules,
  findNationalitePermisPairs,
  foldLabel,
  isPermisLockedByNationalite,
} from "@/lib/offreNationalitePermis";
import { toggleExclusiveCheckboxSelection } from "@/lib/offreExclusiveCheckbox";
import {
  FIELD_COMMENT_SUFFIX,
  fieldAllowsComment,
  fieldCommentKey,
} from "@/lib/demandesOffres";
import {
  agentLockedFieldNames,
  injectAgentIdentity,
  isAgentIdentityField,
} from "@/lib/offreAgentIdentity";

function FieldShell({ label, required, changed, description, children, commentSlot }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <Label className="text-xs text-muted-foreground">
          {label}
          {required ? <span className="text-rose-600"> *</span> : null}
        </Label>
        {changed ? (
          <span className="inline-flex rounded-full bg-rose-500/15 text-rose-800 ring-1 ring-inset ring-rose-500/30 px-1.5 py-0.5 text-[10px] font-semibold">
            Modifié
          </span>
        ) : null}
      </div>
      {children}
      {description ? <p className="text-[11px] text-muted-foreground leading-snug">{description}</p> : null}
      {commentSlot}
    </div>
  );
}

function ChoiceSelect({ value, onChange, options, placeholder = "Sélectionner", disabled }) {
  const normalized = value || "__none";
  return (
    <Select value={normalized} onValueChange={(v) => onChange(v === "__none" ? "" : v)} disabled={disabled}>
      <SelectTrigger>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none">Non renseigné</SelectItem>
        {(options || []).map((option) => (
          <SelectItem key={String(option)} value={String(option)}>
            {option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function RadioGroup({ value, onChange, options, disabled, name }) {
  return (
    <div className="flex flex-wrap gap-3">
      {(options || []).map((option) => {
        const checked = value === option;
        return (
          <label
            key={option}
            className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${
              disabled ? "opacity-70 cursor-default" : "cursor-pointer"
            } ${checked ? "border-[#002FA7]/40 bg-[#002FA7]/5" : "border-border"}`}
          >
            <input
              type="radio"
              name={name}
              checked={checked}
              disabled={disabled}
              onChange={() => onChange(option)}
              className="accent-[#002FA7]"
            />
            {option}
          </label>
        );
      })}
    </div>
  );
}

function CheckGrid({ options, selected, onToggle, disabled }) {
  const list = Array.isArray(selected) ? selected : [];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {(options || []).map((option) => {
        const checked = list.includes(option);
        return (
          <label
            key={option}
            className={`flex items-center gap-2 rounded-md border p-2.5 text-sm ${
              disabled ? "opacity-70 cursor-default" : "cursor-pointer"
            } ${checked ? "border-[#002FA7]/40 bg-[#002FA7]/5" : "border-border"}`}
          >
            <input
              type="checkbox"
              checked={checked}
              disabled={disabled}
              onChange={() => onToggle(option)}
              className="accent-[#002FA7]"
            />
            {option}
          </label>
        );
      })}
    </div>
  );
}

function ListField({ columns, value, onChange, disabled }) {
  const cols = columns?.length ? columns : ["Valeur"];
  const rows = Array.isArray(value) && value.length
    ? value
    : [Object.fromEntries(cols.map((c) => [c, ""]))];

  const update = (rowIdx, col, v) => {
    const next = rows.map((r, i) => (i === rowIdx ? { ...r, [col]: v } : { ...r }));
    onChange(next);
  };
  const addRow = () => onChange([...rows, Object.fromEntries(cols.map((c) => [c, ""]))]);
  const removeRow = (idx) => {
    if (rows.length <= 1) {
      onChange([Object.fromEntries(cols.map((c) => [c, ""]))]);
      return;
    }
    onChange(rows.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-2">
      {rows.map((row, idx) => (
        <div key={idx} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 items-end">
          {cols.map((col) => (
            <div key={col} className="space-y-1">
              {idx === 0 ? <p className="text-[10px] uppercase text-muted-foreground">{col}</p> : null}
              <Input
                value={row?.[col] || ""}
                disabled={disabled}
                onChange={(e) => update(idx, col, e.target.value)}
              />
            </div>
          ))}
          {!disabled ? (
            <Button type="button" variant="ghost" size="icon" className="text-rose-700" onClick={() => removeRow(idx)}>
              <Trash2 className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      ))}
      {!disabled ? (
        <Button type="button" variant="outline" size="sm" onClick={addRow}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Ajouter une ligne
        </Button>
      ) : null}
    </div>
  );
}

/** Evaluate Gravity-Forms style show_when against current values. */
export function isFieldVisible(field, values) {
  const sw = field?.show_when;
  if (!sw || !Array.isArray(sw.rules) || !sw.rules.length) return true;
  const results = sw.rules.map((rule) => {
    const raw = values?.[rule.field];
    const expected = rule.value;
    if (Array.isArray(raw)) {
      // Checkbox multi: "is" means contains
      return raw.includes(expected);
    }
    const actual = raw == null ? "" : String(raw);
    if (rule.op === "isnot") return actual !== expected;
    return actual === expected;
  });
  return (sw.logic || "all") === "any" ? results.some(Boolean) : results.every(Boolean);
}

function applyDefaults(schema, values) {
  const next = { ...(values || {}) };
  let changed = false;
  for (const field of schema?.fields || []) {
    if (field.type === "section" || field.type === "html") continue;
    const name = field.name || field.id;
    if (!name) continue;
    const cur = next[name];
    const empty = cur == null || cur === "" || (Array.isArray(cur) && cur.length === 0);
    if (!empty) continue;
    if (field.default != null && field.default !== "") {
      next[name] = field.type === "checkbox" ? [].concat(field.default) : field.default;
      changed = true;
    }
  }
  return changed ? next : values;
}

/** Ne conserve que les clés du schéma courant (évite la fuite entre form_type). */
function stripToSchema(schema, values) {
  const allowed = new Set();
  for (const field of schema?.fields || []) {
    if (field.type === "section" || field.type === "html") continue;
    // hidden inclus : valeurs GF (ex. Pays=Suisse) doivent être persistées
    const name = field.name || field.id;
    if (name) {
      allowed.add(name);
      allowed.add(`${name}${FIELD_COMMENT_SUFFIX}`);
    }
  }
  if (!allowed.size) return values || {};
  const src = values || {};
  const next = {};
  let changed = false;
  for (const key of Object.keys(src)) {
    if (allowed.has(key)) next[key] = src[key];
    else changed = true;
  }
  for (const name of allowed) {
    if (!(name in next)) {
      // leave missing — applyDefaults fills defaults
      changed = changed || name in src;
    }
  }
  // Also mark changed if key count differs
  if (Object.keys(src).length !== Object.keys(next).length) changed = true;
  return changed ? next : src;
}

function payloadsEqual(a, b) {
  try {
    return JSON.stringify(a || {}) === JSON.stringify(b || {});
  } catch {
    return a === b;
  }
}

function asText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  // Arrays/objects must not be forced into <input value> (React crash after refresh)
  return "";
}

/**
 * Identity free-text fields must never become selects even if a schema
 * still carries leaked civilité options (Monsieur/Madame).
 */
function isIdentityTextField(field) {
  const lab = foldLabel(field?.label);
  const type = field?.type || "text";
  if (type === "section" || type === "html") return false;
  if (lab.includes("prenom et nom")) return false;
  if (lab.includes("prenom")) return true;
  if (
    lab === "nom" ||
    lab === "nom :" ||
    lab.startsWith("nom du ") ||
    lab.startsWith("nom de la ") ||
    lab.startsWith("nom de l ") ||
    lab.startsWith("nom de l'") ||
    /^nom\b/.test(lab)
  ) {
    // Keep assureur / vétérinaire free-form or choice fields alone
    if (lab.includes("assureur") || lab.includes("veterinaire")) return false;
    return true;
  }
  return false;
}

/**
 * Rendu générique d'un schéma Gravity Forms extrait (form_payload).
 * @param {Set|string[]|undefined} changedKeys — champs marqués « Modifié »
 * @param {object|null|undefined} agentIdentity — profil session (prenom/nom/email/finma)
 */
export default function OffreSchemaForm({
  schema,
  values,
  onChange,
  readOnly = false,
  changedKeys,
  persistKey,
  onPageChange,
  agentIdentity = null,
}) {
  const fields = useMemo(() => schema?.fields || [], [schema?.fields]);
  const pages = useMemo(() => schema?.pages || [], [schema?.pages]);
  const hasPages = pages.length > 1 || fields.some((f) => f.page && f.page > 1);
  const lockedAgentNames = useMemo(() => agentLockedFieldNames(schema), [schema]);

  const pageNums = useMemo(() => {
    if (!hasPages) return [1];
    return [...new Set(fields.map((f) => f.page || 1))].sort((a, b) => a - b);
  }, [fields, hasPages]);

  const [page, setPage] = useState(() => {
    if (!persistKey || typeof window === "undefined") return 1;
    try {
      const raw = sessionStorage.getItem(`offre-form-page:${persistKey}`);
      const n = Number(raw);
      return Number.isFinite(n) && n > 0 ? n : 1;
    } catch {
      return 1;
    }
  });

  useEffect(() => {
    if (!persistKey || typeof window === "undefined") return;
    try {
      const raw = sessionStorage.getItem(`offre-form-page:${persistKey}`);
      const n = Number(raw);
      if (Number.isFinite(n) && n > 0) setPage(n);
      else setPage(1);
    } catch {
      setPage(1);
    }
  }, [persistKey]);

  useEffect(() => {
    if (!persistKey || typeof window === "undefined") return;
    try {
      sessionStorage.setItem(`offre-form-page:${persistKey}`, String(page));
    } catch {
      /* ignore */
    }
  }, [page, persistKey]);

  const changedSet = useMemo(() => {
    if (!changedKeys) return new Set();
    if (changedKeys instanceof Set) return changedKeys;
    return new Set(Array.isArray(changedKeys) ? changedKeys : []);
  }, [changedKeys]);

  const natPermisPairs = useMemo(
    () => findNationalitePermisPairs(fields),
    [fields],
  );

  /** Signature of nationality values — re-sync Permis when they change (e.g. client prefill). */
  const nationaliteSignature = useMemo(() => {
    return natPermisPairs
      .map(({ nationalite }) => {
        const n = nationalite.name || nationalite.id;
        return `${n}=${values?.[n] ?? ""}`;
      })
      .join("|");
  }, [natPermisPairs, values]);

  const agentSignature = useMemo(() => {
    if (!agentIdentity) return "";
    return [
      agentIdentity.prenom || "",
      agentIdentity.nom || "",
      agentIdentity.email || "",
      agentIdentity.finma || "",
    ].join("|");
  }, [agentIdentity]);

  useEffect(() => {
    if (readOnly || !onChange || !schema) return;
    // Changement de form_type / schéma : purger les clés étrangères puis defaults + règles nationalité
    let next = stripToSchema(schema, values);
    next = applyDefaults(schema, next);
    if (agentIdentity) {
      next = injectAgentIdentity(schema, next, agentIdentity, { overwrite: true });
    }
    next = applyNationalitePermisRules(schema, next);
    if (!payloadsEqual(next, values)) onChange(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema?.id, nationaliteSignature, agentSignature]);

  const setField = (name, value) => {
    if (readOnly || !onChange) return;
    if (lockedAgentNames.has(name)) return;
    if (isPermisLockedByNationalite(schema, values, name)) return;
    let next = { ...(values || {}), [name]: value };
    next = applyNationalitePermisRules(schema, next);
    onChange(next);
  };

  const toggleMulti = (name, option) => {
    if (readOnly || !onChange) return;
    if (lockedAgentNames.has(name)) return;
    const current = Array.isArray(values?.[name]) ? values[name] : [];
    const field = (schema?.fields || []).find((f) => (f.name || f.id) === name);
    const next = toggleExclusiveCheckboxSelection(current, option, field?.exclusive_none);
    onChange({ ...(values || {}), [name]: next });
  };

  const goToPage = (nextPage) => {
    setPage(nextPage);
    if (typeof onPageChange === "function") onPageChange(nextPage);
  };

  if (!fields.length) {
    return <p className="text-sm text-muted-foreground">Aucun champ pour ce formulaire.</p>;
  }

  const mark = (name) => changedSet.has(name);
  const inputCls = (name) => (mark(name) ? "border-rose-400 bg-rose-50/60 focus-visible:ring-rose-300" : "");

  const currentPage = pageNums.includes(page) ? page : pageNums[0];
  const pageLabel = pages.find((p) => p.page === currentPage)?.label || `Étape ${currentPage}`;

  const visibleFields = fields.filter((field) => {
    if (hasPages && (field.page || 1) !== currentPage) return false;
    return isFieldVisible(field, values || {});
  });

  const renderField = (field) => {
    const name = field.name || field.id;
    const type = field.type || "text";
    const identityText = isIdentityTextField(field);
    // Ignore leaked options on identity free-text fields (Prénom/Nom).
    const options = identityText
      ? []
      : (field.options || []).filter((o) => o != null && String(o).trim() !== "");
    const required = Boolean(field.required);
    const label = field.label || name;
    const changed = mark(name);
    const description = field.description || "";
    const lockedByNat = isPermisLockedByNationalite(schema, values, name);
    const lockedByAgent = lockedAgentNames.has(name) || isAgentIdentityField(field);
    // Ne pas appliquer schema.disabled (export GF) : le conseiller doit pouvoir éditer
    // les champs visibles (ex. adresse secondaire quand « même adresse = Non »).
    const fieldDisabled = readOnly || lockedByNat || lockedByAgent;
    const showComment = !readOnly && fieldAllowsComment(field);
    const commentKey = name ? fieldCommentKey(name) : "";
    const commentSlot = showComment ? (
      <div className="pt-1">
        <Label className="text-[10px] uppercase tracking-wide text-muted-foreground">
          Précision (optionnel)
        </Label>
        <Textarea
          rows={2}
          value={asText(values?.[commentKey])}
          disabled={fieldDisabled}
          placeholder="Précision pour le service Offres…"
          onChange={(e) => setField(commentKey, e.target.value)}
          className="mt-1 text-sm"
        />
      </div>
    ) : null;

    if (type === "html") return null;
    if (type === "hidden") return null;

    if (type === "section") {
      return (
        <div key={field.id || name} className="pt-2 border-t border-border/70 first:border-0 first:pt-0">
          <h3 className="font-display font-bold text-[#dd0000] text-base uppercase tracking-wide">{label}</h3>
          {description ? <p className="text-[11px] text-muted-foreground mt-1">{description}</p> : null}
        </div>
      );
    }

    if (type === "list") {
      return (
        <FieldShell key={field.id || name} label={label} required={required} changed={changed} description={description} commentSlot={commentSlot}>
          <ListField
            columns={field.columns}
            value={values?.[name]}
            onChange={(v) => setField(name, v)}
            disabled={fieldDisabled}
          />
        </FieldShell>
      );
    }

    if (!identityText && (type === "checkbox" || (Array.isArray(values?.[name]) && options.length > 2))) {
      return (
        <FieldShell key={field.id || name} label={label} required={required} changed={changed} description={description} commentSlot={commentSlot}>
          <CheckGrid
            options={options}
            selected={Array.isArray(values?.[name]) ? values[name] : []}
            onToggle={(opt) => toggleMulti(name, opt)}
            disabled={fieldDisabled}
          />
        </FieldShell>
      );
    }

    if (!identityText && type === "radio") {
      return (
        <FieldShell key={field.id || name} label={label} required={required} changed={changed} description={description} commentSlot={commentSlot}>
          <RadioGroup
            name={name}
            value={asText(values?.[name])}
            onChange={(v) => setField(name, v)}
            options={options}
            disabled={fieldDisabled}
          />
        </FieldShell>
      );
    }

    if (!identityText && (type === "select" || (options.length > 0 && type !== "file"))) {
      return (
        <FieldShell key={field.id || name} label={label} required={required} changed={changed} description={description} commentSlot={commentSlot}>
          <ChoiceSelect
            value={asText(values?.[name])}
            onChange={(v) => setField(name, v)}
            options={options}
            disabled={fieldDisabled}
          />
        </FieldShell>
      );
    }

    if (type === "textarea") {
      return (
        <FieldShell key={field.id || name} label={label} required={required} changed={changed} description={description} commentSlot={null}>
          <Textarea
            rows={4}
            value={asText(values?.[name])}
            disabled={fieldDisabled}
            onChange={(e) => setField(name, e.target.value)}
            className={inputCls(name)}
          />
        </FieldShell>
      );
    }

    if (type === "file") {
      return (
        <FieldShell key={field.id || name} label={label} required={required} changed={changed} description={description}>
          {readOnly ? (
            <p className="text-sm">{asText(values?.[name]) || "—"}</p>
          ) : (
            <Input
              type="file"
              onChange={(e) => setField(name, e.target.files?.[0]?.name || "")}
            />
          )}
          <p className="text-[11px] text-muted-foreground">
            Les pièces jointes définitives se gèrent aussi dans la zone Documents de la demande.
          </p>
        </FieldShell>
      );
    }

    const inputType =
      type === "email" || type === "tel" || type === "number" ? type : "text";
    // Dates: Swiss jj.mm.aaaa free text (GF datepicker), not HTML5 yyyy-mm-dd.
    // Live value stays as typed (ISO → Swiss only). Normalize on blur — never force year 2020 mid-typing.
    const resolvedType = type === "date" ? "text" : inputType;
    const placeholder =
      field.placeholder ||
      (type === "date" ? "jj.mm.aaaa" : undefined);
    const rawText = asText(values?.[name]);
    const displayValue =
      type === "date"
        ? (/^\d{4}-\d{2}-\d{2}/.test(String(rawText).trim())
            ? toSwissDate(rawText) || rawText
            : rawText)
        : rawText;

    return (
      <FieldShell
        key={field.id || name}
        label={label}
        required={required}
        changed={changed}
        description={
          lockedByAgent
            ? (description ? `${description} ` : "") + "Renseigné automatiquement depuis votre profil (non modifiable)."
            : description
        }
        commentSlot={commentSlot}
      >
        <Input
          type={resolvedType}
          value={displayValue}
          disabled={fieldDisabled}
          readOnly={lockedByAgent}
          placeholder={placeholder}
          inputMode={type === "date" ? "numeric" : undefined}
          onChange={(e) => setField(name, e.target.value)}
          onBlur={
            type === "date" && !fieldDisabled && !lockedByAgent
              ? (e) => {
                  const next = normalizeSwissDateInput(e.target.value);
                  if (next !== e.target.value) setField(name, next);
                }
              : undefined
          }
          className={`${inputCls(name)}${lockedByAgent ? " bg-slate-50 text-slate-700" : ""}`}
          data-agent-locked={lockedByAgent ? "true" : undefined}
        />
      </FieldShell>
    );
  };

  return (
    <div className="space-y-5">
      {hasPages ? (
        <div className="rounded-md border bg-slate-50/80 px-4 py-3 space-y-2">
          <p className="text-sm font-medium text-slate-800">
            Étape {pageNums.indexOf(currentPage) + 1} sur {pageNums.length}
            {pageLabel ? <span className="text-muted-foreground font-normal"> — {pageLabel}</span> : null}
          </p>
          <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
            <div
              className="h-full bg-[#002FA7] transition-all"
              style={{ width: `${((pageNums.indexOf(currentPage) + 1) / pageNums.length) * 100}%` }}
            />
          </div>
        </div>
      ) : null}

      {visibleFields.map(renderField)}

      {hasPages && !readOnly ? (
        <div className="flex items-center justify-between gap-3 pt-2">
          <Button
            type="button"
            variant="outline"
            disabled={pageNums.indexOf(currentPage) === 0}
            onClick={() => goToPage(pageNums[pageNums.indexOf(currentPage) - 1])}
          >
            <ChevronLeft className="h-4 w-4 mr-1" /> Précédent
          </Button>
          <Button
            type="button"
            className="bg-[#002FA7] hover:bg-[#00248a]"
            disabled={pageNums.indexOf(currentPage) >= pageNums.length - 1}
            onClick={() => goToPage(pageNums[pageNums.indexOf(currentPage) + 1])}
          >
            Suivant <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function SchemaReadOnlySummary({ schema, values }) {
  const fields = (schema?.fields || []).filter(
    (f) => f.type !== "section" && f.type !== "html" && f.type !== "file" && isFieldVisible(f, values || {}),
  );
  const filled = fields.filter((f) => {
    const name = f.name || f.id;
    const v = values?.[name];
    if (Array.isArray(v)) {
      if (!v.length) return false;
      if (typeof v[0] === "object") {
        return v.some((row) => Object.values(row || {}).some((x) => String(x || "").trim()));
      }
      return true;
    }
    return v !== null && v !== undefined && String(v).trim() !== "";
  });

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {filled.map((field) => {
        const name = field.name || field.id;
        const raw = values?.[name];
        let display;
        if (Array.isArray(raw)) {
          if (raw.length && typeof raw[0] === "object") {
            display = raw
              .map((row) => Object.values(row || {}).filter(Boolean).join(" · "))
              .filter(Boolean)
              .join("\n");
          } else {
            display = raw.join(", ");
          }
        } else {
          display = field.type === "date" ? (toSwissDate(raw) || String(raw ?? "")) : String(raw);
        }
        const precision = asText(values?.[fieldCommentKey(name)]);
        return (
          <div key={field.id || name} className={`rounded-md border p-3${precision ? " sm:col-span-2" : ""}`}>
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{field.label || name}</p>
            <p className="text-sm font-medium mt-1 whitespace-pre-wrap">{display || "—"}</p>
            {precision ? (
              <p className="text-sm mt-2 text-slate-700 whitespace-pre-wrap">
                <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Précision — </span>
                {precision}
              </p>
            ) : null}
          </div>
        );
      })}
      {!filled.length && <p className="text-sm text-muted-foreground col-span-full">Aucune donnée saisie.</p>}
    </div>
  );
}
