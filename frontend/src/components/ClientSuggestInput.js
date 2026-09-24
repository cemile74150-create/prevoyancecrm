import React, { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { toSwissDate } from "@/lib/dates";

/**
 * Champ texte avec suggestions clients (GET /clients/search) en temps réel.
 * Recherche dans toute la base centrale Clients (pas les seules demandes d'offres).
 */
export default function ClientSuggestInput({
  value,
  onChange,
  searchTerm,
  onSelectClient,
  enabled = true,
  placeholder,
  className = "",
  "data-testid": testId,
  ...inputProps
}) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [searched, setSearched] = useState(false);
  const wrapRef = useRef(null);
  const activeRef = useRef(false);

  useEffect(() => {
    const onDoc = (e) => {
      if (!wrapRef.current?.contains(e.target)) {
        setOpen(false);
        activeRef.current = false;
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (!enabled || !activeRef.current) return undefined;
    const term = (searchTerm || "").trim();
    if (term.length < 2) {
      setResults([]);
      setSearched(false);
      setOpen(false);
      return undefined;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await api.get("/clients/search", { params: { q: term, limit: 20 } });
        if (cancelled) return;
        const list = Array.isArray(res.data) ? res.data.slice(0, 20) : [];
        setResults(list);
        setSearched(true);
        setOpen(true);
      } catch {
        if (!cancelled) {
          setResults([]);
          setSearched(true);
          setOpen(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [searchTerm, enabled]);

  return (
    <div className={`relative ${className}`} ref={wrapRef}>
      <Input
        value={value}
        placeholder={placeholder}
        data-testid={testId}
        autoComplete="off"
        {...inputProps}
        onFocus={(e) => {
          activeRef.current = true;
          inputProps.onFocus?.(e);
          if ((searchTerm || "").trim().length >= 2) setOpen(true);
        }}
        onChange={(e) => {
          activeRef.current = true;
          onChange?.(e);
        }}
      />
      {open && activeRef.current && (loading || searched) && (
        <div
          className="absolute z-50 mt-1 w-full min-w-[260px] max-h-60 overflow-y-auto rounded-md border border-border bg-white shadow-lg"
          data-testid="client-suggest-dropdown"
        >
          {loading && (
            <p className="flex items-center gap-2 text-xs text-muted-foreground px-3 py-2.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Recherche…
            </p>
          )}
          {!loading && searched && results.length === 0 && (
            <p className="text-sm px-3 py-2.5 text-sky-900 bg-sky-50" data-testid="client-suggest-none">
              Aucun client trouvé — Créer un nouveau client
            </p>
          )}
          {!loading &&
            results.map((c) => (
              <button
                key={c.id}
                type="button"
                className="w-full text-left px-3 py-2.5 hover:bg-[#002FA7]/5 text-sm border-b border-border last:border-0"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onSelectClient?.(c);
                  setOpen(false);
                  activeRef.current = false;
                  setResults([]);
                  setSearched(false);
                }}
              >
                <span className="font-medium text-foreground">
                  {c.prenom} {c.nom}
                </span>
                <span className="block text-xs text-muted-foreground mt-0.5">
                  {[toSwissDate(c.date_naissance), c.ville, c.numero_dossier].filter(Boolean).join(" · ")}
                </span>
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
