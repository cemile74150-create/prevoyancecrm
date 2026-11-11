import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CLOTURE_MOTIFS, todayZurichIso } from "@/lib/dossierCloture";

/**
 * Demande date + motif obligatoires avant de passer un dossier à « Clôturé ».
 */
export default function ClotureDossierDialog({
  open,
  onOpenChange,
  title = "Clôturer le dossier",
  description,
  initialDate,
  initialMotif,
  onConfirm,
  saving = false,
}) {
  const [date, setDate] = useState(todayZurichIso());
  const [motif, setMotif] = useState("");

  useEffect(() => {
    if (!open) return;
    setDate(initialDate || todayZurichIso());
    setMotif(initialMotif || "");
  }, [open, initialDate, initialMotif]);

  const canSubmit = Boolean(date && motif) && !saving;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="cloture-dossier-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {description || "Indiquez la date et le motif de clôture. Le motif est obligatoire."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="cloture-date">Date de clôture</Label>
            <Input
              id="cloture-date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              data-testid="cloture-date-input"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Motif de clôture</Label>
            <Select value={motif || undefined} onValueChange={setMotif}>
              <SelectTrigger data-testid="cloture-motif-select">
                <SelectValue placeholder="Choisir un motif" />
              </SelectTrigger>
              <SelectContent>
                {CLOTURE_MOTIFS.map((m) => (
                  <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              Annuler
            </Button>
            <Button
              type="button"
              data-testid="cloture-confirm-btn"
              className="bg-[#002FA7] hover:bg-[#00248a]"
              disabled={!canSubmit}
              onClick={() => onConfirm?.({ cloture_date: date, cloture_motif: motif })}
            >
              {saving ? "Enregistrement…" : "Clôturer"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
