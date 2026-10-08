// @ts-nocheck
"use client";

import { useEffect, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/analyse-prevoyance/ui/alert";
import { analyseFetch } from "@/analyse-prevoyance/api";

export function fiscalAsOfFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("asOf");
}

export function FiscalUpdateAlert() {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    const injected = fiscalAsOfFromLocation();
    const query = injected ? `?asOf=${encodeURIComponent(injected)}` : "";
    let cancelled = false;
    analyseFetch(`/fiscal-config${query}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setText(data?.alert || null);
      })
      .catch(() => {
        if (!cancelled) setText(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!text) return null;
  return (
    <Alert className="mb-6 border-amber-300 bg-amber-50 text-amber-950" data-testid="alerte-fiscale">
      <AlertTitle>Mise à jour fiscale</AlertTitle>
      <AlertDescription>{text}</AlertDescription>
    </Alert>
  );
}
