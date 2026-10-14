// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import { RENTE_PONT_CAISSE_WARNING } from "@/analyse-prevoyance/lib/planificationSaisie";
import type { LppByAge, PersonInput, RentePontInput } from "@/analyse-prevoyance/lib/types";
import {
  LPP_PCT_DEBLOCABLE_DEFAULT,
  RETIREMENT_AGES,
} from "@/analyse-prevoyance/lib/types";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";

function pontRows(person: PersonInput): RentePontInput[] {
  if (person.rentePonts?.length) return person.rentePonts;
  if ((person.rentePont || 0) > 0) {
    return [{
      id: "legacy-rente-pont",
      ageDebut: null,
      ageFin: null,
      montantAnnuel: person.rentePont || 0,
    }];
  }
  return [];
}

export function LppFields({
  title,
  person,
  onChange,
  dossierAge = null,
}: {
  title: string;
  person: PersonInput;
  onChange: (p: PersonInput) => void;
  /** Âge de l'onglet Client, repris tant que l'âge LPP n'est pas personnalisé. */
  dossierAge?: number | null;
}) {
  const pct =
    person.lppPctDeblocable == null || Number.isNaN(person.lppPctDeblocable)
      ? LPP_PCT_DEBLOCABLE_DEFAULT
      : person.lppPctDeblocable;
  const lpp65 = person.lpp.find((r) => r.age === 65) ?? {
    age: 65 as const,
    capital: 0,
    rente: 0,
  };
  const capitalRetire = Math.round((lpp65.capital || 0) * (pct / 100));
  const renteResiduelle = Math.round((lpp65.rente || 0) * (1 - pct / 100));
  const personalized =
    person.ageRetraitLppSouhaite != null &&
    Number.isFinite(Number(person.ageRetraitLppSouhaite));
  const ageShown = personalized ? person.ageRetraitLppSouhaite : (dossierAge ?? "");
  const ponts = pontRows(person);

  function setPonts(next: RentePontInput[]) {
    onChange({ ...person, rentePonts: next, rentePont: 0 });
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
    onChange({ ...person, lpp });
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium">{title}</h3>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[480px] text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Âge</th>
              <th className="px-3 py-2 text-left font-medium">Capital (CHF)</th>
              <th className="px-3 py-2 text-left font-medium">
                Rente annuelle (CHF)
              </th>
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

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="space-y-2">
          <Label>% LPP disponible</Label>
          <Input
            type="number"
            min={0}
            max={100}
            step={1}
            value={pct}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") {
                onChange({ ...person, lppPctDeblocable: LPP_PCT_DEBLOCABLE_DEFAULT });
                return;
              }
              const v = Number(raw);
              onChange({
                ...person,
                lppPctDeblocable: Number.isFinite(v)
                  ? Math.min(100, Math.max(0, v))
                  : LPP_PCT_DEBLOCABLE_DEFAULT,
              });
            }}
          />
          <p className="text-xs text-muted-foreground">
            Saisie libre (100, 50, 25…). Défaut {LPP_PCT_DEBLOCABLE_DEFAULT} % si
            non renseigné.
          </p>
        </div>
        <div className="space-y-1 rounded-md border bg-muted/30 px-3 py-2 text-sm">
          <p className="text-xs text-muted-foreground">À 65 ans (aperçu)</p>
          <p>
            Capital retiré : <strong>{formatChf(capitalRetire)}</strong>
          </p>
          <p>
            Rente résiduelle : <strong>{formatChf(renteResiduelle)}</strong>
          </p>
        </div>
      </div>

      <div className="max-w-xs space-y-2">
        <Label>Âge souhaité de retrait LPP</Label>
        <Input
          type="number"
          min={50}
          max={70}
          value={ageShown ?? ""}
          onChange={(e) =>
            onChange({
              ...person,
              ageRetraitLppSouhaite:
                e.target.value === "" ? null : Number(e.target.value),
            })
          }
        />
        <p className="text-xs text-muted-foreground">
          {personalized
            ? "Valeur propre à cet assuré. Elle reste en place si l'âge du dossier change."
            : "Reprend l'âge de retraite souhaité de l'onglet Client. Modifiez-le ici pour le personnaliser."}
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-medium">Rente-pont</h4>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              setPonts([
                ...ponts,
                {
                  id: crypto.randomUUID(),
                  ageDebut: null,
                  ageFin: null,
                  montantAnnuel: 0,
                },
              ])
            }
          >
            <Plus className="size-4" />
            Ajouter une rente-pont
          </Button>
        </div>
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
          {RENTE_PONT_CAISSE_WARNING}
        </p>
        {ponts.length === 0 ? (
          <p className="text-xs text-muted-foreground">Aucune rente-pont.</p>
        ) : (
          ponts.map((row) => (
            <div key={row.id} className="flex flex-wrap items-end gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Âge de début de la rente-pont</Label>
                <Input
                  type="number"
                  min={50}
                  max={70}
                  className="w-28"
                  value={row.ageDebut ?? ""}
                  onChange={(e) =>
                    setPonts(
                      ponts.map((item) =>
                        item.id === row.id
                          ? {
                              ...item,
                              ageDebut:
                                e.target.value === "" ? null : Number(e.target.value),
                            }
                          : item,
                      ),
                    )
                  }
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Montant de la rente-pont (CHF/an)</Label>
                <Input
                  type="number"
                  min={0}
                  className="w-40"
                  value={row.montantAnnuel || ""}
                  onChange={(e) =>
                    setPonts(
                      ponts.map((item) =>
                        item.id === row.id
                          ? { ...item, montantAnnuel: Number(e.target.value) || 0 }
                          : item,
                      ),
                    )
                  }
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Âge de fin</Label>
                <Input
                  type="number"
                  min={50}
                  max={80}
                  className="w-28"
                  value={row.ageFin ?? ""}
                  onChange={(e) =>
                    setPonts(
                      ponts.map((item) =>
                        item.id === row.id
                          ? {
                              ...item,
                              ageFin:
                                e.target.value === "" ? null : Number(e.target.value),
                            }
                          : item,
                      ),
                    )
                  }
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setPonts(ponts.filter((item) => item.id !== row.id))}
                aria-label="Supprimer la rente-pont"
              >
                <Trash2 className="size-4" />
              </Button>
              {(row.ageDebut == null || row.ageFin == null) && (
                <p className="w-full text-xs text-amber-800">
                  Période incomplète : la rente-pont n&apos;est pas projetée. Le calcul est à vérifier.
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
