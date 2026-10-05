// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import type {
  PersonInput,
  ThirdPillarContract,
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
          disabled={contracts.length >= 4}
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
              className="grid gap-2 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-5"
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
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeContract(c.id)}
                  aria-label="Supprimer contrat"
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
