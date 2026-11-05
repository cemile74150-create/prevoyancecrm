import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  GESTION_KANBAN_FALLBACK,
  PRIORITE_STYLE,
  prioriteLabel,
  clientLabel,
  formatDateFr,
  formatVariantesSummary,
  COMPAGNIES_DEFAUT,
  compagniesAffichees,
  PERIODE_FILTERS,
  statutLabel,
  DEMANDE_ORIGINE_LABELS,
  DEMANDE_ORIGINE_STYLE,
  demandeOrigineKey,
  demandeOrigineShort,
  demandeOrigineLabel,
  soumisCompagnieLabel,
  isSoumisCompagnie,
  AVANCEMENT_BADGE_STYLE,
  avancementCode,
  avancementLabel,
  formatHeureRdv,
  rdvProximite,
} from "@/lib/demandesOffres";
import { uniqueConseillerNames } from "@/lib/conseillers";
import { PendingComplementBadge } from "@/components/NotesConseiller";
import { offreNotificationPath } from "@/lib/complementsOffre";
import {
  Bell, Briefcase, ClipboardList, Columns3, Eye, Filter,
  Loader2, Search, Users, AlertTriangle, Inbox, Sparkles, Clock, BarChart3,
} from "lucide-react";
import { toast } from "sonner";

const ACCENT = "#002FA7";

const DAY_ACTIONS = [
  { id: "urgentes", label: "Urgentes", icon: AlertTriangle, tone: "text-red-700 bg-red-50 border-red-200" },
  { id: "a_surveiller", label: "À surveiller", icon: Clock, tone: "text-amber-800 bg-amber-50 border-amber-200" },
  { id: "nouvelles", label: "Nouvelles", icon: Sparkles, tone: "text-sky-800 bg-sky-50 border-sky-200" },
  { id: "incompletes", label: "Incomplètes", icon: AlertTriangle, tone: "text-rose-800 bg-rose-50 border-rose-200" },
  { id: "offres_recues", label: "Offres reçues", icon: Inbox, tone: "text-violet-800 bg-violet-50 border-violet-200" },
];

const TERMINAL = new Set(["Offre signée", "Offre refusée", "Demande annulée", "demande_annulee", "offre_non_signee", "Offre non signée", "Brouillon"]);

function prioRank(p) {
  if (p === "urgent") return 0;
  if (p === "surveiller") return 1;
  return 2;
}

function isOffreAModifier(row) {
  const st = row?.statut;
  return st === "Offre à modifier" || st === "Offre modifiée";
}

function rowHighlight(row) {
  const p = row?.priorite;
  const st = row?.statut;
  return p === "urgent" || p === "surveiller" || st === "Demande incomplète" || st === "Offre reçue" || isOffreAModifier(row);
}

function sortQueue(rows) {
  return [...rows].sort((a, b) => {
    const urgent = Number(Boolean(b.urgente)) - Number(Boolean(a.urgente));
    if (urgent !== 0) return urgent;
    const d = prioRank(a.priorite) - prioRank(b.priorite);
    if (d !== 0) return d;
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });
}

const INDICATEURS = [
  { id: "nouvelles", label: "Nouvelles demandes" },
  { id: "en_cours", label: "En cours de traitement" },
  { id: "attente_compagnie", label: "En attente de la compagnie" },
  { id: "relances", label: "Relances effectuées" },
  { id: "offre_transmise", label: "Offres transmises à l'agent" },
];

const RDV_PROXIMITE = {
  aujourdhui: { label: "RDV aujourd'hui", className: "bg-amber-100 text-amber-950" },
  demain: { label: "RDV demain", className: "bg-sky-100 text-sky-900" },
  proche: { label: "RDV sous 3 jours", className: "bg-indigo-50 text-indigo-900" },
  passe: { label: "RDV dépassé", className: "bg-slate-100 text-slate-600" },
};

function RdvClient({ row, compact = false }) {
  const date = String(row?.date_prochain_rdv || "").slice(0, 10);
  const heure = formatHeureRdv(row?.heure_rdv);
  if (!date) {
    return <span className={compact ? "text-sm text-slate-500" : "block text-[11px] text-slate-400 mt-1"}>Aucun RDV renseigné</span>;
  }
  if (compact) {
    return (
      <span className="text-sm text-slate-800 whitespace-nowrap" data-testid={`rdv-client-${row.id || "row"}`}>
        {formatDateFr(date)}{heure ? ` à ${heure}` : ""}
      </span>
    );
  }
  const chip = RDV_PROXIMITE[rdvProximite(date)];
  return (
    <span className="block mt-1" data-testid={`rdv-client-${row.id || "row"}`}>
      <span className="block text-[11px] font-semibold text-[#002FA7]">
        RDV client : {formatDateFr(date)}{heure ? ` à ${heure}` : ""}
      </span>
      {chip ? (
        <span className={`inline-flex mt-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${chip.className}`}>
          {chip.label}
        </span>
      ) : null}
    </span>
  );
}

function AvancementBadge({ row }) {
  const code = avancementCode(row);
  return (
    <span
      className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${AVANCEMENT_BADGE_STYLE[code] || AVANCEMENT_BADGE_STYLE.en_attente}`}
      title={statutLabel(row?.statut)}
    >
      {avancementLabel(row)}
    </span>
  );
}

function PrioriteBadge({ niveau }) {
  const cls = PRIORITE_STYLE[niveau] || PRIORITE_STYLE.normal;
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {prioriteLabel(niveau)}
    </span>
  );
}

export default function GestionReponsesOffres() {
  const navigate = useNavigate();
  const { hasPerm, isAdmin } = useAuth();
  const canProcess = hasPerm("demandes_offres.process");

  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState(null);
  const [formTypes, setFormTypes] = useState([]);
  const [compagniesFiltre, setCompagniesFiltre] = useState(COMPAGNIES_DEFAUT);
  const [notifs, setNotifs] = useState([]);
  const [notifCount, setNotifCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const [tab, setTab] = useState("file");
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [conseiller, setConseiller] = useState("all");
  const [compagnie, setCompagnie] = useState("all");
  const [formType, setFormType] = useState("all");
  const [priorite, setPriorite] = useState("all");
  const [periode, setPeriode] = useState("all");
  const [categorie, setCategorie] = useState(null);
  const [enRetard, setEnRetard] = useState(false);
  const [dayAction, setDayAction] = useState(null);
  const [origine, setOrigine] = useState("all");
  const [tri, setTri] = useState("maj");
  const [fileFilter, setFileFilter] = useState("nouvelles");
  const [erreurStats, setErreurStats] = useState(null);
  const [erreursAgentStats, setErreursAgentStats] = useState(null);

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get("/demandes-offres/meta");
        setFormTypes(res.data?.form_types || []);
        setCompagniesFiltre(
          res.data?.compagnies_referentiel?.length
            ? res.data.compagnies_referentiel
            : COMPAGNIES_DEFAUT,
        );
      } catch {
        setFormTypes([]);
      }
    })();
  }, []);

  const loadNotifs = useCallback(async () => {
    try {
      const res = await api.get("/notifications/offres", { params: { limit: 20 } });
      const data = res.data || {};
      setNotifs(Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : []);
      setNotifCount(typeof data.count === "number" ? data.count : 0);
    } catch {
      setNotifs([]);
      setNotifCount(0);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 500 };
      if (qDebounced) params.q = qDebounced;
      if (conseiller !== "all") params.conseiller = conseiller;
      if (compagnie !== "all") params.compagnie = compagnie;
      if (formType !== "all") params.form_type = formType;
      if (priorite !== "all") params.priorite = priorite;
      if (periode && periode !== "all") params.periode = periode;
      if (origine !== "all") params.demande_origine = origine;
      if (tri && tri !== "maj") params.tri = tri;

      const cat = categorie;
      if (cat && cat !== "en_retard") params.categorie = cat;
      if (enRetard || cat === "en_retard") params.en_retard = true;

      // Day-action shortcuts that map to API filters
      const statsParams = { periode: periode && periode !== "all" ? periode : undefined };
      if (conseiller !== "all") statsParams.conseiller = conseiller;

      const [listRes, statsRes, errRes, errAgentRes] = await Promise.all([
        api.get("/demandes-offres", { params }),
        api.get("/demandes-offres/stats", { params: statsParams }).catch((err) => {
          console.warn("stats offres", err);
          return { data: null, _error: err };
        }),
        api.get("/demandes-offres/stats/erreurs", { params: statsParams }).catch(() => ({ data: null })),
        api.get("/demandes-offres/stats/erreurs-agent", { params: statsParams }).catch(() => ({ data: null })),
        loadNotifs(),
      ]);
      setRows(Array.isArray(listRes.data) ? listRes.data : []);
      if (statsRes?.data) setStats(statsRes.data);
      else if (statsRes?._error) {
        toast.error(statsRes._error?.response?.data?.detail || "Statistiques indisponibles");
      }
      setErreurStats(errRes.data || null);
      setErreursAgentStats(errAgentRes.data || null);
    } catch (e) {
      setRows([]);
      toast.error(e?.response?.data?.detail || "Chargement impossible");
    } finally {
      setLoading(false);
    }
  }, [qDebounced, conseiller, compagnie, formType, priorite, periode, categorie, enRetard, origine, tri, loadNotifs]);

  useEffect(() => { load(); }, [load]);

  const openFiche = useCallback((id) => {
    if (!id) return;
    navigate(`/demandes-offres/${id}?from=gestion`);
  }, [navigate]);

  const toggleSoumis = useCallback(async (row, next, event) => {
    event?.stopPropagation?.();
    if (!canProcess || !row?.id) return;
    try {
      const res = await api.post(`/demandes-offres/${row.id}/soumis-compagnie`, { soumis: Boolean(next) });
      const updated = res.data || {};
      setRows((prev) => prev.map((r) => (
        r.id === row.id
          ? { ...r, soumis_compagnie: updated.soumis_compagnie ?? { soumis: Boolean(next) } }
          : r
      )));
      toast.success(next ? "Soumis à la compagnie" : "Indicateur retiré");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Mise à jour impossible");
    }
  }, [canProcess]);

  const onNotifClick = async (n) => {
    try {
      if (!n.read) await api.post(`/notifications/offres/${n.id}/read`);
    } catch { /* ignore */ }
    if (n.demande_id) {
      const target = offreNotificationPath(n, { fromGestion: true });
      if (target) navigate(target);
    } else loadNotifs();
  };

  const applyDayAction = (id) => {
    const next = dayAction === id ? null : id;
    setDayAction(next);
    setCategorie(null);
    setPriorite("all");
    setEnRetard(false);
    setTab("file");
  };

  const applyKpi = (id) => {
    const next = categorie === id ? null : id;
    setCategorie(next);
    setDayAction(null);
    if (next === "en_retard") setEnRetard(true);
    else if (!next) setEnRetard(false);
    else setEnRetard(false);
    setTab("file");
  };

  const queueRows = useMemo(() => {
    let list = rows;
    if (!qDebounced) list = list.filter((r) => r.statut !== "Brouillon");
    return tri && tri !== "maj" ? list : sortQueue(list);
  }, [rows, qDebounced, tri]);

  const visibleRows = useMemo(() => {
    const active = qDebounced ? "toutes" : fileFilter;
    if (active === "nouvelles") return queueRows.filter((r) => r.est_nouvelle);
    if (active === "relances") return queueRows.filter((r) => r.relance_en_cours);
    if (active === "en_cours") return queueRows.filter((r) => !r.est_nouvelle && !r.relance_en_cours && r.etape_suivi === "en_cours");
    if (active === "attente_compagnie") return queueRows.filter((r) => !r.est_nouvelle && !r.relance_en_cours && r.etape_suivi === "attente_compagnie");
    if (active === "offre_transmise") return queueRows.filter((r) => r.etape_suivi === "offre_transmise");
    return queueRows;
  }, [queueRows, qDebounced, fileFilter]);

  const conseillers = useMemo(() => {
    const fromStats = (stats?.by_agent || []).map((a) => a.agent).filter(Boolean);
    const fromRows = rows.map((r) => r.agent_label).filter(Boolean);
    return uniqueConseillerNames([...fromStats, ...fromRows]);
  }, [stats, rows]);

  const kanbanCols = stats?.gestion_kanban?.length ? stats.gestion_kanban : GESTION_KANBAN_FALLBACK;
  const gestion = stats?.gestion || {};

  const kanbanBoard = useMemo(() => {
    const placed = new Set();
    return kanbanCols.map((col) => {
      const set = new Set(col.statuts || []);
      const cards = queueRows.filter((r) => {
        if (placed.has(r.id)) return false;
        if (set.has(r.statut)) {
          placed.add(r.id);
          return true;
        }
        return false;
      });
      return { ...col, cards };
    });
  }, [kanbanCols, queueRows]);

  const typeLabel = (r) => r.form_type_label || r.type_pilier || "—";
  const compsShort = (r) => {
    const c = compagniesAffichees(r);
    if (!c.length) return "—";
    return c.length <= 2 ? c.join(", ") : `${c.slice(0, 2).join(", ")} +${c.length - 2}`;
  };

  if (!canProcess && !isAdmin) {
    return (
      <Layout>
        <div className="p-6">
          <Card className="p-6 border-rose-200 bg-rose-50">
            <h1 className="text-lg font-semibold text-rose-900">Accès restreint</h1>
            <p className="text-sm text-rose-700 mt-1">
              Cet espace est réservé aux gestionnaires disposant de la permission de traitement des offres.
            </p>
          </Card>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="p-6 space-y-6" data-testid="gestion-reponses-offres-page">
        {!canProcess ? (
          isAdmin ? (
            <div className="flex justify-end">
              <UrgenceQuotaButton />
            </div>
          ) : null
        ) : (<>
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
              <Briefcase className="h-6 w-6" style={{ color: ACCENT }} strokeWidth={1.75} />
              Gestion réponses offres
            </h1>
            <p className="text-sm text-slate-500 mt-1 max-w-2xl">
              Espace back-office pour traiter les demandes envoyées par les conseillers : prioriser,
              compléter les offres et suivre l&apos;activité.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {isAdmin && <UrgenceQuotaButton />}
            <Button
              variant="outline"
              size="sm"
              onClick={() => load()}
              disabled={loading}
              className="gap-1.5"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Actualiser
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3" data-testid="indicateurs-avancement">
          {INDICATEURS.map((item) => {
            const n = stats?.avancement?.[item.id] ?? 0;
            const active = fileFilter === item.id && !q;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setFileFilter(item.id);
                  setQ("");
                  setTab("file");
                }}
                className={`rounded-xl border bg-white px-4 py-4 text-left transition ${
                  active ? "border-[#002FA7] ring-2 ring-[#002FA7]/20" : "border-slate-200 hover:border-slate-300"
                }`}
                data-testid={`indicateur-${item.id}`}
              >
                <div className="text-3xl font-semibold tabular-nums text-slate-900">{n}</div>
                <div className="mt-1 text-sm text-slate-600">{item.label}</div>
              </button>
            );
          })}
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            className={`text-sm ${fileFilter === "toutes" || q ? "text-[#002FA7] font-medium" : "text-slate-500 hover:text-slate-800"}`}
            onClick={() => setFileFilter("toutes")}
          >
            Toutes les demandes
          </button>
        </div>

        {/* Filters */}
        <Card className="p-3 border-slate-200">
          <div className="flex flex-wrap items-center gap-2">
            <Filter className="h-4 w-4 text-slate-400 shrink-0" />
            <div className="relative flex-1 min-w-[160px] max-w-xs">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Rechercher…"
                className="pl-8 h-9"
              />
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-600">
              Trier les demandes par
              <Select value={tri} onValueChange={setTri}>
                <SelectTrigger className="h-9 w-[280px]" data-testid="tri-demandes"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="maj">Tri actuel</SelectItem>
                  <SelectItem value="soumission_desc">Date de soumission — plus récentes</SelectItem>
                  <SelectItem value="soumission_asc">Date de soumission — plus anciennes</SelectItem>
                  <SelectItem value="rdv_asc">Date de rendez-vous — plus proche</SelectItem>
                  <SelectItem value="rdv_desc">Date de rendez-vous — plus éloignée</SelectItem>
                </SelectContent>
              </Select>
            </label>
            <Select value={conseiller} onValueChange={setConseiller}>
              <SelectTrigger className="h-9 w-[160px]"><SelectValue placeholder="Conseiller" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous conseillers</SelectItem>
                {conseillers.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={compagnie} onValueChange={setCompagnie}>
              <SelectTrigger className="h-9 w-[140px]"><SelectValue placeholder="Compagnie" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Toutes compagnies</SelectItem>
                {compagniesFiltre.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={formType} onValueChange={setFormType}>
              <SelectTrigger className="h-9 w-[160px]"><SelectValue placeholder="Type" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous types</SelectItem>
                {formTypes.map((ft) => (
                  <SelectItem key={ft.id} value={ft.id}>{ft.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={priorite} onValueChange={(v) => { setPriorite(v); setDayAction(null); }}>
              <SelectTrigger className="h-9 w-[140px]"><SelectValue placeholder="Priorité" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Toutes priorités</SelectItem>
                <SelectItem value="normal">Normal</SelectItem>
                <SelectItem value="surveiller">À surveiller</SelectItem>
                <SelectItem value="urgent">Urgent</SelectItem>
              </SelectContent>
            </Select>
            <Select value={periode} onValueChange={setPeriode}>
              <SelectTrigger className="h-9 w-[150px]"><SelectValue placeholder="Période" /></SelectTrigger>
              <SelectContent>
                {PERIODE_FILTERS.filter((p) => p.id !== "custom").map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={origine} onValueChange={setOrigine}>
              <SelectTrigger className="h-9 min-w-[220px]"><SelectValue placeholder="Type de demande" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous les types de demande</SelectItem>
                {Object.entries(DEMANDE_ORIGINE_LABELS).map(([id, label]) => (
                  <SelectItem key={id} value={id}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              size="sm"
              variant={enRetard ? "default" : "outline"}
              className={enRetard ? "text-white" : ""}
              style={enRetard ? { background: ACCENT } : undefined}
              onClick={() => {
                setEnRetard((v) => !v);
                setCategorie(null);
                setDayAction(null);
              }}
            >
              En retard
            </Button>
            {(categorie || dayAction || enRetard || priorite !== "all" || q || conseiller !== "all" || origine !== "all") && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="text-slate-500"
                onClick={() => {
                  setQ("");
                  setConseiller("all");
                  setCompagnie("all");
                  setFormType("all");
                  setPriorite("all");
                  setPeriode("all");
                  setOrigine("all");
                  setCategorie(null);
                  setEnRetard(false);
                  setDayAction(null);
                  setFileFilter("nouvelles");
                  setTri("maj");
                }}
              >
                Réinitialiser
              </Button>
            )}
          </div>
        </Card>

        {/* Tabs */}
        <div className="flex flex-wrap gap-1 border-b border-slate-200 pb-0">
          {[
            { id: "file", label: "File à traiter", icon: ClipboardList },
            { id: "kanban", label: "Kanban", icon: Columns3 },
            { id: "agents", label: "Activité conseillers", icon: Users },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 -mb-px transition ${
                tab === id
                  ? "border-[#002FA7] text-[#002FA7]"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
          <span className="ml-auto self-center text-xs text-slate-400 tabular-nums">
            {loading ? "…" : `${visibleRows.length} dossier${visibleRows.length !== 1 ? "s" : ""}`}
          </span>
        </div>

        {/* File à traiter */}
        {tab === "file" && (
          <Card className="border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50/80 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {["Client", "Numéro OFF", "Conseiller", "Type d'assurance", "Date de réception", "RDV client", "Avancement du traitement", "Action"].map((h) => (
                      <th key={h} className="px-3 py-2.5 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={8} className="px-3 py-12 text-center text-slate-400">
                        <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Chargement…
                      </td>
                    </tr>
                  ) : visibleRows.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-3 py-12 text-center text-slate-400">
                        Aucune demande dans cette vue.
                      </td>
                    </tr>
                  ) : (
                    visibleRows.map((r) => {
                      const actionLabel = "Traiter";
                      return (
                        <tr
                          key={r.id}
                          className={`border-t border-slate-100 hover:bg-slate-50 ${
                            r.est_nouvelle ? "bg-sky-50/70" : r.urgente ? "bg-rose-50/40" : ""
                          }`}
                        >
                          <td className="px-3 py-3 font-medium text-slate-900 whitespace-nowrap">
                            {clientLabel(r)}
                            {r.urgente && (
                              <span className="ml-2 inline-flex rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                                URGENT
                              </span>
                            )}
                            {r.urgente && r.urgence_motif ? (
                              <span className="mt-1 block text-[11px] font-normal text-rose-800 max-w-[220px] whitespace-normal">{r.urgence_motif}</span>
                            ) : null}
                            {r.est_nouvelle && (
                              <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-[#002FA7]">Nouvelle</span>
                            )}
                          </td>
                          <td className="px-3 py-3 text-slate-700 whitespace-nowrap">{r.numero || "—"}</td>
                          <td className="px-3 py-3 text-slate-600 whitespace-nowrap">{r.agent_label || "—"}</td>
                          <td className="px-3 py-3 text-slate-600 max-w-[180px] truncate" title={typeLabel(r)}>{typeLabel(r)}</td>
                          <td className="px-3 py-3 text-slate-700 whitespace-nowrap">{r.date_envoi ? formatDateFr(r.date_envoi) : "—"}</td>
                          <td className="px-3 py-3"><RdvClient row={r} compact /></td>
                          <td className="px-3 py-3">
                            <AvancementBadge row={r} />
                            {r.relance_en_cours && (
                              <span className="mt-1 block text-[11px] text-slate-500">Relance effectuée auprès de la compagnie</span>
                            )}
                          </td>
                          <td className="px-3 py-3">
                            <Button
                              size="sm"
                              className="h-8 text-xs"
                              style={{ background: ACCENT }}
                              onClick={() => openFiche(r.id)}
                            >
                              {actionLabel}
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {/* Kanban — visual only */}
        {tab === "kanban" && (
          <div className="overflow-x-auto pb-2">
            <div className="flex gap-3 min-w-max">
              {kanbanBoard.map((col) => (
                <div key={col.id} className="w-64 shrink-0 flex flex-col rounded-xl border border-slate-200 bg-slate-50/50">
                  <div className="px-3 py-2.5 border-b border-slate-200 flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-700">{col.label}</span>
                    <span
                      className="text-[10px] font-bold px-1.5 py-0.5 rounded-full text-white tabular-nums"
                      style={{ background: ACCENT }}
                    >
                      {col.cards.length}
                    </span>
                  </div>
                  <div className="p-2 space-y-2 max-h-[560px] overflow-y-auto">
                    {col.cards.length === 0 ? (
                      <p className="text-[11px] text-slate-400 text-center py-6">Vide</p>
                    ) : (
                      col.cards.map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          onClick={() => openFiche(r.id)}
                          className={`w-full text-left rounded-lg border bg-white p-2.5 shadow-sm hover:shadow transition ${
                            r.priorite === "urgent"
                              ? "border-red-200"
                              : r.priorite === "surveiller"
                                ? "border-amber-200"
                                : "border-slate-150 border-slate-200"
                          }`}
                        >
                          <p className="text-sm font-semibold text-slate-900 truncate">{clientLabel(r)}</p>
                          <p className="text-[11px] text-slate-500 truncate mt-0.5">{r.agent_label || "—"}</p>
                          <p className="text-[11px] text-slate-500 mt-0.5">Soumission : {formatDateFr(r.date_envoi || r.created_at)}</p>
                          <RdvClient row={r} />
                          <p className="text-[11px] text-slate-600 truncate mt-1">{typeLabel(r)}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5 truncate">{compsShort(r)}</p>
                          <div className="flex items-center justify-between gap-1 mt-2">
                            <span className="flex flex-wrap items-center gap-1">
                              <AvancementBadge row={r} />
                              <PendingComplementBadge count={r.nb_complements_en_attente} />
                            </span>
                            <PrioriteBadge niveau={r.priorite} />
                          </div>
                          <p className="text-[10px] text-slate-400 mt-1.5">{formatDateFr(r.date_envoi || r.created_at)}</p>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Tableau de pilotage visuel — le changement de statut se fait sur la fiche demande.
            </p>
          </div>
        )}

        {/* Activité conseillers */}
        {tab === "agents" && (
          <Card className="border-slate-200 overflow-hidden">
            <p className="px-3 pt-3 text-xs text-slate-500">
              Compteurs par agent : demandes hors brouillon et annulées, et nombre d&apos;offres signées.
              Le taux de signature n&apos;est pas recalculé ici. Il se lit sur la fiche :
              signées / dossiers transmis au client (envoyée au client, en conclusion, signée ou refusée).
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50/80 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {["Conseiller", "Demandes", "Variantes", "Offres reçues", "Incomplètes", "Complètes", "Signées"].map((h) => (
                      <th key={h} className="px-3 py-2.5 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(stats?.by_agent || []).length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-3 py-10 text-center text-slate-400">Aucune activité</td>
                    </tr>
                  ) : (
                    (stats.by_agent || []).map((a) => (
                      <tr
                        key={a.agent}
                        className="border-t border-slate-100 hover:bg-[#002FA7]/5 cursor-pointer"
                        onClick={() => {
                          setConseiller(a.agent);
                          setTab("file");
                          setFileFilter("toutes");
                          setDayAction(null);
                          setCategorie(null);
                        }}
                      >
                        <td className="px-3 py-2.5 font-medium text-slate-900">{a.agent}</td>
                        <td className="px-3 py-2.5 tabular-nums">{a.nb_demandes ?? 0}</td>
                        <td className="px-3 py-2.5 tabular-nums">{a.nb_variantes_sollicitees ?? 0}</td>
                        <td className="px-3 py-2.5 tabular-nums">{a.nb_offres_recues ?? 0}</td>
                        <td className="px-3 py-2.5 tabular-nums text-rose-700">{a.incompletes ?? 0}</td>
                        <td className="px-3 py-2.5 tabular-nums text-emerald-700">{a.completes ?? 0}</td>
                        <td className="px-3 py-2.5 tabular-nums font-semibold" style={{ color: ACCENT }}>
                          {a.offres_signees ?? 0}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {/* Scoring erreurs */}
        {canProcess && (
          <Card className="border-slate-200 overflow-hidden" data-testid="scoring-erreurs">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
              <BarChart3 className="h-4 w-4" style={{ color: ACCENT }} />
              <h2 className="text-sm font-semibold text-slate-800">Scoring erreurs</h2>
              <span className="text-[11px] text-slate-400">Taux d&apos;incomplètes par conseiller</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50/80 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {["Conseiller", "Demandes", "Incomplètes", "Taux d'erreur", "Erreurs récentes"].map((h) => (
                      <th key={h} className="px-3 py-2.5 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {!(erreurStats?.by_agent || []).length ? (
                    <tr>
                      <td colSpan={5} className="px-3 py-8 text-center text-slate-400">Aucune donnée d&apos;erreur</td>
                    </tr>
                  ) : (
                    (erreurStats.by_agent || []).map((a) => (
                      <tr key={a.agent} className="border-t border-slate-100">
                        <td className="px-3 py-2.5 font-medium text-slate-900">{a.agent}</td>
                        <td className="px-3 py-2.5 tabular-nums">{a.demandes ?? 0}</td>
                        <td className="px-3 py-2.5 tabular-nums text-rose-700">{a.incompletes ?? 0}</td>
                        <td className="px-3 py-2.5 tabular-nums font-semibold" style={{ color: ACCENT }}>
                          {typeof a.taux_erreur === "number" ? `${a.taux_erreur} %` : "—"}
                        </td>
                        <td className="px-3 py-2.5 text-xs text-slate-600 max-w-md">
                          {(a.erreurs || []).slice(0, 3).map((e, i) => (
                            <span key={`${e.demande_id}-${i}`} className="block truncate">
                              {e.label || e.code}
                              {e.detail ? ` — ${e.detail}` : ""}
                              {e.numero ? ` (${e.numero})` : ""}
                            </span>
                          ))}
                          {(a.erreurs || []).length > 3 && (
                            <span className="text-slate-400">+{(a.erreurs || []).length - 3} autres</span>
                          )}
                          {!(a.erreurs || []).length && "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {/* Erreurs champ par agent (bouton Erreurs) */}
        {canProcess && (
          <Card className="border-slate-200 overflow-hidden" data-testid="erreurs-agent-stats">
            <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-rose-600" />
              <h2 className="text-sm font-semibold text-slate-800">Erreurs sur demandes d&apos;offres</h2>
              <span className="text-[11px] text-slate-400">
                Total : {erreursAgentStats?.total ?? 0}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50/80 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {["Agent", "Total", "Répartition par champ"].map((h) => (
                      <th key={h} className="px-3 py-2.5 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {!(erreursAgentStats?.by_agent || []).length ? (
                    <tr>
                      <td colSpan={3} className="px-3 py-8 text-center text-slate-400">Aucune erreur champ enregistrée</td>
                    </tr>
                  ) : (
                    (erreursAgentStats.by_agent || []).map((a) => (
                      <tr key={a.agent_id || a.agent} className="border-t border-slate-100">
                        <td className="px-3 py-2.5 font-medium text-slate-900">{a.agent}</td>
                        <td className="px-3 py-2.5 tabular-nums font-semibold text-rose-700">{a.total ?? 0}</td>
                        <td className="px-3 py-2.5 text-xs text-slate-600">
                          {(a.by_field || []).map((f) => (
                            <span key={f.code} className="inline-flex mr-2 mb-1 rounded bg-rose-50 text-rose-900 px-2 py-0.5" title={(f.comments || []).join(" · ")}>
                              {f.label} : {f.count}
                              {(f.comments || [])[0] ? ` — ${(f.comments || [])[0]}` : ""}
                            </span>
                          ))}
                          {!(a.by_field || []).length && "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        )}

      </>)}
      </div>
    </Layout>
  );
}

function UrgenceQuotaButton() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);
  const [agent, setAgent] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await api.get("/demandes-offres/parametres-urgence");
      setSettings(res.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Paramètres d'urgence indisponibles");
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const save = async () => {
    if (!settings) return;
    setBusy(true);
    try {
      const res = await api.put("/demandes-offres/parametres-urgence", {
        quota_actif: Boolean(settings.quota_actif),
        max_par_agent: Number(settings.max_par_agent) || 0,
        periode: settings.periode === "annee" ? "annee" : "mois",
      });
      setSettings(res.data);
      toast.success("Quotas d'urgence enregistrés");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Enregistrement impossible");
    } finally {
      setBusy(false);
    }
  };

  const grant = async (label) => {
    const name = (label || "").trim();
    if (!name) return;
    setBusy(true);
    try {
      const res = await api.post("/demandes-offres/parametres-urgence/exception", { agent_label: name });
      setSettings(res.data);
      setAgent("");
      toast.success(`Urgence supplémentaire accordée à ${name}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Exception impossible");
    } finally {
      setBusy(false);
    }
  };

  const usages = Array.isArray(settings?.usages) ? settings.usages : [];
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        data-testid="urgence-quota-button"
      >
        Quotas d&apos;urgence
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="urgence-quota-panel">
          <DialogHeader>
            <DialogTitle>Quotas d&apos;urgence</DialogTitle>
            <DialogDescription>
              La limite est désactivée tant qu&apos;elle n&apos;est pas cochée.
              Une exception ajoute une urgence au plafond de l&apos;agent pour la période en cours.
            </DialogDescription>
          </DialogHeader>
          {!settings ? (
            <p className="text-sm text-slate-500">Chargement…</p>
          ) : (
          <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={Boolean(settings.quota_actif)}
            onChange={(e) => setSettings({ ...settings, quota_actif: e.target.checked })}
          />
          Limite active
        </label>
        <label className="text-sm">
          Maximum par agent
          <Input
            type="number"
            min="0"
            className="mt-1 w-28"
            value={settings.max_par_agent}
            onChange={(e) => setSettings({ ...settings, max_par_agent: e.target.value })}
          />
        </label>
        <label className="text-sm">
          Période
          <select
            className="mt-1 block h-9 rounded-md border px-2"
            value={settings.periode === "annee" ? "annee" : "mois"}
            onChange={(e) => setSettings({ ...settings, periode: e.target.value })}
          >
            <option value="mois">Mensuelle</option>
            <option value="annee">Annuelle</option>
          </select>
        </label>
        <Button size="sm" onClick={save} disabled={busy} className="bg-[#002FA7] hover:bg-[#00248a]">Enregistrer</Button>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-sm">
          Accorder une urgence à
          <Input className="mt-1 w-56" value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="Nom de l'agent" />
        </label>
        <Button size="sm" variant="outline" disabled={busy || !agent.trim()} onClick={() => grant(agent)}>
          Accorder une urgence supplémentaire
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
              <th className="py-2 pr-3">Agent</th>
              <th className="py-2 pr-3">Urgences utilisées</th>
              <th className="py-2 pr-3">Plafond</th>
              <th className="py-2 pr-3">Exceptions</th>
              <th className="py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {usages.length === 0 ? (
              <tr><td colSpan={5} className="py-4 text-slate-400">Aucune urgence enregistrée sur la période.</td></tr>
            ) : usages.map((row) => (
              <tr key={row.agent} className="border-t border-slate-100">
                <td className="py-2 pr-3">{row.agent}</td>
                <td className="py-2 pr-3 tabular-nums">{row.utilisees}</td>
                <td className="py-2 pr-3 tabular-nums">{settings.quota_actif ? row.plafond : "Illimité"}</td>
                <td className="py-2 pr-3 tabular-nums">{row.exceptions}</td>
                <td className="py-2">
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => grant(row.agent)}>
                    +1 urgence
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
          </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
