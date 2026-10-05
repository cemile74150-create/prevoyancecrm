// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/analyse-prevoyance/ui/select";
import type {
  Civilite,
  LppByAge,
  PersonInput,
  ThirdPillarContract,
} from "@/analyse-prevoyance/lib/types";
import { RETIREMENT_AGES } from "@/analyse-prevoyance/lib/types";

interface Props {
  title: string;
  person: PersonInput;
  onChange: (p: PersonInput) => void;
  showRentePont?: boolean;
}

export function PersonForm({ title, person, onChange, showRentePont }: Props) {
  function patch(partial: Partial<PersonInput>) {
    onChange({ ...person, ...partial });
  }

  function updateLpp(age: number, field: "capital" | "rente", value: number) {
    const lpp: LppByAge[] = RETIREMENT_AGES.map((a) => {
      const existing = person.lpp.find((r) => r.age === a) ?? {
        age: a,
        capital: 0,
        rente: 0,
      };
      if (a === age) return { ...existing, [field]: value };
      return existing;
    });
    patch({ lpp });
  }

  function addContract() {
    const c: ThirdPillarContract = {
      id: crypto.randomUUID(),
      echeance: "",
      montant: 0,
      police: "",
      prime: 0,
      compagnie: "",
    };
    patch({ troisiemePilier: [...person.troisiemePilier, c] });
  }

  function updateContract(id: string, partial: Partial<ThirdPillarContract>) {
    patch({
      troisiemePilier: person.troisiemePilier.map((c) =>
        c.id === id ? { ...c, ...partial } : c,
      ),
    });
  }

  function removeContract(id: string) {
    patch({
      troisiemePilier: person.troisiemePilier.filter((c) => c.id !== id),
    });
  }

  return (
    <div className="space-y-6">
      <h3 className="font-heading text-lg font-semibold tracking-tight">
        {title}
      </h3>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2">
          <Label>Civilité</Label>
          <Select
            value={person.civilite}
            onValueChange={(v) => patch({ civilite: v as Civilite })}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Monsieur">Monsieur</SelectItem>
              <SelectItem value="Madame">Madame</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Nom</Label>
          <Input
            value={person.nom}
            onChange={(e) => patch({ nom: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label>Prénom</Label>
          <Input
            value={person.prenom}
            onChange={(e) => patch({ prenom: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label>Date de naissance</Label>
          <Input
            type="date"
            value={person.dateNaissance}
            onChange={(e) => patch({ dateNaissance: e.target.value })}
          />
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-sm font-medium text-muted-foreground">
          AVS
        </h4>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>Rente mensuelle (CHF)</Label>
            <Input
              type="number"
              min={0}
              step={1}
              value={person.avsMensuel || ""}
              onChange={(e) =>
                patch({ avsMensuel: Number(e.target.value) || 0 })
              }
            />
            <p className="text-xs text-muted-foreground">
              Annuel calculé = mensuel × 13
            </p>
          </div>
          <div className="space-y-2">
            <Label>AVS annuel (optionnel, prioritaire)</Label>
            <Input
              type="number"
              min={0}
              step={1}
              value={person.avsAnnuel ?? ""}
              onChange={(e) =>
                patch({
                  avsAnnuel: e.target.value === "" ? null : Number(e.target.value) || 0,
                })
              }
            />
          </div>
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-sm font-medium text-muted-foreground">
          LPP par âge de retraite
        </h4>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[420px] text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Âge</th>
                <th className="px-3 py-2 text-left font-medium">Capital</th>
                <th className="px-3 py-2 text-left font-medium">Rente annuelle</th>
              </tr>
            </thead>
            <tbody>
              {RETIREMENT_AGES.map((age) => {
                const row = person.lpp.find((r) => r.age === age) ?? {
                  age,
                  capital: 0,
                  rente: 0,
                };
                return (
                  <tr key={age} className="border-t">
                    <td className="px-3 py-2 font-medium">{age}</td>
                    <td className="px-3 py-1.5">
                      <Input
                        type="number"
                        min={0}
                        className="h-8"
                        value={row.capital || ""}
                        onChange={(e) =>
                          updateLpp(age, "capital", Number(e.target.value) || 0)
                        }
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <Input
                        type="number"
                        min={0}
                        className="h-8"
                        value={row.rente || ""}
                        onChange={(e) =>
                          updateLpp(age, "rente", Number(e.target.value) || 0)
                        }
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {showRentePont && (
          <div className="mt-3 max-w-xs space-y-2">
            <Label>Rente pont</Label>
            <Input
              type="number"
              min={0}
              value={person.rentePont || ""}
              onChange={(e) =>
                patch({ rentePont: Number(e.target.value) || 0 })
              }
            />
          </div>
        )}
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between gap-2">
          <h4 className="text-sm font-medium text-muted-foreground">
            3e pilier (jusqu’à 4 contrats)
          </h4>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={person.troisiemePilier.length >= 4}
            onClick={addContract}
          >
            <Plus className="size-4" />
            Ajouter
          </Button>
        </div>
        {person.troisiemePilier.length === 0 ? (
          <p className="text-sm text-muted-foreground">Aucun contrat saisi.</p>
        ) : (
          <div className="space-y-3">
            {person.troisiemePilier.map((c) => (
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
    </div>
  );
}
