// @ts-nocheck
"use client";

import { useState } from "react";
import {
  Calculator,
  Copy,
  Plus,
  Trash2,
} from "lucide-react";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import type {
  AnalyseInput,
  PersonComputed,
  WithdrawalPlanItem,
  WithdrawalScenario,
  WithdrawalScenarioResult,
} from "@/analyse-prevoyance/lib/types";
import {
  buildDefaultWithdrawalItems,
  duplicateWithdrawalScenario,
  kindLabel,
  newEmptyScenario,
} from "@/analyse-prevoyance/lib/withdrawalDefaults";
import {
  itemMontantRetire,
  mergeCalendarWithResult,
} from "@/analyse-prevoyance/lib/withdrawalPlanUtils";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";

/**
 * Section planification des retraits — tableau, calendrier, scénarios.
 * Pas de règles légales inventées (1re/dernière année = saisie libre).
 */
export function WithdrawalPlanningFields({
  input,
  onChange,
  previewBasics,
  planningResults,
  onRecalculate,
  recalculatePending,
}: {
  input: AnalyseInput;
  onChange: (scenarios: WithdrawalScenario[]) => void;
  previewBasics?: {
    client1: PersonComputed;
    conjoint: PersonComputed | null;
  } | null;
  planningResults?: WithdrawalScenarioResult[] | null;
  onRecalculate?: () => void;
  recalculatePending?: boolean;
}) {
  const scenarios = input.withdrawalScenarios || [];
  const [activeId, setActiveId] = useState<string | null>(
    scenarios[0]?.id ?? null,
  );
  const active =
    scenarios.find((s) => s.id === activeId) || scenarios[0] || null;
  const activeResult =
    planningResults?.find((r) => r.scenarioId === active?.id) ?? null;

  function addScenario(preset: "A" | "B" | "C" | "empty") {
    const id = `sc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    let items: WithdrawalPlanItem[] = [];
    let name = "Nouveau scénario";
    if (previewBasics && preset !== "empty") {
      items = buildDefaultWithdrawalItems(
        input,
        previewBasics.client1,
        previewBasics.conjoint,
      );
      if (preset === "A") {
        name = "A — Regroupé (même année si possible)";
        const years = items
          .map((i) => i.anneeRetraitPrevue)
          .filter((y): y is number => y != null);
        const y = years.length ? Math.min(...years) : null;
        items = items.map((i) => ({ ...i, anneeRetraitPrevue: y }));
      } else if (preset === "B") {
        name = "B — Réparti (dates sources)";
      } else {
        name = "C — Personnalisé";
      }
    } else if (preset !== "empty") {
      name =
        preset === "A"
          ? "A — Regroupé"
          : preset === "B"
            ? "B — Réparti"
            : "C — Personnalisé";
    }
    const sc: WithdrawalScenario = {
      id,
      name,
      items,
      includeInReport: false,
    };
    onChange([...scenarios, sc]);
    setActiveId(id);
  }

  function updateScenario(id: string, partial: Partial<WithdrawalScenario>) {
    onChange(
      scenarios.map((s) => (s.id === id ? { ...s, ...partial } : s)),
    );
  }

  function removeScenario(id: string) {
    const next = scenarios.filter((s) => s.id !== id);
    onChange(next);
    if (activeId === id) setActiveId(next[0]?.id ?? null);
  }

  function duplicate(id: string) {
    const src = scenarios.find((s) => s.id === id);
    if (!src) return;
    const copy = duplicateWithdrawalScenario(src);
    onChange([...scenarios, copy]);
    setActiveId(copy.id);
  }

  function updateItem(
    scenarioId: string,
    itemId: string,
    partial: Partial<WithdrawalPlanItem>,
  ) {
    onChange(
      scenarios.map((s) =>
        s.id !== scenarioId
          ? s
          : {
              ...s,
              items: s.items.map((it) =>
                it.id === itemId ? { ...it, ...partial } : it,
              ),
            },
      ),
    );
  }

  function removeItem(scenarioId: string, itemId: string) {
    onChange(
      scenarios.map((s) =>
        s.id !== scenarioId
          ? s
          : { ...s, items: s.items.filter((it) => it.id !== itemId) },
      ),
    );
  }

  function refillFromDossier(scenarioId: string) {
    if (!previewBasics) return;
    const items = buildDefaultWithdrawalItems(
      input,
      previewBasics.client1,
      previewBasics.conjoint,
    );
    updateScenario(scenarioId, { items });
  }

  const calendar = active
    ? mergeCalendarWithResult(active.items, activeResult)
    : [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium">Planification des retraits</h3>
          <p className="text-xs text-muted-foreground">
            Tableau interactif · calendrier · scénarios. Agrégation ESTV :
            personne + année. Pas de qualification « meilleur ».
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => addScenario("A")}
            disabled={!previewBasics}
          >
            <Plus className="size-4" />A regroupé
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => addScenario("B")}
            disabled={!previewBasics}
          >
            <Plus className="size-4" />B réparti
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => addScenario("C")}
            disabled={!previewBasics}
          >
            <Plus className="size-4" />C perso
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              const sc = newEmptyScenario();
              onChange([...scenarios, sc]);
              setActiveId(sc.id);
            }}
          >
            Vide
          </Button>
          {onRecalculate && (
            <Button
              type="button"
              size="sm"
              onClick={onRecalculate}
              disabled={recalculatePending || scenarios.length === 0}
            >
              <Calculator className="size-4" />
              {recalculatePending
                ? "Calcul ESTV…"
                : "Recalculer la fiscalité"}
            </Button>
          )}
        </div>
      </div>

      {!previewBasics && (
        <p className="text-xs text-amber-800 dark:text-amber-200">
          Astuce : lancez un calcul pour préremplir LPP / LP / 3P. Les années
          1re/dernière possibles restent en saisie libre (aucune règle légale
          inventée).
        </p>
      )}

      {scenarios.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Aucun scénario. Cochez « Inclure dans le rapport » sur 1–2 scénarios
          pour la page PDF (opt-in).
        </p>
      ) : (
        <>
          {/* Liste scénarios */}
          <div className="flex flex-wrap gap-2">
            {scenarios.map((sc) => (
              <button
                key={sc.id}
                type="button"
                onClick={() => setActiveId(sc.id)}
                className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
                  active?.id === sc.id
                    ? "border-[var(--ap-accent)] bg-[var(--ap-accent)]/10 font-medium"
                    : "hover:bg-muted/50"
                }`}
              >
                {sc.name}
                {sc.includeInReport && (
                  <span className="ml-1 text-[10px] text-[var(--ap-accent)]">
                    PDF
                  </span>
                )}
              </button>
            ))}
          </div>

          {active && (
            <div className="space-y-4 rounded-md border p-3">
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-[200px] flex-1 space-y-1">
                  <Label className="text-xs">Nom du scénario</Label>
                  <Input
                    value={active.name}
                    onChange={(e) =>
                      updateScenario(active.id, { name: e.target.value })
                    }
                  />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={!!active.includeInReport}
                    onChange={(e) =>
                      updateScenario(active.id, {
                        includeInReport: e.target.checked,
                      })
                    }
                  />
                  Inclure dans le rapport
                </label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => duplicate(active.id)}
                >
                  <Copy className="size-4" />
                  Dupliquer
                </Button>
                {previewBasics && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => refillFromDossier(active.id)}
                  >
                    Recharger capitaux
                  </Button>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => removeScenario(active.id)}
                >
                  <Trash2 className="size-4" />
                  Supprimer
                </Button>
              </div>

              {/* 1. Tableau interactif */}
              <div>
                <h4 className="mb-2 text-sm font-medium">
                  Capitaux disponibles
                </h4>
                {active.items.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Aucune ligne — utilisez A/B/C après calcul, ou « Recharger
                    capitaux ».
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[900px] text-sm">
                      <thead className="bg-muted/40 text-left">
                        <tr>
                          <th className="px-2 py-1">Titulaire</th>
                          <th className="px-2 py-1">Type</th>
                          <th className="px-2 py-1">Institution</th>
                          <th className="px-2 py-1">Dispo</th>
                          <th className="px-2 py-1">% retiré</th>
                          <th className="px-2 py-1">Montant retiré</th>
                          <th className="px-2 py-1">Année prévue</th>
                          <th className="px-2 py-1">1re possible</th>
                          <th className="px-2 py-1">Dernière</th>
                          <th className="px-2 py-1" />
                        </tr>
                      </thead>
                      <tbody>
                        {active.items.map((it) => (
                          <tr key={it.id} className="border-t">
                            <td className="px-2 py-1">
                              {it.titulaire === "client1"
                                ? "Assuré 1"
                                : "Assuré 2"}
                            </td>
                            <td className="px-2 py-1">
                              <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">
                                {kindLabel(it.kind)}
                              </span>
                            </td>
                            <td className="px-2 py-1">
                              <Input
                                className="h-8 min-w-[100px]"
                                value={it.institution || ""}
                                onChange={(e) =>
                                  updateItem(active.id, it.id, {
                                    institution: e.target.value,
                                  })
                                }
                              />
                            </td>
                            <td className="px-2 py-1 tabular-nums">
                              {formatChf(it.montantDisponible)}
                            </td>
                            <td className="px-2 py-1">
                              <Input
                                type="number"
                                min={0}
                                max={100}
                                className="h-8 w-20"
                                value={it.pctCapital}
                                onChange={(e) =>
                                  updateItem(active.id, it.id, {
                                    pctCapital: Math.min(
                                      100,
                                      Math.max(0, Number(e.target.value) || 0),
                                    ),
                                  })
                                }
                              />
                            </td>
                            <td className="px-2 py-1 font-medium tabular-nums">
                              {formatChf(itemMontantRetire(it))}
                            </td>
                            <td className="px-2 py-1">
                              <Input
                                type="number"
                                className="h-8 w-24"
                                value={it.anneeRetraitPrevue ?? ""}
                                onChange={(e) =>
                                  updateItem(active.id, it.id, {
                                    anneeRetraitPrevue: e.target.value
                                      ? Number(e.target.value)
                                      : null,
                                  })
                                }
                              />
                            </td>
                            <td className="px-2 py-1">
                              <Input
                                type="number"
                                className="h-8 w-24"
                                placeholder="—"
                                value={it.anneePremierePossible ?? ""}
                                onChange={(e) =>
                                  updateItem(active.id, it.id, {
                                    anneePremierePossible: e.target.value
                                      ? Number(e.target.value)
                                      : null,
                                  })
                                }
                              />
                            </td>
                            <td className="px-2 py-1">
                              <Input
                                type="number"
                                className="h-8 w-24"
                                placeholder="—"
                                value={it.anneeDernierePossible ?? ""}
                                onChange={(e) =>
                                  updateItem(active.id, it.id, {
                                    anneeDernierePossible: e.target.value
                                      ? Number(e.target.value)
                                      : null,
                                  })
                                }
                              />
                            </td>
                            <td className="px-2 py-1">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => removeItem(active.id, it.id)}
                              >
                                <Trash2 className="size-3.5" />
                              </Button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="mt-1 text-xs text-muted-foreground">
                  1re / dernière année : contrainte saisie conseiller — pas
                  d’AVS anticipée, plafonds ni indexation inventés.
                </p>
              </div>

              {/* 2. Calendrier */}
              <div>
                <h4 className="mb-2 text-sm font-medium">
                  Vue calendrier
                </h4>
                {calendar.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Aucune année prévue renseignée.
                  </p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {calendar.map((y) => (
                      <div
                        key={y.year}
                        className="rounded-md border bg-muted/20 p-3"
                      >
                        <p className="mb-2 text-lg font-semibold tabular-nums text-[var(--ap-accent)]">
                          {y.year}
                        </p>
                        <ul className="mb-3 space-y-1 text-xs">
                          {y.lines.map((l, i) => (
                            <li key={`${y.year}-${i}`}>
                              {(l.titulaire === "client1"
                                ? "Assuré 1"
                                : "Assuré 2")}{" "}
                              — {kindLabel(
                                l.kind as
                                  | "lpp"
                                  | "libre_passage"
                                  | "3p"
                                  | "autre",
                              )}
                              {l.institution ? ` / ${l.institution}` : ""} :{" "}
                              <strong>{formatChf(l.montantRetire)}</strong>
                            </li>
                          ))}
                        </ul>
                        <div className="space-y-0.5 border-t pt-2 text-sm">
                          <div className="flex justify-between">
                            <span>Total retiré</span>
                            <span className="tabular-nums font-medium">
                              {formatChf(y.totalRetire)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span>Impôt</span>
                            <span className="tabular-nums">
                              {formatChf(y.impot)}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span>Net</span>
                            <span className="tabular-nums font-medium">
                              {formatChf(y.net)}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {activeResult && (
                <p className="text-xs text-muted-foreground">
                  Dernier calcul : capital{" "}
                  {formatChf(activeResult.capitalRetireTotal)} · impôt{" "}
                  {formatChf(activeResult.impotTotal)} · net{" "}
                  {formatChf(activeResult.capitalNet)}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
