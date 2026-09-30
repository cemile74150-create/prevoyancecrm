import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { blobErrorMessage, downloadAuthenticatedBlob, openAuthenticatedBlob } from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import ConseillerCombobox from "@/components/ConseillerCombobox";
import ClientPicker from "@/components/ClientPicker";
import ClientDuplicateDialog from "@/components/ClientDuplicateDialog";
import { parseClientDuplicateError } from "@/lib/clientDuplicate";
import { conseillerNames, normalizeConseillerKey, uniqueConseillerNames } from "@/lib/conseillers";
import { Checkbox } from "@/components/ui/checkbox";
import {
  SUIVI_3P_STATUTS,
  SUIVI_3P_STATUT_STYLE,
  SUIVI_3P_GEO_OPTIONS,
  SUIVI_3P_GEO_STYLE,
  SUIVI_3P_EXPORT_COLUMNS,
  DEFAULT_SUIVI_3P_EXPORT_COLUMN_KEYS,
  formatChf,
  formatDateFr,
  toIsoDate,
  toSwissDate,
} from "@/lib/suivi3p";
import {
  Shield,
  Search,
  FileSearch,
  PiggyBank,
  PenLine,
  Users,
  Plus,
  Upload,
  Link2,
  ExternalLink,
  Trash2,
  AlertTriangle,
  Check,
  ChevronRight,
  Loader2,
  Mail,
  Download,
  Minus,
  CalendarDays,
  PhoneCall,
  Send,
} from "lucide-react";
import { toast } from "sonner";

const Kpi = ({ icon: Icon, label, value, accent, testid, selected, onClick }) => (
  <Card
    data-testid={testid}
    role="button"
    tabIndex={0}
    aria-pressed={selected}
    onClick={onClick}
    onKeyDown={(e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onClick?.();
      }
    }}
    className={`p-4 border-border/80 cursor-pointer transition-all duration-200 ${
      selected
        ? "ring-2 ring-[#002FA7] border-[#002FA7]/40 bg-[#002FA7]/[0.04] shadow-sm"
        : "hover:border-[#002FA7]/25 hover:shadow-sm hover:-translate-y-px"
    }`}
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className={`text-xs font-medium tracking-wide uppercase ${selected ? "text-[#002FA7]" : "text-muted-foreground"}`}>{label}</p>
        <p className="font-display font-black text-2xl sm:text-3xl tracking-tight mt-1.5 truncate">{value}</p>
      </div>
      <div className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ${accent}`}>
        <Icon className="h-4 w-4" strokeWidth={1.75} />
      </div>
    </div>
  </Card>
);

const BoolMark = ({ yes, label }) => (
  <span
    className="inline-flex items-center justify-center"
    title={yes ? `${label} : Oui` : `${label} : Non`}
    aria-label={yes ? "Oui" : "Non"}
  >
    {yes ? (
      <Check className="h-4 w-4 text-emerald-600" strokeWidth={2.5} />
    ) : (
      <Minus className="h-3.5 w-3.5 text-muted-foreground/50" strokeWidth={2} />
    )}
  </span>
);

function InlineConseillerCell({
  row,
  isGlobal,
  options,
  savingId,
  onSave,
  className = "",
  compact = false,
}) {
  const [draft, setDraft] = React.useState(row.conseiller || "");
  const isSaving = savingId === row.id;

  React.useEffect(() => {
    setDraft(row.conseiller || "");
  }, [row.id, row.conseiller]);

  const commit = async () => {
    const next = draft.trim() || null;
    const current = row.conseiller?.trim() || null;
    if (next === current) return;
    const ok = await onSave(row.id, next);
    if (!ok) setDraft(row.conseiller || "");
  };

  const stopRowNav = (e) => {
    e.stopPropagation();
  };

  if (!isGlobal) {
    return <span className={className}>{row.conseiller || "—"}</span>;
  }

  return (
    <div
      className={`relative ${compact ? "min-w-[120px]" : "min-w-[180px] max-w-[240px]"}`}
      onMouseDown={stopRowNav}
      onClick={stopRowNav}
    >
      <ConseillerCombobox
        value={draft}
        onChange={setDraft}
        options={options}
        placeholder="Conseiller"
        disabled={isSaving}
        className={compact ? "h-8 text-xs" : "h-9 text-sm"}
        data-testid={`suivi-3p-row-conseiller-${row.id}`}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
        onBlur={commit}
      />
      {isSaving && (
        <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 animate-spin text-[#002FA7] pointer-events-none" />
      )}
    </div>
  );
}

const emptyForm = {
  client_id: null,
  linkedClient: null,
  prenom: "",
  nom: "",
  date_naissance: "",
  etat_civil: "",
  conseiller: "",
  conjoint: "",
};

export default function Suivi3P() {
  const { user, isGlobal, isAdmin, hasPerm } = useAuth();
  const canEditSuivi = hasPerm("suivi_3p.edit");
  const navigate = useNavigate();
  const importRef = useRef(null);
  const addressImportRef = useRef(null);
  const tableRef = useRef(null);
  const [stats, setStats] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [statut, setStatut] = useState("all");
  const [filterConseiller, setFilterConseiller] = useState("all");
  const [kpiFilter, setKpiFilter] = useState("all");
  const [geoFilter, setGeoFilter] = useState("all");
  const [conseillerRows, setConseillerRows] = useState([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [duplicateConflict, setDuplicateConflict] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importingAddresses, setImportingAddresses] = useState(false);
  const [addressReport, setAddressReport] = useState(null);
  const [pending, setPending] = useState([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignDoc, setAssignDoc] = useState(null);
  const [assignClientId, setAssignClientId] = useState("");
  const [allClients, setAllClients] = useState([]);
  const [savingConseillerRowId, setSavingConseillerRowId] = useState(null);
  const [savingSexeRowId, setSavingSexeRowId] = useState(null);
  const [conseillerOptions, setConseillerOptions] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [generatingCourriers, setGeneratingCourriers] = useState(false);
  const [downloadingCourriers, setDownloadingCourriers] = useState(false);
  const [courrierReport, setCourrierReport] = useState(null);
  const [bulkStatutBusy, setBulkStatutBusy] = useState(false);
  const [exportingSuivi, setExportingSuivi] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportScope, setExportScope] = useState("a_appeler");
  const [exportGrouping, setExportGrouping] = useState("par_conseiller");
  const [exportColumnKeys, setExportColumnKeys] = useState(() =>
    Object.fromEntries(DEFAULT_SUIVI_3P_EXPORT_COLUMN_KEYS.map((k) => [k, true]))
  );

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const loadPending = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const res = await api.get("/suivi-3p/pending-documents");
      setPending(res.data || []);
    } catch {
      setPending([]);
    }
  }, [isAdmin]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statut && statut !== "all") params.statut = statut;
      if (qDebounced) params.q = qDebounced;
      if (isGlobal && filterConseiller && filterConseiller !== "all") {
        params.conseiller = filterConseiller;
      }
      if (kpiFilter && kpiFilter !== "all") {
        params.filtre = kpiFilter;
      }
      if (geoFilter && geoFilter !== "all") {
        params.geo = geoFilter;
      }
      const [statsRes, listRes, consRes] = await Promise.all([
        api.get("/suivi-3p/stats", {
          params: isGlobal && filterConseiller !== "all" ? { conseiller: filterConseiller } : {},
        }),
        api.get("/suivi-3p", { params }),
        isGlobal ? api.get("/suivi-3p/conseillers") : Promise.resolve({ data: [] }),
      ]);
      setStats(statsRes.data);
      setRows(listRes.data || []);
      // Répartition : toujours la vue globale (fournie par /stats et /conseillers)
      setConseillerRows(consRes.data?.length ? consRes.data : (statsRes.data?.by_conseiller || []));
    } catch {
      setStats({
        total: 0,
        analyses_realisees: 0,
        gain_fiscal_total: 0,
        contrats_signes: 0,
        rdv_pris: 0,
        clients_contactes: 0,
        a_contacter: 0,
        offres_envoyees: 0,
        frontaliers: 0,
        suisses: 0,
        upcoming_rdvs: [],
        by_statut: {},
        by_conseiller: [],
      });
      setRows([]);
      setConseillerRows([]);
    } finally {
      setLoading(false);
    }
  }, [statut, qDebounced, filterConseiller, kpiFilter, geoFilter, isGlobal]);

  const refreshStats = useCallback(async () => {
    try {
      const [statsRes, consRes] = await Promise.all([
        api.get("/suivi-3p/stats", {
          params: isGlobal && filterConseiller !== "all" ? { conseiller: filterConseiller } : {},
        }),
        isGlobal ? api.get("/suivi-3p/conseillers") : Promise.resolve({ data: [] }),
      ]);
      setStats(statsRes.data);
      setConseillerRows(consRes.data?.length ? consRes.data : (statsRes.data?.by_conseiller || []));
    } catch {
      /* ignore */
    }
  }, [isGlobal, filterConseiller]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadPending();
  }, [loadPending]);

  useEffect(() => {
    if (!isGlobal) return;
    let cancelled = false;
    (async () => {
      try {
        const [suiviCons, usersCons] = await Promise.all([
          api.get("/suivi-3p/conseillers").catch(() => ({ data: [] })),
          api.get("/users/conseillers").catch(() => ({ data: [] })),
        ]);
        if (cancelled) return;
        const names = [
          ...(Array.isArray(suiviCons.data) ? suiviCons.data.map((c) => c.conseiller) : []),
          ...conseillerNames(usersCons.data),
        ].filter(Boolean);
        setConseillerOptions([...new Set(names)]);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isGlobal]);

  const saveConseiller = async (rowId, value) => {
    setSavingConseillerRowId(rowId);
    try {
      const res = await api.put(`/suivi-3p/${rowId}`, {
        conseiller: value?.trim() || null,
      });
      const updated = res.data?.conseiller ?? (value?.trim() || null);
      setRows((prev) => prev.map((r) => (r.id === rowId ? { ...r, conseiller: updated } : r)));
      toast.success("Conseiller mis à jour");
      await refreshStats();
      return true;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Modification impossible");
      return false;
    } finally {
      setSavingConseillerRowId(null);
    }
  };

  const saveSexe = async (rowId, value) => {
    const sexe = value === "unset" ? null : value;
    setSavingSexeRowId(rowId);
    try {
      const res = await api.put(`/suivi-3p/${rowId}`, { sexe });
      const updated = res.data?.sexe || null;
      setRows((prev) => prev.map((r) => (r.id === rowId ? { ...r, sexe: updated, civilite: updated } : r)));
      toast.success("Civilité enregistrée");
      return true;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Civilité non enregistrée");
      return false;
    } finally {
      setSavingSexeRowId(null);
    }
  };

  const statutCounts = useMemo(() => {
    const by = stats?.by_statut || {};
    return SUIVI_3P_STATUTS.map((s) => ({ id: s, count: by[s] || 0 }));
  }, [stats]);

  const byConseiller = useMemo(
    () => (stats?.by_conseiller?.length ? stats.by_conseiller : conseillerRows),
    [stats, conseillerRows],
  );

  const mergedConseillerOptions = useMemo(() => {
    const names = [
      ...conseillerOptions,
      ...byConseiller.map((c) => c.conseiller),
      ...rows.map((r) => r.conseiller),
    ].filter(Boolean);
    return uniqueConseillerNames(names);
  }, [conseillerOptions, byConseiller, rows]);

  const sortedConseillers = useMemo(
    () => [...byConseiller].sort((a, b) => (b.total || 0) - (a.total || 0)),
    [byConseiller],
  );
  const maxConseillerTotal = Math.max(1, ...sortedConseillers.map((c) => c.total || 0));
  const totalConseillerClients = sortedConseillers.reduce((s, c) => s + (c.total || 0), 0);

  const selectedConseillerMeta = useMemo(() => {
    if (filterConseiller === "all") return null;
    const key = normalizeConseillerKey(filterConseiller);
    return sortedConseillers.find((c) => normalizeConseillerKey(c.conseiller) === key) || {
      conseiller: filterConseiller,
      total: 0,
    };
  }, [filterConseiller, sortedConseillers]);

  const displayedRows = rows;

  const resetConseillerFilter = () => setFilterConseiller("all");

  const applyKpiFilter = (next) => {
    setKpiFilter((prev) => {
      const value = prev === next ? "all" : next;
      return value;
    });
    setStatut("all");
    setTimeout(() => {
      tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  const applyConseillerFilter = (name) => {
    setFilterConseiller((prev) => (prev === name ? "all" : name));
    setTimeout(() => {
      tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  const createClient = async () => {
    if (!form.prenom.trim() || !form.nom.trim()) {
      toast.error("Prénom et nom requis");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        prenom: form.prenom.trim(),
        nom: form.nom.trim(),
        date_naissance: toIsoDate(form.date_naissance) || null,
        etat_civil: form.etat_civil || null,
        conseiller: isGlobal ? (form.conseiller || null) : undefined,
        conjoint: form.conjoint.trim() || null,
        client_id: form.client_id || undefined,
      };
      const res = await api.post("/suivi-3p", payload);
      toast.success("Client Suivi 3P créé");
      setCreateOpen(false);
      setForm(emptyForm);
      navigate(`/suivi-3p/${res.data.id}`);
    } catch (e) {
      const dup = parseClientDuplicateError(e);
      if (dup.isDuplicate) {
        setDuplicateConflict(dup);
        toast.error(dup.message);
      } else {
        toast.error(dup.message || "Création impossible");
      }
    } finally {
      setSaving(false);
    }
  };

  const importAnalyses = async (e) => {
    const fileList = e.target.files;
    if (!fileList?.length) return;
    setImporting(true);
    try {
      const fd = new FormData();
      const files = Array.from(fileList);
      const isZip = files.length === 1 && files[0].name.toLowerCase().endsWith(".zip");
      if (isZip) {
        fd.append("zip_file", files[0]);
      } else {
        files.forEach((f) => fd.append("files", f));
      }
      const res = await api.post("/admin/import-suivi-3p-analyses", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(
        `Import : ${res.data.matched} associés, ${res.data.pending} à vérifier, ${res.data.skipped} ignorés` +
          (res.data.details_sample?.some((d) => d.gain_fiscal_estime != null)
            ? " — gains fiscaux extraits automatiquement"
            : ""),
      );
      await Promise.all([load(), loadPending()]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Import impossible");
    } finally {
      setImporting(false);
      if (importRef.current) importRef.current.value = "";
    }
  };

  const importAddresses = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportingAddresses(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post("/suivi-3p/import-addresses", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setAddressReport(res.data);
      toast.success(
        `${res.data.updated_count || 0} adresse(s) mise(s) à jour` +
          (res.data.error_count ? ` · ${res.data.error_count} erreur(s)` : ""),
      );
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Import des adresses impossible");
    } finally {
      setImportingAddresses(false);
      if (addressImportRef.current) addressImportRef.current.value = "";
    }
  };

  const openAssign = async (doc) => {
    setAssignDoc(doc);
    setAssignClientId("");
    setAssignOpen(true);
    try {
      const res = await api.get("/suivi-3p");
      setAllClients(res.data || []);
    } catch {
      setAllClients([]);
    }
  };

  const confirmAssign = async () => {
    if (!assignDoc || !assignClientId) {
      toast.error("Choisissez un client");
      return;
    }
    try {
      await api.post(`/suivi-3p/pending-documents/${assignDoc.id}/assign`, {
        client_id: assignClientId,
      });
      toast.success("Document lié au client");
      setAssignOpen(false);
      setAssignDoc(null);
      await Promise.all([load(), loadPending()]);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Liaison impossible");
    }
  };

  const deletePending = async (doc) => {
    if (!window.confirm(`Ignorer « ${doc.original_filename} » ?`)) return;
    try {
      await api.delete(`/suivi-3p/pending-documents/${doc.id}`);
      setPending((prev) => prev.filter((p) => p.id !== doc.id));
      toast.success("Document retiré");
    } catch {
      toast.error("Suppression impossible");
    }
  };

  const openPending = async (doc) => {
    try {
      await openAuthenticatedBlob(
        `/suivi-3p/pending-documents/${doc.id}/download`,
        doc.original_filename || "analyse.pdf"
      );
    } catch {
      toast.error("Ouverture impossible");
    }
  };

  const toggleSelected = (id, e) => {
    e?.stopPropagation?.();
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const allVisibleSelected =
    displayedRows.length > 0 && displayedRows.every((r) => selectedIds.includes(r.id));

  const toggleSelectAllVisible = (e) => {
    e?.stopPropagation?.();
    const ids = displayedRows.map((r) => r.id);
    if (allVisibleSelected) {
      setSelectedIds((prev) => prev.filter((id) => !ids.includes(id)));
    } else {
      setSelectedIds((prev) => [...new Set([...prev, ...ids])]);
    }
  };

  const generateCourriers = async () => {
    setGeneratingCourriers(true);
    try {
      const res = await api.post("/suivi-3p/courriers/generate", {
        client_ids: selectedIds.length ? selectedIds : undefined,
      }, { timeout: 300000 });
      const r = res.data || {};
      setCourrierReport(r);
      const n = r.generated || 0;
      if (n > 0) {
        toast.success(`${n} courrier(s) généré(s) — téléchargement du ZIP…`);
        await downloadAllCourriers();
      } else {
        toast.error("Aucun courrier généré (aucun client avec un gain fiscal > 250 CHF)");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || (await blobErrorMessage(e, "Génération des courriers impossible")));
    } finally {
      setGeneratingCourriers(false);
    }
  };

  const downloadAllCourriers = async () => {
    setDownloadingCourriers(true);
    try {
      await downloadAuthenticatedBlob("/suivi-3p/courriers/download-all", "Courriers_Optimisation_Fiscale.zip");
      toast.success("Téléchargement du ZIP lancé");
    } catch (e) {
      toast.error(await blobErrorMessage(e, e?.response?.data?.detail || "Téléchargement impossible"));
    } finally {
      setDownloadingCourriers(false);
    }
  };

  const exportSelectionCount = selectedIds.length;
  const exportFilteredCount = displayedRows.length;
  const exportCallableHint = useMemo(
    () => displayedRows.filter((r) => !r.client_contacte && r.statut_suivi === "Offre envoyée").length,
    [displayedRows]
  );

  const toggleExportColumn = (key, checked) => {
    setExportColumnKeys((prev) => ({ ...prev, [key]: checked }));
  };

  const runExportSuivi3P = async () => {
    const cols = SUIVI_3P_EXPORT_COLUMNS.map((c) => c.key).filter((k) => exportColumnKeys[k]);
    if (!cols.length) {
      toast.error("Sélectionnez au moins une colonne à exporter");
      return;
    }
    if (exportScope === "selection" && !selectedIds.length) {
      toast.error("Cochez au moins un client dans le tableau");
      return;
    }

    setExportingSuivi(true);
    try {
      const params = new URLSearchParams();
      params.set("scope", exportScope);
      params.set("regroupement", exportGrouping);
      if (cols.length < DEFAULT_SUIVI_3P_EXPORT_COLUMN_KEYS.length) {
        params.set("colonnes", cols.join(","));
      }
      if (statut && statut !== "all") params.set("statut", statut);
      if (qDebounced) params.set("q", qDebounced);
      if (isGlobal && filterConseiller && filterConseiller !== "all") {
        params.set("conseiller", filterConseiller);
      }
      if (kpiFilter && kpiFilter !== "all") params.set("filtre", kpiFilter);
      if (exportScope === "selection") {
        params.set("client_ids", selectedIds.join(","));
      }
      const path = `/suivi-3p/export.xlsx?${params.toString()}`;
      const name = await downloadAuthenticatedBlob(path, "Suivi_3e_pilier.xlsx");
      toast.success(`Export téléchargé (${name})`);
      setExportOpen(false);
    } catch (e) {
      toast.error(await blobErrorMessage(e, e?.response?.data?.detail || "Export impossible"));
    } finally {
      setExportingSuivi(false);
    }
  };

  const markOffresEnvoyees = async () => {
    if (!canEditSuivi) {
      toast.error("Permission insuffisante");
      return;
    }
    const ids = selectedIds.length ? selectedIds : undefined;
    if (
      !window.confirm(
        `Passer en « Offre envoyée » uniquement les clients avec un PDF d'analyse ET un gain fiscal > 250 CHF${selectedIds.length ? ` (parmi les ${selectedIds.length} sélectionné(s))` : ""} ?\n\nLes autres fiches ne seront pas modifiées.`
      )
    ) {
      return;
    }
    setBulkStatutBusy(true);
    try {
      const res = await api.post("/suivi-3p/bulk-statut", {
        statut: "Offre envoyée",
        client_ids: ids,
        only_offre_eligible: true,
      });
      const n = res.data?.updated ?? res.data?.matched ?? 0;
      const eligible = res.data?.eligible_count;
      toast.success(
        eligible != null
          ? `${n} fiche(s) passée(s) en « Offre envoyée » (${eligible} éligible(s))`
          : `${n} fiche(s) passée(s) en « Offre envoyée »`
      );
      setSelectedIds([]);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Mise à jour groupée impossible");
    } finally {
      setBulkStatutBusy(false);
    }
  };

  const upcomingRdvs = stats?.upcoming_rdvs || [];

  const subtitle = isGlobal
    ? filterConseiller !== "all"
      ? `Base clients Suivi 3P — ${filterConseiller}`
      : "Base clients indépendante — optimisation fiscale / 3e pilier"
    : `Vos clients Suivi 3P — ${user?.conseiller || user?.name || ""}`;

  return (
    <Layout>
      <div className="animate-fade-up max-w-7xl" data-testid="suivi-3p-page">
        <div className="flex items-start justify-between flex-wrap gap-4 mb-6">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
              <Shield className="h-7 w-7 text-[#002FA7]" /> Fiscalité, 3e pilier & Fortune 2026
            </h1>
            <p className="text-muted-foreground mt-1">{subtitle}</p>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {isAdmin && (
              <>
                <input
                  ref={importRef}
                  type="file"
                  accept=".pdf,.zip,application/pdf,application/zip"
                  multiple
                  className="hidden"
                  onChange={importAnalyses}
                />
                <input
                  ref={addressImportRef}
                  type="file"
                  accept=".xlsx,.xlsm,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
                  className="hidden"
                  onChange={importAddresses}
                  data-testid="suivi-3p-address-file"
                />
                <Button
                  variant="outline"
                  className="gap-1.5"
                  disabled={importingAddresses}
                  onClick={() => addressImportRef.current?.click()}
                  data-testid="suivi-3p-import-addresses"
                >
                  <Upload className="h-4 w-4" />
                  {importingAddresses ? "Import…" : "Importer adresses Excel"}
                </Button>
                <Button
                  variant="outline"
                  className="gap-1.5"
                  disabled={importing}
                  onClick={() => importRef.current?.click()}
                  data-testid="suivi-3p-import-pdfs"
                >
                  <Upload className="h-4 w-4" />
                  {importing ? "Import…" : "Importer analyses PDF"}
                </Button>
              </>
            )}
            {canEditSuivi && (
            <Button
              className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
              onClick={() => setCreateOpen(true)}
              data-testid="suivi-3p-create"
            >
              <Plus className="h-4 w-4" /> Nouveau client
            </Button>
            )}
          </div>
        </div>

        <Card className="p-4 mb-5 border-[#002FA7]/40 bg-[#002FA7]/5" data-testid="suivi-3p-courriers-banner">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div>
              <p className="font-display font-bold text-lg text-[#002FA7]">Courriers d&apos;optimisation fiscale</p>
              <p className="text-sm text-muted-foreground">
                Un clic génère tous les courriers Word (clients avec gain fiscal &gt; 250 CHF) et télécharge un fichier ZIP.
              </p>
            </div>
            <div className="flex gap-2 flex-wrap shrink-0">
              <Button
                className="bg-[#002FA7] hover:bg-[#00248a] font-bold gap-2"
                disabled={generatingCourriers || !canEditSuivi}
                onClick={generateCourriers}
                data-testid="suivi-3p-generate-courriers"
              >
                {generatingCourriers ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                {generatingCourriers
                  ? "Génération…"
                  : selectedIds.length
                    ? `GÉNÉRER (${selectedIds.length})`
                    : "GÉNÉRER TOUS LES COURRIERS"}
              </Button>
              <Button
                variant="outline"
                className="gap-1.5 font-semibold"
                disabled={downloadingCourriers}
                onClick={downloadAllCourriers}
                data-testid="suivi-3p-download-courriers"
              >
                {downloadingCourriers ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Télécharger le ZIP
              </Button>
              {canEditSuivi && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={markOffresEnvoyees}
                  disabled={bulkStatutBusy || loading}
                  className="gap-1.5 border-amber-500/40 text-amber-900 hover:bg-amber-50"
                  data-testid="suivi-3p-bulk-offre-envoyee"
                >
                  {bulkStatutBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  {selectedIds.length
                    ? `Offre envoyée (${selectedIds.length})`
                    : "Offres envoyées (PDF + gain > 250)"}
                </Button>
              )}
            </div>
          </div>
        </Card>

        <Card className="px-4 py-3.5 mb-4 border-[#002FA7]/30 bg-white shadow-sm" data-testid="suivi-3p-geo-filter">
          <p className="text-sm font-semibold text-[#002FA7] mb-2">
            Filtrer : Suivi 3P – Frontaliers / Suisses
          </p>
          <div className="flex flex-wrap gap-2">
            {SUIVI_3P_GEO_OPTIONS.map((opt) => {
              const count =
                opt.id === "all"
                  ? (stats?.total ?? 0)
                  : opt.id === "frontaliers"
                    ? (stats?.frontaliers ?? 0)
                    : (stats?.suisses ?? 0);
              const active = geoFilter === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setGeoFilter(opt.id)}
                  className={`text-sm px-3.5 py-2 rounded-lg transition-colors border ${
                    active
                      ? "bg-[#002FA7] text-white font-semibold border-[#002FA7] shadow-sm"
                      : "bg-secondary/60 text-foreground border-border/80 hover:border-[#002FA7]/40"
                  }`}
                  data-testid={`suivi-3p-geo-${opt.id}`}
                  aria-pressed={active}
                >
                  {opt.label} · {count}
                </button>
              );
            })}
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">
            Selon l&apos;adresse (France → Frontalier, Suisse → Suisse). Les deux listes ne se mélangent pas.
          </p>
        </Card>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3 mb-5">
          <Kpi
            testid="suivi-3p-kpi-total"
            icon={Users}
            label="Clients suivis"
            value={stats?.total ?? "—"}
            accent="bg-[#002FA7]/10 text-[#002FA7]"
            selected={kpiFilter === "all"}
            onClick={() => {
              setKpiFilter("all");
              setStatut("all");
            }}
          />
          <Kpi
            testid="suivi-3p-kpi-analyses"
            icon={FileSearch}
            label="Analyses réalisées"
            value={stats?.analyses_realisees ?? "—"}
            accent="bg-sky-100 text-sky-700"
            selected={kpiFilter === "analyses"}
            onClick={() => applyKpiFilter("analyses")}
          />
          <Kpi
            testid="suivi-3p-kpi-gain"
            icon={PiggyBank}
            label="Gain fiscal proposé"
            value={formatChf(stats?.gain_fiscal_total)}
            accent="bg-emerald-100 text-emerald-700"
            selected={kpiFilter === "gain"}
            onClick={() => applyKpiFilter("gain")}
          />
          <Kpi
            testid="suivi-3p-kpi-rdv"
            icon={CalendarDays}
            label="Rendez-vous pris"
            value={stats?.rdv_pris ?? "—"}
            accent="bg-violet-100 text-violet-800"
            selected={kpiFilter === "rdv"}
            onClick={() => applyKpiFilter("rdv")}
          />
          <Kpi
            testid="suivi-3p-kpi-signes"
            icon={PenLine}
            label="Contrats signés"
            value={stats?.contrats_signes ?? "—"}
            accent="bg-amber-100 text-amber-800"
            selected={kpiFilter === "signes"}
            onClick={() => applyKpiFilter("signes")}
          />
        </div>

        <Card className="p-5 mb-5 border-border/80" data-testid="suivi-3p-rdv-panel">
          <div className="mb-4">
            <p className="text-sm font-semibold text-[#002FA7]">Suivi des rendez-vous</p>
            <p className="text-xs text-muted-foreground mt-1">
              Activité commerciale issue du suivi commercial des fiches clients.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
            <button
              type="button"
              onClick={() => applyKpiFilter("rdv")}
              className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                kpiFilter === "rdv"
                  ? "border-violet-400 bg-violet-50"
                  : "border-border/70 bg-secondary/20 hover:border-violet-300/60"
              }`}
              data-testid="suivi-3p-rdv-stat-pris"
            >
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground font-medium">
                <CalendarDays className="h-3.5 w-3.5 text-violet-700" />
                RDV pris
              </div>
              <p className="font-display font-black text-2xl mt-1.5 tabular-nums text-violet-900">
                {stats?.rdv_pris ?? 0}
              </p>
            </button>
            <button
              type="button"
              onClick={() => applyKpiFilter("contactes")}
              className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                kpiFilter === "contactes"
                  ? "border-emerald-400 bg-emerald-50"
                  : "border-border/70 bg-secondary/20 hover:border-emerald-300/60"
              }`}
              data-testid="suivi-3p-rdv-stat-contactes"
            >
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground font-medium">
                <PhoneCall className="h-3.5 w-3.5 text-emerald-700" />
                Clients contactés
              </div>
              <p className="font-display font-black text-2xl mt-1.5 tabular-nums text-emerald-900">
                {stats?.clients_contactes ?? 0}
              </p>
            </button>
            <button
              type="button"
              onClick={() => {
                setKpiFilter("all");
                setStatut("Offre envoyée");
                setTimeout(() => {
                  tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                }, 50);
              }}
              className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                statut === "Offre envoyée"
                  ? "border-amber-400 bg-amber-50"
                  : "border-border/70 bg-secondary/20 hover:border-amber-300/60"
              }`}
              data-testid="suivi-3p-rdv-stat-courrier-envoye"
            >
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground font-medium">
                <Mail className="h-3.5 w-3.5 text-amber-700" />
                Courrier envoyé
              </div>
              <p className="font-display font-black text-2xl mt-1.5 tabular-nums text-amber-900">
                {stats?.by_statut?.["Offre envoyée"] ?? stats?.offres_envoyees ?? 0}
              </p>
            </button>
          </div>

          <div className="rounded-lg border border-[#002FA7]/25 bg-[#002FA7]/5 px-4 py-3 mb-5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[#002FA7]">Liste d&apos;appels pour la téléphoniste</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Excel (.xlsx) — choisissez le périmètre, les colonnes et le regroupement avant export.
              </p>
            </div>
            <Button
              className="gap-1.5 shrink-0 bg-[#002FA7] hover:bg-[#00248a] text-white font-semibold w-full sm:w-auto"
              disabled={exportingSuivi || loading}
              onClick={() => setExportOpen(true)}
              data-testid="suivi-3p-export-telephoniste-bar"
            >
              {exportingSuivi ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Exporter le suivi 3e pilier
            </Button>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              Prochains rendez-vous
            </p>
            {upcomingRdvs.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center border border-dashed rounded-md">
                Aucun rendez-vous à venir. Ajoutez une date dans le suivi commercial d&apos;une fiche.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-md border border-border/70">
                <table className="w-full text-sm" data-testid="suivi-3p-upcoming-rdv-table">
                  <thead>
                    <tr className="border-b border-border/60 bg-secondary/30 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">Client</th>
                      <th className="px-3 py-2.5 font-medium hidden sm:table-cell">Conseiller</th>
                      <th className="px-3 py-2.5 font-medium whitespace-nowrap">Date du RDV</th>
                      <th className="px-3 py-2.5 font-medium w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {upcomingRdvs.map((rdv) => (
                      <tr
                        key={`${rdv.id}-${rdv.date_rdv}`}
                        className="border-b border-border/40 last:border-0 cursor-pointer transition-colors hover:bg-[#002FA7]/[0.04]"
                        onClick={() => navigate(`/suivi-3p/${rdv.id}`)}
                        data-testid={`suivi-3p-upcoming-rdv-${rdv.id}`}
                      >
                        <td className="px-4 py-2.5 font-medium">
                          {rdv.prenom} {rdv.nom}
                        </td>
                        <td className="px-3 py-2.5 text-muted-foreground hidden sm:table-cell">
                          {rdv.conseiller || "—"}
                        </td>
                        <td className="px-3 py-2.5 tabular-nums whitespace-nowrap font-medium text-violet-900">
                          {formatDateFr(rdv.date_rdv)}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <ChevronRight className="h-4 w-4 text-muted-foreground/40 inline-block" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>

        {isGlobal && sortedConseillers.length > 0 && (
          <Card className="px-4 py-3 mb-4 border-border/80" data-testid="suivi-3p-conseiller-bars">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Filtrer par conseiller</p>
                <span className="text-[11px] text-muted-foreground/80 tabular-nums">
                  {totalConseillerClients}
                </span>
              </div>
              {filterConseiller !== "all" && (
                <button
                  type="button"
                  onClick={resetConseillerFilter}
                  className="text-[11px] text-[#002FA7] hover:underline underline-offset-2"
                >
                  Réinitialiser
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-4 gap-y-1.5 max-h-[7.5rem] overflow-y-auto pr-1">
              {sortedConseillers.map((c) => {
                const total = c.total || 0;
                const pct = Math.max(total > 0 ? 8 : 0, Math.round((total / maxConseillerTotal) * 100));
                const active = filterConseiller === c.conseiller;
                return (
                  <button
                    key={c.conseiller}
                    type="button"
                    onClick={() => applyConseillerFilter(c.conseiller)}
                    className={`w-full text-left rounded-md px-2 py-1 transition-colors ${
                      active ? "bg-[#002FA7]/8 ring-1 ring-[#002FA7]/25" : "hover:bg-secondary/60"
                    }`}
                    data-testid={`suivi-3p-agent-${c.conseiller}`}
                    aria-pressed={active}
                  >
                    <div className="flex items-center justify-between gap-2 mb-0.5">
                      <span className={`text-xs truncate ${active ? "font-semibold text-[#002FA7]" : "text-foreground/90"}`}>
                        {c.conseiller}
                      </span>
                      <span className={`text-[10px] tabular-nums shrink-0 ${active ? "font-semibold text-[#002FA7]" : "text-muted-foreground"}`}>
                        {total}
                      </span>
                    </div>
                    <div className="h-1 rounded-full bg-secondary overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${active ? "bg-[#002FA7]" : "bg-[#002FA7]/60"}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </Card>
        )}

        <div className="flex flex-wrap gap-1.5 mb-4">
          <button
            type="button"
            onClick={() => setStatut("all")}
            className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
              statut === "all"
                ? "bg-[#002FA7] text-white font-medium shadow-sm"
                : "bg-secondary/80 text-muted-foreground hover:bg-secondary hover:text-foreground"
            }`}
          >
            Tous · {stats?.total ?? 0}
          </button>
          {statutCounts.map(({ id, count }) => (
            <button
              key={id}
              type="button"
              onClick={() => setStatut(id)}
              className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                statut === id
                  ? `${SUIVI_3P_STATUT_STYLE[id] || ""} font-medium`
                  : "bg-secondary/80 text-muted-foreground hover:bg-secondary hover:text-foreground"
              }`}
            >
              {id} · {count}
            </button>
          ))}
        </div>

        {isAdmin && pending.length > 0 && (
          <Card className="p-4 mb-5 border-amber-200 bg-amber-50/40">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="h-4 w-4 text-amber-700" />
              <p className="text-sm font-semibold text-amber-900">
                Documents à vérifier ({pending.length})
              </p>
            </div>
            <p className="text-xs text-amber-800/80 mb-3">
              PDF non associés automatiquement (nom/prénom introuvable ou ambigu). Liez-les manuellement.
            </p>
            <ul className="space-y-2 max-h-64 overflow-y-auto">
              {pending.map((doc) => (
                <li key={doc.id} className="flex items-center justify-between gap-3 p-2.5 rounded-md border border-amber-200 bg-white">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{doc.original_filename}</p>
                    <p className="text-xs text-muted-foreground">
                      {doc.parsed_nom && doc.parsed_prenom
                        ? `Lu : ${doc.parsed_prenom} ${doc.parsed_nom}`
                        : "Nom non détecté"}
                      {doc.match_reason ? ` · ${doc.match_reason}` : ""}
                      {doc.source_folder ? ` · ${doc.source_folder}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => openPending(doc)} title="Ouvrir">
                      <ExternalLink className="h-4 w-4" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => openAssign(doc)} title="Lier">
                      <Link2 className="h-4 w-4" />
                    </Button>
                    <Button size="icon" variant="ghost" className="h-8 w-8 text-rose-600" onClick={() => deletePending(doc)} title="Ignorer">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <div ref={tableRef} className="space-y-3">
        {(selectedConseillerMeta || kpiFilter !== "all" || geoFilter !== "all" || q.trim()) && (
          <div
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#002FA7]/15 bg-[#002FA7]/[0.03] px-3 py-2"
            data-testid="suivi-3p-active-filters"
          >
            <p className="text-xs sm:text-sm text-[#002FA7]">
              {selectedConseillerMeta && (
                <>
                  Filtre : <span className="font-semibold">{selectedConseillerMeta.conseiller}</span>
                  {" "}({selectedConseillerMeta.total})
                </>
              )}
              {selectedConseillerMeta && (kpiFilter !== "all" || geoFilter !== "all" || q.trim()) && <span className="text-muted-foreground"> · </span>}
              {geoFilter === "frontaliers" && <span className="font-semibold">Suivi 3P – Frontaliers</span>}
              {geoFilter === "suisses" && <span className="font-semibold">Suivi 3P – Suisses</span>}
              {geoFilter !== "all" && (kpiFilter !== "all" || q.trim()) && <span className="text-muted-foreground"> · </span>}
              {kpiFilter === "analyses" && <span>Analyses réalisées</span>}
              {kpiFilter === "gain" && <span>Gain fiscal proposé</span>}
              {kpiFilter === "signes" && <span>Contrats signés</span>}
              {kpiFilter !== "all" && q.trim() && <span className="text-muted-foreground"> · </span>}
              {q.trim() && <span>Recherche « {q.trim()} »</span>}
              <span className="text-muted-foreground"> · {displayedRows.length} affiché{displayedRows.length === 1 ? "" : "s"}</span>
            </p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-[#002FA7]"
              onClick={() => {
                resetConseillerFilter();
                setKpiFilter("all");
                setGeoFilter("all");
                setQ("");
                setStatut("all");
              }}
              data-testid="suivi-3p-reset-filters"
            >
              Réinitialiser
            </Button>
          </div>
        )}

        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            data-testid="suivi-3p-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Rechercher un client, conjoint, conseiller…"
            className="pl-10 h-11 rounded-xl border-border/80 bg-white shadow-sm"
          />
        </div>

        <Card className="p-0 overflow-hidden border-border/80 shadow-sm">
          {loading ? (
            <p className="text-sm text-muted-foreground p-10 text-center">Chargement…</p>
          ) : displayedRows.length === 0 ? (
            <p className="text-sm text-muted-foreground p-10 text-center">
              Aucun client pour ces filtres.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="suivi-3p-table">
                <thead>
                  <tr className="border-b border-border/60 bg-secondary/30 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-2.5 font-medium w-10">
                      <input
                        type="checkbox"
                        checked={allVisibleSelected}
                        onChange={toggleSelectAllVisible}
                        onClick={(e) => e.stopPropagation()}
                        aria-label="Sélectionner tous les clients visibles"
                        data-testid="suivi-3p-select-all"
                        className="h-4 w-4 accent-[#002FA7]"
                      />
                    </th>
                    <th className="px-4 py-2.5 font-medium">Client</th>
                    <th className="px-3 py-2.5 font-medium hidden lg:table-cell">Résidence</th>
                    <th className="px-3 py-2.5 font-medium">Civilité</th>
                    <th className="px-3 py-2.5 font-medium hidden md:table-cell">Conseiller</th>
                    <th className="px-3 py-2.5 font-medium">Statut</th>
                    <th className="px-3 py-2.5 font-medium">Analyses</th>
                    <th className="px-3 py-2.5 font-medium text-right">Gain fiscal</th>
                    <th className="px-2 py-2.5 font-medium text-center w-12" title="Contact effectué">Contact</th>
                    <th className="px-2 py-2.5 font-medium text-center w-12" title="Rendez-vous pris">RDV</th>
                    <th className="px-3 py-2.5 font-medium hidden sm:table-cell">Date RDV</th>
                    <th className="px-3 py-2.5 font-medium w-8" />
                  </tr>
                </thead>
                <tbody>
                  {displayedRows.map((r) => {
                    const gain = r.gain_fiscal_estime;
                    const hasGain = gain != null && Number(gain) !== 0 && !Number.isNaN(Number(gain));
                    return (
                      <tr
                        key={r.id}
                        className="group border-b border-border/40 last:border-0 cursor-pointer transition-colors hover:bg-[#002FA7]/[0.04]"
                        onClick={() => navigate(`/suivi-3p/${r.id}`)}
                      >
                        <td
                          className="px-3 py-3 w-10"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={selectedIds.includes(r.id)}
                            onChange={(e) => toggleSelected(r.id, e)}
                            aria-label={`Sélectionner ${r.prenom} ${r.nom}`}
                            data-testid={`suivi-3p-select-${r.id}`}
                            className="h-4 w-4 accent-[#002FA7]"
                          />
                        </td>
                        <td className="px-4 py-3">
                          <p className="font-medium text-foreground group-hover:text-[#002FA7] transition-colors">
                            {r.prenom} {r.nom}
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[220px] md:max-w-none">
                            {r.conjoint ? `Conjoint : ${r.conjoint}` : (r.etat_civil || "—")}
                            <span className="md:hidden inline-flex items-center gap-1">
                              {" · "}
                              <InlineConseillerCell
                                row={r}
                                isGlobal={isGlobal}
                                savingId={savingConseillerRowId}
                                options={mergedConseillerOptions}
                                onSave={saveConseiller}
                                compact
                                className="inline text-xs"
                              />
                            </span>
                          </p>
                          {r.residence_suivi && (
                            <span className={`lg:hidden mt-1 inline-flex text-[10px] font-medium px-1.5 py-0.5 rounded ${SUIVI_3P_GEO_STYLE[r.residence_suivi] || "bg-slate-100 text-slate-700"}`}>
                              {r.residence_suivi}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-3 hidden lg:table-cell">
                          {r.residence_suivi ? (
                            <span className={`inline-flex text-[11px] font-medium px-2 py-0.5 rounded ${SUIVI_3P_GEO_STYLE[r.residence_suivi] || "bg-slate-100 text-slate-700"}`}>
                              {r.residence_suivi}
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </td>
                        <td
                          className="px-3 py-3 align-middle"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Select
                            value={r.sexe || "unset"}
                            onValueChange={(v) => saveSexe(r.id, v)}
                            disabled={!canEditSuivi || savingSexeRowId === r.id}
                          >
                            <SelectTrigger
                              className={`h-8 w-[8.5rem] text-xs ${r.sexe ? "" : "border-amber-400 text-amber-800"}`}
                              data-testid={`suivi-3p-row-sexe-${r.id}`}
                            >
                              <SelectValue placeholder="À renseigner" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="unset">À renseigner</SelectItem>
                              <SelectItem value="Homme">M. Homme</SelectItem>
                              <SelectItem value="Femme">Mme Femme</SelectItem>
                            </SelectContent>
                          </Select>
                        </td>
                        <td
                          className="px-3 py-3 hidden md:table-cell align-middle"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <InlineConseillerCell
                            row={r}
                            isGlobal={isGlobal}
                            savingId={savingConseillerRowId}
                            options={mergedConseillerOptions}
                            onSave={saveConseiller}
                            className="text-muted-foreground"
                          />
                        </td>
                        <td className="px-3 py-3">
                          <span className={`inline-flex text-[11px] leading-none px-2 py-1 rounded-full font-medium ${SUIVI_3P_STATUT_STYLE[r.statut_suivi] || ""}`}>
                            {r.statut_suivi}
                          </span>
                        </td>
                        <td
                          className="px-3 py-3"
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {r.has_analyse_3p || r.has_analyse_fortune ? (
                            <div className="inline-flex flex-wrap items-center gap-1.5">
                              {r.has_analyse_3p && (
                                <span className="text-xs text-muted-foreground whitespace-nowrap">
                                  3e Pilier
                                </span>
                              )}
                              {r.has_analyse_3p && r.has_analyse_fortune && (
                                <span className="text-muted-foreground/50 text-xs">·</span>
                              )}
                              {r.has_analyse_fortune && (
                                <button
                                  type="button"
                                  title={
                                    r.analyse_fortune_doc_id
                                      ? "Ouvrir l’Analyse Fortune"
                                      : "Analyse Fortune"
                                  }
                                  disabled={!r.analyse_fortune_doc_id}
                                  onClick={async (e) => {
                                    e.stopPropagation();
                                    if (!r.analyse_fortune_doc_id) return;
                                    try {
                                      await openAuthenticatedBlob(
                                        `/suivi-3p/documents/${r.analyse_fortune_doc_id}/download`
                                      );
                                    } catch {
                                      /* 401 géré par l’interceptor */
                                    }
                                  }}
                                  data-testid={`suivi-3p-fortune-${r.id}`}
                                  className="inline-flex items-center rounded-md bg-amber-500 text-white px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase shadow-sm hover:bg-amber-600 disabled:opacity-70 disabled:cursor-default transition-colors"
                                >
                                  Fortune
                                </button>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted-foreground/60">—</span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-right">
                          {hasGain ? (
                            <span className="inline-flex items-center rounded-full bg-emerald-500/10 text-emerald-800 ring-1 ring-inset ring-emerald-500/20 px-2.5 py-1 text-xs font-semibold tabular-nums">
                              {formatChf(gain)}
                            </span>
                          ) : (
                            <span className="text-muted-foreground/60 tabular-nums">—</span>
                          )}
                        </td>
                        <td className="px-2 py-3 text-center">
                          <BoolMark yes={Boolean(r.client_contacte)} label="Contact effectué" />
                        </td>
                        <td className="px-2 py-3 text-center">
                          <BoolMark yes={Boolean(r.rdv_pris)} label="Rendez-vous pris" />
                        </td>
                        <td className="px-3 py-3 text-muted-foreground hidden sm:table-cell tabular-nums whitespace-nowrap">
                          {r.rdv_pris && r.date_rdv ? formatDateFr(r.date_rdv) : "—"}
                        </td>
                        <td className="px-3 py-3 text-right">
                          <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-[#002FA7] transition-colors inline-block" />
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

      <Dialog open={createOpen} onOpenChange={(open) => { setCreateOpen(open); if (!open) setForm(emptyForm); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display">Nouveau client Suivi 3P</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-2">
            Le client sera également créé ou lié dans la base Clients.
          </p>
          <div className="space-y-1.5 py-1">
            <Label className="text-xs text-muted-foreground">Client existant (optionnel)</Label>
            <ClientPicker
              value={form.linkedClient}
              onSelect={(client) => {
                if (!client) {
                  setForm((prev) => ({ ...prev, client_id: null, linkedClient: null }));
                  return;
                }
                setForm((prev) => ({
                  ...prev,
                  client_id: client.id,
                  linkedClient: client,
                  prenom: client.prenom || prev.prenom,
                  nom: client.nom || prev.nom,
                  date_naissance: toSwissDate(client.date_naissance) || prev.date_naissance,
                  etat_civil: client.etat_civil || prev.etat_civil,
                }));
              }}
              placeholder="Rechercher dans Clients…"
            />
          </div>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Prénom</Label>
              <Input value={form.prenom} onChange={(e) => setForm({ ...form, prenom: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Nom</Label>
              <Input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Date de naissance</Label>
              <Input
                type="text"
                inputMode="numeric"
                placeholder="jj.mm.aaaa"
                value={form.date_naissance}
                onChange={(e) => setForm({ ...form, date_naissance: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">État civil</Label>
              <Input value={form.etat_civil} onChange={(e) => setForm({ ...form, etat_civil: e.target.value })} />
            </div>
            <div className="space-y-1.5 col-span-2">
              <Label className="text-xs text-muted-foreground">Conjoint (optionnel)</Label>
              <Input value={form.conjoint} onChange={(e) => setForm({ ...form, conjoint: e.target.value })} />
            </div>
            {isGlobal && (
              <div className="space-y-1.5 col-span-2">
                <Label className="text-xs text-muted-foreground">Conseiller</Label>
                <ConseillerCombobox
                  value={form.conseiller || ""}
                  onChange={(v) => setForm({ ...form, conseiller: v })}
                  options={byConseiller.map((c) => c.conseiller).filter(Boolean)}
                  placeholder="Choisir ou saisir un nom…"
                  data-testid="suivi-3p-field-conseiller"
                />
                <p className="text-[11px] text-muted-foreground">
                  Choisissez dans la liste ou tapez un nouveau nom.
                </p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Annuler</Button>
            <Button onClick={createClient} disabled={saving} className="bg-[#002FA7] hover:bg-[#00248a]">
              {saving ? "Création…" : "Créer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display">Lier le document</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground">
            {assignDoc?.original_filename}
            {assignDoc?.parsed_prenom ? ` — détecté : ${assignDoc.parsed_prenom} ${assignDoc.parsed_nom}` : ""}
          </p>
          <div className="space-y-1.5 py-2">
            <Label className="text-xs text-muted-foreground">Client Suivi 3P</Label>
            <Select value={assignClientId} onValueChange={setAssignClientId}>
              <SelectTrigger><SelectValue placeholder="Choisir un client" /></SelectTrigger>
              <SelectContent>
                {allClients.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.prenom} {c.nom}{c.conseiller ? ` (${c.conseiller})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignOpen(false)}>Annuler</Button>
            <Button onClick={confirmAssign} className="bg-[#002FA7] hover:bg-[#00248a]">Lier</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={exportOpen} onOpenChange={setExportOpen}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="suivi-3p-export-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Exporter le suivi 3e pilier</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-2">
            Les filtres actifs (conseiller, statut, recherche, KPI) sont appliqués avant l&apos;export.
          </p>

          <div className="space-y-4 py-1">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Clients à inclure
              </Label>
              <div className="space-y-2">
                {[
                  {
                    id: "a_appeler",
                    title: "Clients à appeler",
                    hint: `Courrier envoyé / non contactés — ~${exportCallableHint} visible(s) avec filtres actuels`,
                  },
                  {
                    id: "liste_filtree",
                    title: "Liste filtrée actuelle",
                    hint: `${exportFilteredCount} client(s) affiché(s) dans le tableau`,
                  },
                  {
                    id: "selection",
                    title: "Sélection du tableau",
                    hint: exportSelectionCount
                      ? `${exportSelectionCount} client(s) coché(s)`
                      : "Cochez des lignes dans le tableau ci-dessous",
                  },
                ].map((opt) => (
                  <label
                    key={opt.id}
                    className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
                      exportScope === opt.id
                        ? "border-[#002FA7]/40 bg-[#002FA7]/5"
                        : "border-border/70 hover:border-[#002FA7]/20"
                    } ${opt.id === "selection" && !exportSelectionCount ? "opacity-70" : ""}`}
                  >
                    <input
                      type="radio"
                      name="export-scope"
                      className="mt-1"
                      checked={exportScope === opt.id}
                      onChange={() => setExportScope(opt.id)}
                      disabled={opt.id === "selection" && !exportSelectionCount}
                    />
                    <span>
                      <span className="text-sm font-medium block">{opt.title}</span>
                      <span className="text-xs text-muted-foreground">{opt.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Regroupement Excel
              </Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {[
                  { id: "par_conseiller", title: "Un onglet par conseiller", hint: "Recommandé pour la téléphoniste" },
                  { id: "feuille_unique", title: "Une seule feuille", hint: "Tous les clients sur un onglet" },
                ].map((opt) => (
                  <label
                    key={opt.id}
                    className={`rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${
                      exportGrouping === opt.id
                        ? "border-[#002FA7]/40 bg-[#002FA7]/5"
                        : "border-border/70 hover:border-[#002FA7]/20"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <input
                        type="radio"
                        name="export-grouping"
                        className="mt-1"
                        checked={exportGrouping === opt.id}
                        onChange={() => setExportGrouping(opt.id)}
                      />
                      <span>
                        <span className="text-sm font-medium block">{opt.title}</span>
                        <span className="text-xs text-muted-foreground">{opt.hint}</span>
                      </span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Colonnes
                </Label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-[11px] text-[#002FA7] hover:underline"
                    onClick={() => setExportColumnKeys(
                      Object.fromEntries(DEFAULT_SUIVI_3P_EXPORT_COLUMN_KEYS.map((k) => [k, true]))
                    )}
                  >
                    Tout cocher
                  </button>
                  <button
                    type="button"
                    className="text-[11px] text-muted-foreground hover:underline"
                    onClick={() => setExportColumnKeys(
                      Object.fromEntries(DEFAULT_SUIVI_3P_EXPORT_COLUMN_KEYS.map((k) => [k, false]))
                    )}
                  >
                    Tout décocher
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1">
                {SUIVI_3P_EXPORT_COLUMNS.map((col) => (
                  <label
                    key={col.key}
                    className="flex items-center gap-2 text-sm rounded-md border border-border/60 px-2.5 py-2 cursor-pointer hover:bg-secondary/40"
                  >
                    <Checkbox
                      checked={Boolean(exportColumnKeys[col.key])}
                      onCheckedChange={(v) => toggleExportColumn(col.key, Boolean(v))}
                    />
                    <span className="text-xs leading-snug">{col.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setExportOpen(false)} disabled={exportingSuivi}>
              Annuler
            </Button>
            <Button
              className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
              disabled={exportingSuivi}
              onClick={runExportSuivi3P}
              data-testid="suivi-3p-export-confirm"
            >
              {exportingSuivi ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              Télécharger Excel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(addressReport)} onOpenChange={(open) => !open && setAddressReport(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Récapitulatif import adresses</DialogTitle>
          </DialogHeader>
          {addressReport && (
            <div className="space-y-3 text-sm">
              <p>
                <strong>{addressReport.updated_count || 0}</strong> mise(s) à jour ·{" "}
                <strong>{addressReport.skipped || 0}</strong> inchangé(s) ·{" "}
                <strong>{addressReport.error_count || 0}</strong> erreur(s)
                {" "}({addressReport.rows_read || 0} ligne(s) lues)
              </p>
              {(addressReport.updated || []).length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-muted-foreground uppercase mb-1">Adresses mises à jour</p>
                  <ul className="space-y-1 max-h-40 overflow-y-auto text-xs">
                    {addressReport.updated.map((u) => (
                      <li key={u.client_id}>
                        {u.prenom} {u.nom} — {[u.adresse, u.npa, u.ville].filter(Boolean).join(", ")}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {(addressReport.errors || []).length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-red-700 uppercase mb-1">Erreurs</p>
                  <ul className="space-y-1 max-h-40 overflow-y-auto text-xs text-red-700">
                    {addressReport.errors.map((err, i) => (
                      <li key={`${i}-${err}`}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setAddressReport(null)} className="bg-[#002FA7] hover:bg-[#00248a]">Fermer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(courrierReport)} onOpenChange={(open) => !open && setCourrierReport(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display">Génération terminée</DialogTitle>
          </DialogHeader>
          {courrierReport && (
            <div className="space-y-2 text-sm">
              <p><strong>{courrierReport.analyzed ?? 0}</strong> clients analysés</p>
              <p><strong>{courrierReport.eligible ?? 0}</strong> clients avec un gain fiscal &gt; 250 CHF</p>
              <p><strong>{courrierReport.generated ?? 0}</strong> courriers générés{courrierReport.updated ? ` (${courrierReport.updated} mis à jour)` : ""}</p>
              <p><strong>{courrierReport.excluded ?? 0}</strong> clients exclus car gain fiscal ≤ 250 CHF (aucun courrier)</p>
              {courrierReport.removed > 0 && (
                <p><strong>{courrierReport.removed}</strong> courrier(s) retiré(s) des dossiers non éligibles</p>
              )}
              {courrierReport.error_count > 0 && (
                <p className="text-red-700">{courrierReport.error_count} erreur(s)</p>
              )}
            </div>
          )}
          <DialogFooter className="gap-2 sm:gap-2">
            <Button variant="outline" onClick={() => setCourrierReport(null)}>Fermer</Button>
            <Button
              className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
              onClick={downloadAllCourriers}
              disabled={downloadingCourriers || !(courrierReport?.generated)}
            >
              {downloadingCourriers ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              TÉLÉCHARGER TOUS LES COURRIERS
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ClientDuplicateDialog
        open={Boolean(duplicateConflict)}
        onOpenChange={(v) => { if (!v) setDuplicateConflict(null); }}
        conflict={duplicateConflict}
      />
    </Layout>
  );
}
