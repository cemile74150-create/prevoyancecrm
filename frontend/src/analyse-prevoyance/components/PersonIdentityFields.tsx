// @ts-nocheck
"use client";

import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/analyse-prevoyance/ui/select";
import type { Civilite, PersonInput } from "@/analyse-prevoyance/lib/types";
import {
  desiredRetirementAgeOptions,
  legalAgeLabel,
} from "@/analyse-prevoyance/lib/avsAge";

export function PersonIdentityFields({
  person,
  onChange,
  desiredAge,
  onDesiredAge,
}: {
  person: PersonInput;
  onChange: (p: PersonInput) => void;
  desiredAge: number | null;
  onDesiredAge: (age: number | null) => void;
}) {
  function patch(partial: Partial<PersonInput>) {
    onChange({ ...person, ...partial });
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div className="space-y-2">
        <Label>Prénom</Label>
        <Input
          value={person.prenom}
          onChange={(e) => patch({ prenom: e.target.value })}
        />
      </div>
      <div className="space-y-2">
        <Label>Nom</Label>
        <Input
          value={person.nom}
          onChange={(e) => patch({ nom: e.target.value })}
        />
      </div>
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
        <Label>Date de naissance</Label>
        <Input
          type="date"
          value={person.dateNaissance}
          onChange={(e) => patch({ dateNaissance: e.target.value })}
        />
      </div>
      <div className="space-y-2">
        <Label>Âge légal de référence AVS</Label>
        <Input
          readOnly
          disabled
          className="bg-muted text-muted-foreground"
          value={legalAgeLabel(person.civilite, person.dateNaissance)}
          aria-label="Âge légal de référence AVS"
        />
      </div>
      <div className="space-y-2">
        <Label>Âge de retraite souhaité (début des rentes de retraite)</Label>
        <select
          className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
          value={desiredAge == null ? "" : String(desiredAge)}
          onChange={(e) =>
            onDesiredAge(e.target.value === "" ? null : Number(e.target.value))
          }
        >
          <option value="">Âge applicable au dossier</option>
          {desiredRetirementAgeOptions(
            person.civilite,
            person.dateNaissance,
          ).map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
