// @ts-nocheck
"use client";

import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import { Button, buttonVariants } from "@/analyse-prevoyance/ui/button";
import type { AvsRenteAnticipee, PersonInput } from "@/analyse-prevoyance/lib/types";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { ConfirmDeleteButton } from "@/analyse-prevoyance/components/ConfirmDeleteButton";

const ACOR_AVS_URL = "https://acor-avs.ch/requerant";

export function AvsFields({
  title,
  person,
  onChange,
}: {
  title: string;
  person: PersonInput;
  onChange: (p: PersonInput) => void;
}) {
  const annuelle = Math.round((person.avsMensuel || 0) * 12);
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
            onChange={(e) => {
              const avsMensuel = Number(e.target.value) || 0;
              onChange({
                ...person,
                avsMensuel,
                avsAnnuel: Math.round(avsMensuel * 12),
              });
            }}
          />
        </div>
        <div className="space-y-2">
          <Label>AVS annuelle (CHF)</Label>
          <Input
            readOnly
            disabled
            className="bg-muted text-muted-foreground"
            value={annuelle}
            aria-label="AVS annuelle"
          />
          <p className="text-xs text-muted-foreground">Mensuelle × 12</p>
        </div>
        <div className="flex items-end">
          <a
            href={ACOR_AVS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "outline" })}
          >
            <ExternalLink className="size-4" />
            Simuler l'AVS
          </a>
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
            <ConfirmDeleteButton
              ariaLabel="Supprimer la rente AVS anticipée"
              onConfirm={() => setAnticipees(anticipees.filter((item) => item.id !== row.id))}
            >
              <Trash2 className="size-4" />
            </ConfirmDeleteButton>
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
