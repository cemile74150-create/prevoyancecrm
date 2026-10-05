// @ts-nocheck
"use client";

import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import type { LppByAge, PersonInput } from "@/analyse-prevoyance/lib/types";
import {
  LPP_PCT_DEBLOCABLE_DEFAULT,
  RETIREMENT_AGES,
} from "@/analyse-prevoyance/lib/types";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";

export function LppFields({
  title,
  person,
  onChange,
  showRentePont,
}: {
  title: string;
  person: PersonInput;
  onChange: (p: PersonInput) => void;
  showRentePont?: boolean;
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
          <Label>% LPP déblocable en capital</Label>
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
            non renseigné. ESTV capital = capital × ce %.
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

      {showRentePont && (
        <div className="max-w-xs space-y-2">
          <Label>Rente pont</Label>
          <Input
            type="number"
            min={0}
            value={person.rentePont || ""}
            onChange={(e) =>
              onChange({ ...person, rentePont: Number(e.target.value) || 0 })
            }
          />
        </div>
      )}
    </div>
  );
}
