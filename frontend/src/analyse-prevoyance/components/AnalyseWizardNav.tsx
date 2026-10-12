// @ts-nocheck
"use client";

import { Check } from "lucide-react";
import {
  ANALYSE_STEPS,
  type AnalyseStepId,
} from "@/analyse-prevoyance/lib/analyseWizard";
import { cn } from "@/analyse-prevoyance/utils";

export function AnalyseWizardNav({
  activeId,
  completed,
  onSelect,
}: {
  activeId: AnalyseStepId;
  completed: Record<string, boolean>;
  onSelect: (id: AnalyseStepId) => void;
}) {
  return (
    <nav
      aria-label="Étapes de l'analyse"
      className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-sm"
      data-testid="analyse-wizard-nav"
    >
      <p className="mb-2 px-2 text-[11px] font-semibold tracking-[0.14em] text-slate-400 uppercase">
        Parcours
      </p>
      <ol className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
        {ANALYSE_STEPS.map((step) => {
          const active = step.id === activeId;
          const done = Boolean(completed[step.id]);
          return (
            <li key={step.id} className="min-w-[7.5rem] lg:min-w-0">
              <button
                type="button"
                data-testid={`analyse-step-${step.id}`}
                aria-current={active ? "step" : undefined}
                onClick={() => onSelect(step.id)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm transition-colors",
                  active
                    ? "bg-[#002FA7] font-semibold text-white shadow-sm"
                    : "text-slate-700 hover:bg-slate-50",
                )}
              >
                <span
                  className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                    active
                      ? "bg-white/15 text-white"
                      : "bg-slate-100 text-slate-600",
                  )}
                >
                  {step.n}
                </span>
                <span className="flex-1 leading-tight">{step.label}</span>
                {done ? (
                  <Check
                    className={cn(
                      "size-4 shrink-0",
                      active ? "text-emerald-300" : "text-emerald-600",
                    )}
                    aria-label="Section renseignée"
                    data-testid={`analyse-step-done-${step.id}`}
                  />
                ) : null}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
