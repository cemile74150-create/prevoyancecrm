// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { ConfirmDeleteButton } from "@/analyse-prevoyance/components/ConfirmDeleteButton";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import type { AnalyseInput, RenteHypothesisInput } from "@/analyse-prevoyance/lib/types";

function emptyHypothesis(): RenteHypothesisInput {
  return {
    id: `rh-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    type: "certaine",
    compagnie: "",
    capitalPlace: 0,
    dureeAnnees: null,
    renteGarantieAnnuelle: 0,
    participationExcedentsAnnuelle: 0,
  };
}

export function RenteHypothesisFields({
  input,
  onChange,
}: {
  input: AnalyseInput;
  onChange: (partial: Partial<AnalyseInput>) => void;
}) {
  const rows = input.renteHypotheses || [];

  function update(id: string, partial: Partial<RenteHypothesisInput>) {
    onChange({
      renteHypotheses: rows.map((row) => (row.id === id ? { ...row, ...partial } : row)),
    });
  }

  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={Boolean(input.comparerAvecRenteLpp)}
          onChange={(e) => onChange({ comparerAvecRenteLpp: e.target.checked })}
        />
        Comparer avec la rente LPP
      </label>
      {rows.map((row, index) => (
        <div key={row.id} className="space-y-3 rounded-md border p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">Hypothèse {index + 1}</p>
            <ConfirmDeleteButton
              ariaLabel="Supprimer l'hypothèse"
              onConfirm={() =>
                onChange({ renteHypotheses: rows.filter((item) => item.id !== row.id) })
              }
            >
              <Trash2 className="size-4" />
            </ConfirmDeleteButton>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1">
              <Label className="text-xs">Type de rente</Label>
              <select
                className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
                value={row.type}
                onChange={(e) =>
                  update(row.id, {
                    type: e.target.value,
                    dureeAnnees: e.target.value === "viagere" ? null : row.dureeAnnees,
                  })
                }
              >
                <option value="certaine">Rente certaine</option>
                <option value="viagere">Rente viagère</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Nom de la compagnie</Label>
              <Input
                value={row.compagnie}
                onChange={(e) => update(row.id, { compagnie: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Capital placé (CHF)</Label>
              <Input
                type="number"
                min={0}
                value={row.capitalPlace || ""}
                onChange={(e) =>
                  update(row.id, { capitalPlace: Number(e.target.value) || 0 })
                }
              />
            </div>
            {row.type === "certaine" && (
              <div className="space-y-1">
                <Label className="text-xs">Durée de la rente (années)</Label>
                <Input
                  type="number"
                  min={1}
                  value={row.dureeAnnees ?? ""}
                  onChange={(e) =>
                    update(row.id, {
                      dureeAnnees:
                        e.target.value === "" ? null : Number(e.target.value) || null,
                    })
                  }
                />
              </div>
            )}
            <div className="space-y-1">
              <Label className="text-xs">Rente garantie annuelle (CHF)</Label>
              <Input
                type="number"
                min={0}
                value={row.renteGarantieAnnuelle || ""}
                onChange={(e) =>
                  update(row.id, { renteGarantieAnnuelle: Number(e.target.value) || 0 })
                }
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Participation aux excédents annuelle (CHF)</Label>
              <Input
                type="number"
                min={0}
                value={row.participationExcedentsAnnuelle || ""}
                onChange={(e) =>
                  update(row.id, {
                    participationExcedentsAnnuelle: Number(e.target.value) || 0,
                  })
                }
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {row.type === "certaine"
              ? "Revenu fiscal = rente AVS + 70 % de la participation. La rente garantie est encaissée, elle n'entre pas dans l'impôt."
              : "Revenu fiscal = rente AVS + 4 % de la rente garantie + 70 % de la participation."}
          </p>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange({ renteHypotheses: [...rows, emptyHypothesis()] })}
      >
        <Plus className="size-4" />
        Ajouter une hypothèse
      </Button>
    </div>
  );
}
