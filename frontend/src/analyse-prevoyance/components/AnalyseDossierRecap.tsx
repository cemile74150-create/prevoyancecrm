// @ts-nocheck
"use client";

import { ChevronDown } from "lucide-react";
import type { DossierRecap } from "@/analyse-prevoyance/lib/analyseWizard";
import { NON_RENSEIGNE } from "@/analyse-prevoyance/lib/analyseWizard";

function Row({ label, value }: { label: string; value: string }) {
  const empty = value === NON_RENSEIGNE;
  return (
    <div className="flex items-start justify-between gap-3 border-b border-slate-100 py-2 last:border-0">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd
        className={`text-right text-sm ${empty ? "text-slate-400 italic" : "font-medium text-slate-800 tabular-nums"}`}
      >
        {value}
      </dd>
    </div>
  );
}

function RecapBody({ recap }: { recap: DossierRecap }) {
  return (
    <dl data-testid="analyse-dossier-recap">
      <Row label="Nom" value={recap.nom} />
      <Row label="Conjoint" value={recap.conjoint} />
      <Row label="Commune / canton" value={recap.communeCanton} />
      <Row label="AVS mensuelle" value={recap.avsMensuelle} />
      <Row label="LPP total" value={recap.lppTotal} />
      <Row label="3e piliers" value={recap.piliers3} />
      <Row label="Libres passages" value={recap.libresPassages} />
      <Row label="Scénario" value={recap.scenario} />
      <Row label="Enregistrement" value={recap.statut} />
    </dl>
  );
}

export function AnalyseDossierRecap({ recap }: { recap: DossierRecap }) {
  return (
    <>
      <aside className="hidden lg:block">
        <div className="sticky top-4 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <p className="mb-1 text-[11px] font-semibold tracking-[0.14em] text-slate-400 uppercase">
            Dossier
          </p>
          <h2 className="mb-3 font-heading text-base font-semibold text-slate-900">
            Récapitulatif
          </h2>
          <RecapBody recap={recap} />
        </div>
      </aside>
      <details className="rounded-2xl border border-slate-200/80 bg-white shadow-sm lg:hidden">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium [&::-webkit-details-marker]:hidden">
          <span>Récapitulatif du dossier</span>
          <ChevronDown className="size-4 text-slate-400" />
        </summary>
        <div className="border-t px-4 py-3">
          <RecapBody recap={recap} />
        </div>
      </details>
    </>
  );
}
