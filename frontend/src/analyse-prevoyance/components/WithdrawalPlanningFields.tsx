// @ts-nocheck
"use client";

import { useState } from "react";
import {
  Calculator,
  Copy,
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
import { ConfirmDeleteButton } from "@/analyse-prevoyance/components/ConfirmDeleteButton";
import { PILIER_3B_NOTE, RACHAT_ABSENT_UI } from "@/analyse-prevoyance/lib/planificationSaisie";
import {
  buildDefaultWithdrawalItems,
  duplicateWithdrawalScenario,
  lppPlanYear,
  capitalTypeText,
  thirdPillarTaxMark,
  withPillarCapital,
} from "@/analyse-prevoyance/lib/withdrawalDefaults";
import {
  itemMontantRetire,
  mergeCalendarWithResult,
} from "@/analyse-prevoyance/lib/withdrawalPlanUtils";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";

function prenomTitulaire(input: AnalyseInput, titulaire: string): string {
  const person = titulaire === "conjoint" ? input.conjoint : input.client1;
  const prenom = String(person?.prenom || "").trim();
  if (prenom) return prenom;
  return titulaire === "conjoint" ? "Assuré 2" : "Assuré 1";
}

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

  function refillFromDossier(scenarioId?: string) {
    if (!previewBasics) return;
    const items = buildDefaultWithdrawalItems(
      input,
      previewBasics.client1,
      previewBasics.conjoint,
    );
    if (!scenarioId || !scenarios.some((s) => s.id === scenarioId)) {
      const id = `sc-${Date.now()}`;
      const sc: WithdrawalScenario = {
        id,
        name: "Capitaux disponibles",
        items,
        includeInReport: false,
      };
      onChange([...scenarios, sc]);
      setActiveId(id);
      return;
    }
    updateScenario(scenarioId, { items });
  }

  const shownItems = (active?.items || []).map((it) => {
    const next = withPillarCapital(input, it);
    const year = lppPlanYear(input, it);
    return year == null
      ? next
      : { ...next, anneeRetraitPrevue: year, anneePremierePossible: year };
  });
  const calendar = active
    ? mergeCalendarWithResult(shownItems, activeResult)
    : [];
  const indicative = shownItems.filter((it) => it.capitalStatut === "indicatif");
  const has3b = shownItems.some((it) => thirdPillarTaxMark(input, it)?.exonere);

  return (
    <div className="space-y-4">
      {scenarios.length === 0 ? (
        <div className="space-y-3">
          <h3 className="text-sm font-medium">Capitaux disponibles</h3>
          <p className="text-sm text-muted-foreground">Aucun capital chargé.</p>
          {previewBasics && (
            <Button type="button" variant="outline" size="sm" onClick={() => refillFromDossier()}>
              Recharger les capitaux
            </Button>
          )}
        </div>
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
                    Recharger les capitaux
                  </Button>
                )}
                <ConfirmDeleteButton
                  ariaLabel="Supprimer le scénario"
                  onConfirm={() => removeScenario(active.id)}
                >
                  <Trash2 className="size-4" />
                  Supprimer
                </ConfirmDeleteButton>
              </div>

              {/* 1. Tableau interactif */}
              <div>
                <h4 className="mb-2 text-sm font-medium">
                  Capitaux disponibles
                </h4>
                {shownItems.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Aucune ligne. Utilisez « Recharger les capitaux » après le calcul.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[760px] text-sm">
                      <thead className="bg-muted/40 text-left">
                        <tr>
                          <th className="px-2 py-1">Titulaire</th>
                          <th className="px-2 py-1">Type</th>
                          <th className="px-2 py-1">Institution</th>
                          <th className="px-2 py-1">Dispo</th>
                          <th className="px-2 py-1">Montant retiré</th>
                          <th className="px-2 py-1">Année prévue</th>
                          <th className="px-2 py-1">1re possible</th>
                          <th className="px-2 py-1">Dernière</th>
                          <th className="px-2 py-1" />
                        </tr>
                      </thead>
                      <tbody>
                        {shownItems.map((it) => (
                          <tr key={it.id} className="border-t">
                            <td className="px-2 py-1">
                              {prenomTitulaire(input, it.titulaire)}
                            </td>
                            <td className="px-2 py-1">
                              <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium whitespace-nowrap">
                                {capitalTypeText(input, it)}
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
                              {it.capitalStatut === "indicatif" && (
                                <span className="mt-1 block text-[11px] font-medium text-amber-800">
                                  Estimation non confirmée
                                </span>
                              )}
                              {it.capitalStatut === "rachat" && (
                                <span className="mt-1 block text-[11px] text-muted-foreground">
                                  Valeur de rachat confirmée
                                </span>
                              )}
                            </td>
                            <td className="px-2 py-1 font-medium tabular-nums">
                              {formatChf(itemMontantRetire(it))}
                            </td>
                            <td className="px-2 py-1">
                              <Input
                                type="text"
                                readOnly
                                disabled
                                className="h-8 w-24 bg-muted text-muted-foreground"
                                value={it.anneeRetraitPrevue ?? ""}
                                aria-label="Année prévue"
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
                              <ConfirmDeleteButton
                                ariaLabel="Supprimer la ligne"
                                onConfirm={() => removeItem(active.id, it.id)}
                              >
                                <Trash2 className="size-3.5" />
                              </ConfirmDeleteButton>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="mt-1 text-xs text-muted-foreground">
                  Année prévue : échéance du contrat, non modifiable. 1re
                  possible : année de retrait du scénario, utilisée pour le
                  calcul et le PDF.
                </p>
                {indicative.length > 0 && (
                  <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
                    {RACHAT_ABSENT_UI}
                  </p>
                )}
                {has3b && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {PILIER_3B_NOTE}
                  </p>
                )}
                {onRecalculate && (
                  <Button
                    type="button"
                    className="mt-3"
                    size="sm"
                    onClick={onRecalculate}
                    disabled={recalculatePending || scenarios.length === 0}
                  >
                    <Calculator className="size-4" />
                    {recalculatePending ? "Calcul ESTV…" : "Recalculer la fiscalité"}
                  </Button>
                )}
              </div>

              {/* 2. Calendrier */}
              <div>
                <h4 className="mb-2 text-sm font-medium">
                  Vue calendrier
                </h4>
                {calendar.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Aucune année de retrait renseignée.
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
                              {prenomTitulaire(input, l.titulaire)}{" "}
                              — {capitalTypeText(input, l)}
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
