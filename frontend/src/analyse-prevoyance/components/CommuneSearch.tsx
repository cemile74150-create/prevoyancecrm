// @ts-nocheck
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Search } from "lucide-react";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import type { TaxLocation } from "@/analyse-prevoyance/lib/types";
import { analyseFetch } from "@/analyse-prevoyance/api";

interface Props {
  value: string;
  taxLocationId: number | null;
  taxYear: number;
  onChange: (ville: string, location: TaxLocation | null) => void;
  disabled?: boolean;
}

export function CommuneSearch({
  value,
  taxLocationId,
  taxYear,
  onChange,
  disabled,
}: Props) {
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<TaxLocation[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  const search = useCallback(
    async (q: string) => {
      if (q.trim().length < 2) {
        setResults([]);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const res = await analyseFetch(
          `/locations?q=${encodeURIComponent(q)}&taxYear=${taxYear}`,
        );
        const data = await res.json();
        if (!res.ok) {
          setError(data.detail || data.error || "Recherche de commune impossible");
          setResults([]);
        } else {
          setResults(data.locations || []);
          setOpen(true);
        }
      } catch {
        setError("Impossible de joindre le service fiscal");
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [taxYear],
  );

  function handleInput(v: string) {
    setQuery(v);
    onChange(v, null);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => search(v), 350);
  }

  function select(loc: TaxLocation) {
    const label = [loc.ZipCode, loc.City || loc.BfsName]
      .filter(Boolean)
      .join(" ");
    setQuery(label);
    onChange(label, loc);
    setOpen(false);
  }

  return (
    <div className="relative space-y-2">
      <Label htmlFor="commune">
        Commune fiscale <span className="text-destructive">*</span>
      </Label>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          id="commune"
          value={query}
          disabled={disabled}
          placeholder="Ex. Ferreyres ou 1313"
          className="pl-9"
          autoComplete="off"
          onChange={(e) => handleInput(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {loading && (
          <Loader2 className="absolute top-1/2 right-3 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>
      {taxLocationId != null && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <MapPin className="size-3.5" />
          TaxLocationID / TaxGroupID : {taxLocationId}
        </p>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
      {open && results.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border bg-popover text-sm shadow-md">
          {results.map((loc) => (
            <li key={loc.TaxLocationID}>
              <button
                type="button"
                className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left hover:bg-accent"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => select(loc)}
              >
                <span className="font-medium">
                  {loc.ZipCode} {loc.City || loc.BfsName}
                </span>
                <span className="text-xs text-muted-foreground">
                  {loc.Canton} · ID {loc.TaxLocationID}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
