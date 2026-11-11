import React, { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import MonthlyBarChart from "@/components/MonthlyBarChart";
import { STATUTS, STATUT_DOT } from "@/lib/constants";
import { NON_ATTRIBUE } from "@/lib/kanbanConseiller";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from "recharts";

const PERIODES = [
  { id: "all", label: "Toute période" },
  { id: "month", label: "Ce mois" },
  { id: "year", label: "Cette année" },
  { id: "custom", label: "Dates personnalisées" },
];

const PIE_COLORS = {
  Nouveau: "#10b981",
  "Documents en attente": "#f59e0b",
  "Analyse en cours": "#3b82f6",
  "Stand-by": "#f97316",
  "À présenter": "#a855f7",
  "Dossier présenté — en cours": "#14b8a6",
  Clôturé: "#64748b",
};

function Kpi({ label, value, hint, tone = "border-slate-200 bg-white", testId }) {
  return (
    <div
      data-testid={testId}
      className={`rounded-lg border px-3 py-3 ${tone}`}
    >
      <span className="block text-[12px] font-medium text-slate-600 leading-snug">{label}</span>
      <span className="block text-2xl font-bold tabular-nums mt-1 text-slate-900">{value ?? "—"}</span>
      {hint ? <span className="block text-[10px] text-slate-500 mt-1 leading-snug">{hint}</span> : null}
    </div>
  );
}

function formatMonthLabel(ym) {
  if (!ym || ym.length < 7) return ym || "";
  const [y, m] = ym.split("-");
  const d = new Date(Number(y), Number(m) - 1, 1);
  return d.toLocaleDateString("fr-CH", { month: "short", year: "2-digit" });
}

/**
 * Tableau de bord statistique sous le kanban (remplace « Nouveaux dossiers »).
 * Filtres agent / période / statut ; chiffres issus de GET /dossiers/stats (permissions server).
 */
export default function SuiviDossiersStats({ conseillerOptions = [] }) {
  const [agent, setAgent] = useState("all");
  const [period, setPeriod] = useState("all");
  const [statut, setStatut] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = { period };
      if (agent && agent !== "all") params.conseiller = agent;
      if (statut && statut !== "all") params.statut = statut;
      if (period === "custom") {
        if (dateFrom) params.date_from = dateFrom;
        if (dateTo) params.date_to = dateTo;
      }
      const res = await api.get("/dossiers/stats", { params });
      setStats(res.data || null);
    } catch (e) {
      setStats(null);
      setError(e?.response?.data?.detail || "Impossible de charger les statistiques");
    } finally {
      setLoading(false);
    }
  }, [agent, period, statut, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const pieData = useMemo(() => {
    const by = stats?.by_statut || {};
    return STATUTS
      .map((s) => ({ name: s, value: by[s] || 0 }))
      .filter((d) => d.value > 0);
  }, [stats]);

  const agentBars = useMemo(() => (stats?.abouties_par_agent || []).map((row) => ({
    agent: row.agent || NON_ATTRIBUE,
    abouties: row.abouties || 0,
    non_abouties: row.non_abouties || 0,
  })), [stats]);

  const evolution = useMemo(() => (stats?.evolution_mensuelle || []).map((row) => ({
    ...row,
    mois: formatMonthLabel(row.mois),
  })), [stats]);

  const taux = stats?.taux_reussite;
  const tauxLabel = taux == null ? "—" : `${taux} %`;

  return (
    <section className="mt-6 space-y-4" data-testid="suivi-dossiers-stats">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Tableau de bord</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Chiffres selon votre périmètre d&apos;accès. Taux de réussite = abouties ÷ (abouties + non abouties) ;
            les clôtures « Non renseigné » sont exclues.
          </p>
        </div>
        {loading && <span className="text-xs text-muted-foreground">Mise à jour…</span>}
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label className="text-[11px] text-muted-foreground">Agent</Label>
          <Select value={agent} onValueChange={setAgent}>
            <SelectTrigger className="w-[200px] h-8 text-xs" data-testid="stats-filter-agent">
              <SelectValue placeholder="Tous les agents" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tous les agents</SelectItem>
              <SelectItem value={NON_ATTRIBUE}>{NON_ATTRIBUE}</SelectItem>
              {conseillerOptions.map((n) => (
                <SelectItem key={n} value={n}>{n}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-[11px] text-muted-foreground">Période</Label>
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-[180px] h-8 text-xs" data-testid="stats-filter-period">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIODES.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {period === "custom" && (
          <>
            <div className="space-y-1">
              <Label className="text-[11px] text-muted-foreground">Du</Label>
              <Input type="date" className="h-8 w-[150px] text-xs" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="stats-date-from" />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] text-muted-foreground">Au</Label>
              <Input type="date" className="h-8 w-[150px] text-xs" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="stats-date-to" />
            </div>
          </>
        )}
        <div className="space-y-1">
          <Label className="text-[11px] text-muted-foreground">Statut</Label>
          <Select value={statut} onValueChange={setStatut}>
            <SelectTrigger className="w-[220px] h-8 text-xs" data-testid="stats-filter-statut">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tous les statuts</SelectItem>
              {STATUTS.map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-600" data-testid="stats-error">{error}</p>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        <Kpi testId="stat-total" label="Total dossiers" value={stats?.total ?? 0} />
        <Kpi testId="stat-nouveaux" label="Nouveaux" value={stats?.nouveaux ?? 0} tone="border-emerald-200 bg-emerald-50/60" />
        <Kpi testId="stat-attente" label="En attente" value={stats?.en_attente ?? 0} tone="border-amber-200 bg-amber-50/60" hint="Documents en attente" />
        <Kpi testId="stat-encours" label="En cours" value={stats?.en_cours ?? 0} tone="border-blue-200 bg-blue-50/60" hint="Analyse → présenté" />
        <Kpi testId="stat-clotures" label="Clôturés" value={stats?.clotures ?? 0} tone="border-slate-300 bg-slate-50" />
        <Kpi testId="stat-abouties" label="Affaires abouties" value={stats?.affaires_abouties ?? 0} tone="border-emerald-300 bg-emerald-50" />
        <Kpi testId="stat-non-abouties" label="Affaires non abouties" value={stats?.affaires_non_abouties ?? 0} tone="border-red-200 bg-red-50/70" />
        <Kpi
          testId="stat-taux"
          label="Taux de réussite"
          value={tauxLabel}
          tone="border-[#002FA7]/30 bg-[#002FA7]/5"
          hint={stats?.clotures_non_renseignees ? `${stats.clotures_non_renseignees} non renseigné(s) exclus` : undefined}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="p-4">
          <h3 className="text-sm font-semibold mb-1">Répartition par statut</h3>
          <p className="text-xs text-muted-foreground mb-3">Anneau du pipeline</p>
          {pieData.length ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={48} outerRadius={78} paddingAngle={2}>
                  {pieData.map((d) => (
                    <Cell key={d.name} fill={PIE_COLORS[d.name] || "#94a3b8"} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground py-12 text-center">Aucun dossier</p>
          )}
          <ul className="mt-1 space-y-1">
            {pieData.map((d) => (
              <li key={d.name} className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <span className={`h-2 w-2 rounded-full ${STATUT_DOT[d.name] || "bg-slate-400"}`} />
                <span className="truncate flex-1">{d.name}</span>
                <span className="tabular-nums font-medium text-foreground">{d.value}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-4 lg:col-span-2">
          <h3 className="text-sm font-semibold mb-1">Abouties vs non abouties par agent</h3>
          <p className="text-xs text-muted-foreground mb-3">Histogramme (clôtures avec motif uniquement)</p>
          {agentBars.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={agentBars} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f6" />
                <XAxis dataKey="agent" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#64748b" }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "#64748b" }} allowDecimals={false} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="abouties" name="Abouties" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="non_abouties" name="Non abouties" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-muted-foreground py-12 text-center">Aucune clôture avec motif sur cette sélection</p>
          )}
        </Card>
      </div>

      <Card className="p-4">
        <h3 className="text-sm font-semibold mb-1">Évolution mensuelle</h3>
        <p className="text-xs text-muted-foreground mb-3">Dossiers ouverts et clôturés par mois</p>
        <MonthlyBarChart
          data={evolution}
          bars={[
            { key: "ouverts", label: "Ouverts", color: "#002FA7" },
            { key: "clotures", label: "Clôturés", color: "#64748b" },
          ]}
          height={260}
          keepOrder
        />
      </Card>
    </section>
  );
}
