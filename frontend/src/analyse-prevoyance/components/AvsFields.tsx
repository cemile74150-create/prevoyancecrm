// @ts-nocheck
"use client";

import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import { Button, buttonVariants } from "@/analyse-prevoyance/ui/button";
import type { AvsRenteAnticipee, PersonInput } from "@/analyse-prevoyance/lib/types";
import { avsAnnuelFromMensuel } from "@/analyse-prevoyance/lib/avsAnnuel";
import {
  ageAvecAnticipationAvs,
  anticipationAvsAnnees,
  formatLegalAgeLabel,
  getLegalRetirementAge,
} from "@/analyse-prevoyance/lib/avsAge";
import { useState } from "react";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { ConfirmDeleteButton } from "@/analyse-prevoyance/components/ConfirmDeleteButton";
import {
  annuelAvs,
  anticipationAvsRenseignee,
  formatChfAvs,
  suggestionAvsDepart,
} from "../../../../backend/analyse_prevoyance_engine/rules/analyse-avs-depart";

const ACOR_AVS_URL = "https://acor-avs.ch/requerant";

const CHAMPS_ANTICIPATION = [
  {
    depart: 63,
    titre: "Départ à 63 ans",
    lignes: [
      ["mensuel63Avant65", "Rente AVS mensuelle de 63 à 65 ans (CHF)"],
      ["mensuel63Des65", "Rente AVS mensuelle dès 65 ans (CHF)"],
    ],
  },
  {
    depart: 64,
    titre: "Départ à 64 ans",
    lignes: [
      ["mensuel64Avant65", "Rente AVS mensuelle de 64 à 65 ans (CHF)"],
      ["mensuel64Des65", "Rente AVS mensuelle dès 65 ans (CHF)"],
    ],
  },
  {
    depart: 65,
    titre: "Départ à 65 ans",
    lignes: [["mensuel65", "Rente AVS mensuelle dès 65 ans, sans anticipation (CHF)"]],
  },
];

function valeurAnticipation(person, cle) {
  const stocke = person?.avsDepart?.[cle];
  if (stocke == null) return "";
  return stocke;
}

export function AvsFields({
  title,
  person,
  onChange,
}: {
  title: string;
  person: PersonInput;
  onChange: (p: PersonInput) => void;
}) {
  const annuelle = avsAnnuelFromMensuel(person.avsMensuel);
  const anticipees = person.avsRentesAnticipees || [];
  const anticipation = anticipationAvsAnnees(person.anticipationAvsAnnees);
  const ageLegal = person.dateNaissance
    ? getLegalRetirementAge(person.civilite, person.dateNaissance)
    : null;
  const ageRetenu =
    ageLegal == null ? null : ageAvecAnticipationAvs(ageLegal, anticipation);
  const [anticipationOuverte, setAnticipationOuverte] = useState(() =>
    anticipationAvsRenseignee(person),
  );
  const suggestion = suggestionAvsDepart(person);
  const dejaActive = Boolean(person.avsDejaActive);

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
                avsAnnuel: avsAnnuelFromMensuel(avsMensuel),
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
          <p className="text-xs text-muted-foreground">Mensuelle × 13</p>
        </div>
        <div className="space-y-2">
          <Label>Anticipation AVS pour l'étude</Label>
          <select
            className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
            value={String(anticipation)}
            data-testid={`avs-anticipation-${title}`}
            onChange={(e) =>
              onChange({
                ...person,
                anticipationAvsAnnees: anticipationAvsAnnees(e.target.value),
              })
            }
          >
            <option value="0">À l'âge de référence</option>
            <option value="1">Anticipation de 1 an</option>
            <option value="2">Anticipation de 2 ans</option>
          </select>
          <p className="text-xs text-muted-foreground">
            {ageRetenu == null
              ? "Maximum 2 ans. L'âge et la date du retrait AVS suivent ce choix."
              : `Retrait AVS retenu : ${formatLegalAgeLabel(ageRetenu)}. Maximum 2 ans.`}
            {anticipation > 0
              ? ` Sans rente saisie à cet âge, la rente de référence est réduite de ${anticipation === 1 ? "6,8" : "13,6"} %.`
              : ""}
          </p>
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
        <label className="flex items-start gap-2 text-sm sm:col-span-3">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 shrink-0"
            checked={Boolean(person.avsMontantIssuSimulation)}
            onChange={(e) =>
              onChange({
                ...person,
                avsMontantIssuSimulation: e.target.checked,
              })
            }
            data-testid={`avs-simulation-checkbox-${title}`}
          />
          <span>Montant AVS issu d'une simulation (estimation)</span>
        </label>
        <label className="flex items-start gap-2 text-sm sm:col-span-3">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 shrink-0"
            checked={dejaActive}
            onChange={(e) =>
              onChange({
                ...person,
                avsDejaActive: e.target.checked,
              })
            }
            data-testid={`avs-deja-active-${title}`}
          />
          <span>AVS déjà active – L'assuré perçoit actuellement une rente AVS.</span>
        </label>
        {dejaActive && (
          <>
            <div className="space-y-2">
              <Label>Date de début de perception de la rente AVS</Label>
              <Input
                type="date"
                value={person.dateDebutRenteAvs || ""}
                onChange={(e) =>
                  onChange({ ...person, dateDebutRenteAvs: e.target.value || null })
                }
                data-testid={`avs-date-debut-${title}`}
                aria-required="true"
              />
              <p className="text-xs text-muted-foreground">JJ/MM/AAAA. Indépendante de la fin d'activité.</p>
            </div>
            <div className="space-y-2">
              <Label>Montant de la rente AVS mensuelle (CHF)</Label>
              <Input
                type="number"
                min={0}
                value={person.renteAvsPercueMensuelle ?? ""}
                onChange={(e) =>
                  onChange({
                    ...person,
                    renteAvsPercueMensuelle:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
                data-testid={`avs-montant-percu-${title}`}
                aria-required="true"
              />
              <p className="text-xs text-muted-foreground">
                {person.renteAvsPercueMensuelle
                  ? `Annuelle : ${formatChfAvs(annuelAvs(Number(person.renteAvsPercueMensuelle)))} (mensuelle × 13, une fois)`
                  : "Montant effectivement perçu. L'annuelle = mensuelle × 13."}
              </p>
            </div>
            {(!person.dateDebutRenteAvs || !(Number(person.renteAvsPercueMensuelle) > 0)) && (
              <p className="text-sm text-orange-800 sm:col-span-3">
                Date de début et montant mensuel obligatoires.
              </p>
            )}
          </>
        )}
      </div>
      {anticipees.length > 0 && (
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
      </div>
      )}
      {anticipationOuverte ? (
        <div className="space-y-3" data-testid={`avs-anticipation-champs-${title}`}>
          <div className="grid gap-3 lg:grid-cols-3">
            {CHAMPS_ANTICIPATION.map((bloc) => (
              <div key={bloc.depart} className="space-y-3 rounded-md bg-slate-50 p-3">
                <p className="text-sm font-medium">{bloc.titre}</p>
                {bloc.lignes.map(([cle, libelle]) => {
                  const affiche = valeurAnticipation(person, cle);
                  const propose = suggestion?.[cle];
                  const mensuel = affiche === "" ? null : Number(affiche);
                  return (
                    <div key={cle} className="space-y-1">
                      <Label className="text-xs">{libelle}</Label>
                      <Input
                        type="number"
                        min={0}
                        value={affiche}
                        placeholder={propose != null ? String(propose) : ""}
                        onChange={(e) => {
                          const brut = e.target.value;
                          const valeur = brut === "" ? null : Number(brut);
                          onChange({
                            ...person,
                            avsDepart: {
                              ...(person.avsDepart || {}),
                              [cle]: Number.isFinite(valeur) ? valeur : null,
                            },
                          });
                        }}
                        data-testid={`avs-${cle}`}
                      />
                      <p className="text-xs text-muted-foreground">
                        {mensuel == null || !Number.isFinite(mensuel)
                          ? "Annuelle : à compléter"
                          : `Annuelle : ${formatChfAvs(annuelAvs(mensuel))} (× 13)`}
                      </p>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setAnticipationOuverte(false)}
          >
            Masquer les rentes anticipées
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setAnticipationOuverte(true)}
        >
          <Plus className="size-4" />
          Ajouter une rente AVS anticipée
        </Button>
      )}
    </div>
  );
}
