import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  formatDateFr,
  STATUT_STYLE,
} from "@/lib/demandesOffres";
import {
  AlertTriangle, CheckCircle2, ChevronRight, Clock, FilePlus2, FileSearch,
  FileSpreadsheet, FolderKanban, Layers, TrendingUp, User, X,
} from "lucide-react";

const ANNULEE = "Demande annulée";
const BROUILLON = "Brouillon";

const KPI_DEFS = [
  { key: "demandes", label: "Demandes d'offre", icon: FolderKanban, accent: "bg-slate-100 text-slate-700" },
  { key: "brouillons", label: "Brouillons", icon: FilePlus2, accent: "bg-zinc-100 text-zinc-700" },
  { key: "attente", label: "En attente", icon: Clock, accent: "bg-amber-100 text-amber-700" },
  { key: "recues", label: "Offres reçues", icon: FileSearch, accent: "bg-violet-100 text-violet-800" },
  { key: "incompletes", label: "Offres incomplètes", icon: AlertTriangle, accent: "bg-rose-100 text-rose-700" },
  { key: "signees", label: "Offres signées", icon: CheckCircle2, accent: "bg-emerald-100 text-emerald-700" },
  { key: "envoyees", label: "Offres envoyées au client", icon: FileSpreadsheet, accent: "bg-purple-100 text-purple-700" },
  { key: "variantes", label: "Variantes sollicitées", icon: Layers, accent: "bg-blue-100 text-blue-700" },
  { key: "completes", label: "Offres complètes", icon: CheckCircle2, accent: "bg-emerald-100 text-emerald-700" },
];

const PIPELINE_STAGES = [
  { id: "brouillon", label: "Brouillon", statuts: [BROUILLON] },
  { id: "demande_envoyee", label: "Demande envoyée", statuts: ["Demande envoyée", "Demande validée"] },
  { id: "en_attente", label: "En attente", statuts: ["En attente d'informations", "Demande incomplète"] },
  { id: "offre_recue", label: "Offre reçue", statuts: ["Offre reçue"] },
  { id: "completes", label: "Offres complètes", statuts: ["Offres complètes", "Offre complète", "Offre choisie", "En conclusion"] },
  { id: "envoyee_client", label: "Envoyée au client", statuts: ["Offre envoyée au client"] },
  { id: "signee", label: "Signée", statuts: ["Offre signée"] },
  { id: "refusee", label: "Refusée", statuts: ["Offre refusée"] },
];

const PERIODES_UI = [
  { id: "today", label: "Aujourd'hui" },
  { id: "week", label: "Cette semaine" },
  { id: "month", label: "Ce mois" },
  { id: "year", label: "Cette année" },
  { id: "custom", label: "Personnalisé" },
  { id: "all", label: "Toute période" },
];

function matchesKpi(row, key) {
  const st = row.statut || BROUILLON;
  if (st === ANNULEE && key !== "all") return false;
  switch (key) {
    case "demandes":
      return st !== BROUILLON && st !== ANNULEE;
    case "brouillons":
      return st === BROUILLON;
    case "variantes":
      return st !== BROUILLON && st !== ANNULEE && (row.compagnies || []).length > 0;
    case "attente":
      return ["Demande envoyée", "Demande validée", "En attente d'informations"].includes(st);
    case "incompletes":
      return ["Demande incomplète", "En attente d'informations"].includes(st);
    case "recues":
      // KPI « Offres reçues » — statut exact uniquement
      return st === "Offre reçue";
    case "completes":
      return st === "Offres complètes" || st === "Offre complète";
    case "envoyees":
      // KPI « Offres envoyées au client » — statut exact
      return st === "Offre envoyée au client";
    case "signees":
      return st === "Offre signée";
    case "refusees":
      return st === "Offre refusée";
    case "all":
    default:
      return st !== ANNULEE;
  }
}

function matchesPipeline(row, stageId) {
  const stage = PIPELINE_STAGES.find((s) => s.id === stageId);
  if (!stage) return true;
  return stage.statuts.includes(row.statut || BROUILLON);
}

function offerType(row) {
  return (row.form_type_label || row.type_pilier || "—").trim() || "—";
}

function agentName(row) {
  return (row.agent_label || `${row.agent_prenom || ""} ${row.agent_nom || ""}`.trim() || "Non attribué");
}

function clientName(row) {
  return (row.client_label || `${row.prenom || ""} ${row.nom || ""}`.trim() || "—");
}

function dateReception(row) {
  const offres = row.offres || [];
  if (offres.length) {
    const dates = offres.map((o) => o.date_reception || o.received_at).filter(Boolean);
    if (dates.length) return dates.sort().slice(-1)[0];
  }
  return row.offre?.date_reception || row.offre?.received_at || null;
}

function relevantDates(row) {
  const items = [
    { label: "Création", value: row.created_at },
    { label: "Envoi demande", value: row.date_envoi },
    { label: "Réception offre", value: dateReception(row) },
    { label: "Envoi client", value: row.envoi_client?.at },
    { label: "Signature", value: row.signature?.date_signature || (row.signature?.signee ? row.signature?.at : null) },
  ];
  return items.filter((d) => d.value);
}

function computeAgentBuckets(rows) {
  const map = {};
  for (const r of rows) {
    const st = r.statut || BROUILLON;
    if (st === ANNULEE) continue;
    const name = agentName(r);
    if (!map[name]) {
      map[name] = {
        agent: name,
        nb_demandes: 0,
        nb_brouillons: 0,
        offres_envoyees: 0,
        nb_offres_recues: 0,
        offres_signees: 0,
        offres_refusees: 0,
      };
    }
    const b = map[name];
    if (st === BROUILLON) b.nb_brouillons += 1;
    else b.nb_demandes += 1;
    if (["Offre envoyée au client"].includes(st)) {
      b.offres_envoyees += 1;
    }
    if (st === "Offre reçue") {
      b.nb_offres_recues += 1;
    }
    if (st === "Offre signée") b.offres_signees += 1;
    if (st === "Offre refusée") b.offres_refusees += 1;
  }
  return Object.values(map).sort(
    (a, b) => (b.nb_demandes + b.nb_brouillons) - (a.nb_demandes + a.nb_brouillons)
      || a.agent.localeCompare(b.agent, "fr"),
  );
}

function KpiCard({ def, value, active, onClick }) {
  const Icon = def.icon;
  return (
    <Card
      data-testid={`kpi-offres-${def.key}`}
      onClick={onClick}
      className={`p-5 border transition-all cursor-pointer hover:-translate-y-[2px] ${
        active ? "border-[#002FA7] ring-2 ring-[#002FA7]/25 bg-[#002FA7]/[0.03]" : "border-border"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground font-medium truncate">{def.label}</p>
          <p className="font-display font-black text-3xl tracking-tight mt-2 tabular-nums">{value ?? 0}</p>
        </div>
        <div className={`h-9 w-9 rounded-md flex items-center justify-center shrink-0 ${def.accent}`}>
          <Icon className="h-4 w-4" strokeWidth={1.75} />
        </div>
      </div>
    </Card>
  );
}

export default function OffresDashboardPanel({
  isGlobal,
  filterConseiller,
  conseillerNames = [],
}) {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [catalogTypes, setCatalogTypes] = useState([]); // [{ id, label }]
  const [periode, setPeriode] = useState("all");
  const [dateDe, setDateDe] = useState("");
  const [dateA, setDateA] = useState("");
  const [agentFilter, setAgentFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [kpiFilter, setKpiFilter] = useState("demandes");
  const [pipelineFilter, setPipelineFilter] = useState(null);

  const effectiveAgent = isGlobal
    ? (filterConseiller && filterConseiller !== "all" ? filterConseiller : agentFilter)
    : "all";

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get("/demandes-offres/meta");
        const fromApi = (res.data?.form_types || [])
          .filter((ft) => ft?.id)
          .map((ft) => ({
            id: String(ft.id).trim(),
            label: (ft.label || ft.id).trim(),
          }));
        // Menu intranet : tous les types créables (y compris libellés distincts)
        const byId = new Map(fromApi.map((ft) => [ft.id, ft]));
        const menu = res.data?.form_menu;
        const walk = (items) => {
          for (const item of items || []) {
            const id = (item?.form_type || "").trim();
            if (!id || item?.coming_soon) continue;
            if (!byId.has(id)) {
              byId.set(id, { id, label: (item.label || id).trim() });
            }
          }
        };
        for (const family of menu?.families || []) {
          for (const section of family.sections || []) {
            walk(section.items);
          }
        }
        walk(menu?.extra_items);
        setCatalogTypes(
          [...byId.values()].sort((a, b) => a.label.localeCompare(b.label, "fr")),
        );
      } catch {
        setCatalogTypes([]);
      }
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 1000, periode: periode || "all" };
      if (periode === "custom") {
        if (dateDe) params.date_de = dateDe;
        if (dateA) params.date_a = dateA;
      }
      if (isGlobal && effectiveAgent && effectiveAgent !== "all") {
        params.conseiller = effectiveAgent;
      }
      const res = await api.get("/demandes-offres", { params });
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [periode, dateDe, dateA, isGlobal, effectiveAgent]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (isGlobal && filterConseiller && filterConseiller !== "all") {
      setAgentFilter(filterConseiller);
    }
  }, [filterConseiller, isGlobal]);

  const typeOptions = useMemo(() => {
    const byId = new Map(catalogTypes.map((ft) => [ft.id, ft]));
    // Types déjà utilisés en base mais absents du catalogue (historique)
    for (const r of rows) {
      const id = (r.form_type || "").trim();
      if (!id || byId.has(id)) continue;
      byId.set(id, {
        id,
        label: (r.form_type_label || id).trim() || id,
      });
    }
    return [...byId.values()].sort((a, b) => a.label.localeCompare(b.label, "fr"));
  }, [catalogTypes, rows]);

  const agentOptions = useMemo(() => {
    if (conseillerNames?.length) return conseillerNames;
    const set = new Set();
    for (const r of rows) set.add(agentName(r));
    return [...set].sort((a, b) => a.localeCompare(b, "fr"));
  }, [rows, conseillerNames]);

  const baseRows = useMemo(() => {
    let list = rows.filter((r) => (r.statut || BROUILLON) !== ANNULEE);
    if (typeFilter !== "all") {
      list = list.filter((r) => (r.form_type || "").trim() === typeFilter);
    }
    // Si le filtre agent du panneau local est actif et différent du conseiller global déjà appliqué côté API
    if (isGlobal && agentFilter !== "all" && (!filterConseiller || filterConseiller === "all")) {
      list = list.filter((r) => agentName(r) === agentFilter);
    }
    return list;
  }, [rows, typeFilter, agentFilter, isGlobal, filterConseiller]);

  const kpiCounts = useMemo(() => {
    const c = {
      demandes: 0, brouillons: 0, variantes: 0, attente: 0,
      recues: 0, incompletes: 0, completes: 0, envoyees: 0, signees: 0, refusees: 0,
    };
    for (const r of baseRows) {
      const st = r.statut || BROUILLON;
      if (st === BROUILLON) c.brouillons += 1;
      else c.demandes += 1;
      if (st !== BROUILLON && (r.compagnies || []).length) {
        c.variantes += (r.compagnies || []).length;
      }
      if (matchesKpi(r, "attente")) c.attente += 1;
      if (matchesKpi(r, "incompletes")) c.incompletes += 1;
      if (matchesKpi(r, "recues")) c.recues += 1;
      if (matchesKpi(r, "completes")) c.completes += 1;
      if (matchesKpi(r, "envoyees")) c.envoyees += 1;
      if (matchesKpi(r, "signees")) c.signees += 1;
      if (matchesKpi(r, "refusees")) c.refusees += 1;
    }
    return c;
  }, [baseRows]);

  const pipelineCounts = useMemo(() => {
    return PIPELINE_STAGES.map((stage) => ({
      ...stage,
      count: baseRows.filter((r) => stage.statuts.includes(r.statut || BROUILLON)).length,
    }));
  }, [baseRows]);

  const agents = useMemo(() => computeAgentBuckets(baseRows), [baseRows]);

  const detailRows = useMemo(() => {
    let list = baseRows;
    if (pipelineFilter) {
      list = list.filter((r) => matchesPipeline(r, pipelineFilter));
    } else if (kpiFilter) {
      list = list.filter((r) => matchesKpi(r, kpiFilter));
    }
    return [...list].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  }, [baseRows, kpiFilter, pipelineFilter]);

  const activeKpiLabel = useMemo(() => {
    if (pipelineFilter) {
      return PIPELINE_STAGES.find((s) => s.id === pipelineFilter)?.label || pipelineFilter;
    }
    return KPI_DEFS.find((k) => k.key === kpiFilter)?.label || "Toutes";
  }, [kpiFilter, pipelineFilter]);

  const selectKpi = (key) => {
    setPipelineFilter(null);
    setKpiFilter((prev) => (prev === key ? "all" : key));
  };

  const selectPipeline = (id) => {
    setKpiFilter(null);
    setPipelineFilter((prev) => (prev === id ? null : id));
  };

  const selectAgent = (name) => {
    setAgentFilter((prev) => (prev === name ? "all" : name));
  };

  const clearDetailFilters = () => {
    setKpiFilter("demandes");
    setPipelineFilter(null);
  };

  const taux = kpiCounts.envoyees
    ? Math.round((kpiCounts.signees / kpiCounts.envoyees) * 1000) / 10
    : 0;

  return (
    <div className="space-y-6" data-testid="offres-dashboard-panel">
      {/* Filtres */}
      <Card className="p-4 border-border">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5 min-w-[160px]">
            <Label className="text-xs text-muted-foreground">Période</Label>
            <Select value={periode} onValueChange={setPeriode}>
              <SelectTrigger data-testid="offres-filter-periode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PERIODES_UI.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {periode === "custom" && (
            <>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Du</Label>
                <Input type="date" value={dateDe} onChange={(e) => setDateDe(e.target.value)} className="w-[150px]" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Au</Label>
                <Input type="date" value={dateA} onChange={(e) => setDateA(e.target.value)} className="w-[150px]" />
              </div>
            </>
          )}
          {isGlobal && (
            <div className="space-y-1.5 min-w-[180px]">
              <Label className="text-xs text-muted-foreground">Agent</Label>
              <Select
                value={agentFilter}
                onValueChange={setAgentFilter}
                disabled={Boolean(filterConseiller && filterConseiller !== "all")}
              >
                <SelectTrigger data-testid="offres-filter-agent">
                  <SelectValue placeholder="Tous" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tous</SelectItem>
                  <SelectItem value="Non attribué">Non attribué</SelectItem>
                  {agentOptions.map((n) => (
                    <SelectItem key={n} value={n}>{n}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1.5 min-w-[200px]">
            <Label className="text-xs text-muted-foreground">Type d&apos;offre</Label>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger data-testid="offres-filter-type">
                <SelectValue placeholder="Tous" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous</SelectItem>
                {typeOptions.map((t) => (
                  <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {(kpiFilter && kpiFilter !== "demandes") || pipelineFilter || typeFilter !== "all" || (agentFilter !== "all" && !(filterConseiller && filterConseiller !== "all")) ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-xs gap-1"
              onClick={() => {
                clearDetailFilters();
                setTypeFilter("all");
                if (!(filterConseiller && filterConseiller !== "all")) setAgentFilter("all");
              }}
            >
              <X className="h-3.5 w-3.5" /> Réinitialiser
            </Button>
          ) : null}
        </div>
      </Card>

      {/* KPI */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {KPI_DEFS.map((def) => (
          <KpiCard
            key={def.key}
            def={def}
            value={kpiCounts[def.key]}
            active={!pipelineFilter && kpiFilter === def.key}
            onClick={() => selectKpi(def.key)}
          />
        ))}
        <Card className="p-5 border-border">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm text-muted-foreground font-medium">Taux de signature</p>
              <p className="font-display font-black text-3xl tracking-tight mt-2 tabular-nums">{taux}%</p>
            </div>
            <div className="h-9 w-9 rounded-md flex items-center justify-center bg-green-100 text-green-700">
              <TrendingUp className="h-4 w-4" strokeWidth={1.75} />
            </div>
          </div>
        </Card>
      </div>

      {/* Pipeline */}
      <Card className="p-5 border-border">
        <h2 className="font-display font-bold text-lg tracking-tight mb-1">Pipeline des offres</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Cliquez une étape pour filtrer le détail
        </p>
        <div className="flex flex-wrap items-stretch gap-2">
          {pipelineCounts.map((stage, idx) => (
            <React.Fragment key={stage.id}>
              {idx > 0 && (
                <div className="hidden sm:flex items-center text-muted-foreground/50 px-0.5">
                  <ChevronRight className="h-4 w-4" />
                </div>
              )}
              <button
                type="button"
                data-testid={`pipeline-${stage.id}`}
                onClick={() => selectPipeline(stage.id)}
                className={`flex-1 min-w-[110px] rounded-md border px-3 py-3 text-left transition-colors ${
                  pipelineFilter === stage.id
                    ? "border-[#002FA7] bg-[#002FA7]/5 ring-1 ring-[#002FA7]/30"
                    : "border-border hover:border-[#002FA7]/40 hover:bg-secondary/40"
                }`}
              >
                <p className="text-[11px] font-medium text-muted-foreground leading-tight">{stage.label}</p>
                <p className="font-display font-bold text-xl tabular-nums mt-1">{stage.count}</p>
              </button>
            </React.Fragment>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Activité par agent */}
        <Card className="p-5 border-border lg:col-span-1">
          <h2 className="font-display font-bold text-lg tracking-tight mb-1">Activité par agent</h2>
          <p className="text-xs text-muted-foreground mb-4">
            Cliquez un agent pour filtrer le détail
          </p>
          {agents.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Aucune activité.</p>
          ) : (
            <div className="space-y-2 max-h-[420px] overflow-y-auto">
              {agents.map((a) => {
                const active = agentFilter === a.agent;
                return (
                  <button
                    key={a.agent}
                    type="button"
                    data-testid={`agent-card-${a.agent}`}
                    onClick={() => selectAgent(a.agent)}
                    className={`w-full text-left rounded-md border px-3 py-3 transition-colors ${
                      active
                        ? "border-[#002FA7] bg-[#002FA7]/5 ring-1 ring-[#002FA7]/25"
                        : "border-border hover:border-[#002FA7]/35 hover:bg-secondary/40"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <User className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className={`text-sm truncate ${active ? "font-semibold text-[#002FA7]" : "font-medium"}`}>
                        {a.agent}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                      <span><strong className="text-foreground tabular-nums">{a.nb_demandes}</strong> demandes</span>
                      <span><strong className="text-foreground tabular-nums">{a.nb_brouillons}</strong> brouillons</span>
                      <span><strong className="text-foreground tabular-nums">{a.offres_envoyees}</strong> envoyées client</span>
                      <span><strong className="text-foreground tabular-nums">{a.nb_offres_recues}</strong> offres reçues</span>
                      <span><strong className="text-foreground tabular-nums">{a.offres_signees}</strong> signées</span>
                      <span><strong className="text-foreground tabular-nums">{a.offres_refusees}</strong> refusées</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Card>

        {/* Détail */}
        <Card className="p-5 border-border lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div>
              <h2 className="font-display font-bold text-lg tracking-tight">Détail des offres</h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Filtre : <span className="font-medium text-foreground">{activeKpiLabel}</span>
                {agentFilter !== "all" ? (
                  <> · Agent : <span className="font-medium text-foreground">{agentFilter}</span></>
                ) : null}
                {" · "}
                <span className="tabular-nums">{detailRows.length}</span> résultat{detailRows.length === 1 ? "" : "s"}
              </p>
            </div>
            {(pipelineFilter || (kpiFilter && kpiFilter !== "demandes" && kpiFilter !== "all")) && (
              <Button type="button" variant="outline" size="sm" className="text-xs" onClick={clearDetailFilters}>
                Voir les demandes
              </Button>
            )}
          </div>

          {loading ? (
            <p className="text-sm text-muted-foreground py-10 text-center">Chargement…</p>
          ) : detailRows.length === 0 ? (
            <p className="text-sm text-muted-foreground py-10 text-center">
              Aucune offre pour ce filtre.
            </p>
          ) : (
            <div className="overflow-x-auto -mx-1">
              <table className="w-full text-sm min-w-[720px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 px-2 font-medium">Client</th>
                    <th className="py-2 px-2 font-medium">Type d&apos;offre</th>
                    <th className="py-2 px-2 font-medium">Agent demandeur</th>
                    <th className="py-2 px-2 font-medium">Dates</th>
                    <th className="py-2 px-2 font-medium">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {detailRows.map((r) => {
                    const dates = relevantDates(r);
                    return (
                      <tr
                        key={r.id}
                        className="border-b border-border/70 hover:bg-secondary/40 cursor-pointer"
                        onClick={() => navigate(`/demandes-offres/${r.id}`)}
                      >
                        <td className="py-2.5 px-2 align-top">
                          {r.client_id ? (
                            <button
                              type="button"
                              className="text-[#002FA7] font-medium hover:underline text-left"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/clients/${r.client_id}`);
                              }}
                            >
                              {clientName(r)}
                            </button>
                          ) : (
                            <span className="font-medium">{clientName(r)}</span>
                          )}
                          {r.numero ? (
                            <p className="text-[11px] text-muted-foreground mt-0.5">{r.numero}</p>
                          ) : null}
                        </td>
                        <td className="py-2.5 px-2 align-top text-muted-foreground">{offerType(r)}</td>
                        <td className="py-2.5 px-2 align-top">
                          <span className="font-medium">{agentName(r)}</span>
                        </td>
                        <td className="py-2.5 px-2 align-top">
                          {dates.length === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <ul className="space-y-0.5 text-[11px] text-muted-foreground">
                              {dates.map((d) => (
                                <li key={d.label}>
                                  <span className="text-foreground/80">{d.label}</span>
                                  {" · "}
                                  {formatDateFr(d.value)}
                                </li>
                              ))}
                            </ul>
                          )}
                        </td>
                        <td className="py-2.5 px-2 align-top">
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${
                              STATUT_STYLE[r.statut] || "bg-slate-100 text-slate-700"
                            }`}
                          >
                            {r.statut || BROUILLON}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
