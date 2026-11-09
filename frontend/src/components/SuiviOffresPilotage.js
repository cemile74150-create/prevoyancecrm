import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  PRIORITE_STYLE,
  clientLabel,
  compagniesAffichees,
  formatDateFr,
  prioriteLabel,
  rdvClientAffiche,
} from "@/lib/demandesOffres";
import {
  A_ATTRIBUER_COLUMNS,
  CARTES_COMMERCIALES,
  CARTES_GLOBALES,
  COMMERCIAL_LABELS,
  COMMERCIAL_ORDER,
  COMMERCIAL_STYLE,
  DETAIL_COLUMNS,
  FILTRES_VIDES,
  NON_ATTRIBUE,
  NON_ATTRIBUE_LABEL,
  REPARTITION_COLUMNS,
  TRAITEMENT_ORDER,
  TRAITEMENT_STYLE,
  boutonTraiter,
  commercialCode,
  commercialLabel,
  filtrerDetail,
  filtresActifs,
  gestionnaireLabel,
  listerNonAttribuees,
  tauxSignatureLabel,
  trierRepartition,
} from "@/lib/suiviOffres";
import OffresStatsMensuelles from "@/components/OffresStatsMensuelles";
import { ArrowDown, ArrowUp, ChevronRight, Loader2, UserCheck, UserCog, X } from "lucide-react";

const PERIODES = [
  { id: "all", label: "Toute période" },
  { id: "today", label: "Aujourd'hui" },
  { id: "week", label: "Cette semaine" },
  { id: "month", label: "Ce mois" },
  { id: "year", label: "Cette année" },
  { id: "custom", label: "Personnalisé" },
];

function Compteur({ label, value, active, onClick, tone = "", testId, hint }) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className={`rounded-lg border px-3 py-3 text-left transition ${tone || "border-slate-200 bg-white"} ${
        active ? "ring-2 ring-[#002FA7] ring-offset-1" : "hover:border-[#002FA7]/40"
      }`}
    >
      <span className="block text-[12px] font-medium text-slate-600 leading-snug">{label}</span>
      <span className="block text-2xl font-bold tabular-nums mt-1 text-slate-900">{value ?? 0}</span>
      {hint ? <span className="block text-[10px] text-slate-500 mt-1 leading-snug">{hint}</span> : null}
    </button>
  );
}

export function TraitementBadge({ row }) {
  const code = row?.statut_traitement;
  if (!code) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${TRAITEMENT_STYLE[code] || ""}`}>
      {row.statut_traitement_label || code}
    </span>
  );
}

export function CommercialBadge({ row }) {
  const code = commercialCode(row);
  return (
    <span
      className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${COMMERCIAL_STYLE[code] || ""}`}
      data-testid="statut-commercial-badge"
    >
      {commercialLabel(row)}
    </span>
  );
}

export function ReattribuerDialog({ row, open, onOpenChange, onDone }) {
  const [gestionnaires, setGestionnaires] = useState([]);
  const [cible, setCible] = useState("");
  const [motif, setMotif] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCible("");
    setMotif("");
    api.get("/demandes-offres/gestionnaires")
      .then((res) => setGestionnaires(Array.isArray(res.data) ? res.data : []))
      .catch(() => setGestionnaires([]));
  }, [open]);

  const submit = async () => {
    if (!cible || !row?.id) return;
    setSaving(true);
    try {
      const res = await api.post(`/demandes-offres/${row.id}/reattribuer`, { gestionnaire_id: cible, motif });
      toast.success(`Dossier attribué à ${res.data?.gestionnaire_nom || "ce gestionnaire"}`);
      onOpenChange(false);
      onDone?.(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Réattribution impossible");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Réattribuer le dossier</DialogTitle>
          <DialogDescription>
            {row?.numero || ""} · actuellement : {gestionnaireLabel(row)}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Nouveau gestionnaire</Label>
            <Select value={cible} onValueChange={setCible}>
              <SelectTrigger data-testid="reattribuer-cible"><SelectValue placeholder="Choisir un gestionnaire" /></SelectTrigger>
              <SelectContent>
                {gestionnaires
                  .filter((g) => g.id !== row?.gestionnaire_id)
                  .map((g) => <SelectItem key={g.id} value={g.id}>{g.nom}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Motif (facultatif)</Label>
            <Input value={motif} maxLength={500} onChange={(e) => setMotif(e.target.value)} placeholder="Absence, répartition de charge…" />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
            <Button
              type="button"
              disabled={!cible || saving}
              onClick={submit}
              className="text-white bg-[#002FA7] hover:bg-[#00237d]"
              data-testid="reattribuer-confirmer"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
              Réattribuer
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Bouton « M'attribuer » : prise en charge atomique côté API. */
export function useAttribuer(onDone) {
  const [busyId, setBusyId] = useState(null);
  const attribuer = useCallback(async (row, event) => {
    event?.stopPropagation?.();
    if (!row?.id) return;
    setBusyId(row.id);
    try {
      const res = await api.post(`/demandes-offres/${row.id}/attribuer`);
      toast.success("Dossier attribué à vous-même");
      onDone?.(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Attribution impossible");
      onDone?.(null);
    } finally {
      setBusyId(null);
    }
  }, [onDone]);
  return { attribuer, busyId };
}

function SelectFiltre({ label, value, onChange, options, testId, width = "w-[170px]" }) {
  return (
    <div className="space-y-1">
      <Label className="text-[11px] text-slate-500">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className={`h-9 ${width}`} data-testid={testId}><SelectValue /></SelectTrigger>
        <SelectContent>
          {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Agent : résultat commercial de ses propres demandes et décisions à renseigner. */
export function SuiviMesOffres() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/demandes-offres/pilotage")
      .then((res) => setData(res.data || null))
      .catch(() => setData(null));
  }, []);

  if (!data) return null;
  const ind = data.indicateurs || {};
  const decisions = data.decisions_a_renseigner || [];
  return (
    <Card className="p-5 border-border space-y-3" data-testid="suivi-mes-offres">
      <div>
        <h2 className="font-display font-bold text-lg tracking-tight">Suivi de mes offres</h2>
        <p className="text-xs text-slate-500">
          Indiquez sur chaque demande si l&apos;offre a été transmise au client, signée ou non signée.
        </p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {CARTES_COMMERCIALES.map((c) => (
          <div key={c.tag} className="rounded-lg border border-slate-200 bg-white px-3 py-3">
            <span className="block text-[12px] font-medium text-slate-600 leading-snug">{c.label}</span>
            <span className="block text-2xl font-bold tabular-nums mt-1">{ind[c.tag] ?? 0}</span>
          </div>
        ))}
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3">
          <span className="block text-[12px] font-medium text-emerald-900">Taux de signature</span>
          <span className="block text-2xl font-bold tabular-nums mt-1">{tauxSignatureLabel(data.taux_signature)}</span>
        </div>
      </div>
      {decisions.length > 0 && (
        <div>
          <p className="text-sm font-semibold text-slate-800 mb-1.5">
            Statut agent à renseigner ({decisions.length})
          </p>
          <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
            {decisions.slice(0, 20).map((d) => (
              <li key={d.id}>
                <button
                  type="button"
                  className={`w-full flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                    d.depasse_14j ? "bg-red-50/70" : ""
                  }`}
                  onClick={() => navigate(`/demandes-offres/${d.id}`)}
                >
                  <span><strong>{d.numero}</strong> · {d.client}</span>
                  <span className={`text-xs ${d.depasse_14j ? "font-bold text-red-700" : "text-slate-500"}`}>
                    {d.transmis_agent_at
                      ? `Offres transmises à l'agent le ${formatDateFr(d.transmis_agent_at)} · ${d.jours ?? 0} j`
                      : `Documents transmis le ${formatDateFr(d.docs_transmis_at)} · transmission complète non enregistrée`}
                    {" · "}{d.statut_commercial_label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export default function SuiviOffresPilotage({ filterConseiller, conseillerNames = [], typeOptions = [] }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [periode, setPeriode] = useState("all");
  const [dateDe, setDateDe] = useState("");
  const [dateA, setDateA] = useState("");
  const [agent, setAgent] = useState("all");
  const [filtres, setFiltres] = useState(FILTRES_VIDES);
  const [tri, setTri] = useState({ key: "attribues", direction: "desc" });
  const [reattribuer, setReattribuer] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const conseiller = filterConseiller && filterConseiller !== "all" ? filterConseiller : agent;

  const load = useCallback(async () => {
    setLoading(true);
    const params = { periode };
    if (periode === "custom") {
      if (dateDe) params.date_de = dateDe;
      if (dateA) params.date_a = dateA;
    }
    if (conseiller !== "all") params.conseiller = conseiller;
    try {
      const [pil, list] = await Promise.all([
        api.get("/demandes-offres/pilotage", { params }),
        api.get("/demandes-offres", { params: { ...params, limit: 1000 } }),
      ]);
      setData(pil.data || null);
      setRows(Array.isArray(list.data) ? list.data : []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suivi des offres indisponible");
      setData(null);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [periode, dateDe, dateA, conseiller]);

  useEffect(() => { load(); }, [load]);

  const { attribuer, busyId } = useAttribuer(useCallback(() => load(), [load]));

  const ind = data?.indicateurs || {};
  const setFiltre = (key, value) => setFiltres((prev) => ({ ...prev, [key]: value }));
  const toggleTag = (tag, extra = {}) => {
    setFiltres((prev) => (prev.tag === tag && !Object.keys(extra).length
      ? { ...prev, tag: null }
      : { ...prev, ...extra, tag }));
  };

  const detail = useMemo(() => filtrerDetail(rows, filtres), [rows, filtres]);
  const nonAttribuees = useMemo(() => listerNonAttribuees(rows), [rows]);
  const repartition = useMemo(
    () => trierRepartition(data?.gestionnaires || [], tri.key, tri.direction),
    [data, tri],
  );

  const agentOptions = useMemo(() => {
    const names = new Set(conseillerNames || []);
    rows.forEach((r) => { if (r.agent_label) names.add(r.agent_label); });
    return [...names].sort((a, b) => a.localeCompare(b, "fr"));
  }, [rows, conseillerNames]);

  const compagnieOptions = useMemo(() => {
    const set = new Set();
    rows.forEach((r) => compagniesAffichees(r).forEach((c) => set.add(c)));
    return [...set].sort((a, b) => a.localeCompare(b, "fr"));
  }, [rows]);

  const typeChoices = useMemo(() => {
    const map = new Map((typeOptions || []).map((t) => [t.id, t.label]));
    rows.forEach((r) => { if (r.form_type && !map.has(r.form_type)) map.set(r.form_type, r.form_type_label || r.form_type); });
    return [...map.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, "fr"));
  }, [rows, typeOptions]);

  const gestionnaireOptions = useMemo(() => {
    const map = new Map();
    (data?.gestionnaires || []).forEach((g) => { if (g.id !== NON_ATTRIBUE) map.set(g.id, g.nom); });
    rows.forEach((r) => { if (r.gestionnaire_id && !map.has(r.gestionnaire_id)) map.set(r.gestionnaire_id, r.gestionnaire_nom); });
    return [...map.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, "fr"));
  }, [data, rows]);

  const sortBy = (key) => setTri((prev) => ({
    key,
    direction: prev.key === key && prev.direction === "desc" ? "asc" : "desc",
  }));

  const filtrerGestionnaire = (ligne, tag) => {
    setFiltres({ ...FILTRES_VIDES, gestionnaire: ligne.id, tag: tag || null });
    document.getElementById("suivi-offres-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const openFiche = (row) => navigate(`/demandes-offres/${row.id}`);
  const labelTag = data?.labels?.[filtres.tag] || (filtres.tag === "attente_compagnie_ou_relance" ? "En attente compagnie" : filtres.tag);

  return (
    <div className="space-y-6" data-testid="suivi-offres-pilotage">
      <Card className="p-4 border-border">
        <div className="flex flex-wrap items-end gap-3">
          <SelectFiltre
            label="Période"
            value={periode}
            onChange={setPeriode}
            testId="pilotage-filter-periode"
            options={PERIODES.map((p) => ({ value: p.id, label: p.label }))}
          />
          {periode === "custom" && (
            <>
              <div className="space-y-1">
                <Label className="text-[11px] text-slate-500">Du</Label>
                <Input type="date" value={dateDe} onChange={(e) => setDateDe(e.target.value)} className="h-9 w-[150px]" />
              </div>
              <div className="space-y-1">
                <Label className="text-[11px] text-slate-500">Au</Label>
                <Input type="date" value={dateA} onChange={(e) => setDateA(e.target.value)} className="h-9 w-[150px]" />
              </div>
            </>
          )}
          {!(filterConseiller && filterConseiller !== "all") && (
            <SelectFiltre
              label="Agent demandeur"
              value={agent}
              onChange={setAgent}
              testId="pilotage-filter-agent"
              options={[{ value: "all", label: "Tous les agents" }, ...agentOptions.map((n) => ({ value: n, label: n }))]}
            />
          )}
          <p className="text-[11px] text-slate-500 max-w-sm leading-snug">
            Les compteurs suivent la période et l&apos;agent choisis. Cliquez un compteur pour filtrer le tableau détaillé.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => { load(); setRefreshKey((k) => k + 1); }}
            disabled={loading}
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
            Actualiser
          </Button>
        </div>
      </Card>

      {/* B3 — vue globale */}
      <section className="space-y-2">
        <h2 className="font-display font-bold text-lg tracking-tight">Vue globale du service</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          {CARTES_GLOBALES.map((c) => (
            <Compteur
              key={c.tag}
              testId={`pilotage-carte-${c.tag}`}
              label={c.label}
              value={ind[c.tag]}
              tone={c.tone}
              active={filtres.tag === c.tag}
              onClick={() => toggleTag(c.tag)}
            />
          ))}
        </div>
      </section>

      {/* A1 — six statuts de traitement */}
      <section className="space-y-2">
        <h2 className="font-display font-bold text-lg tracking-tight">Avancement du traitement</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          {(data?.traitement || TRAITEMENT_ORDER.map((code) => ({ code, tag: `traitement:${code}`, label: code, count: 0 }))).map((t) => (
            <Compteur
              key={t.code}
              testId={`pilotage-traitement-${t.code}`}
              label={t.label}
              value={t.count}
              tone={`border ${TRAITEMENT_STYLE[t.code] || ""}`}
              active={filtres.tag === t.tag}
              onClick={() => toggleTag(t.tag)}
            />
          ))}
        </div>
      </section>

      {/* A3 — résultat commercial */}
      <section className="space-y-2">
        <h2 className="font-display font-bold text-lg tracking-tight">Résultat commercial</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
          {CARTES_COMMERCIALES.map((c) => (
            <Compteur
              key={c.tag}
              testId={`pilotage-commercial-${c.tag.replace(":", "-")}`}
              label={c.label}
              value={ind[c.tag]}
              active={filtres.tag === c.tag}
              onClick={() => toggleTag(c.tag)}
            />
          ))}
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3" data-testid="pilotage-taux-signature">
            <span className="block text-[12px] font-medium text-emerald-900">Taux de signature</span>
            <span className="block text-2xl font-bold tabular-nums mt-1 text-emerald-950">{tauxSignatureLabel(data?.taux_signature)}</span>
            <span className="block text-[10px] text-emerald-900/80 mt-1 leading-snug">{data?.taux_signature_definition}</span>
          </div>
        </div>
      </section>

      <OffresStatsMensuelles
        periode={periode}
        dateDe={dateDe}
        dateA={dateA}
        conseiller={conseiller}
        filtres={filtres}
        refreshKey={refreshKey}
      />

      {/* B8 — pipeline en trois sections */}
      <Card className="p-5 border-border">
        <h2 className="font-display font-bold text-lg tracking-tight mb-3">Pipeline des offres</h2>
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_2.4fr_1.3fr] gap-4">
          {(data?.pipeline || []).map((section) => (
            <div key={section.id} data-testid={`pipeline-section-${section.id}`}>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-2">{section.label}</p>
              <div className="flex flex-wrap items-stretch gap-1.5">
                {section.etapes.map((step, idx) => (
                  <React.Fragment key={step.tag}>
                    {idx > 0 && <ChevronRight className="h-4 w-4 self-center text-slate-300 hidden sm:block" />}
                    <button
                      type="button"
                      data-testid={`pipeline-${step.tag.replace(":", "-")}`}
                      onClick={() => toggleTag(step.tag)}
                      className={`flex-1 min-w-[96px] rounded-md border px-2.5 py-2 text-left transition ${
                        filtres.tag === step.tag ? "border-[#002FA7] bg-[#002FA7]/5 ring-1 ring-[#002FA7]/30" : "border-slate-200 hover:border-[#002FA7]/40"
                      }`}
                    >
                      <span className="block text-[11px] text-slate-600 leading-tight">{step.label}</span>
                      <span className="block text-lg font-bold tabular-nums mt-0.5">{step.count}</span>
                    </button>
                  </React.Fragment>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* B4 — répartition des gestionnaires */}
      <Card className="p-5 border-border overflow-hidden">
        <h2 className="font-display font-bold text-lg tracking-tight">Répartition et activité des gestionnaires d&apos;offres</h2>
        <p className="text-xs text-slate-500 mt-0.5 mb-3">
          « Attribués » : dossiers actuellement sous la responsabilité du gestionnaire. Les autres colonnes décrivent ces dossiers
          (elles ne s&apos;additionnent pas). Cliquez un nombre pour afficher les dossiers concernés.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[760px]" data-testid="repartition-gestionnaires">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wide text-slate-500">
                {REPARTITION_COLUMNS.map((col) => (
                  <th key={col.key} className="py-2 px-2 font-semibold whitespace-nowrap">
                    <button type="button" className="inline-flex items-center gap-1 hover:text-slate-900" onClick={() => sortBy(col.key)}>
                      {col.label}
                      {tri.key === col.key ? (tri.direction === "desc" ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />) : null}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {repartition.map((ligne) => (
                <tr
                  key={ligne.id}
                  className={`border-b border-slate-100 ${ligne.id === NON_ATTRIBUE ? "bg-amber-50/60" : ""} ${
                    filtres.gestionnaire === ligne.id ? "ring-1 ring-inset ring-[#002FA7]/40" : ""
                  }`}
                  data-testid={`repartition-${ligne.id}`}
                >
                  {REPARTITION_COLUMNS.map((col) => (
                    <td key={col.key} className="py-2 px-2 tabular-nums">
                      {col.key === "nom" ? (
                        <button
                          type="button"
                          className={`text-left hover:underline ${ligne.id === NON_ATTRIBUE ? "font-semibold text-amber-900" : "font-medium text-slate-900"}`}
                          onClick={() => filtrerGestionnaire(ligne, null)}
                        >
                          {ligne.nom}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className={`min-w-[2rem] text-left hover:underline ${ligne[col.key] ? "text-slate-900 font-semibold" : "text-slate-400"} ${
                            col.key === "en_retard" && ligne[col.key] ? "text-red-700" : ""
                          }`}
                          onClick={() => filtrerGestionnaire(ligne, col.tag)}
                        >
                          {ligne[col.key] ?? 0}
                        </button>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-5 border-t border-amber-200/80 pt-4" data-testid="dossiers-a-attribuer">
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
            <h3 className="font-display font-bold text-base tracking-tight text-amber-950">
              Dossiers à attribuer
              <span className="ml-2 tabular-nums text-sm font-semibold text-amber-800">({nonAttribuees.length})</span>
            </h3>
            <p className="text-xs text-slate-500 max-w-xl">
              Liste des demandes sans gestionnaire. « M&apos;attribuer » prend le dossier en charge sans ouvrir la fiche
              (réservé aux gestionnaires / process).
            </p>
          </div>
          {nonAttribuees.length === 0 ? (
            <p className="text-sm text-slate-400 py-4 text-center">Aucun dossier à attribuer.</p>
          ) : (
            <div className="overflow-x-auto max-h-[420px] overflow-y-auto rounded-md border border-amber-100 bg-amber-50/30">
              <table className="w-full text-sm min-w-[980px]">
                <thead className="sticky top-0 bg-amber-50/95 backdrop-blur-sm">
                  <tr className="border-b border-amber-200/80 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    {A_ATTRIBUER_COLUMNS.map((h) => (
                      <th key={h} className="py-2 px-2 font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {nonAttribuees.map((r) => {
                    const rdv = rdvClientAffiche(r);
                    const comps = compagniesAffichees(r);
                    return (
                      <tr
                        key={r.id}
                        role="button"
                        tabIndex={0}
                        title="Ouvrir la fiche"
                        className={`border-b border-amber-100/80 cursor-pointer transition-colors hover:bg-white ${r.urgente ? "bg-red-50/50" : ""}`}
                        data-testid={`a-attribuer-${r.id}`}
                        onClick={() => openFiche(r)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            openFiche(r);
                          }
                        }}
                      >
                        <td className="py-2 px-2 whitespace-nowrap">
                          <span className="font-semibold text-slate-900">{r.numero || "—"}</span>
                          <span className="block text-[11px] text-slate-500">{clientLabel(r)}</span>
                        </td>
                        <td className="py-2 px-2 font-bold text-slate-900 whitespace-nowrap">{r.agent_label || "—"}</td>
                        <td className="py-2 px-2 whitespace-nowrap text-slate-700">{formatDateFr(r.date_envoi)}</td>
                        <td className="py-2 px-2 whitespace-nowrap text-slate-700">{rdv.date ? formatDateFr(rdv.date) : "—"}</td>
                        <td className="py-2 px-2 max-w-[150px] truncate text-slate-600" title={r.form_type_label || ""}>
                          {r.form_type_label || r.type_pilier || "—"}
                        </td>
                        <td className="py-2 px-2 max-w-[140px] truncate text-slate-600" title={comps.join(", ")}>
                          {comps.join(", ") || "—"}
                        </td>
                        <td className="py-2 px-2"><TraitementBadge row={r} /></td>
                        <td className="py-2 px-2 tabular-nums">{r.jours_depuis ?? "—"}</td>
                        <td className="py-2 px-2 whitespace-nowrap">
                          {r.urgente ? (
                            <span className="inline-flex rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-semibold text-white mr-1">URGENT</span>
                          ) : null}
                          <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${PRIORITE_STYLE[r.priorite] || PRIORITE_STYLE.normal}`}>
                            {prioriteLabel(r.priorite)}
                          </span>
                        </td>
                        <td className="py-2 px-2" onClick={(e) => e.stopPropagation()}>
                          {r.can_attribuer ? (
                            <Button
                              size="sm"
                              className="h-7 text-xs gap-1 whitespace-nowrap text-white bg-[#002FA7] hover:bg-[#00237d]"
                              disabled={busyId === r.id}
                              onClick={(e) => attribuer(r, e)}
                              data-testid={`a-attribuer-btn-${r.id}`}
                            >
                              {busyId === r.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <UserCheck className="h-3 w-3" />}
                              M&apos;attribuer
                            </Button>
                          ) : (
                            <span className="text-[11px] text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>

      {/* B5 — tableau détaillé */}
      <Card className="p-5 border-border overflow-hidden" id="suivi-offres-detail">
        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
          <div>
            <h2 className="font-display font-bold text-lg tracking-tight">Détail des demandes</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {filtres.tag ? <>Indicateur : <strong className="text-slate-800">{labelTag}</strong> · </> : null}
              <span className="tabular-nums">{detail.length}</span> dossier{detail.length > 1 ? "s" : ""}
            </p>
          </div>
          {filtresActifs(filtres) && (
            <Button type="button" variant="ghost" size="sm" className="gap-1 text-xs" onClick={() => setFiltres(FILTRES_VIDES)}>
              <X className="h-3.5 w-3.5" /> Effacer les filtres
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-2 mb-3" data-testid="detail-filtres">
          <SelectFiltre
            label="Gestionnaire"
            value={filtres.gestionnaire}
            onChange={(v) => setFiltre("gestionnaire", v)}
            testId="detail-filter-gestionnaire"
            options={[
              { value: "all", label: "Tous" },
              { value: NON_ATTRIBUE, label: NON_ATTRIBUE_LABEL },
              ...gestionnaireOptions,
            ]}
          />
          <SelectFiltre
            label="Type d'offre"
            value={filtres.type}
            onChange={(v) => setFiltre("type", v)}
            testId="detail-filter-type"
            options={[{ value: "all", label: "Tous" }, ...typeChoices]}
          />
          <SelectFiltre
            label="Compagnie"
            value={filtres.compagnie}
            onChange={(v) => setFiltre("compagnie", v)}
            testId="detail-filter-compagnie"
            width="w-[150px]"
            options={[{ value: "all", label: "Toutes" }, ...compagnieOptions.map((c) => ({ value: c, label: c }))]}
          />
          <SelectFiltre
            label="Statut traitement"
            value={filtres.traitement}
            onChange={(v) => setFiltre("traitement", v)}
            testId="detail-filter-traitement"
            width="w-[220px]"
            options={[
              { value: "all", label: "Tous" },
              ...(data?.traitement || []).map((t) => ({ value: t.code, label: t.label })),
            ]}
          />
          <SelectFiltre
            label="Statut commercial"
            value={filtres.commercial}
            onChange={(v) => setFiltre("commercial", v)}
            testId="detail-filter-commercial"
            width="w-[200px]"
            options={[{ value: "all", label: "Tous" }, ...COMMERCIAL_ORDER.map((c) => ({ value: c, label: COMMERCIAL_LABELS[c] }))]}
          />
          <SelectFiltre
            label="Priorité / urgence"
            value={filtres.priorite}
            onChange={(v) => setFiltre("priorite", v)}
            testId="detail-filter-priorite"
            width="w-[160px]"
            options={[
              { value: "all", label: "Toutes" },
              { value: "urgence_agent", label: "Urgence agent" },
              { value: "urgent", label: "Urgent" },
              { value: "surveiller", label: "À surveiller" },
              { value: "normal", label: "Normal" },
            ]}
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[1200px]" data-testid="detail-demandes">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wide text-slate-500">
                {DETAIL_COLUMNS.map((h) => <th key={h} className="py-2 px-2 font-semibold whitespace-nowrap">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={DETAIL_COLUMNS.length} className="py-10 text-center text-slate-400"><Loader2 className="h-4 w-4 animate-spin inline mr-1" /> Chargement…</td></tr>
              ) : detail.length === 0 ? (
                <tr><td colSpan={DETAIL_COLUMNS.length} className="py-10 text-center text-slate-400">Aucune demande pour ces filtres.</td></tr>
              ) : detail.map((r) => {
                const bouton = boutonTraiter(r);
                const rdv = rdvClientAffiche(r);
                const comps = compagniesAffichees(r);
                return (
                  <tr
                    key={r.id}
                    role="button"
                    tabIndex={0}
                    title="Ouvrir la fiche"
                    data-testid={`detail-row-${r.id}`}
                    className={`border-b border-slate-100 cursor-pointer transition-colors hover:bg-slate-50 ${r.urgente ? "bg-red-50/40" : ""}`}
                    onClick={() => openFiche(r)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openFiche(r);
                      }
                    }}
                  >
                    <td className="py-2 px-2 whitespace-nowrap">
                      <span className="font-semibold text-slate-900">{r.numero || "—"}</span>
                      <span className="block text-[11px] text-slate-500">{clientLabel(r)}</span>
                    </td>
                    <td className="py-2 px-2 font-bold text-slate-900 whitespace-nowrap" data-testid="detail-agent">{r.agent_label || "—"}</td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      {r.gestionnaire_id ? (
                        <span className="font-medium text-slate-800">{r.gestionnaire_nom}</span>
                      ) : (
                        <span className="inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-900">
                          Non attribuée
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-2 whitespace-nowrap text-slate-700">{formatDateFr(r.date_envoi)}</td>
                    <td className="py-2 px-2 whitespace-nowrap text-slate-700">{rdv.date ? formatDateFr(rdv.date) : "—"}</td>
                    <td className="py-2 px-2 max-w-[150px] truncate text-slate-600" title={r.form_type_label || ""}>{r.form_type_label || r.type_pilier || "—"}</td>
                    <td className="py-2 px-2 max-w-[150px] truncate text-slate-600" title={comps.join(", ")}>{comps.join(", ") || "—"}</td>
                    <td className="py-2 px-2"><TraitementBadge row={r} /></td>
                    <td className="py-2 px-2"><CommercialBadge row={r} /></td>
                    <td className="py-2 px-2 tabular-nums">{r.jours_depuis ?? "—"}</td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      {r.urgente ? (
                        <span className="inline-flex rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-semibold text-white mr-1">URGENT</span>
                      ) : null}
                      <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${PRIORITE_STYLE[r.priorite] || PRIORITE_STYLE.normal}`}>
                        {prioriteLabel(r.priorite)}
                      </span>
                    </td>
                    <td className="py-2 px-2 max-w-[160px] truncate text-xs text-slate-500" title={r.derniere_action || ""}>{r.derniere_action || "—"}</td>
                    <td className="py-2 px-2" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          className={`h-7 rounded-md px-2.5 text-xs font-medium whitespace-nowrap ${bouton.className}`}
                          onClick={() => openFiche(r)}
                          data-testid={`detail-traiter-${r.id}`}
                        >
                          {bouton.label}
                        </button>
                        {r.can_attribuer ? (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs gap-1 whitespace-nowrap"
                            disabled={busyId === r.id}
                            onClick={(e) => attribuer(r, e)}
                            data-testid={`detail-attribuer-${r.id}`}
                          >
                            <UserCheck className="h-3 w-3" /> M&apos;attribuer
                          </Button>
                        ) : null}
                        {r.can_reattribuer ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 text-xs gap-1 whitespace-nowrap"
                            onClick={() => setReattribuer(r)}
                            data-testid={`detail-reattribuer-${r.id}`}
                            title="Réattribuer le dossier"
                          >
                            <UserCog className="h-3 w-3" /> Réattribuer
                          </Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <ReattribuerDialog
        row={reattribuer}
        open={Boolean(reattribuer)}
        onOpenChange={(open) => { if (!open) setReattribuer(null); }}
        onDone={() => load()}
      />
    </div>
  );
}
