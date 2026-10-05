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

export function PersonIdentityFields({
  person,
  onChange,
}: {
  person: PersonInput;
  onChange: (p: PersonInput) => void;
}) {
  function patch(partial: Partial<PersonInput>) {
    onChange({ ...person, ...partial });
  }

  return (
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
  );
}
