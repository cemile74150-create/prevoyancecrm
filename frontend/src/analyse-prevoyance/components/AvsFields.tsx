// @ts-nocheck
"use client";

import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import { Button } from "@/analyse-prevoyance/ui/button";
import type { AvsRenteAnticipee, PersonInput } from "@/analyse-prevoyance/lib/types";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";
import { Plus, Trash2 } from "lucide-react";

export function AvsFields({
  title,
  person,
  onChange,
}: {
  title: string;
  person: PersonInput;
  onChange: (p: PersonInput) => void;
}) {
  const calcAnnuel = Math.round((person.avsMensuel || 0) * 13);
  const annuelle =
    person.avsAnnuel != null && person.avsAnnuel > 0 ? person.avsAnnuel : calcAnnuel;
  const anticipees = person.avsRentesAnticipees || [];

  function setAnticipees(next: AvsRenteAnticipee[]) {
    onChange({ ...person, avsRentesAnticipees: next });
  }

  return (
    <div className="space-y-3 rounded-md border p-3">
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label>Rente mensuelle (CHF)</Label>
          <Input
            type="number"
            min={0}
            value={person.avsMensuel || ""}
            onChange={(e) =>
              onChange({ ...person, avsMensuel: Number(e.target.value) || 0 })
            }
          />
        </div>
        <div className="space-y-2">
          <Label>Rente AVS à 65 ans (CHF / an)</Label>
          <Input
            type="number"
            min={0}
            value={person.avsAnnuel ?? ""}
            onChange={(e) =>
              onChange({
                ...person,
                avsAnnuel:
                  e.target.value === "" ? null : Number(e.target.value) || 0,
              })
            }
          />
          <p className="text-sm tabular-nums">
            Rente AVS à 65 ans : {formatChf(annuelle)} / an
          </p>
        </div>
      </div>
      <div className="space-y-2">
        {anticipees.map((row) => (
          <div key={row.id} className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label className="text-xs">Âge</Label>
              <Input
                type="number"
                min={60}
                max={64}
                className="w-24"
                value={row.age}
                onChange={(e) =>
                  setAnticipees(
                    anticipees.map((item) =>
                      item.id === row.id
                        ? { ...item, age: Number(e.target.value) || row.age }
                        : item,
                    ),
                  )
                }
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Rente AVS à {row.age} ans (CHF / an)</Label>
              <Input
                type="number"
                min={0}
                value={row.montantAnnuel || ""}
                onChange={(e) =>
                  setAnticipees(
                    anticipees.map((item) =>
                      item.id === row.id
                        ? { ...item, montantAnnuel: Number(e.target.value) || 0 }
                        : item,
                    ),
                  )
                }
              />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setAnticipees(anticipees.filter((item) => item.id !== row.id))}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            setAnticipees([
              ...anticipees,
              {
                id: `avs-${Date.now()}`,
                age: 64,
                montantAnnuel: 0,
              },
            ])
          }
        >
          <Plus className="size-4" />
          Ajouter une rente AVS anticipée
        </Button>
      </div>
    </div>
  );
}
