import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUT_DOT, STATUTS } from "@/lib/constants";
import { useAuth } from "@/context/AuthContext";
import {
  FilePlus2, Clock, FileSearch, Presentation, CheckCircle2, AlertTriangle,
  FolderKanban, Plus, CalendarClock, ListTodo, PauseCircle, User,
  Shield, Landmark, FileSpreadsheet, PhoneCall, TrendingUp,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
  PieChart, Pie, Cell,
} from "recharts";
import { getDashboardTarget } from "@/lib/dashboardRoutes";
import { conseillerNames as toConseillerNameList } from "@/lib/conseillers";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import OffresDashboardPanel from "@/components/OffresDashboardPanel";

const CATEGORIES = [
  { id: "prevoyance", label: "Suivi Prévoyance", icon: Shield },
  { id: "suivi_3p", label: "Suivi 3e pilier", icon: Landmark },
  { id: "offres", label: "Suivi des offres", icon: FileSpreadsheet },
];

const KPI = ({ icon: Icon, label, value, accent, testid, onClick }) => (
  <Card
    data-testid={testid}
    onClick={onClick}
    className="p-6 border-border hover:-translate-y-[2px] transition-transform duration-200 cursor-pointer"
  >
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm text-muted-foreground font-medium">{label}</p>
        <p className="font-display font-black text-4xl tracking-tight mt-2">{value ?? 0}</p>
      </div>
      <div className={`h-10 w-10 rounded-md flex items-center justify-center ${accent}`}>
        <Icon className="h-5 w-5" strokeWidth={1.75} />
      </div>
    </div>
  </Card>
);

function formatGain(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return new Intl.NumberFormat("fr-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(Number(v));
}

export default function Dashboard() {
  const { user, isGlobal, hasPerm } = useAuth();
  const [stats, setStats] = useState(null);
  const [dialog, setDialog] = useState(false);
  const [openConseiller, setOpenConseiller] = useState(null);
  const [filterConseiller, setFilterConseiller] = useState("all");
  const [categorie, setCategorie] = useState("prevoyance");
  const [conseillerNames, setConseillerNames] = useState([]);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const params = { categorie };
      if (isGlobal && filterConseiller && filterConseiller !== "all") {
        params.conseiller = filterConseiller;
      }
      const res = await api.get("/dashboard/stats", { params });
      setStats(res.data);
    } catch (e) {
      setStats({
        nouveaux: 0, en_attente_docs: 0, en_analyse: 0, stand_by: 0, a_presenter: 0, termines: 0,
        urgent: 0, total: 0, pending_tasks: 0, statuts: [], by_statut: {}, monthly: [],
        today_appointments: [], upcoming_tasks: [], by_conseiller: [],
        prevoyance: null, suivi_3p: null, offres: null, categorie,
      });
    }
  };
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterConseiller, isGlobal, categorie]);

  useEffect(() => {
    if (!isGlobal) return;
    api.get("/users/conseillers").then((r) => setConseillerNames(toConseillerNameList(r.data))).catch(() => {});
  }, [isGlobal]);

  if (!stats) return <Layout><div className="animate-pulse text-muted-foreground">Chargement…</div></Layout>;

  const prev = stats.prevoyance || stats;
  const suivi = stats.suivi_3p || {};

  const pieData = (prev.statuts || STATUTS || []).map((s) => ({ name: s, value: prev.by_statut?.[s] })).filter((d) => d.value > 0);
  const pieColors = ["#10b981", "#f59e0b", "#3b82f6", "#f97316", "#a855f7", "#64748b"];
  const byConseiller = Array.isArray(prev.by_conseiller)
    ? [...prev.by_conseiller].sort((a, b) => (b.total || 0) - (a.total || 0))
    : [];
  const maxConseillerTotal = Math.max(1, ...byConseiller.map((c) => c.total || 0));

  const goToDashboardTarget = (key) => {
    const target = getDashboardTarget(key);
    navigate(`${target.path}${target.search || ""}`);
  };

  const subtitle = isGlobal
    ? (filterConseiller !== "all"
      ? `Vue filtrée — ${filterConseiller}`
      : "Vue globale · base clients unique")
    : `Vos clients uniquement · ${user?.conseiller || user?.name || "espace personnel"}`;

  const catMeta = CATEGORIES.find((c) => c.id === categorie);

  return (
    <Layout>
      <div className="animate-fade-up">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
          <div>
            <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Tableau de bord</h1>
            <p className="text-muted-foreground mt-1">{subtitle}</p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {isGlobal && (
              <Select value={filterConseiller} onValueChange={setFilterConseiller}>
                <SelectTrigger className="w-[220px]" data-testid="filter-conseiller">
                  <SelectValue placeholder="Tous les conseillers" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tous les conseillers</SelectItem>
                  <SelectItem value="Non attribué">Non attribué</SelectItem>
                  {conseillerNames.map((n) => (
                    <SelectItem key={n} value={n}>{n}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {hasPerm("dossiers.create") && categorie === "prevoyance" && (
            <Button data-testid="new-dossier-btn" onClick={() => setDialog(true)} className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
              <Plus className="h-4 w-4" /> Nouveau dossier
            </Button>
            )}
          </div>
        </div>

        {/* Filtres de catégorie */}
        <div className="flex flex-wrap gap-2 mb-8" role="tablist" aria-label="Catégorie du tableau de bord">
          {CATEGORIES.map(({ id, label, icon: Icon }) => {
            const active = categorie === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`dashboard-cat-${id}`}
                onClick={() => setCategorie(id)}
                className={`inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium border transition-colors ${
                  active
                    ? "bg-[#002FA7] text-white border-[#002FA7]"
                    : "bg-white text-foreground border-border hover:border-[#002FA7]/40 hover:bg-secondary/50"
                }`}
              >
                <Icon className="h-4 w-4" strokeWidth={1.75} />
                {label}
              </button>
            );
          })}
        </div>

        <p className="text-sm text-muted-foreground mb-4">
          Affichage : <span className="font-medium text-foreground">{catMeta?.label}</span>
          {" · "}données limitées à votre périmètre d&apos;accès
        </p>

        {/* —— Prévoyance —— */}
        {categorie === "prevoyance" && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <KPI testid="kpi-nouveaux" icon={FilePlus2} label="Nouveaux dossiers" value={prev.nouveaux} accent="bg-blue-100 text-blue-700" onClick={() => goToDashboardTarget("nouveaux")} />
              <KPI testid="kpi-attente-docs" icon={Clock} label="Documents en attente" value={prev.en_attente_docs} accent="bg-amber-100 text-amber-700" onClick={() => goToDashboardTarget("attente-docs")} />
              <KPI testid="kpi-analyse" icon={FileSearch} label="Analyse en cours" value={prev.en_analyse} accent="bg-blue-100 text-blue-700" onClick={() => goToDashboardTarget("analyse")} />
              <KPI testid="kpi-stand-by" icon={PauseCircle} label="Stand-by" value={prev.stand_by || 0} accent="bg-orange-100 text-orange-700" onClick={() => goToDashboardTarget("stand-by")} />
              <KPI testid="kpi-presenter" icon={Presentation} label="À présenter" value={prev.a_presenter} accent="bg-purple-100 text-purple-700" onClick={() => goToDashboardTarget("presenter")} />
              <KPI testid="kpi-termines" icon={CheckCircle2} label="Dossiers terminés" value={prev.termines} accent="bg-emerald-100 text-emerald-700" onClick={() => goToDashboardTarget("termines")} />
              <KPI testid="kpi-urgents" icon={AlertTriangle} label="Dossiers urgents" value={prev.urgent} accent="bg-red-100 text-red-700" onClick={() => goToDashboardTarget("urgent")} />
              <KPI testid="kpi-total" icon={FolderKanban} label="Total des dossiers" value={prev.total} accent="bg-slate-100 text-slate-700" onClick={() => goToDashboardTarget("total")} />
              <KPI testid="kpi-taches" icon={ListTodo} label="Tâches en attente" value={prev.pending_tasks} accent="bg-indigo-100 text-indigo-700" onClick={() => goToDashboardTarget("taches")} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
              <Card className="lg:col-span-2 p-6">
                <h2 className="font-display font-bold text-lg tracking-tight mb-1">Statistiques mensuelles</h2>
                <p className="text-sm text-muted-foreground mb-6">Dossiers, rendez-vous et rapports (6 derniers mois)</p>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={prev.monthly || []} barGap={4}>
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
                ) : <p className="text-sm text-muted-foreground py-12 text-center">Aucun dossier pour l&apos;instant</p>}
              </Card>
            </div>

            <Card className="p-6 mb-6">
              <div className="flex items-center gap-2 mb-4">
                <CalendarClock className="h-5 w-5 text-[#002FA7]" />
                <h2 className="font-display font-bold text-lg tracking-tight">Rendez-vous du jour</h2>
              </div>
              {(prev.today_appointments || []).length === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center">Aucun rendez-vous prévu aujourd&apos;hui.</p>
              ) : (
                <div className="space-y-2" data-testid="today-appointments">
                  {(prev.today_appointments || []).map((a) => (
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

            {isGlobal && (
            <Card className="p-5" data-testid="conseiller-repartition">
              <h2 className="font-display font-bold text-lg tracking-tight mb-1">Répartition par conseiller</h2>
              <p className="text-xs text-muted-foreground mb-4">
                Cliquez sur une barre pour voir le détail, puis filtrer les dossiers
              </p>
              {byConseiller.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">Aucun dossier.</p>
              ) : (
                <div className="space-y-2">
                  {byConseiller.map((c) => {
                    const total = c.total || 0;
                    const pct = Math.max(total > 0 ? 6 : 0, Math.round((total / maxConseillerTotal) * 100));
                    const isOpen = openConseiller === c.name;
                    return (
                      <div
                        key={c.name}
                        className={`rounded-md px-2 py-1.5 -mx-2 transition-colors ${
                          isOpen ? "bg-[#002FA7]/8 ring-1 ring-[#002FA7]/30" : ""
                        }`}
                      >
                        <button
                          type="button"
                          data-testid={`conseiller-count-${c.name}`}
                          onClick={() => setOpenConseiller(isOpen ? null : c.name)}
                          className="w-full text-left"
                          aria-expanded={isOpen}
                        >
                          <div className="flex items-center justify-between gap-3 mb-1.5">
                            <span className={`text-sm truncate flex items-center gap-2 ${isOpen ? "font-semibold text-[#002FA7]" : "font-medium"}`}>
                              <User className="h-4 w-4 text-muted-foreground shrink-0" />
                              {c.name}
                            </span>
                            <span className={`text-xs tabular-nums shrink-0 ${isOpen ? "font-semibold text-[#002FA7]" : "text-muted-foreground"}`}>
                              {total} dossier{total === 1 ? "" : "s"}
                            </span>
                          </div>
                          <div className="h-3 rounded-full bg-secondary overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${isOpen ? "bg-[#002FA7]" : "bg-[#002FA7]/75"}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </button>
                        {isOpen && (
                          <div className="mt-3 ml-1 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
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
            )}
          </>
        )}

        {/* —— Suivi 3e pilier —— */}
        {categorie === "suivi_3p" && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <KPI testid="kpi-3p-total" icon={FolderKanban} label="Clients suivi 3P" value={suivi.total} accent="bg-slate-100 text-slate-700" onClick={() => goToDashboardTarget("3p-total")} />
              <KPI testid="kpi-3p-analyses" icon={FileSearch} label="Analyses réalisées" value={suivi.analyses_realisees} accent="bg-blue-100 text-blue-700" onClick={() => goToDashboardTarget("3p-analyses")} />
              <KPI testid="kpi-3p-contactes" icon={PhoneCall} label="Clients contactés" value={suivi.clients_contactes} accent="bg-cyan-100 text-cyan-700" onClick={() => goToDashboardTarget("3p-contactes")} />
              <KPI testid="kpi-3p-a-contacter" icon={AlertTriangle} label="À contacter" value={suivi.a_contacter} accent="bg-amber-100 text-amber-700" onClick={() => goToDashboardTarget("3p-a-contacter")} />
              <KPI testid="kpi-3p-rdv" icon={CalendarClock} label="RDV pris" value={suivi.rdv_pris} accent="bg-indigo-100 text-indigo-700" onClick={() => goToDashboardTarget("3p-rdv")} />
              <KPI testid="kpi-3p-offres" icon={FileSpreadsheet} label="Offres envoyées" value={suivi.offres_envoyees} accent="bg-purple-100 text-purple-700" onClick={() => goToDashboardTarget("3p-offres")} />
              <KPI testid="kpi-3p-signes" icon={CheckCircle2} label="Contrats signés" value={suivi.contrats_signes} accent="bg-emerald-100 text-emerald-700" onClick={() => goToDashboardTarget("3p-signes")} />
              <KPI testid="kpi-3p-gain" icon={TrendingUp} label="Gain fiscal estimé" value={formatGain(suivi.gain_fiscal_total)} accent="bg-green-100 text-green-700" onClick={() => goToDashboardTarget("3p-total")} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <Card className="p-6">
                <h2 className="font-display font-bold text-lg tracking-tight mb-1">Pipeline 3e pilier</h2>
                <p className="text-sm text-muted-foreground mb-4">Répartition par statut de suivi</p>
                {Object.keys(suivi.by_statut || {}).length === 0 ? (
                  <p className="text-sm text-muted-foreground py-8 text-center">Aucune donnée.</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(suivi.by_statut || {})
                      .filter(([, v]) => v > 0)
                      .sort((a, b) => b[1] - a[1])
                      .map(([name, value]) => (
                        <button
                          key={name}
                          type="button"
                          onClick={() => navigate(`/suivi-3p?statut=${encodeURIComponent(name)}`)}
                          className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-md border border-border hover:border-[#002FA7]/40 hover:bg-secondary/50 text-left"
                        >
                          <span className="text-sm">{name}</span>
                          <span className="text-sm font-semibold tabular-nums">{value}</span>
                        </button>
                      ))}
                  </div>
                )}
              </Card>

              <Card className="p-6">
                <h2 className="font-display font-bold text-lg tracking-tight mb-1">Prochains RDV</h2>
                <p className="text-sm text-muted-foreground mb-4">Rendez-vous planifiés (suivi 3P)</p>
                {(suivi.upcoming_rdvs || []).length === 0 ? (
                  <p className="text-sm text-muted-foreground py-8 text-center">Aucun RDV à venir.</p>
                ) : (
                  <div className="space-y-2 max-h-72 overflow-y-auto">
                    {(suivi.upcoming_rdvs || []).slice(0, 12).map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => navigate(`/suivi-3p/${r.id}`)}
                        className="w-full flex items-center gap-3 p-3 rounded-md border border-border hover:bg-secondary text-left"
                      >
                        <div className="text-xs font-semibold text-[#002FA7] w-20 shrink-0">{r.date_rdv}</div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium truncate">{r.prenom} {r.nom}</p>
                          <p className="text-xs text-muted-foreground">{r.conseiller}</p>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            {isGlobal && (suivi.by_conseiller || []).length > 0 && (
              <Card className="p-5">
                <h2 className="font-display font-bold text-lg tracking-tight mb-1">Répartition par conseiller</h2>
                <p className="text-xs text-muted-foreground mb-4">Clients suivi 3e pilier</p>
                <div className="space-y-2">
                  {suivi.by_conseiller.map((c) => (
                    <button
                      key={c.conseiller}
                      type="button"
                      onClick={() => navigate(`/suivi-3p?conseiller=${encodeURIComponent(c.conseiller)}`)}
                      className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-md border border-border hover:bg-secondary/50 text-left"
                    >
                      <span className="text-sm flex items-center gap-2">
                        <User className="h-4 w-4 text-muted-foreground" />
                        {c.conseiller}
                      </span>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {c.total} · {c.signes} signé{c.signes === 1 ? "" : "s"}
                      </span>
                    </button>
                  ))}
                </div>
              </Card>
            )}
          </>
        )}

        {/* —— Suivi des offres —— */}
        {categorie === "offres" && (
          <OffresDashboardPanel
            isGlobal={isGlobal}
            filterConseiller={filterConseiller}
            conseillerNames={conseillerNames}
          />
        )}
      </div>

      <ClientFormDialog
        open={dialog}
        onOpenChange={setDialog}
        defaultActivites={["prevoyance"]}
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
