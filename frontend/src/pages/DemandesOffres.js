import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  COMPAGNIES_DEFAUT, DEMANDE_ORIGINE_FILTERS, DEMANDE_ORIGINE_STYLE,
  KANBAN_COLUMNS, PERIODE_FILTERS, STATUTS,
  TYPES_CLIENT, demandeOrigineKey, demandeOrigineLabel, demandeOrigineShort,
  formatChf, formatDateFr, formatVariantesSummary, periodeLabel,
} from "@/lib/demandesOffres";
import { uniqueConseillerNames } from "@/lib/conseillers";
import {
  BarChart3, Briefcase, CheckCircle2, Clock3, FilePlus2, FileSpreadsheet,
  FileText, Layers, Loader2, Mail, RotateCcw, Search, Signature, Tag, Trash2, TriangleAlert,
  UserRound, XCircle,
} from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const RED = "#C62828";
const RED_SOFT = "#F3C4C4";
const RED_BG = "#FFF7F7";
const NAVY = "#1e2a44";

/** Catalogue intranet — toujours affiché sur la page (pas de modal / bouton). */
const FALLBACK_MENU = {
  title: "Offres",
  families: [
    {
      id: "particulier",
      label: "Assurances particulier",
      icon: "person",
      sections: [
        {
          id: "pilier3",
          label: "Formulaires 3ème pilier",
          items: [
            { label: "3ème pilier", form_type: "pilier3" },
            { label: "3ème pilier parent-enfant", form_type: "pilier3_parent_enfant" },
            { label: "3ème pilier risque pur", form_type: "pilier3_risque_pur" },
          ],
        },
        {
          id: "choses",
          label: "Formulaires choses",
          items: [
            { label: "Bâtiment", form_type: "assurances_particulier" },
            { label: "RC seule", form_type: "menage_rc" },
            { label: "RC-Ménage", form_type: "menage_rc" },
            { label: "Motocycles", form_type: "motocycle" },
            { label: "Véhicule", form_type: "vehicule" },
            { label: "Véhicule plaques interchangeables", form_type: "voyage" },
            { label: "Attestation Véhicule uniquement", form_type: "attestation_vehicule" },
          ],
        },
        {
          id: "autres_particulier",
          label: "Autres assurances pour particulier",
          items: [
            { label: "Maladie (Non CICERO)", form_type: "pilier3_autre" },
            { label: "Animaux", form_type: "animaux" },
            { label: "LAA employée de maison", form_type: "laa_employee_maison" },
            { label: "Protection juridique privé", form_type: "protection_juridique_particulier" },
          ],
        },
      ],
    },
    {
      id: "professionnelles",
      label: "Assurances professionnelles",
      icon: "briefcase",
      notice:
        "Nous attirons votre attention sur le fait que le délai de retour pour toutes demandes d'offres professionnelles est au minimum de 5 jours. Ce délai n'est malheureusement pas de notre fait, nous sommes dépendants du temps de réponse des compagnies.",
      notice_highlight: "au minimum de 5 jours",
      sections: [
        {
          id: "complets",
          label: "Formulaires complets",
          items: [
            {
              label: "Entreprise COMPLET",
              subtitle: "RC pro, assurances choses et assurance de personnes employées",
              form_type: "entreprise",
            },
            {
              label: "Indépendant COMPLET",
              subtitle: "RC pro, PGM, LAAF et rente invalidité",
              form_type: "formulaire_complet",
            },
          ],
        },
        {
          id: "autres_pro",
          label: "Autres formulaires pro",
          items: [
            { label: "Assurance chef d'entreprise", form_type: "entreprise_31" },
            { label: "Assurance de personne employée", form_type: "entreprise_32" },
            { label: "La prévoyance professionnelle (LPP)", form_type: "entreprise_46" },
            { label: "LAAF / LAAC", form_type: "entreprise_28" },
            { label: "Perte de gain", form_type: "entreprise_27" },
            { label: "Rente invalidité", form_type: "entreprise_29" },
            { label: "Responsabilité civile", form_type: "rc_entreprise" },
            { label: "Assurances choses", form_type: "entreprise_33" },
            { label: "Véhicule entreprise", form_type: "entreprise_offres" },
            { label: "Véhicule entreprise plaques interchangeables", form_type: "entreprise_50" },
            { label: "Protection juridique ENTREPRISE", form_type: "protection_juridique_entreprise" },
            { label: "Protection juridique INDÉPENDANT", form_type: "protection_juridique_entreprise_2" },
          ],
        },
      ],
    },
  ],
};

/** Dashboard — cartes aérées, intitulés complets (pas de troncature). */
const KPI_FEATURED = [
  ["nb_origine_conseiller", "Demandes d'offre – Conseiller", UserRound, "bg-sky-100 text-sky-800"],
  ["nb_origine_attribuee", "Demandes d'offre attribuées", Tag, "bg-indigo-100 text-indigo-800"],
  ["nb_demandes", "Total des demandes", FileSpreadsheet, "bg-[#002FA7]/10 text-[#002FA7]"],
];

const KPI_SECONDARY = [
  ["nb_brouillons", "Brouillons", FilePlus2, "bg-zinc-100 text-zinc-700"],
  ["en_attente", "En attente", Clock3, "bg-amber-100 text-amber-800"],
  ["incompletes", "Incomplètes", TriangleAlert, "bg-rose-100 text-rose-700"],
  ["offres_recues", "Offres complètes", CheckCircle2, "bg-emerald-100 text-emerald-700"],
  ["nb_variantes_sollicitees", "Variantes sollicitées", Layers, "bg-indigo-100 text-indigo-800"],
  ["offres_signees", "Offres signées", CheckCircle2, "bg-emerald-100 text-emerald-700"],
  ["taux_signature", "Taux de signature", Signature, "bg-teal-100 text-teal-700"],
];

/**
 * Filtre appliqué au clic d'une carte KPI (aligné sur compute_stats backend).
 * kind: all | statut | statuts | variantes | has_offres | origine
 */
const KPI_CLICK_FILTERS = {
  nb_origine_conseiller: { kind: "origine", value: "conseiller", label: "Demandes d'offre – Conseiller" },
  nb_origine_attribuee: { kind: "origine", value: "attribuee", label: "Demandes d'offre attribuées" },
  nb_demandes: { kind: "all", label: "Toutes les demandes" },
  nb_brouillons: { kind: "statut", value: "Brouillon", label: "Brouillons" },
  nb_variantes_sollicitees: { kind: "variantes", label: "Variantes sollicitées" },
  en_attente: {
    kind: "statuts",
    values: ["Demande envoyée", "Demande validée", "En attente d'informations"],
    label: "En attente",
  },
  incompletes: {
    kind: "statuts",
    values: ["Demande incomplète", "En attente d'informations"],
    label: "Incomplètes",
  },
  offres_recues: {
    kind: "statuts",
    values: ["Offres complètes", "Offre complète"],
    label: "Offres complètes",
  },
  nb_offres_recues_detail: { kind: "has_offres", label: "Réponses comparées" },
  offres_signees: { kind: "statut", value: "Offre signée", label: "Offres signées" },
  taux_signature: { kind: "statut", value: "Offre signée", label: "Offres signées (taux)" },
};

function rowMatchesKpi(row, kpiKey) {
  const conf = KPI_CLICK_FILTERS[kpiKey];
  if (!conf) return true;
  const st = row?.statut || "Brouillon";
  if (conf.kind === "all") return true;
  if (conf.kind === "origine") return demandeOrigineKey(row?.demande_origine) === conf.value;
  if (conf.kind === "statut") return st === conf.value;
  if (conf.kind === "statuts") return (conf.values || []).includes(st);
  if (conf.kind === "variantes") {
    if (st === "Brouillon" || st === "Demande annulée") return false;
    const n = row?.nb_variantes_sollicitees ?? (row?.compagnies?.length || 0);
    return n > 0;
  }
  if (conf.kind === "has_offres") {
    const n = row?.nb_offres_recues_detail ?? (Array.isArray(row?.offres) ? row.offres.length : 0);
    if (n > 0) return true;
    return Boolean(row?.offre && typeof row.offre === "object");
  }
  return true;
}

function StatutBadge({ statut }) {
  return (
    <span
      className="inline-flex rounded-full px-3 py-1 text-xs font-medium border"
      style={{ borderColor: RED_SOFT, color: RED, background: RED_BG }}
    >
      {statut || "—"}
    </span>
  );
}

function OrigineBadge({ origine }) {
  const key = demandeOrigineKey(origine);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ${DEMANDE_ORIGINE_STYLE[key]}`}
      title={demandeOrigineLabel(key)}
    >
      {demandeOrigineShort(key)}
    </span>
  );
}

function KpiCard({ item, stats, active, onSelect, large = false }) {
  const [key, label, Icon, accent] = item;
  const raw = stats?.[key]
    ?? (key === "nb_origine_conseiller" ? stats?.nb_demandes_conseiller : undefined)
    ?? (key === "nb_origine_attribuee" ? stats?.nb_demandes_attribuees : undefined)
    ?? (key === "nb_demandes" ? stats?.total : undefined);
  const clickable = Boolean(KPI_CLICK_FILTERS[key]);
  return (
    <button
      type="button"
      onClick={() => clickable && onSelect?.(key)}
      disabled={!clickable}
      data-testid={`demandes-offres-kpi-${key}`}
      aria-pressed={active}
      title={clickable ? `Afficher : ${KPI_CLICK_FILTERS[key]?.label || label}` : undefined}
      className={`w-full text-left rounded-2xl border shadow-none transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#002FA7]/40 ${
        large ? "px-5 py-5" : "px-4 py-4"
      } ${
        active
          ? "border-[#002FA7] bg-[#002FA7]/5 ring-1 ring-[#002FA7]/30"
          : "border-border/70 bg-card hover:border-[#002FA7]/50 hover:bg-[#002FA7]/5 hover:shadow-sm cursor-pointer"
      } ${clickable ? "" : "opacity-80 cursor-default"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className={`font-medium text-muted-foreground leading-snug ${large ? "text-sm" : "text-xs"}`}>
            {label}
          </p>
          <p className={`font-display font-bold tabular-nums leading-none mt-2 ${large ? "text-3xl" : "text-2xl"}`}>
            {key === "taux_signature" ? `${raw ?? 0} %` : (raw ?? "—")}
          </p>
        </div>
        <span className={`rounded-xl flex items-center justify-center shrink-0 ${accent} ${large ? "h-11 w-11" : "h-9 w-9"}`}>
          <Icon className={large ? "h-5 w-5" : "h-4 w-4"} />
        </span>
      </div>
    </button>
  );
}

function SectionTitle({ children }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className="text-sm leading-none" style={{ color: "#1d4ed8" }}>◆</span>
      <h3 className="font-semibold text-base" style={{ color: NAVY }}>{children}</h3>
    </div>
  );
}

function FamilyPill({ icon: Icon, children }) {
  return (
    <div
      className="inline-flex items-center gap-2.5 rounded-full border bg-white px-4 py-2 mb-4"
      style={{ borderColor: RED_SOFT }}
    >
      <Icon className="h-5 w-5 shrink-0" style={{ color: RED }} strokeWidth={1.75} />
      <span className="font-semibold text-base" style={{ color: NAVY }}>{children}</span>
    </div>
  );
}

function renderNotice(notice, highlight) {
  if (!highlight || !notice.includes(highlight)) return notice;
  const [before, after] = notice.split(highlight);
  return (
    <>
      {before}
      <span className="underline font-medium" style={{ color: RED }}>{highlight}</span>
      {after}
    </>
  );
}

export default function DemandesOffres({ mode = "conseiller" }) {
  const isGestion = mode === "gestion";
  const navigate = useNavigate();
  const location = useLocation();
  const { hasPerm, isGlobal, isAdmin } = useAuth();
  const canEdit = hasPerm("demandes_offres.edit");
  const canProcess = hasPerm("demandes_offres.process");
  const listSectionRef = useRef(null);
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState(null);
  const [formTypes, setFormTypes] = useState([]);
  const [formMenu, setFormMenu] = useState(null);
  const [loading, setLoading] = useState(true);
  const [creatingKey, setCreatingKey] = useState(null);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [mainTab, setMainTab] = useState("tableau");
  const urlParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const initialStatut = useMemo(() => {
    const s = (urlParams.get("statut") || "").trim();
    return s && STATUTS.includes(s) ? s : "all";
  }, [urlParams]);
  const initialKpi = useMemo(() => {
    const k = (urlParams.get("kpi") || "").trim();
    return KPI_CLICK_FILTERS[k] ? k : null;
  }, [urlParams]);
  const [statut, setStatut] = useState(initialStatut);
  const [kpiFilter, setKpiFilter] = useState(initialKpi);
  const [conseiller, setConseiller] = useState("all");
  const [formTypeFilter, setFormTypeFilter] = useState("all");
  const [compagnie, setCompagnie] = useState("all");
  const [periode, setPeriode] = useState("all");
  const [origine, setOrigine] = useState("all");
  const [dateDe, setDateDe] = useState("");
  const [dateA, setDateA] = useState("");
  const [expandedAgent, setExpandedAgent] = useState(null);
  const [createTypeOpen, setCreateTypeOpen] = useState(false);
  const [pendingCreate, setPendingCreate] = useState(null);
  const [createTypeClient, setCreateTypeClient] = useState("");
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelComment, setCancelComment] = useState("");
  const [cancelBusy, setCancelBusy] = useState(false);
  const [resendTarget, setResendTarget] = useState(null);
  const [resendBusy, setResendBusy] = useState(false);
  const [mesErreurs, setMesErreurs] = useState(null);

  useEffect(() => {
    setStatut(initialStatut);
    setKpiFilter(initialKpi);
  }, [initialStatut, initialKpi]);

  useEffect(() => {
    const timer = setTimeout(() => setQDebounced(q.trim()), 250);
    return () => clearTimeout(timer);
  }, [q]);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get("/demandes-offres/meta");
        setFormTypes(res.data?.form_types || []);
        setFormMenu(res.data?.form_menu || null);
      } catch {
        setFormTypes([]);
        setFormMenu(null);
      }
    })();
  }, []);

  const syncUrl = useCallback((nextStatut, nextKpi) => {
    const params = new URLSearchParams(location.search);
    if (nextKpi && KPI_CLICK_FILTERS[nextKpi]) {
      params.set("kpi", nextKpi);
      params.delete("statut");
    } else {
      params.delete("kpi");
      if (nextStatut && nextStatut !== "all") params.set("statut", nextStatut);
      else params.delete("statut");
    }
    const qs = params.toString();
    navigate({ pathname: location.pathname, search: qs ? `?${qs}` : "" }, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (qDebounced) params.q = qDebounced;
      // Filtre serveur exact uniquement si KPI mono-statut ou filtre statut manuel
      const kpiConf = kpiFilter ? KPI_CLICK_FILTERS[kpiFilter] : null;
      if (kpiConf?.kind === "statut" && kpiConf.value) {
        params.statut = kpiConf.value;
      } else if (!kpiFilter && statut !== "all") {
        params.statut = statut;
      }
      if (isGlobal && conseiller !== "all") params.conseiller = conseiller;
      if (formTypeFilter !== "all") params.form_type = formTypeFilter;
      if (compagnie !== "all") params.compagnie = compagnie;
      if (origine !== "all") params.demande_origine = origine;
      if (periode && periode !== "all") {
        params.periode = periode;
        if (periode === "custom") {
          if (dateDe) params.date_de = dateDe;
          if (dateA) params.date_a = dateA;
        }
      }
      const statsParams = { ...params };
      // Stats globales de période (sans filtre KPI) pour garder les cartes cohérentes
      delete statsParams.statut;
      if (isGlobal && conseiller !== "all" && !statsParams.conseiller) {
        statsParams.conseiller = conseiller;
      }
      const [listRes, statsRes, errAgentRes] = await Promise.all([
        api.get("/demandes-offres", { params }),
        api.get("/demandes-offres/stats", { params: statsParams }),
        api.get("/demandes-offres/stats/erreurs-agent", { params: statsParams }).catch(() => ({ data: null })),
      ]);
      setRows(listRes.data || []);
      setStats(statsRes.data || {});
      setMesErreurs(errAgentRes.data || null);
    } catch (e) {
      setRows([]);
      toast.error(e?.response?.data?.detail || "Chargement des demandes impossible");
    } finally {
      setLoading(false);
    }
  }, [qDebounced, statut, kpiFilter, conseiller, formTypeFilter, compagnie, origine, periode, dateDe, dateA, isGlobal]);

  useEffect(() => { load(); }, [load]);

  const selectKpi = useCallback((key) => {
    const conf = KPI_CLICK_FILTERS[key];
    if (!conf) return;
    const nextKpi = kpiFilter === key ? null : key;
    const nextConf = nextKpi ? KPI_CLICK_FILTERS[nextKpi] : null;
    let nextStatut = "all";
    if (nextConf?.kind === "statut") nextStatut = nextConf.value;
    setKpiFilter(nextKpi);
    setStatut(nextStatut);
    if (nextConf?.kind === "origine") setOrigine(nextConf.value);
    else if (conf.kind === "origine") setOrigine("all");
    setMainTab("tableau");
    syncUrl(nextStatut, nextKpi);
    requestAnimationFrame(() => {
      listSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [kpiFilter, syncUrl]);

  const selectOrigineFilter = useCallback((value) => {
    setOrigine(value);
    if (value === "conseiller") {
      setKpiFilter("nb_origine_conseiller");
      syncUrl("all", "nb_origine_conseiller");
    } else if (value === "attribuee") {
      setKpiFilter("nb_origine_attribuee");
      syncUrl("all", "nb_origine_attribuee");
    } else {
      if (kpiFilter && KPI_CLICK_FILTERS[kpiFilter]?.kind === "origine") {
        setKpiFilter(null);
        syncUrl("all", null);
      }
    }
    setStatut("all");
    setMainTab("tableau");
  }, [kpiFilter, syncUrl]);

  const onStatutChange = useCallback((value) => {
    setStatut(value);
    setKpiFilter(null);
    syncUrl(value, null);
  }, [syncUrl]);

  const conseillers = useMemo(
    () => uniqueConseillerNames(rows.map((r) => r.agent_label)),
    [rows],
  );

  const filteredRows = useMemo(() => {
    if (!kpiFilter) return rows;
    const conf = KPI_CLICK_FILTERS[kpiFilter];
    if (!conf || conf.kind === "statut") return rows;
    return rows.filter((r) => rowMatchesKpi(r, kpiFilter));
  }, [rows, kpiFilter]);

  const byStatus = useMemo(
    () => KANBAN_COLUMNS.map((name) => ({
      name,
      rows: filteredRows.filter((r) => r.statut === name),
      total: stats?.by_statut?.[name] || 0,
    })),
    [filteredRows, stats],
  );

  const groupedRows = useMemo(() => {
    const order = [...KANBAN_COLUMNS, ...STATUTS.filter((s) => !KANBAN_COLUMNS.includes(s))];
    const map = new Map();
    for (const name of order) map.set(name, []);
    for (const r of filteredRows) {
      const key = r.statut || "Brouillon";
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(r);
    }
    return [...map.entries()].filter(([, list]) => list.length > 0);
  }, [filteredRows]);

  const startForm = async (item, sectionId) => {
    if (!canEdit) {
      toast.error("Vous n'avez pas le droit de créer une demande");
      return;
    }
    if (item.coming_soon || !item.form_type) {
      toast.message("Formulaire bientôt disponible", { description: item.label });
      return;
    }
    setPendingCreate({ item, sectionId });
    setCreateTypeClient("");
    setCreateTypeOpen(true);
  };

  const confirmCreate = async () => {
    if (!pendingCreate) return;
    const { item, sectionId } = pendingCreate;
    const key = `${sectionId}-${item.label}`;
    setCreatingKey(key);
    setCreateTypeOpen(false);
    try {
      const body = {
        form_type: item.form_type,
        form_type_label: item.label,
      };
      if (createTypeClient) body.type_client = createTypeClient;
      const res = await api.post("/demandes-offres", body);
      navigate(`/demandes-offres/${res.data.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Création impossible");
    } finally {
      setCreatingKey(null);
      setPendingCreate(null);
      setCreateTypeClient("");
    }
  };

  const clearFilters = () => {
    setQ("");
    setStatut("all");
    setKpiFilter(null);
    setConseiller("all");
    setFormTypeFilter("all");
    setCompagnie("all");
    setOrigine("all");
    setPeriode("all");
    setDateDe("");
    setDateA("");
    syncUrl("all", null);
  };

  const deleteBrouillon = async (r, event) => {
    event?.stopPropagation?.();
    event?.preventDefault?.();
    if (!(canEdit || canProcess)) return;
    if (!["Brouillon", "Demande annulée"].includes(r.statut)) return;
    const label = r.statut === "Brouillon" ? "brouillon" : "demande annulée";
    if (!window.confirm(`Supprimer définitivement le ${label} ${r.numero} ?`)) return;
    try {
      await api.delete(`/demandes-offres/${r.id}`);
      toast.success("Demande supprimée");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suppression impossible");
    }
  };

  const openCancel = (r, event) => {
    event?.stopPropagation?.();
    event?.preventDefault?.();
    if (!(canEdit || canProcess)) return;
    if (["Offre signée", "Demande annulée"].includes(r.statut)) return;
    setCancelTarget(r);
    setCancelComment("");
  };

  const confirmCancel = async () => {
    if (!cancelTarget) return;
    setCancelBusy(true);
    try {
      await api.post(`/demandes-offres/${cancelTarget.id}/annuler`, {
        commentaire: cancelComment.trim() || null,
      });
      toast.success("Offre / demande annulée");
      setCancelTarget(null);
      setCancelComment("");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Annulation impossible");
    } finally {
      setCancelBusy(false);
    }
  };

  const restoreDemande = async (r, event) => {
    event?.stopPropagation?.();
    event?.preventDefault?.();
    if (!(canEdit || canProcess)) return;
    if (r.statut !== "Demande annulée") return;
    try {
      await api.post(`/demandes-offres/${r.id}/restaurer`);
      toast.success("Demande restaurée");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Restauration impossible");
    }
  };

  const openResend = (r, event) => {
    event?.stopPropagation?.();
    event?.preventDefault?.();
    if (!isAdmin) return;
    if (r.statut !== "Demande envoyée") return;
    setResendTarget(r);
  };

  const confirmResend = async () => {
    if (!resendTarget) return;
    setResendBusy(true);
    try {
      await api.post(`/demandes-offres/${resendTarget.id}/renvoyer`);
      toast.success("Offre renvoyée avec succès");
      setResendTarget(null);
      await load();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const msg = typeof detail === "string"
        ? detail
        : detail?.message || "Renvoi impossible";
      toast.error(msg);
    } finally {
      setResendBusy(false);
    }
  };

  const typeLabel = (r) => r.form_type_label || r.type_pilier || "—";
  const filterActive = statut !== "all" || Boolean(kpiFilter) || conseiller !== "all" || formTypeFilter !== "all"
    || compagnie !== "all" || origine !== "all" || Boolean(q) || periode !== "all";
  const agentRows = stats?.by_agent || [];
  const chartAgents = stats?.chart_agents || [];
  const families = (formMenu?.families?.length ? formMenu.families : FALLBACK_MENU.families);
  const activeKpiLabel = kpiFilter ? KPI_CLICK_FILTERS[kpiFilter]?.label : null;

  return (
    <Layout>
      <div className="animate-fade-up max-w-6xl space-y-6 pb-10" data-testid="demandes-offres-page">
        {/* 1. En-tête */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-800 flex items-center gap-3">
            <FileSpreadsheet className="h-8 w-8" style={{ color: RED }} strokeWidth={1.75} />
            {isGestion ? "Gestion des réponses aux offres" : "Demandes d'offres"}
          </h1>
          <p className="text-base text-slate-500 mt-2 max-w-3xl leading-relaxed">
            {isGestion
              ? "Traitez les demandes envoyées par les conseillers : offres complètes, incomplètes et documents."
              : "Deux types de demandes : celles créées par le conseiller, et celles attribuées par le service Offre. Créez, suivez et consultez l'historique complet."}
          </p>
          {isGestion && !canProcess && (
            <p className="text-sm text-rose-700 mt-2">Accès réservé aux gestionnaires d&apos;offres.</p>
          )}
        </div>

        {/* 2. Période */}
        <Card className="p-5 border-border/80 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">Période d&apos;analyse</p>
              <p className="text-sm text-muted-foreground mt-1">
                {periode === "all"
                  ? "Toutes les demandes"
                  : periode === "custom" && dateDe
                    ? `Du ${formatDateFr(dateDe)} au ${formatDateFr(dateA || dateDe)}`
                    : periodeLabel(periode)}
              </p>
            </div>
            {filterActive && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                Réinitialiser tout
              </Button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {PERIODE_FILTERS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPeriode(p.id)}
                className={`text-sm px-3.5 py-2 rounded-xl transition-colors ${
                  periode === p.id
                    ? "bg-[#002FA7] text-white font-medium shadow-sm"
                    : "bg-secondary/80 text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`}
                data-testid={`demandes-offres-periode-${p.id}`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {periode === "custom" && (
            <div className="flex flex-wrap items-end gap-3 pt-1">
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Du</Label>
                <Input type="date" value={dateDe} onChange={(e) => setDateDe(e.target.value)} className="h-11 w-44" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-sm text-muted-foreground">Au</Label>
                <Input type="date" value={dateA} onChange={(e) => setDateA(e.target.value)} className="h-11 w-44" />
              </div>
            </div>
          )}
        </Card>

        {/* 3. KPI types + secondaires */}
        <div className="space-y-3">
          <div>
            <h2 className="text-lg font-bold text-slate-800">Tableau de bord</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Cliquez sur une carte pour filtrer la liste. Les deux types de demandes sont comptés séparément.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {KPI_FEATURED.map((item) => (
              <KpiCard
                key={item[0]}
                item={item}
                stats={stats}
                active={kpiFilter === item[0] || (item[0] === "nb_origine_conseiller" && origine === "conseiller" && !kpiFilter)}
                onSelect={selectKpi}
                large
              />
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {KPI_SECONDARY.map((item) => (
              <KpiCard
                key={item[0]}
                item={item}
                stats={stats}
                active={kpiFilter === item[0]}
                onSelect={selectKpi}
              />
            ))}
          </div>
          {!canProcess && (mesErreurs?.total > 0 || (mesErreurs?.by_agent || []).length > 0) && (
            <Card className="p-4 border-rose-200 bg-rose-50/40" data-testid="mes-erreurs-offres">
              <p className="text-sm font-semibold text-rose-900">
                Erreurs sur demandes d&apos;offres : {(mesErreurs.by_agent?.[0]?.total ?? mesErreurs.total) || 0}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {(mesErreurs.by_agent?.[0]?.by_field || []).map((f) => (
                  <span key={f.code} className="inline-flex rounded-md bg-white border border-rose-200 px-2 py-1 text-xs text-rose-900">
                    {f.label} : {f.count}
                  </span>
                ))}
              </div>
            </Card>
          )}
        </div>

        {/* 4. Formulaires — aérés */}
        {!isGestion && (
        <section aria-label="Choisir un formulaire" className="space-y-4">
          <div>
            <h2 className="text-lg font-bold text-slate-800">Choisir un formulaire</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Crée une <strong>demande d&apos;offre – Conseiller</strong> destinée au service Offre.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
            {families.map((family) => {
              const Icon = family.icon === "briefcase" ? Briefcase : UserRound;
              return (
                <div
                  key={family.id}
                  className="rounded-2xl border bg-white px-5 py-5"
                  style={{ borderColor: RED_SOFT }}
                >
                  <FamilyPill icon={Icon}>{family.label}</FamilyPill>

                  {family.notice && (
                    <p className="text-sm text-slate-600 leading-relaxed mb-4">
                      {renderNotice(family.notice, family.notice_highlight)}
                    </p>
                  )}

                  <div className="space-y-5">
                    {(family.sections || []).map((section) => (
                      <div key={section.id}>
                        <SectionTitle>{section.label}</SectionTitle>
                        <ul className="space-y-1.5">
                          {(section.items || []).map((item) => {
                            const unavailable = Boolean(item.coming_soon || !item.form_type);
                            const key = `${section.id}-${item.label}`;
                            const busy = creatingKey === key;
                            return (
                              <li key={key}>
                                <button
                                  type="button"
                                  disabled={unavailable || !canEdit || Boolean(creatingKey)}
                                  onClick={() => startForm(item, section.id)}
                                  className={`w-full text-left flex items-start gap-3 rounded-xl px-3 py-3 transition ${
                                    unavailable ? "opacity-45 cursor-not-allowed" : "hover:bg-[#FFF7F7]"
                                  }`}
                                >
                                  {busy
                                    ? <Loader2 className="h-5 w-5 shrink-0 mt-0.5 animate-spin text-slate-400" />
                                    : <FileText className="h-5 w-5 shrink-0 mt-0.5 text-slate-400" />}
                                  <span className="min-w-0">
                                    <span
                                      className="block text-base font-semibold leading-snug"
                                      style={{ color: unavailable ? "#94a3b8" : RED }}
                                    >
                                      {item.label}
                                      {unavailable ? " (bientôt)" : ""}
                                    </span>
                                    {item.subtitle && (
                                      <span className="block text-sm text-slate-500 leading-snug mt-0.5">
                                        {item.subtitle}
                                      </span>
                                    )}
                                  </span>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
        )}

        {/* 5. Demandes existantes */}
        <section
          ref={listSectionRef}
          id="demandes-en-cours"
          className="space-y-4 pt-2 border-t border-slate-100 scroll-mt-4"
          aria-label="Demandes en cours"
        >
          <div>
            <h2 className="text-lg font-bold text-slate-800">
              {isGestion ? "Toutes les demandes à traiter" : "Mon historique des demandes d'offres"}
            </h2>
            <p className="text-sm text-slate-500 mt-1">
              {isGestion
                ? "Vue gestionnaire : toutes les demandes de tous les conseillers."
                : "Filtrez par type de demande, statut ou formulaire. Une demande ≠ une variante."}
            </p>
          </div>

          {/* Filtre type de demande — prioritaire */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2" data-testid="demandes-offres-origine-filter">
            {DEMANDE_ORIGINE_FILTERS.map((f) => {
              const active = origine === f.id;
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => selectOrigineFilter(f.id)}
                  className={`rounded-2xl border px-4 py-3.5 text-left transition ${
                    active
                      ? "border-[#002FA7] bg-[#002FA7]/5 ring-1 ring-[#002FA7]/25"
                      : "border-border/70 bg-white hover:border-[#002FA7]/40"
                  }`}
                >
                  <span className="block text-sm font-semibold text-slate-900">{f.label}</span>
                  {f.id !== "all" && (
                    <span className="block text-xs text-muted-foreground mt-1 leading-snug">
                      {f.id === "conseiller"
                        ? "Créée par le conseiller pour le service Offre"
                        : "Créée par le service Offre pour un conseiller"}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <Card className="p-5 border-border/80 space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              <div className="relative sm:col-span-2 lg:col-span-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="N°, client, agent…" className="pl-9 h-11" />
              </div>
              <FilterSelect value={statut} onChange={onStatutChange} placeholder="Statut" options={STATUTS} />
              {isGlobal && <FilterSelect value={conseiller} onChange={setConseiller} placeholder="Conseiller" options={conseillers} />}
              <Select value={formTypeFilter} onValueChange={setFormTypeFilter}>
                <SelectTrigger className="h-11"><SelectValue placeholder="Type de formulaire" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tous les types de formulaire</SelectItem>
                  {formTypes.map((ft) => (
                    <SelectItem key={ft.id} value={ft.id}>{ft.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FilterSelect value={compagnie} onChange={setCompagnie} placeholder="Compagnie" options={COMPAGNIES_DEFAUT} />
            </div>
            {(filterActive || activeKpiLabel) && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                {activeKpiLabel ? (
                  <p className="text-sm text-[#002FA7] font-medium" data-testid="demandes-offres-kpi-active">
                    Filtre actif : {activeKpiLabel}
                    {filteredRows.length !== rows.length ? ` · ${filteredRows.length} résultat(s)` : ""}
                  </p>
                ) : <span />}
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  Réinitialiser les filtres
                </Button>
              </div>
            )}
          </Card>

          <Tabs value={mainTab} onValueChange={setMainTab}>
            <TabsList>
              <TabsTrigger value="tableau">Tableau</TabsTrigger>
              <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
              <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
            </TabsList>

            <TabsContent value="tableau" className="mt-4">
              <div
                className="rounded-[24px] border bg-white px-4 py-4 sm:px-5"
                style={{ borderColor: RED_SOFT }}
              >
                {loading ? <Loading /> : filteredRows.length === 0 ? <Empty /> : (
                  <div className="space-y-6">
                    {groupedRows.map(([sectionStatut, list]) => (
                      <div key={sectionStatut}>
                        <SectionTitle>
                          {sectionStatut}
                          <span className="ml-2 text-xs font-normal text-slate-400">({list.length})</span>
                        </SectionTitle>
                        <ul className="space-y-0.5">
                          {list.map((r) => (
                            <li key={r.id} className="flex items-start gap-1 group/row">
                              <button
                                type="button"
                                onClick={() => navigate(`/demandes-offres/${r.id}`)}
                                className="flex-1 text-left flex items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-[#FFF7F7] transition group"
                              >
                                <FileText className="h-4 w-4 mt-0.5 shrink-0 text-slate-400" />
                                <span className="min-w-0 flex-1">
                                  <span className="block text-base font-semibold group-hover:underline" style={{ color: RED }}>
                                    {r.client_label !== "—" ? r.client_label : "Nouvelle demande"}
                                    <span className="font-normal text-slate-400"> · {r.numero}</span>
                                  </span>
                                  <span className="block text-sm text-slate-500 mt-1">
                                    {typeLabel(r)}
                                    {(r.compagnies || []).length
                                      ? ` · ${(r.compagnies || []).slice(0, 3).join(", ")}${(r.compagnies || []).length > 3 ? "…" : ""}`
                                      : ""}
                                    {r.montant_prime != null && r.montant_prime !== "" ? ` · ${formatChf(r.montant_prime)}` : ""}
                                    {r.agent_label ? ` · ${r.agent_label}` : ""}
                                    {r.date_envoi
                                      ? ` · Envoyée le ${formatDateFr(r.date_envoi)}`
                                      : ` · ${formatDateFr(r.updated_at)}`}
                                  </span>
                                  {r.commentaires ? (
                                    <span className="block text-xs text-slate-400 mt-0.5 line-clamp-1">
                                      Note : {r.commentaires}
                                    </span>
                                  ) : null}
                                </span>
                              </button>
                              <span className="flex flex-col items-end shrink-0 gap-1 pt-2">
                                <OrigineBadge origine={r.demande_origine} />
                                <span className="flex items-center gap-1.5 flex-wrap justify-end">
                                  <StatutBadge statut={r.statut} />
                                  {isAdmin && r.statut === "Demande envoyée" && (
                                    <button
                                      type="button"
                                      title="Renvoyer l'offre"
                                      onClick={(e) => openResend(r, e)}
                                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-[#002FA7] hover:bg-sky-50 border border-[#002FA7]/20"
                                      data-testid="renvoyer-offre-list-btn"
                                    >
                                      <Mail className="h-3.5 w-3.5" />
                                      Renvoyer l&apos;offre
                                    </button>
                                  )}
                                </span>
                                <span className="flex flex-row gap-0.5">
                                {(canEdit || canProcess) && r.statut === "Demande annulée" && (
                                  <button
                                    type="button"
                                    title="Restaurer la demande"
                                    onClick={(e) => restoreDemande(r, e)}
                                    className="p-1.5 rounded-md text-slate-400 hover:text-[#002FA7] hover:bg-sky-50 opacity-70 group-hover/row:opacity-100"
                                    data-testid="restore-demande-list-btn"
                                  >
                                    <RotateCcw className="h-4 w-4" />
                                  </button>
                                )}
                                {(canEdit || canProcess) && !["Offre signée", "Demande annulée"].includes(r.statut) && (
                                  <button
                                    type="button"
                                    title="Annuler l'offre"
                                    onClick={(e) => openCancel(r, e)}
                                    className="p-1.5 rounded-md text-slate-400 hover:text-rose-700 hover:bg-rose-50 opacity-70 group-hover/row:opacity-100"
                                  >
                                    <XCircle className="h-4 w-4" />
                                  </button>
                                )}
                                {(canEdit || canProcess) && ["Brouillon", "Demande annulée"].includes(r.statut) && (
                                  <button
                                    type="button"
                                    title={r.statut === "Brouillon" ? "Supprimer le brouillon" : "Supprimer définitivement"}
                                    onClick={(e) => deleteBrouillon(r, e)}
                                    className="p-1.5 rounded-md text-slate-400 hover:text-rose-700 hover:bg-rose-50 opacity-70 group-hover/row:opacity-100"
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </button>
                                )}
                                </span>
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="pipeline" className="mt-4">
              {loading ? <Loading /> : (
                <div className="overflow-x-auto pb-2">
                  <div className="flex gap-3 min-w-max">
                    {byStatus.map((column) => (
                      <div
                        key={column.name}
                        className="w-72 rounded-2xl border bg-white p-3"
                        style={{ borderColor: RED_SOFT }}
                      >
                        <div className="flex items-center justify-between gap-2 mb-3">
                          <StatutBadge statut={column.name} />
                          <span className="text-xs font-semibold text-muted-foreground">{column.total}</span>
                        </div>
                        <div className="space-y-1">
                          {column.rows.map((r) => (
                            <button
                              key={r.id}
                              type="button"
                              onClick={() => navigate(`/demandes-offres/${r.id}`)}
                              className="w-full text-left rounded-lg border border-transparent px-2 py-2 hover:bg-[#FFF7F7] hover:border-[#F3C4C4]"
                            >
                              <p className="text-sm font-medium" style={{ color: RED }}>{r.client_label}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">{typeLabel(r)}</p>
                              <div className="mt-1.5"><OrigineBadge origine={r.demande_origine} /></div>
                              <p className="text-sm font-bold mt-1.5 text-slate-800">{formatChf(r.montant_prime)}</p>
                            </button>
                          ))}
                          {!column.rows.length && (
                            <p className="text-xs text-muted-foreground text-center py-5">Aucune demande</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent value="dashboard" className="mt-4 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Card className="p-5 border-sky-200 bg-sky-50/40">
                  <p className="text-sm font-medium text-sky-900">Demandes d&apos;offre – Conseiller</p>
                  <p className="font-display font-bold text-4xl mt-2 tabular-nums text-sky-950">
                    {stats?.nb_origine_conseiller ?? stats?.nb_demandes_conseiller ?? "—"}
                  </p>
                  <p className="text-sm text-sky-800/80 mt-2 leading-snug">
                    Créées par les conseillers pour le service Offre.
                  </p>
                </Card>
                <Card className="p-5 border-indigo-200 bg-indigo-50/40">
                  <p className="text-sm font-medium text-indigo-900">Demandes d&apos;offre attribuées</p>
                  <p className="font-display font-bold text-4xl mt-2 tabular-nums text-indigo-950">
                    {stats?.nb_origine_attribuee ?? stats?.nb_demandes_attribuees ?? "—"}
                  </p>
                  <p className="text-sm text-indigo-800/80 mt-2 leading-snug">
                    Créées par le service Offre pour un conseiller.
                  </p>
                </Card>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card className="p-5">
                  <div className="flex items-center gap-2 mb-4">
                    <BarChart3 className="h-5 w-5 text-[#002FA7]" />
                    <h3 className="font-display font-bold text-lg">Activité par agent</h3>
                  </div>
                  {chartAgents.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-8 text-center">Aucune donnée pour cette période.</p>
                  ) : (
                    <div className="h-72 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartAgents} margin={{ top: 8, right: 8, left: 0, bottom: 48 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="agent" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={60} />
                          <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                          <Tooltip />
                          <Legend />
                          <Bar dataKey="demandes" name="Demandes" fill="#002FA7" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="variantes" name="Variantes sollicitées" fill="#6366f1" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </Card>

                <Card className="p-5">
                  <div className="flex items-center gap-2 mb-4">
                    <Layers className="h-5 w-5 text-indigo-600" />
                    <h3 className="font-display font-bold text-lg">Répartition du pipeline</h3>
                  </div>
                  <div className="space-y-3">
                    {byStatus.map((column) => {
                      const count = stats?.by_statut?.[column.name] || 0;
                      const base = stats?.nb_demandes ?? stats?.total ?? 0;
                      const pct = Math.round((count / Math.max(1, base)) * 100);
                      return (
                        <div key={column.name}>
                          <div className="flex justify-between text-xs mb-1">
                            <span>{column.name}</span>
                            <span>{count} · {pct}%</span>
                          </div>
                          <div className="h-2 bg-secondary rounded-full overflow-hidden">
                            <div className="h-full bg-[#002FA7] rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              </div>

              <Card className="p-5 overflow-x-auto">
                <div className="flex items-center gap-2 mb-4">
                  <UserRound className="h-5 w-5 text-[#002FA7]" />
                  <h3 className="font-display font-bold text-lg">Statistiques par agent</h3>
                </div>
                {agentRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-6 text-center">Aucune statistique agent pour cette période.</p>
                ) : (
                  <table className="w-full text-sm min-w-[720px]" data-testid="demandes-offres-agent-stats">
                    <thead>
                      <tr className="border-b text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                        <th className="py-2 pr-3 font-medium">Agent</th>
                        <th className="py-2 px-3 font-medium text-right">Demandes</th>
                        <th className="py-2 px-3 font-medium text-right">Variantes</th>
                        <th className="py-2 px-3 font-medium text-right">Réponses</th>
                        <th className="py-2 pl-3 font-medium">Détail</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agentRows.map((a) => (
                        <React.Fragment key={a.agent}>
                          <tr className="border-b border-border/50 hover:bg-secondary/30">
                            <td className="py-2.5 pr-3 font-medium">{a.agent}</td>
                            <td className="py-2.5 px-3 text-right tabular-nums">{a.nb_demandes}</td>
                            <td className="py-2.5 px-3 text-right tabular-nums text-indigo-700">{a.nb_variantes_sollicitees}</td>
                            <td className="py-2.5 px-3 text-right tabular-nums">{a.nb_offres_recues}</td>
                            <td className="py-2.5 pl-3">
                              <button
                                type="button"
                                className="text-xs text-[#002FA7] hover:underline"
                                onClick={() => setExpandedAgent((prev) => (prev === a.agent ? null : a.agent))}
                              >
                                {expandedAgent === a.agent ? "Masquer" : "Voir détail"}
                              </button>
                            </td>
                          </tr>
                          {expandedAgent === a.agent && (
                            <tr className="bg-secondary/20">
                              <td colSpan={5} className="py-3 px-2">
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                                  <BucketList title="Par type d'offre" buckets={a.by_form_type} />
                                  <BucketList title="Par catégorie" buckets={a.by_category} />
                                  <BucketList title="Compagnies sollicitées" buckets={a.by_compagnie} />
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                )}
              </Card>

              {(stats?.by_category && Object.keys(stats.by_category).length > 0) && (
                <Card className="p-5">
                  <h3 className="font-display font-bold text-base mb-3">Vue globale par catégorie</h3>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(stats.by_category)
                      .sort((a, b) => b[1] - a[1])
                      .map(([cat, n]) => (
                        <span key={cat} className="text-xs rounded-full border px-2.5 py-1 bg-white">
                          {cat} · <strong>{n}</strong>
                        </span>
                      ))}
                  </div>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </section>
      </div>

      <Dialog open={Boolean(cancelTarget)} onOpenChange={(open) => {
        if (!open) {
          setCancelTarget(null);
          setCancelComment("");
        }
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Annuler cette offre / demande ?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {cancelTarget
              ? `${cancelTarget.numero || ""} — ${cancelTarget.client_label || "Demande"}`.trim()
              : ""}
            {" "}passera au statut « Demande annulée ». Toutes les données sont conservées ;
            vous pourrez ensuite la restaurer en brouillon, ou la supprimer définitivement.
          </p>
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground">Motif (optionnel)</Label>
            <Textarea
              rows={3}
              value={cancelComment}
              onChange={(e) => setCancelComment(e.target.value)}
              placeholder="Ex. : client n'est plus intéressé, doublon…"
            />
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => { setCancelTarget(null); setCancelComment(""); }}>
              Retour
            </Button>
            <Button className="bg-rose-700 hover:bg-rose-800" onClick={confirmCancel} disabled={cancelBusy}>
              {cancelBusy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Confirmer l&apos;annulation
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(resendTarget)} onOpenChange={(open) => {
        if (!open && !resendBusy) setResendTarget(null);
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Renvoyer l&apos;offre</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {resendTarget
              ? `${resendTarget.numero || ""} — ${resendTarget.client_label || "Demande"}`.trim()
              : ""}
          </p>
          <p className="text-sm text-slate-700">
            Voulez-vous vraiment renvoyer cette offre avec les informations actuellement enregistrées ?
          </p>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setResendTarget(null)} disabled={resendBusy}>
              Annuler
            </Button>
            <Button className="bg-[#002FA7] hover:bg-[#00248a]" onClick={confirmResend} disabled={resendBusy}>
              {resendBusy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Mail className="h-4 w-4 mr-2" />}
              Renvoyer l&apos;offre
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={createTypeOpen} onOpenChange={(open) => {
        setCreateTypeOpen(open);
        if (!open) {
          setPendingCreate(null);
          setCreateTypeClient("");
        }
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Type de client</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {pendingCreate?.item?.label
              ? `Création de « ${pendingCreate.item.label} » — indiquez le type de client.`
              : "Indiquez le type de client pour cette demande."}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
            {TYPES_CLIENT.map((opt) => {
              const active = createTypeClient === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setCreateTypeClient(opt.id)}
                  className={`rounded-md border px-3 py-2.5 text-sm text-left transition ${
                    active
                      ? "border-[#002FA7] bg-[#002FA7]/5 text-[#002FA7] font-semibold ring-1 ring-[#002FA7]/30"
                      : "border-border hover:border-[#002FA7]/40"
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => { setCreateTypeOpen(false); setPendingCreate(null); }}>
              Annuler
            </Button>
            <Button
              onClick={confirmCreate}
              disabled={!createTypeClient || Boolean(creatingKey)}
              className="bg-[#002FA7] hover:bg-[#00248a]"
            >
              {creatingKey ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Créer la demande
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}

function FilterSelect({ value, onChange, placeholder, options }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-11"><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        <SelectItem value="all">Tous — {placeholder.toLowerCase()}</SelectItem>
        {options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

function BucketList({ title, buckets }) {
  const entries = Object.entries(buckets || {}).sort((a, b) => b[1] - a[1]);
  if (!entries.length) {
    return (
      <div>
        <p className="font-semibold text-muted-foreground mb-1">{title}</p>
        <p className="text-muted-foreground">—</p>
      </div>
    );
  }
  return (
    <div>
      <p className="font-semibold text-muted-foreground mb-1">{title}</p>
      <ul className="space-y-0.5">
        {entries.map(([k, v]) => (
          <li key={k} className="flex justify-between gap-2">
            <span className="truncate">{k}</span>
            <span className="tabular-nums font-medium shrink-0">{v}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const Loading = () => <p className="py-10 text-center text-sm text-muted-foreground animate-pulse">Chargement…</p>;
const Empty = () => <p className="py-10 text-center text-sm text-muted-foreground">Aucune demande pour ces filtres.</p>;
