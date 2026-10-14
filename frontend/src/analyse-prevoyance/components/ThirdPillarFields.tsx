// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { ConfirmDeleteButton } from "@/analyse-prevoyance/components/ConfirmDeleteButton";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import type {
  PersonInput,
  ThirdPillarContract,
  ValeurRachat,
} from "@/analyse-prevoyance/lib/types";

function pillarContracts(person: PersonInput): ThirdPillarContract[] {
  const list = person?.troisiemePilier;
  return Array.isArray(list) ? list : [];
}

export function ThirdPillarFields({
  title,
  person,
  onChange,
}: {
  title: string;
  person: PersonInput;
  onChange: (p: PersonInput) => void;
}) {
  const contracts = pillarContracts(person);

  function addContract() {
    const c: ThirdPillarContract = {
      id: crypto.randomUUID(),
      echeance: "",
      montant: 0,
      police: "",
      prime: 0,
      compagnie: "",
      type: "3A",
    };
    onChange({
      ...person,
      troisiemePilier: [...contracts, c],
    });
  }

  function updateContract(id: string, partial: Partial<ThirdPillarContract>) {
    onChange({
      ...person,
      troisiemePilier: contracts.map((c) =>
        c.id === id ? { ...c, ...partial } : c,
      ),
    });
  }

  function removeContract(id: string) {
    onChange({
      ...person,
      troisiemePilier: contracts.filter((c) => c.id !== id),
    });
  }

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">{title}</h3>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addContract}
        >
          <Plus className="size-4" />
          Ajouter un contrat
        </Button>
      </div>
      {contracts.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucun contrat saisi.</p>
      ) : (
        <div className="space-y-3">
          {contracts.map((c) => (
            <div
              key={c.id}
              className="grid gap-2 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-6"
            >
              <div className="space-y-1">
                <Label className="text-xs">Compagnie</Label>
                <Input
                  value={c.compagnie}
                  onChange={(e) =>
                    updateContract(c.id, { compagnie: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Police</Label>
                <Input
                  value={c.police}
                  onChange={(e) =>
                    updateContract(c.id, { police: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Type 3A/3B</Label>
                <select
                  className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
                  required
                  value={c.type === "3B" ? "3B" : "3A"}
                  onChange={(e) =>
                    updateContract(c.id, {
                      type: e.target.value === "3B" ? "3B" : "3A",
                    })
                  }
                >
                  <option value="3A">3A</option>
                  <option value="3B">3B</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Échéance</Label>
                <Input
                  type="date"
                  value={c.echeance}
                  onChange={(e) =>
                    updateContract(c.id, { echeance: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Montant</Label>
                <Input
                  type="number"
                  min={0}
                  value={c.montant || ""}
                  onChange={(e) =>
                    updateContract(c.id, {
                      montant: Number(e.target.value) || 0,
                    })
                  }
                />
              </div>
              <div className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">Prime</Label>
                  <Input
                    type="number"
                    min={0}
                    value={c.prime || ""}
                    onChange={(e) =>
                      updateContract(c.id, {
                        prime: Number(e.target.value) || 0,
                      })
                    }
                  />
                </div>
                <ConfirmDeleteButton
                  size="icon"
                  ariaLabel="Supprimer contrat"
                  onConfirm={() => removeContract(c.id)}
                >
                  <Trash2 className="size-4" />
                </ConfirmDeleteButton>
              </div>
              <div className="space-y-2 sm:col-span-2 lg:col-span-6">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs text-muted-foreground">
                    Échéance contractuelle et capital à l&apos;échéance restent inchangés.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      updateContract(c.id, {
                        valeursRachat: [
                          ...(c.valeursRachat || []),
                          { id: crypto.randomUUID(), date: "", montant: 0 },
                        ],
                      })
                    }
                  >
                    <Plus className="size-4" />
                    Ajouter une valeur de rachat
                  </Button>
                </div>
                {(c.valeursRachat || []).map((rachat: ValeurRachat) => (
                  <div key={rachat.id} className="flex flex-wrap items-end gap-2">
                    <div className="space-y-1">
                      <Label className="text-xs">Date de rachat souhaitée</Label>
                      <Input
                        type="date"
                        value={rachat.date || ""}
                        onChange={(e) =>
                          updateContract(c.id, {
                            valeursRachat: (c.valeursRachat || []).map((row) =>
                              row.id === rachat.id ? { ...row, date: e.target.value } : row,
                            ),
                          })
                        }
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Montant disponible à cette date (CHF)</Label>
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        value={rachat.montant || ""}
                        onChange={(e) =>
                          updateContract(c.id, {
                            valeursRachat: (c.valeursRachat || []).map((row) =>
                              row.id === rachat.id
                                ? { ...row, montant: Number(e.target.value) || 0 }
                                : row,
                            ),
                          })
                        }
                      />
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="Supprimer la valeur de rachat"
                      onClick={() =>
                        updateContract(c.id, {
                          valeursRachat: (c.valeursRachat || []).filter(
                            (row) => row.id !== rachat.id,
                          ),
                        })
                      }
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
