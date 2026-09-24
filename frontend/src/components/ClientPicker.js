import React, { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, User, X } from "lucide-react";
import { toSwissDate } from "@/lib/dates";

/**
 * Recherche / sélection d'un client de la base centrale « Clients ».
 * onSelect(client) reçoit l'objet client complet (ou null si désélection).
 */
export default function ClientPicker({
  value = null,
  onSelect,
  placeholder = "Rechercher un client existant…",
  disabled = false,
  className = "",
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async (term) => {
    if (!term || term.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const res = await api.get("/clients/search", { params: { q: term.trim(), limit: 20 } });
      setResults(Array.isArray(res.data) ? res.data.slice(0, 20) : []);
      setOpen(true);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => search(q), 250);
    return () => clearTimeout(t);
  }, [q, search]);

  if (value) {
    return (
      <div className={`flex items-center gap-2 rounded-md border border-[#002FA7]/30 bg-[#002FA7]/5 px-3 py-2 ${className}`}>
        <User className="h-4 w-4 text-[#002FA7] shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate">
            {value.prenom} {value.nom}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {[value.numero_dossier, toSwissDate(value.date_naissance), value.ville].filter(Boolean).join(" · ")}
          </p>
        </div>
        {!disabled && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7 shrink-0"
            onClick={() => onSelect?.(null)}
            title="Dissocier"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          className="pl-9"
          data-testid="client-picker-input"
        />
      </div>
      {open && (results.length > 0 || loading) && (
        <div className="absolute z-50 mt-1 w-full max-h-56 overflow-y-auto rounded-md border border-border bg-white shadow-md">
          {loading && (
            <p className="text-xs text-muted-foreground px-3 py-2">Recherche…</p>
          )}
          {results.map((c) => (
            <button
              key={c.id}
              type="button"
              className="w-full text-left px-3 py-2 hover:bg-secondary text-sm border-b border-border last:border-0"
              onClick={() => {
                onSelect?.(c);
                setQ("");
                setOpen(false);
                setResults([]);
              }}
            >
              <span className="font-medium">{c.prenom} {c.nom}</span>
              <span className="text-xs text-muted-foreground ml-2">
                {[c.numero_dossier, toSwissDate(c.date_naissance), c.ville].filter(Boolean).join(" · ")}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
