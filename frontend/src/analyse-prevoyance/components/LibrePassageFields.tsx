// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import {
  emptyLibrePassage,
  librePassageRetire,
  type AnalyseInput,
  type LibrePassageAsset,
  type PersonKey,
} from "@/analyse-prevoyance/lib/types";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";

export function LibrePassageFields({
  input,
  onChange,
}: {
  input: AnalyseInput;
  onChange: (libresPassages: LibrePassageAsset[]) => void;
}) {
  const list = input.libresPassages || [];
  const married = input.etatCivil === "Marié(e)";

  function add(titulaire: PersonKey) {
    onChange([...list, emptyLibrePassage(titulaire)]);
  }

  function update(id: string, partial: Partial<LibrePassageAsset>) {
    onChange(list.map((lp) => (lp.id === id ? { ...lp, ...partial } : lp)));
  }

  function remove(id: string) {
    onChange(list.filter((lp) => lp.id !== id));
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">Libres passages</h3>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => add("client1")}>
            <Plus className="size-4" />
            Assuré 1
          </Button>
          {married && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => add("conjoint")}
            >
              <Plus className="size-4" />
              Assuré 2
            </Button>
          )}
        </div>
      </div>
      {list.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Aucun libre passage. Ajoutez 0..N avoirs (montant, %, date possible).
        </p>
      ) : (
        <div className="space-y-3">
          {list.map((lp) => {
            const retire = librePassageRetire(lp);
            return (
              <div
                key={lp.id}
                className="grid gap-2 rounded-md border p-3 sm:grid-cols-2 lg:grid-cols-6"
              >
                <div className="space-y-1">
                  <Label className="text-xs">Titulaire</Label>
                  <select
                    className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
                    value={lp.titulaire}
                    onChange={(e) =>
                      update(lp.id, {
                        titulaire: e.target.value as PersonKey,
                      })
                    }
                  >
                    <option value="client1">Assuré 1</option>
                    {married && <option value="conjoint">Assuré 2</option>}
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Institution</Label>
                  <Input
                    value={lp.institution}
                    onChange={(e) =>
                      update(lp.id, { institution: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Montant total (CHF)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={lp.montant || ""}
                    onChange={(e) =>
                      update(lp.id, {
                        montant: Number(e.target.value) || 0,
                      })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">% retiré</Label>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    value={lp.pctRetire}
                    onChange={(e) =>
                      update(lp.id, {
                        pctRetire: Math.min(
                          100,
                          Math.max(0, Number(e.target.value) || 0),
                        ),
                      })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Âge de déblocage</Label>
                  <Input
                    type="number"
                    min={50}
                    max={70}
                    placeholder="ex. 64"
                    value={lp.ageDeblocage ?? ""}
                    onChange={(e) =>
                      update(lp.id, {
                        ageDeblocage:
                          e.target.value === "" ? null : Number(e.target.value) || null,
                      })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Date de retrait</Label>
                  <Input
                    type="date"
                    value={lp.dateRetraitPossible || ""}
                    onChange={(e) =>
                      update(lp.id, { dateRetraitPossible: e.target.value })
                    }
                  />
                </div>
                <div className="flex items-end justify-between gap-2">
                  <p className="text-xs text-muted-foreground">
                    Capital effectivement retiré : <strong>{formatChf(retire)}</strong>
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => remove(lp.id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
