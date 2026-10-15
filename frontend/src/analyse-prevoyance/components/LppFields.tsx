// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import { RENTE_PONT_CAISSE_WARNING } from "@/analyse-prevoyance/lib/planificationSaisie";
import type {
  LppAvoir,
  LppByAge,
  LppCaisseType,
  LppRenteUnite,
  LppRetraitEtatique,
  PersonInput,
  RentePontInput,
} from "@/analyse-prevoyance/lib/types";
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

function emptyLppAvoir(): LppAvoir {
  return {
    id: crypto.randomUUID(),
    institution: "",
    rows: RETIREMENT_AGES.map((age) => ({ age, capital: 0, rente: 0 })),
    type: "classique",
    renteUnite: "annuel",
    ageRetrait: null,
    retraitEtatique: "capital_max",
    pctDeblocable: LPP_PCT_DEBLOCABLE_DEFAULT,
  };
}

function annualAmount(amount: number | null | undefined, unite: LppRenteUnite | undefined): number {
  const value = Number(amount) || 0;
  const yearly = unite === "mensuel" ? value * 12 : value;
  return Math.round(yearly * 100) / 100;
}

function etatiquePreview(
  row: LppByAge,
  unite: LppRenteUnite | undefined,
  mode: LppRetraitEtatique | undefined,
): { capital: number; residuelle: number } {
  const renteEntiere = annualAmount(row.rente, unite);
  const renteReduite = annualAmount(row.renteReduite, unite);
  const capitalMax = Math.round((row.capital || 0) * 100) / 100;
  if (mode === "rente_entiere") return { capital: 0, residuelle: renteEntiere };
  if (mode === "saisi" && row.capitalSaisi != null && row.renteConserveeSaisie != null) {
    return {
      capital: Math.round(row.capitalSaisi * 100) / 100,
      residuelle: annualAmount(row.renteConserveeSaisie, unite),
    };
  }
  return { capital: capitalMax, residuelle: renteReduite };
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
  const etatique = person.lppType === "etatique";
  const etat65 = etatiquePreview(
    lpp65,
    person.lppRenteUnite,
    person.lppRetraitEtatique,
  );
  const avoirs = person.lppAvoirs || [];

  function setPonts(next: RentePontInput[]) {
    onChange({ ...person, rentePonts: next, rentePont: 0 });
  }

  function updateLpp(
    age: number,
    field: "capital" | "rente" | "renteReduite" | "capitalSaisi" | "renteConserveeSaisie",
    value: number,
  ) {
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
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>Caisse</Label>
          <Input
            value={person.lppInstitution || ""}
            onChange={(e) => onChange({ ...person, lppInstitution: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label>Type de caisse</Label>
          <select
            className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
            value={etatique ? "etatique" : "classique"}
            onChange={(e) =>
              onChange({
                ...person,
                lppType: e.target.value === "etatique" ? "etatique" : "classique",
              })
            }
          >
            <option value="classique">LPP classique</option>
            <option value="etatique">Caisse étatique</option>
          </select>
        </div>
      </div>
      {etatique && (
        <CaisseEtatiqueOptions
          unite={person.lppRenteUnite}
          mode={person.lppRetraitEtatique}
          onUnite={(renteUnite) => onChange({ ...person, lppRenteUnite: renteUnite })}
          onMode={(retraitEtatique) => onChange({ ...person, lppRetraitEtatique: retraitEtatique })}
        />
      )}
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[480px] text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Âge</th>
              <th className="px-3 py-2 text-left font-medium">
                {etatique ? "Capital maximal (CHF)" : "Capital (CHF)"}
              </th>
              <th className="px-3 py-2 text-left font-medium">
                {etatique ? "Rente entière (CHF)" : "Rente annuelle (CHF)"}
              </th>
              {etatique && (
                <th className="px-3 py-2 text-left font-medium">Rente réduite (CHF)</th>
              )}
              {etatique && person.lppRetraitEtatique === "saisi" && (
                <>
                  <th className="px-3 py-2 text-left font-medium">Capital saisi</th>
                  <th className="px-3 py-2 text-left font-medium">Rente conservée</th>
                </>
              )}
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
                  {etatique && (
                    <td className="px-3 py-1.5">
                      <Input
                        type="number"
                        min={0}
                        className="h-8"
                        value={row.renteReduite ?? ""}
                        onChange={(e) =>
                          updateLpp(age, "renteReduite", Number(e.target.value) || 0)
                        }
                      />
                    </td>
                  )}
                  {etatique && person.lppRetraitEtatique === "saisi" && (
                    <>
                      <td className="px-3 py-1.5">
                        <Input
                          type="number"
                          min={0}
                          className="h-8"
                          value={row.capitalSaisi ?? ""}
                          onChange={(e) =>
                            updateLpp(age, "capitalSaisi", Number(e.target.value) || 0)
                          }
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <Input
                          type="number"
                          min={0}
                          className="h-8"
                          value={row.renteConserveeSaisie ?? ""}
                          onChange={(e) =>
                            updateLpp(age, "renteConserveeSaisie", Number(e.target.value) || 0)
                          }
                        />
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {!etatique && (
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
        )}
        <div className="space-y-1 rounded-md border bg-muted/30 px-3 py-2 text-sm">
          <p className="text-xs text-muted-foreground">À 65 ans (aperçu)</p>
          {etatique ? (
            <>
              <p>
                Capital maximal : <strong>{formatChf(etat65.capital)}</strong>
              </p>
              <p>
                Rente réduite : <strong>{formatChf(etat65.residuelle)}</strong>
              </p>
            </>
          ) : (
            <>
              <p>
                Capital retiré : <strong>{formatChf(capitalRetire)}</strong>
              </p>
              <p>
                Rente résiduelle : <strong>{formatChf(renteResiduelle)}</strong>
              </p>
            </>
          )}
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

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h4 className="text-sm font-medium">Autres caisses LPP</h4>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              onChange({ ...person, lppAvoirs: [...avoirs, emptyLppAvoir()] })
            }
          >
            <Plus className="size-4" />
            Ajouter une LPP
          </Button>
        </div>
        {avoirs.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Une seule caisse. Chaque caisse ajoutée a ses propres montants.
          </p>
        ) : (
          avoirs.map((avoir) => (
            <ExtraLppCard
              key={avoir.id}
              avoir={avoir}
              onChange={(next) =>
                onChange({
                  ...person,
                  lppAvoirs: avoirs.map((item) => (item.id === avoir.id ? next : item)),
                })
              }
              onRemove={() =>
                onChange({
                  ...person,
                  lppAvoirs: avoirs.filter((item) => item.id !== avoir.id),
                })
              }
            />
          ))
        )}
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

function CaisseEtatiqueOptions({
  unite,
  mode,
  onUnite,
  onMode,
}: {
  unite: LppRenteUnite | undefined;
  mode: LppRetraitEtatique | undefined;
  onUnite: (unite: LppRenteUnite) => void;
  onMode: (mode: LppRetraitEtatique) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="space-y-2">
        <Label>Unité de la rente</Label>
        <select
          className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
          value={unite === "mensuel" ? "mensuel" : "annuel"}
          onChange={(e) => onUnite(e.target.value === "mensuel" ? "mensuel" : "annuel")}
        >
          <option value="annuel">Annuelle</option>
          <option value="mensuel">Mensuelle</option>
        </select>
        <p className="text-xs text-muted-foreground">
          Une rente saisie au mois est ramenée à l&apos;année.
        </p>
      </div>
      <div className="space-y-2">
        <Label>Scénario capital</Label>
        <select
          className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
          value={mode || "capital_max"}
          onChange={(e) => onMode(e.target.value as LppRetraitEtatique)}
        >
          <option value="capital_max">Capital maximal et rente réduite</option>
          <option value="rente_entiere">Rente entière, sans capital</option>
          <option value="saisi">Capital et rente saisis</option>
        </select>
      </div>
    </div>
  );
}

function ExtraLppCard({
  avoir,
  onChange,
  onRemove,
}: {
  avoir: LppAvoir;
  onChange: (avoir: LppAvoir) => void;
  onRemove: () => void;
}) {
  const etatique = avoir.type === "etatique";
  function updateRow(
    age: number,
    field: "capital" | "rente" | "renteReduite",
    value: number,
  ) {
    onChange({
      ...avoir,
      rows: RETIREMENT_AGES.map((itemAge) => {
        const existing = avoir.rows.find((row) => row.age === itemAge) ?? {
          age: itemAge,
          capital: 0,
          rente: 0,
        };
        if (itemAge !== age) return existing;
        return { ...existing, [field]: value };
      }),
    });
  }

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[180px] flex-1 space-y-1">
          <Label className="text-xs">Caisse</Label>
          <Input
            value={avoir.institution}
            onChange={(e) => onChange({ ...avoir, institution: e.target.value })}
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Type</Label>
          <select
            className="border-input bg-background h-8 rounded-md border px-2 text-sm"
            value={etatique ? "etatique" : "classique"}
            onChange={(e) =>
              onChange({
                ...avoir,
                type: (e.target.value === "etatique" ? "etatique" : "classique") as LppCaisseType,
              })
            }
          >
            <option value="classique">LPP classique</option>
            <option value="etatique">Caisse étatique</option>
          </select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Âge de retrait</Label>
          <Input
            type="number"
            min={50}
            max={70}
            className="w-24"
            value={avoir.ageRetrait ?? ""}
            onChange={(e) =>
              onChange({
                ...avoir,
                ageRetrait: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          />
        </div>
        <Button type="button" variant="ghost" size="icon" onClick={onRemove} aria-label="Supprimer la caisse">
          <Trash2 className="size-4" />
        </Button>
      </div>
      {etatique ? (
        <CaisseEtatiqueOptions
          unite={avoir.renteUnite}
          mode={avoir.retraitEtatique}
          onUnite={(renteUnite) => onChange({ ...avoir, renteUnite })}
          onMode={(retraitEtatique) => onChange({ ...avoir, retraitEtatique })}
        />
      ) : (
        <div className="max-w-xs space-y-1">
          <Label className="text-xs">% LPP disponible</Label>
          <Input
            type="number"
            min={0}
            max={100}
            value={avoir.pctDeblocable ?? LPP_PCT_DEBLOCABLE_DEFAULT}
            onChange={(e) =>
              onChange({
                ...avoir,
                pctDeblocable: Math.min(100, Math.max(0, Number(e.target.value) || 0)),
              })
            }
          />
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="py-1 pr-2">Âge</th>
              <th className="py-1 pr-2">{etatique ? "Capital maximal" : "Capital"}</th>
              <th className="py-1 pr-2">{etatique ? "Rente entière" : "Rente annuelle"}</th>
              {etatique && <th className="py-1">Rente réduite</th>}
            </tr>
          </thead>
          <tbody>
            {RETIREMENT_AGES.map((age) => {
              const row = avoir.rows.find((item) => item.age === age) ?? {
                age,
                capital: 0,
                rente: 0,
              };
              return (
                <tr key={age}>
                  <td className="py-1 pr-2">{age}</td>
                  <td className="py-1 pr-2">
                    <Input
                      type="number"
                      min={0}
                      className="h-8"
                      value={row.capital || ""}
                      onChange={(e) => updateRow(age, "capital", Number(e.target.value) || 0)}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <Input
                      type="number"
                      min={0}
                      className="h-8"
                      value={row.rente || ""}
                      onChange={(e) => updateRow(age, "rente", Number(e.target.value) || 0)}
                    />
                  </td>
                  {etatique && (
                    <td className="py-1">
                      <Input
                        type="number"
                        min={0}
                        className="h-8"
                        value={row.renteReduite ?? ""}
                        onChange={(e) =>
                          updateRow(age, "renteReduite", Number(e.target.value) || 0)
                        }
                      />
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
