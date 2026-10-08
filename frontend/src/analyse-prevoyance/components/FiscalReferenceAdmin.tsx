// @ts-nocheck
"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { analyseFetch } from "@/analyse-prevoyance/api";
import { fiscalAsOfFromLocation } from "@/analyse-prevoyance/components/FiscalUpdateAlert";
import { toast } from "sonner";

export function FiscalReferenceAdmin() {
  const [referenceYear, setReferenceYear] = useState("2025");
  const [savedYear, setSavedYear] = useState(2025);
  const [alertText, setAlertText] = useState<string | null>(null);
  const [validatedYear, setValidatedYear] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const injected = fiscalAsOfFromLocation();
    const query = injected ? `?asOf=${encodeURIComponent(injected)}` : "";
    const res = await analyseFetch(`/fiscal-config${query}`);
    if (!res.ok) return;
    const data = await res.json();
    const year = Number(data.referenceYear) || 2025;
    setSavedYear(year);
    setReferenceYear(String(year));
    setAlertText(data.alert || null);
    setValidatedYear(
      data.validatedReferenceYear == null ? null : Number(data.validatedReferenceYear),
    );
  }, []);

  useEffect(() => {
    load().catch(() => {});
  }, [load]);

  async function saveYear() {
    const year = Number(referenceYear);
    if (!Number.isFinite(year)) {
      toast.error("Année invalide");
      return;
    }
    setBusy(true);
    try {
      const injected = fiscalAsOfFromLocation();
      const query = injected ? `?asOf=${encodeURIComponent(injected)}` : "";
      const res = await analyseFetch(`/fiscal-config${query}`, {
        method: "PUT",
        body: JSON.stringify({ referenceYear: year }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(data.detail || "Enregistrement impossible");
        return;
      }
      setSavedYear(Number(data.referenceYear) || year);
      setAlertText(data.alert || null);
      setValidatedYear(
        data.validatedReferenceYear == null ? null : Number(data.validatedReferenceYear),
      );
      toast.success("Année fiscale de référence enregistrée");
    } finally {
      setBusy(false);
    }
  }

  async function validateScales() {
    setBusy(true);
    try {
      const injected = fiscalAsOfFromLocation();
      const query = injected ? `?asOf=${encodeURIComponent(injected)}` : "";
      const res = await analyseFetch(`/fiscal-config/validate${query}`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(data.detail || "Validation impossible");
        return;
      }
      setAlertText(data.alert || null);
      setValidatedYear(
        data.validatedReferenceYear == null ? null : Number(data.validatedReferenceYear),
      );
      toast.success("Barèmes validés pour l'année de référence");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-6 border-border" data-testid="fiscal-reference-admin">
      <h2 className="font-display font-bold text-lg tracking-tight">Paramètres fiscaux du calculateur</h2>
      <p className="text-sm text-muted-foreground mt-1 max-w-3xl">
        Année fiscale de référence utilisée par les nouvelles analyses. Le formulaire conseiller ne la demande pas.
        Enregistrer une autre année ne confirme pas que les barèmes ont été actualisés.
      </p>
      {alertText && (
        <div
          className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950"
          data-testid="alerte-fiscale-suivi"
        >
          <p className="font-medium flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Mise à jour fiscale
          </p>
          <p className="mt-2">{alertText}</p>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="space-y-2">
          <Label htmlFor="fiscal-reference-year">Année fiscale de référence</Label>
          <Input
            id="fiscal-reference-year"
            type="number"
            min={2000}
            max={2100}
            value={referenceYear}
            onChange={(e) => setReferenceYear(e.target.value)}
            className="w-36"
          />
        </div>
        <Button type="button" variant="outline" disabled={busy} onClick={saveYear}>
          Enregistrer l&apos;année
        </Button>
        <Button type="button" disabled={busy} onClick={validateScales} className="bg-[#002FA7] hover:bg-[#00248a]">
          Valider la mise à jour des barèmes
        </Button>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Année enregistrée : {savedYear}
        {validatedYear == null
          ? " · barèmes non validés pour cette année"
          : ` · barèmes validés pour ${validatedYear}`}
      </p>
    </Card>
  );
}
