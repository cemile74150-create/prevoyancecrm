import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import MonthlyBarChart from "@/components/MonthlyBarChart";
import {
  FILTRES_VIDES,
  STATS_MENSUELLES_MOIS,
  STATS_MENSUELLES_SERIES,
  statsMensuellesParams,
  statsMensuellesVides,
} from "@/lib/suiviOffres";
import { Loader2 } from "lucide-react";

/** Offres reçues / signées / non signées par mois, sur le périmètre et les filtres du pilotage. */
export default function OffresStatsMensuelles({
  periode = "all", dateDe = "", dateA = "", conseiller = "all", filtres = FILTRES_VIDES, perimetre, refreshKey = 0,
}) {
  const [mois, setMois] = useState(6);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const params = useMemo(
    () => statsMensuellesParams({ mois, periode, dateDe, dateA, conseiller, filtres, perimetre }),
    [mois, periode, dateDe, dateA, conseiller, filtres, perimetre],
  );
  const paramsKey = JSON.stringify(params);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    api.get("/demandes-offres/pilotage/mensuel", { params: JSON.parse(paramsKey) })
      .then((res) => { if (!cancelled) setData(res.data || null); })
      .catch(() => { if (!cancelled) { setData(null); setError(true); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [paramsKey, refreshKey]);

  const sansDate = (data?.sans_date?.signees || 0) + (data?.sans_date?.non_signees || 0);
  const periodeActive = params.periode !== "all";

  return (
    <Card className="p-5 border-border" data-testid="offres-stats-mensuelles">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="font-display font-bold text-lg tracking-tight">Statistiques mensuelles des offres</h2>
          <p className="text-xs text-slate-500 mt-0.5 max-w-2xl">
            Chaque série suit sa propre date : réception de la demande, passage à « Signée », passage à « Non signée ».
            {periodeActive ? " Seuls les événements compris dans la période choisie sont comptés." : ""}
          </p>
        </div>
        <div className="inline-flex rounded-md border border-slate-200 p-0.5" role="group" aria-label="Nombre de mois">
          {STATS_MENSUELLES_MOIS.map((n) => (
            <button
              key={n}
              type="button"
              data-testid={`stats-mensuelles-${n}m`}
              aria-pressed={mois === n}
              onClick={() => setMois(n)}
              className={`px-3 py-1 text-xs font-medium rounded ${
                mois === n ? "bg-[#002FA7] text-white" : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {n} mois
            </button>
          ))}
        </div>
      </div>

      {loading && !data ? (
        <p className="text-sm text-slate-400 py-16 text-center">
          <Loader2 className="h-4 w-4 animate-spin inline mr-1" /> Chargement…
        </p>
      ) : error ? (
        <p className="text-sm text-slate-500 py-16 text-center" data-testid="stats-mensuelles-erreur">
          Statistiques mensuelles indisponibles.
        </p>
      ) : statsMensuellesVides(data) ? (
        <p className="text-sm text-slate-500 py-16 text-center" data-testid="stats-mensuelles-vide">
          Aucune offre reçue, signée ou non signée sur les {data?.nb_mois || mois} derniers mois pour ces filtres.
        </p>
      ) : (
        <div className={loading ? "opacity-60 transition-opacity" : ""} data-testid="stats-mensuelles-chart">
          <MonthlyBarChart data={data?.mois} bars={STATS_MENSUELLES_SERIES} xKey="label" keepOrder />
        </div>
      )}

      {sansDate > 0 && (
        <p className="text-[11px] text-slate-500 mt-2" data-testid="stats-mensuelles-sans-date">
          {sansDate} décision{sansDate > 1 ? "s" : ""} commerciale{sansDate > 1 ? "s" : ""} sans date enregistrée
          {sansDate > 1 ? " ne sont" : " n'est"} pas placée{sansDate > 1 ? "s" : ""} sur le graphique.
        </p>
      )}
    </Card>
  );
}
