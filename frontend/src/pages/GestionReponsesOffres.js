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
  GESTION_KPI_CARDS,
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
  rdvClientAffiche,
} from "@/lib/demandesOffres";
import { uniqueConseillerNames } from "@/lib/conseillers";
import { PendingComplementBadge } from "@/components/NotesConseiller";
import { offreNotificationPath } from "@/lib/complementsOffre";
import { FILE_COLUMNS, sortFileATraiter, urgentesAgentEnTete, urgenceDelaiLabel } from "@/lib/transmissionOffre";
import { CARTES_COMMERCIALES, NON_ATTRIBUE, TRAITEMENT_STYLE, boutonTraiter, tauxSignatureLabel } from "@/lib/suiviOffres";
import { CommercialBadge, TraitementBadge, useAttribuer } from "@/components/SuiviOffresPilotage";
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

const FILE_HEADERS = FILE_COLUMNS;

function isOffreAModifier(row) {
  const st = row?.statut;
  return st === "Offre à modifier" || st === "Offre modifiée";
}

function rowHighlight(row) {
  const p = row?.priorite;
  const st = row?.statut;
  return Boolean(row?.urgente) || p === "urgent" || p === "surveiller" || st === "Demande incomplète" || st === "Offre reçue" || isOffreAModifier(row);
}

const RDV_PROXIMITE = {
  aujourdhui: { label: "RDV aujourd'hui", className: "bg-amber-100 text-amber-950" },
  demain: { label: "RDV demain", className: "bg-sky-100 text-sky-900" },
  proche: { label: "RDV sous 3 jours", className: "bg-indigo-50 text-indigo-900" },
  passe: { label: "RDV dépassé", className: "bg-slate-100 text-slate-600" },
};

function isOffreTransmiseAgent(row) {
  return avancementCode(row) === "offre_transmise" || row?.etape_affichee === "offre_transmise";
}

function RdvClient({ row, variant = "inline" }) {
  const rdv = rdvClientAffiche(row);
  const date = rdv.date;
  const heure = formatHeureRdv(rdv.heure);
  const cell = variant === "cell";
  if (!date) {
    return (
      <span className={cell ? "text-xs text-slate-400 whitespace-nowrap" : "block text-[11px] text-slate-400 mt-1"}>
        Aucun RDV renseigné
      </span>
    );
  }
  const chip = RDV_PROXIMITE[rdvProximite(date)];
  const when = `${formatDateFr(date)}${heure ? ` à ${heure}` : ""}`;
  return (
    <span className={cell ? "block whitespace-nowrap" : "block mt-1"} data-testid={`rdv-client-${row.id || "row"}`}>
      <span className={cell ? "block text-sm font-medium text-slate-800" : "block text-[11px] font-semibold text-[#002FA7]"}>
        {cell ? when : `RDV client : ${when}`}
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
  const [erreurStats, setErreurStats] = useState(null);
  const [erreursAgentStats, setErreursAgentStats] = useState(null);
  const [espace, setEspace] = useState("mes_dossiers");
  const [indicateur, setIndicateur] = useState(null);
  const [pilotage, setPilotage] = useState(null);
  const [nbAAttribuer, setNbAAttribuer] = useState(0);

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

      // Day-action shortcuts that map to API filters.
      // « Urgentes » = urgence agent OU priorité système urgent (filtré côté client).
      if (dayAction === "a_surveiller") params.priorite = "surveiller";
      if (dayAction === "incompletes") params.categorie = "incompletes";
      if (dayAction === "offres_recues") params.categorie = "offres_recues";
      if (dayAction === "nouvelles") params.categorie = "envoyees";

      const statsParams = { periode: periode && periode !== "all" ? periode : undefined };
      if (conseiller !== "all") statsParams.conseiller = conseiller;
      // Espace personnel : mes dossiers attribués, ou les demandes encore à prendre en charge.
      const scope = espace === "a_attribuer" ? { gestionnaire: NON_ATTRIBUE } : { perimetre: "personnel" };
      if (canProcess) Object.assign(params, scope);
      if (indicateur) params.indicateur = indicateur;

      const [listRes, statsRes, errRes, errAgentRes, , pilRes, globalRes] = await Promise.all([
        api.get("/demandes-offres", { params }),
        api.get("/demandes-offres/stats", { params: canProcess ? { ...statsParams, ...scope } : statsParams }).catch((err) => {
          console.warn("stats offres", err);
          return { data: null, _error: err };
        }),
        api.get("/demandes-offres/stats/erreurs", { params: statsParams }).catch(() => ({ data: null })),
        api.get("/demandes-offres/stats/erreurs-agent", { params: statsParams }).catch(() => ({ data: null })),
        loadNotifs(),
        canProcess
          ? api.get("/demandes-offres/pilotage", { params: { ...statsParams, perimetre: "personnel" } }).catch(() => ({ data: null }))
          : Promise.resolve({ data: null }),
        canProcess
          ? api.get("/demandes-offres/pilotage", { params: statsParams }).catch(() => ({ data: null }))
          : Promise.resolve({ data: null }),
      ]);
      setPilotage(pilRes?.data || null);
      setNbAAttribuer(globalRes?.data?.indicateurs?.non_attribuees ?? 0);
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
  }, [qDebounced, conseiller, compagnie, formType, priorite, periode, categorie, enRetard, dayAction, origine, tri, loadNotifs, espace, indicateur, canProcess]);

  useEffect(() => { load(); }, [load]);

  const { attribuer, busyId } = useAttribuer(useCallback(() => load(), [load]));

  const applyIndicateur = (tag) => {
    setIndicateur((prev) => (prev === tag ? null : tag));
    setCategorie(null);
    setDayAction(null);
    setEnRetard(false);
    setTab("file");
  };

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

  const visibleRows = useMemo(() => {
    let list = rows;
    if (!qDebounced) list = list.filter((r) => r.statut !== "Brouillon");
    if (dayAction === "urgentes") {
      list = list.filter((r) => Boolean(r.urgente) || r.priorite === "urgent");
    }
    if (dayAction === "nouvelles") {
      list = list.filter((r) => {
        const st = r.statut;
        const j = Number(r.jours_depuis ?? 99);
        return (st === "Demande envoyée" || st === "Demande validée") && j <= 1;
      });
    }
    // L'urgence agent prime toujours, y compris si un autre tri (RDV, soumission) est choisi.
    if (tri && tri !== "maj") return urgentesAgentEnTete(list);
    return sortFileATraiter(list);
  }, [rows, qDebounced, dayAction, tri]);

  const fileRechercheActive = Boolean(
    qDebounced
    || conseiller !== "all"
    || compagnie !== "all"
    || formType !== "all"
    || priorite !== "all"
    || (periode && periode !== "all")
    || origine !== "all"
    || (tri && tri !== "maj")
    || Boolean(indicateur)
  );

  const fileRows = useMemo(() => {
    if (fileRechercheActive) return visibleRows;
    return visibleRows.filter((row) => !isOffreTransmiseAgent(row));
  }, [visibleRows, fileRechercheActive]);

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
      const cards = visibleRows.filter((r) => {
        if (placed.has(r.id)) return false;
        if (set.has(r.statut)) {
          placed.add(r.id);
          return true;
        }
        return false;
      });
      return { ...col, cards };
    });
  }, [kanbanCols, visibleRows]);

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

        {/* Espace personnel du gestionnaire */}
        <Card className="p-3 border-slate-200 space-y-3" data-testid="espace-personnel">
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50" role="tablist">
              {[
                { id: "mes_dossiers", label: "Mes dossiers" },
                { id: "a_attribuer", label: `Demandes non attribuées (${nbAAttribuer})` },
              ].map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={espace === item.id}
                  data-testid={`espace-${item.id}`}
                  onClick={() => { setEspace(item.id); setIndicateur(null); }}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                    espace === item.id ? "bg-white shadow-sm text-[#002FA7]" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-500">
              {espace === "mes_dossiers"
                ? "Seuls les dossiers qui vous sont attribués. Les compteurs ci-dessous portent sur ces dossiers."
                : "Demandes soumises sans gestionnaire : « M'attribuer » pour prendre un dossier en charge."}
            </p>
            <button
              type="button"
              className="ml-auto text-xs font-medium text-[#002FA7] hover:underline"
              onClick={() => navigate("/dashboard?categorie=offres")}
            >
              Suivi global du service
            </button>
          </div>
          {pilotage && (
            <div className="space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Mes indicateurs — avancement du traitement
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2">
                {(pilotage.traitement || []).map((t) => (
                  <button
                    key={t.code}
                    type="button"
                    data-testid={`mes-traitement-${t.code}`}
                    onClick={() => { setEspace("mes_dossiers"); applyIndicateur(t.tag); }}
                    className={`rounded-lg border px-3 py-2 text-left ${TRAITEMENT_STYLE[t.code] || ""} ${
                      indicateur === t.tag ? "ring-2 ring-[#002FA7] ring-offset-1" : ""
                    }`}
                  >
                    <span className="block text-[11px] font-medium leading-snug">{t.label}</span>
                    <span className="block text-lg font-bold tabular-nums">{t.count}</span>
                  </button>
                ))}
              </div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 pt-1">
                Mes indicateurs — résultat commercial
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2">
                {CARTES_COMMERCIALES.map((c) => (
                  <button
                    key={c.tag}
                    type="button"
                    data-testid={`mes-commercial-${c.tag.replace(":", "-")}`}
                    onClick={() => { setEspace("mes_dossiers"); applyIndicateur(c.tag); }}
                    className={`rounded-lg border border-slate-200 bg-white px-3 py-2 text-left ${
                      indicateur === c.tag ? "ring-2 ring-[#002FA7] ring-offset-1" : ""
                    }`}
                  >
                    <span className="block text-[11px] font-medium text-slate-600 leading-snug">{c.label}</span>
                    <span className="block text-lg font-bold tabular-nums">{pilotage.indicateurs?.[c.tag] ?? 0}</span>
                  </button>
                ))}
                <button
                  type="button"
                  data-testid="mes-decision-a-renseigner"
                  onClick={() => { setEspace("mes_dossiers"); applyIndicateur("decision_a_renseigner"); }}
                  className={`rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-left ${
                    indicateur === "decision_a_renseigner" ? "ring-2 ring-[#002FA7] ring-offset-1" : ""
                  }`}
                >
                  <span className="block text-[11px] font-medium text-red-900 leading-snug">Décision client à renseigner</span>
                  <span className="block text-lg font-bold tabular-nums text-red-900">
                    {pilotage.indicateurs?.decision_a_renseigner ?? 0}
                    <span className="ml-1 text-[11px] font-medium">
                      dont {pilotage.indicateurs?.decision_depassee_14j ?? 0} &gt; 14 j
                    </span>
                  </span>
                </button>
              </div>
              <p className="text-[11px] text-slate-500">
                Taux de signature : <strong>{tauxSignatureLabel(pilotage.taux_signature)}</strong>
                {pilotage.taux_signature_definition ? ` (${pilotage.taux_signature_definition})` : ""}
              </p>
            </div>
          )}
        </Card>

        {/* Mes actions du jour */}
        <Card className="p-3 border-slate-200">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <ClipboardList className="h-4 w-4" style={{ color: ACCENT }} />
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Mes actions du jour</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {DAY_ACTIONS.map(({ id, label, icon: Icon, tone }) => {
              const n = gestion[id] ?? 0;
              const active = dayAction === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => applyDayAction(id)}
                  className={`rounded-lg border px-3 py-2.5 text-left transition ${tone} ${
                    active ? "ring-2 ring-[#002FA7] ring-offset-1" : "hover:opacity-90"
                  }`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-[11px] font-medium opacity-80 flex items-center gap-1">
                      <Icon className="h-3 w-3" /> {label}
                    </span>
                    <span className="text-lg font-bold tabular-nums">{n}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </Card>

        {/* Notifications + KPI */}
        <div className="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-4">
          <Card className="p-3 border-slate-200 flex flex-col max-h-64">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-600 flex items-center gap-1.5">
                <Bell className="h-3.5 w-3.5" style={{ color: ACCENT }} />
                Notifications
              </p>
              {notifCount > 0 && (
                <span
                  className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full text-white"
                  style={{ background: ACCENT }}
                >
                  {notifCount}
                </span>
              )}
            </div>
            <div className="overflow-y-auto space-y-1 flex-1 min-h-0">
              {notifs.filter((n) => !n.read).length === 0 ? (
                <p className="text-xs text-slate-400 py-4 text-center">Aucune non lue</p>
              ) : (
                notifs.filter((n) => !n.read).map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => onNotifClick(n)}
                    className="w-full text-left rounded-md px-2 py-1.5 text-xs hover:bg-slate-50 border border-transparent hover:border-slate-100"
                  >
                    <span className="font-medium text-slate-800 line-clamp-2">{n.titre || n.title || "Notification"}</span>
                    {n.created_at && (
                      <span className="block text-[10px] text-slate-400 mt-0.5">{formatDateFr(n.created_at)}</span>
                    )}
                  </button>
                ))
              )}
            </div>
          </Card>

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {GESTION_KPI_CARDS.map((card) => {
              const n = gestion[card.id] ?? 0;
              const active = categorie === card.id;
              return (
                <button
                  key={card.id}
                  type="button"
                  onClick={() => applyKpi(card.id)}
                  className={`rounded-2xl border px-4 py-4 text-left transition ${card.color} ${
                    active ? "ring-2 ring-[#002FA7] ring-offset-1 shadow-sm" : "hover:shadow-sm"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold leading-snug">{card.label}</div>
                      <div className="text-3xl font-bold tabular-nums mt-2">{n}</div>
                    </div>
                    <div className="text-2xl leading-none shrink-0">{card.emoji}</div>
                  </div>
                </button>
              );
            })}
          </div>
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
            {(categorie || dayAction || enRetard || indicateur || priorite !== "all" || q || conseiller !== "all" || origine !== "all") && (
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
                  setIndicateur(null);
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
            {loading ? "…" : `${(tab === "file" ? fileRows : visibleRows).length} dossier${(tab === "file" ? fileRows : visibleRows).length !== 1 ? "s" : ""}`}
          </span>
        </div>

        {/* File à traiter */}
        {tab === "file" && (
          <Card className="border-slate-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50/80 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {FILE_HEADERS.map((h) => (
                      <th key={h} className="px-3 py-2.5 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={FILE_HEADERS.length} className="px-3 py-12 text-center text-slate-400">
                        <Loader2 className="h-5 w-5 animate-spin inline mr-2" /> Chargement…
                      </td>
                    </tr>
                  ) : fileRows.length === 0 ? (
                    <tr>
                      <td colSpan={FILE_HEADERS.length} className="px-3 py-12 text-center text-slate-400">
                        Aucune demande dans la file.
                      </td>
                    </tr>
                  ) : (
                    fileRows.map((r) => {
                      const hi = rowHighlight(r);
                      const actionLabel = TERMINAL.has(r.statut) ? "Voir" : "Traiter";
                      const soumis = isSoumisCompagnie(r.soumis_compagnie);
                      return (
                        <tr
                          key={r.id}
                          className={`border-t border-slate-100 hover:bg-slate-50/60 ${
                            r.urgente || r.priorite === "urgent"
                              ? "bg-red-50/40"
                              : isOffreAModifier(r)
                                ? "bg-amber-50/70"
                                : hi
                                  ? r.priorite === "surveiller" || r.statut === "Demande incomplète"
                                    ? "bg-amber-50/40"
                                    : "bg-violet-50/30"
                                  : ""
                          }`}
                        >
                          <td className="px-3 py-2 font-bold text-slate-900 whitespace-nowrap" data-testid="file-agent">
                            {r.agent_label || "—"}
                          </td>
                          <td className="px-3 py-2 font-normal text-slate-800 whitespace-nowrap" data-testid="file-client">
                            {clientLabel(r)}
                            {r.urgente && (
                              <span className="ml-2 inline-flex rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-semibold text-white">URGENT</span>
                            )}
                            {r.numero && <span className="block text-[10px] text-slate-400 font-normal">{r.numero}</span>}
                            {r.urgente && urgenceDelaiLabel(r) ? (
                              <span className="mt-1 block text-[11px] font-semibold text-rose-800">{urgenceDelaiLabel(r)}</span>
                            ) : null}
                            {r.urgente && r.urgence_motif ? (
                              <span className="mt-1 block max-w-[220px] whitespace-normal text-[11px] font-normal text-rose-800">{r.urgence_motif}</span>
                            ) : null}
                            <span className="block text-[11px] text-slate-500 font-normal mt-0.5">
                              Soumission : {r.date_envoi ? formatDateFr(r.date_envoi) : "—"}
                            </span>
                            {demandeOrigineKey(r.demande_origine) === "attribuee" && (
                              <span
                                className={`inline-flex mt-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${DEMANDE_ORIGINE_STYLE.attribuee}`}
                                title={demandeOrigineLabel(r.demande_origine)}
                              >
                                {demandeOrigineShort(r.demande_origine)}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-slate-600 max-w-[140px] truncate" title={typeLabel(r)}>{typeLabel(r)}</td>
                          <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{formatDateFr(r.created_at)}</td>
                          <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{formatDateFr(r.date_envoi)}</td>
                          <td className="px-3 py-2">
                            <RdvClient row={r} variant="cell" />
                          </td>
                          <td className="px-3 py-2 text-slate-600 text-xs max-w-[140px]">
                            {formatVariantesSummary(r) || compsShort(r)}
                          </td>
                          <td className="px-3 py-2" data-testid="file-statut-traitement">
                            {r.statut_traitement ? <TraitementBadge row={r} /> : <AvancementBadge row={r} />}
                            {Number(r.nb_complements_en_attente) > 0 && (
                              <span className="mt-1 block">
                                <PendingComplementBadge count={r.nb_complements_en_attente} />
                              </span>
                            )}
                            {r.statut === "Offre modifiée" && (
                              <span className="mt-1 block text-[10px] font-semibold text-amber-950">Offre à modifier</span>
                            )}
                          </td>
                          <td className="px-3 py-2" data-testid="file-statut-commercial">
                            <CommercialBadge row={r} />
                          </td>
                          <td className="px-3 py-2">
                            {canProcess ? (
                              <label
                                className="inline-flex items-center gap-1.5 text-xs cursor-pointer"
                                title={soumisCompagnieLabel(r.soumis_compagnie)}
                                onClick={(e) => e.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  className="accent-[#002FA7]"
                                  checked={soumis}
                                  data-testid={`soumis-compagnie-row-${r.id}`}
                                  onChange={(e) => toggleSoumis(r, e.target.checked, e)}
                                />
                                <span className={soumis ? "text-emerald-800" : "text-slate-500"}>
                                  {soumis ? "🟢" : "⚪"}
                                </span>
                              </label>
                            ) : (
                              <span className="text-xs text-slate-500" title={soumisCompagnieLabel(r.soumis_compagnie)}>
                                {soumis ? "🟢" : "⚪"}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-xs text-slate-500 max-w-[120px] truncate" title={r.derniere_action || ""}>
                            {r.derniere_action || "—"}
                          </td>
                          <td className="px-3 py-2 tabular-nums text-slate-700 font-medium">{r.jours_depuis ?? "—"}</td>
                          <td className="px-3 py-2"><PrioriteBadge niveau={r.priorite} /></td>
                          <td className="px-3 py-2">
                            <div className="flex items-center gap-1.5">
                              {r.bouton_traiter ? (
                                <button
                                  type="button"
                                  data-testid={`file-traiter-${r.id}`}
                                  className={`h-7 rounded-md px-2.5 text-xs font-medium whitespace-nowrap ${boutonTraiter(r).className}`}
                                  onClick={() => openFiche(r.id)}
                                >
                                  {boutonTraiter(r).label}
                                </button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant={actionLabel === "Traiter" ? "default" : "outline"}
                                  className="h-7 text-xs gap-1"
                                  style={actionLabel === "Traiter" ? { background: ACCENT } : undefined}
                                  onClick={() => openFiche(r.id)}
                                >
                                  {actionLabel === "Voir" ? <Eye className="h-3 w-3" /> : null}
                                  {actionLabel}
                                </Button>
                              )}
                              {r.can_attribuer ? (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-7 text-xs whitespace-nowrap"
                                  disabled={busyId === r.id}
                                  data-testid={`file-attribuer-${r.id}`}
                                  onClick={(e) => attribuer(r, e)}
                                >
                                  M&apos;attribuer
                                </Button>
                              ) : null}
                            </div>
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
                          <p className="text-[11px] text-slate-500 mt-0.5">Soumission : {r.date_envoi ? formatDateFr(r.date_envoi) : "—"}</p>
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
                    {["Conseiller", "Demandes", "Offres sollicitées", "Offres reçues", "Incomplètes", "Complètes", "Signées"].map((h) => (
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
                          <ErreursRecentesCell erreurs={a.erreurs} onOpen={openFiche} />
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
                            <RepartitionChampErreur key={f.code} agent={a} field={f} onOpen={openFiche} />
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

function texteErreurRecente(erreur) {
  const label = erreur?.label || erreur?.code || "Erreur";
  const detail = erreur?.detail ? ` — ${erreur.detail}` : "";
  const numero = erreur?.numero ? ` (${erreur.numero})` : "";
  return `${label}${detail}${numero}`;
}

function dossiersDuChamp(agent, field) {
  const fromApi = Array.isArray(field?.dossiers) ? field.dossiers.filter((d) => d?.demande_id) : [];
  const source = fromApi.length
    ? fromApi
    : (Array.isArray(agent?.items) ? agent.items : []).reduce((acc, rec) => {
      const code = rec?.field || rec?.code;
      if (code !== field?.code || !rec?.demande_id || acc.some((d) => d.demande_id === rec.demande_id)) return acc;
      acc.push({
        demande_id: rec.demande_id,
        numero: rec.demande_numero || rec.numero || null,
        client: rec.client || null,
        at: rec.at || rec.date || null,
      });
      return acc;
    }, []);
  return [...source].sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
}

function ErreursRecentesCell({ erreurs, onOpen }) {
  const list = Array.isArray(erreurs) ? erreurs : [];
  if (!list.length) return "—";
  return (
    <>
      {list.slice(0, 3).map((erreur, index) => {
        const text = texteErreurRecente(erreur);
        if (!erreur?.demande_id) {
          return <span key={`${erreur?.numero || "err"}-${index}`} className="block truncate">{text}</span>;
        }
        return (
          <button
            key={`${erreur.demande_id}-${erreur.erreur_id || erreur.code || index}`}
            type="button"
            className="block w-full truncate text-left text-[#002FA7] hover:underline"
            data-testid="scoring-erreur-link"
            title="Ouvrir le dossier"
            onClick={() => onOpen(erreur.demande_id)}
          >
            {text}
          </button>
        );
      })}
      {list.length > 3 && <span className="text-slate-400">+{list.length - 3} autres</span>}
    </>
  );
}

function RepartitionChampErreur({ agent, field, onOpen }) {
  const dossiers = dossiersDuChamp(agent, field);
  const [open, setOpen] = useState(false);
  const label = `${field.label} : ${field.count}${(field.comments || [])[0] ? ` — ${field.comments[0]}` : ""}`;
  const chip = "inline-flex mr-2 mb-1 rounded bg-rose-50 text-rose-900 px-2 py-0.5 text-left";
  if (dossiers.length <= 1) {
    const demandeId = dossiers[0]?.demande_id;
    if (!demandeId) {
      return <span className={chip} title={(field.comments || []).join(" · ")}>{label}</span>;
    }
    return (
      <button
        type="button"
        className={`${chip} hover:bg-rose-100 hover:underline`}
        title="Ouvrir le dossier"
        data-testid="erreur-champ-link"
        onClick={() => onOpen(demandeId)}
      >
        {label}
      </button>
    );
  }
  return (
    <span className="inline-flex flex-col items-start mr-2 mb-1 align-top">
      <button
        type="button"
        className="inline-flex rounded bg-rose-50 text-rose-900 px-2 py-0.5 hover:bg-rose-100"
        title="Choisir le dossier"
        data-testid="erreur-champ-link"
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open && (
        <span className="mt-1 flex flex-col gap-0.5 rounded border border-rose-100 bg-white p-1 shadow-sm">
          {dossiers.map((dossier) => (
            <button
              key={dossier.demande_id}
              type="button"
              className="px-1 text-left text-[11px] text-[#002FA7] hover:underline"
              data-testid="erreur-champ-dossier"
              onClick={() => onOpen(dossier.demande_id)}
            >
              {dossier.numero || "Dossier"}{dossier.client ? ` — ${dossier.client}` : ""}
            </button>
          ))}
        </span>
      )}
    </span>
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
