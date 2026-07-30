import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUT_DOT, STATUTS } from "@/lib/constants";
import {
  FilePlus2, Clock, FileSearch, Presentation, CheckCircle2, AlertTriangle,
  FolderKanban, Plus, CalendarClock, ListTodo, PauseCircle, User,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
  PieChart, Pie, Cell,
} from "recharts";
import { getDashboardTarget } from "@/lib/dashboardRoutes";

const KPI = ({ icon: Icon, label, value, accent, testid, onClick }) => (
  <Card
    data-testid={testid}
    onClick={onClick}
    className="p-6 border-border hover:-translate-y-[2px] transition-transform duration-200 cursor-pointer"
  >
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm text-muted-foreground font-medium">{label}</p>
        <p className="font-display font-black text-4xl tracking-tight mt-2">{value}</p>
      </div>
      <div className={`h-10 w-10 rounded-md flex items-center justify-center ${accent}`}>
        <Icon className="h-5 w-5" strokeWidth={1.75} />
      </div>
    </div>
  </Card>
);

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [dialog, setDialog] = useState(false);
  const [openConseiller, setOpenConseiller] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const res = await api.get("/dashboard/stats");
      setStats(res.data);
    } catch (e) {
      setStats({
        nouveaux: 0, en_attente_docs: 0, en_analyse: 0, stand_by: 0, a_presenter: 0, termines: 0,
        urgent: 0, total: 0, pending_tasks: 0, statuts: [], by_statut: {}, monthly: [],
        today_appointments: [], upcoming_tasks: [], by_conseiller: [],
      });
    }
  };
  useEffect(() => { load(); }, []);

  if (!stats) return <Layout><div className="animate-pulse text-muted-foreground">Chargement…</div></Layout>;

  const pieData = (stats.statuts || []).map((s) => ({ name: s, value: stats.by_statut?.[s] })).filter((d) => d.value > 0);
  const pieColors = ["#10b981", "#f59e0b", "#3b82f6", "#f97316", "#a855f7", "#64748b"];
  const byConseiller = Array.isArray(stats.by_conseiller) ? stats.by_conseiller : [];

  const goToDashboardTarget = (key) => {
    const target = getDashboardTarget(key);
    navigate(`${target.path}${target.search || ""}`);
  };

  return (
    <Layout>
      <div className="animate-fade-up">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-8">
          <div>
            <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Tableau de bord</h1>
            <p className="text-muted-foreground mt-1">Vue d'ensemble de votre activité de conseil</p>
          </div>
          <Button data-testid="new-dossier-btn" onClick={() => setDialog(true)} className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
            <Plus className="h-4 w-4" /> Nouveau dossier
          </Button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <KPI testid="kpi-nouveaux" icon={FilePlus2} label="Nouveaux dossiers" value={stats.nouveaux} accent="bg-blue-100 text-blue-700" onClick={() => goToDashboardTarget("nouveaux")} />
          <KPI testid="kpi-attente-docs" icon={Clock} label="Documents en attente" value={stats.en_attente_docs} accent="bg-amber-100 text-amber-700" onClick={() => goToDashboardTarget("attente-docs")} />
          <KPI testid="kpi-analyse" icon={FileSearch} label="Analyse en cours" value={stats.en_analyse} accent="bg-blue-100 text-blue-700" onClick={() => goToDashboardTarget("analyse")} />
          <KPI testid="kpi-stand-by" icon={PauseCircle} label="Stand-by" value={stats.stand_by || 0} accent="bg-orange-100 text-orange-700" onClick={() => goToDashboardTarget("stand-by")} />
          <KPI testid="kpi-presenter" icon={Presentation} label="À présenter" value={stats.a_presenter} accent="bg-purple-100 text-purple-700" onClick={() => goToDashboardTarget("presenter")} />
          <KPI testid="kpi-termines" icon={CheckCircle2} label="Dossiers terminés" value={stats.termines} accent="bg-emerald-100 text-emerald-700" onClick={() => goToDashboardTarget("termines")} />
          <KPI testid="kpi-urgents" icon={AlertTriangle} label="Dossiers urgents" value={stats.urgent} accent="bg-red-100 text-red-700" onClick={() => goToDashboardTarget("urgent")} />
          <KPI testid="kpi-total" icon={FolderKanban} label="Total des dossiers" value={stats.total} accent="bg-slate-100 text-slate-700" onClick={() => goToDashboardTarget("total")} />
          <KPI testid="kpi-taches" icon={ListTodo} label="Tâches en attente" value={stats.pending_tasks} accent="bg-indigo-100 text-indigo-700" onClick={() => goToDashboardTarget("taches")} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <Card className="lg:col-span-2 p-6">
            <h2 className="font-display font-bold text-lg tracking-tight mb-1">Statistiques mensuelles</h2>
            <p className="text-sm text-muted-foreground mb-6">Dossiers, rendez-vous et rapports (6 derniers mois)</p>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={stats.monthly} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2f6" />
                <XAxis dataKey="mois" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "#64748b" }} allowDecimals={false} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }} />
                <Legend wrapperStyle={{ fontSize: 13 }} />
                <Bar dataKey="dossiers" name="Dossiers" fill="#002FA7" radius={[4, 4, 0, 0]} />
                <Bar dataKey="rendezvous" name="Rendez-vous" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                <Bar dataKey="rapports" name="Rapports" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <Card className="p-6">
            <h2 className="font-display font-bold text-lg tracking-tight mb-1">Répartition par statut</h2>
            <p className="text-sm text-muted-foreground mb-4">Pipeline des dossiers</p>
            {pieData.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={2}>
                    {pieData.map((_, i) => <Cell key={i} fill={pieColors[i % pieColors.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 13 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-muted-foreground py-12 text-center">Aucun dossier pour l'instant</p>}
          </Card>
        </div>

        <Card className="p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <CalendarClock className="h-5 w-5 text-[#002FA7]" />
            <h2 className="font-display font-bold text-lg tracking-tight">Rendez-vous du jour</h2>
          </div>
          {(stats.today_appointments || []).length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">Aucun rendez-vous prévu aujourd'hui.</p>
          ) : (
            <div className="space-y-2" data-testid="today-appointments">
              {stats.today_appointments.map((a) => (
                <div key={a.id} className="flex items-center gap-4 p-3 rounded-md border border-border hover:bg-secondary transition-colors">
                  <div className="text-sm font-semibold text-[#002FA7] w-16">
                    {new Date(a.date).toLocaleTimeString("fr-CH", { hour: "2-digit", minute: "2-digit" })}
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-medium">{a.titre}</p>
                    {a.client_name && <p className="text-xs text-muted-foreground">{a.client_name}</p>}
                  </div>
                  <span className="text-xs px-2 py-1 rounded bg-secondary text-muted-foreground">{a.type}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-5" data-testid="conseiller-repartition">
          <h2 className="font-display font-bold text-lg tracking-tight mb-1">Répartition par conseiller</h2>
          <p className="text-xs text-muted-foreground mb-4">Cliquez sur le nombre de dossiers pour voir où ils en sont</p>
          {byConseiller.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">Aucun dossier.</p>
          ) : (
            <div className="divide-y divide-border">
              {byConseiller.map((c) => {
                const isOpen = openConseiller === c.name;
                return (
                  <div key={c.name} className="py-2.5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <User className="h-4 w-4 text-muted-foreground shrink-0" />
                        <span className="text-sm font-medium truncate">{c.name}</span>
                      </div>
                      <button
                        type="button"
                        data-testid={`conseiller-count-${c.name}`}
                        onClick={() => setOpenConseiller(isOpen ? null : c.name)}
                        className="text-sm font-semibold text-[#002FA7] hover:underline tabular-nums shrink-0"
                      >
                        {c.total} dossier{c.total === 1 ? "" : "s"}
                      </button>
                    </div>
                    {isOpen && (
                      <div className="mt-2 ml-6 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                        {STATUTS.map((s) => (
                          <button
                            key={s}
                            type="button"
                            onClick={() => navigate(`/dossiers?conseiller=${encodeURIComponent(c.name)}&statut=${encodeURIComponent(s)}`)}
                            className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded-md border border-border hover:border-[#002FA7]/40 hover:bg-secondary/60 text-left"
                          >
                            <span className="flex items-center gap-1.5 min-w-0">
                              <span className={`h-2 w-2 rounded-full shrink-0 ${STATUT_DOT[s]}`} />
                              <span className="truncate">{s}</span>
                            </span>
                            <span className="font-semibold tabular-nums">{c.by_statut?.[s] || 0}</span>
                          </button>
                        ))}
                        <button
                          type="button"
                          onClick={() => navigate(`/dossiers?conseiller=${encodeURIComponent(c.name)}`)}
                          className="sm:col-span-2 text-[11px] text-[#002FA7] underline underline-offset-2 text-left mt-1"
                        >
                          Voir tous ses dossiers dans le Kanban
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      <ClientFormDialog
        open={dialog}
        onOpenChange={setDialog}
        onSaved={(created, meta = {}) => {
          load();
          if (meta.spouse || meta.isFamily) {
            navigate(`/dossiers/${created.dossier_id || created.id}`);
          }
        }}
      />
    </Layout>
  );
}
