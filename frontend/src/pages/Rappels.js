import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Bell, AlertTriangle, Pencil, Plus, Trash2, Check, CalendarClock, PauseCircle, List, CalendarDays } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import RappelsCalendar from "@/components/RappelsCalendar";
import {
  RAPPEL_STATUT_LABEL,
  RAPPEL_STATUT_STYLE,
  formatRappelAttributionLine,
  formatRappelDateFr,
  formatRappelDateTimeFr,
  rappelEmailHistoryEntries,
  rappelEmailHistoryLabel,
  rappelStatutEffectif,
  rappelStoredStatut,
} from "@/lib/rappels";

const emptyForm = {
  client_id: "",
  titre: "",
  description: "",
  date: "",
  heure: "",
  priorite: "normale",
  send_email: true,
  notify_crm: true,
};

const PRIORITE_STYLE = {
  haute: "text-red-700 bg-red-50 border-red-100",
  normale: "text-slate-700 bg-slate-50 border-slate-200",
  faible: "text-emerald-700 bg-emerald-50 border-emerald-100",
};

const PRIORITE_LABEL = { haute: "Haute", normale: "Normale", faible: "Faible" };

function formatDateFr(iso) {
  return formatRappelDateFr(iso);
}

function rappelTimestamp(r) {
  const d = (r.date || "").slice(0, 10);
  const t = r.heure ? String(r.heure).slice(0, 5) : "00:00";
  if (!d) return Number.POSITIVE_INFINITY;
  const dt = new Date(`${d}T${t}:00`);
  return Number.isFinite(dt.getTime()) ? dt.getTime() : Number.POSITIVE_INFINITY;
}

function monthKeyFromDate(iso) {
  const d = String(iso || "").slice(0, 10);
  if (!/^\d{4}-\d{2}/.test(d)) return "sans-date";
  return d.slice(0, 7);
}

function currentMonthKey() {
  const parts = new Intl.DateTimeFormat("fr-CH", {
    timeZone: "Europe/Zurich",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const year = parts.find((p) => p.type === "year")?.value;
  const month = parts.find((p) => p.type === "month")?.value;
  return year && month ? `${year}-${month}` : "";
}

function monthTitle(key) {
  if (key === "sans-date") return "Sans date";
  const [year, month] = key.split("-");
  const label = new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("fr-FR", {
    month: "long",
    year: "numeric",
  });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function groupRappelsByMonth(list) {
  const sorted = [...list].sort((a, b) => {
    const diff = rappelTimestamp(a) - rappelTimestamp(b);
    if (diff !== 0) return diff;
    const createdA = a.created_at ? new Date(a.created_at).getTime() : Number.POSITIVE_INFINITY;
    const createdB = b.created_at ? new Date(b.created_at).getTime() : Number.POSITIVE_INFINITY;
    if (createdA !== createdB) return createdA - createdB;
    return String(a.id).localeCompare(String(b.id));
  });

  const groups = new Map();
  for (const r of sorted) {
    const key = monthKeyFromDate(r.date);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }

  const current = currentMonthKey();
  const keys = [...groups.keys()];
  const currentKeys = keys.filter((k) => k === current);
  const futureKeys = keys.filter((k) => k !== "sans-date" && k > current).sort();
  const pastKeys = keys.filter((k) => k !== "sans-date" && k < current).sort().reverse();
  const undatedKeys = keys.filter((k) => k === "sans-date");

  return [...currentKeys, ...futureKeys, ...pastKeys, ...undatedKeys].map((key) => ({
    key,
    title: monthTitle(key),
    isCurrent: key === current,
    items: groups.get(key) || [],
  }));
}

function RappelCard({
  d,
  canEdit,
  onNavigate,
  onStatut,
  onDone,
  onPostpone,
  onEdit,
  onRemove,
  now,
}) {
  const stored = rappelStoredStatut(d);
  const effectif = rappelStatutEffectif(d, now);
  return (
    <Card
      data-testid={`rappel-global-${d.id}`}
      className={`p-4 flex items-start gap-3 transition-colors ${
        effectif === "termine"
          ? "opacity-75"
          : effectif === "en_attente"
            ? "border-amber-200 bg-amber-50/40"
            : effectif === "echeance_passee" || d.priorite === "haute"
              ? "border-red-300 bg-red-50/60 ring-1 ring-red-200"
              : "hover:border-[#002FA7]/40"
      }`}
      data-testid={d.priorite === "haute" ? `rappel-urgent-${d.id}` : `rappel-card-${d.id}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <button
            type="button"
            onClick={() => d.client_id && onNavigate(d.client_id)}
            className="text-left min-w-0 flex-1 group"
          >
            <p className="text-sm font-semibold text-foreground group-hover:text-[#002FA7] transition-colors">
              {d.client_name || "Client"}
              {d.numero_dossier ? (
                <span className="ml-2 text-xs font-normal text-muted-foreground font-mono">
                  {d.numero_dossier}
                </span>
              ) : null}
            </p>
            <p className={`text-sm mt-1 font-medium ${effectif === "termine" ? "line-through text-muted-foreground" : ""}`}>
              {d.titre}
            </p>
          </button>
          {canEdit ? (
            <Select value={stored} onValueChange={(v) => onStatut(d, v)}>
              <SelectTrigger
                className={`h-8 w-[9.5rem] text-xs ${RAPPEL_STATUT_STYLE[effectif] || ""}`}
                data-testid={`rappel-statut-${d.id}`}
              >
                <SelectValue>{RAPPEL_STATUT_LABEL[effectif]}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="a_faire">À faire</SelectItem>
                <SelectItem value="en_attente">En attente</SelectItem>
                <SelectItem value="termine">Terminé</SelectItem>
              </SelectContent>
            </Select>
          ) : (
            <span className={`inline-flex text-xs font-medium border px-2 py-0.5 rounded ${RAPPEL_STATUT_STYLE[effectif] || ""}`}>
              {RAPPEL_STATUT_LABEL[effectif]}
            </span>
          )}
        </div>
        {d.description ? (
          <p className="text-xs text-muted-foreground mt-1.5 whitespace-pre-wrap">{d.description}</p>
        ) : null}
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <span className="text-xs text-muted-foreground">
            {formatDateFr(d.date)}
            {d.heure ? ` · ${d.heure}` : ""}
          </span>
          <span className={`inline-flex text-xs font-medium border px-2 py-0.5 rounded ${PRIORITE_STYLE[d.priorite] || PRIORITE_STYLE.normale}`}>
            {d.priorite === "haute" && <AlertTriangle className="h-3 w-3 mr-1" />}
            {PRIORITE_LABEL[d.priorite] || "Normale"}
          </span>
          {effectif === "echeance_passee" && (
            <span className="inline-flex text-xs font-semibold border px-2 py-0.5 rounded text-red-800 bg-red-50 border-red-200">
              Échéance passée
            </span>
          )}
          {d.send_email !== false && (
            <span className="inline-flex text-xs font-medium border px-2 py-0.5 rounded text-sky-800 bg-sky-50 border-sky-100">
              {d.email_sent
                ? (d.email_relance_count > 0
                  ? `E-mail + ${d.email_relance_count} relance${d.email_relance_count > 1 ? "s" : ""}`
                  : "E-mail envoyé")
                : "E-mail prévu"}
            </span>
          )}
          {d.notify_crm === false && (
            <span className="inline-flex text-xs font-medium border px-2 py-0.5 rounded text-slate-600 bg-slate-50 border-slate-200">
              Hors ordre du jour
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-2" data-testid={`rappel-attribution-${d.id}`}>
          {formatRappelAttributionLine(d)}
        </p>
        {rappelEmailHistoryEntries(d).length > 0 && (
          <div className="mt-3 rounded-md border border-sky-100 bg-sky-50/50 px-3 py-2" data-testid={`rappel-email-history-${d.id}`}>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-sky-900 mb-1.5">
              Historique des e-mails / relances
            </p>
            <ul className="space-y-1">
              {rappelEmailHistoryEntries(d).map((h, idx) => (
                <li key={h.log_id || `${h.sent_at}-${idx}`} className="text-xs text-sky-950 flex flex-wrap gap-x-2">
                  <span className="font-medium tabular-nums">{formatRappelDateTimeFr(h.sent_at)}</span>
                  <span>—</span>
                  <span>
                    {rappelEmailHistoryLabel(h)}
                    {h.status === "failed" ? " (échec)" : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {canEdit && (
        <div className="flex flex-col gap-1">
          {stored !== "termine" && (
            <>
              {stored !== "en_attente" && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs gap-1"
                  onClick={() => onStatut(d, "en_attente")}
                  title="Mettre en attente"
                >
                  <PauseCircle className="h-3.5 w-3.5" /> En attente
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs gap-1"
                onClick={() => onDone(d, true)}
                title="Effectué"
              >
                <Check className="h-3.5 w-3.5" /> Effectué
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-8 text-xs gap-1"
                onClick={() => onPostpone(d)}
                title="Reporter de 14 jours"
              >
                <CalendarClock className="h-3.5 w-3.5" /> Reporter
              </Button>
            </>
          )}
          <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => onEdit(d)}>
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => onRemove(d)}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </Card>
  );
}

function MonthSections({ groups, sectionKey, cardProps }) {
  if (!groups.length) return null;
  return (
    <div className="space-y-8">
      {groups.map((group) => (
        <section key={`${sectionKey}-${group.key}`} data-testid={`rappel-month-${sectionKey}-${group.key}`}>
          <div className="flex items-baseline justify-between gap-3 mb-3 pb-2 border-b border-border/70">
            <h2 className="font-display font-bold text-lg tracking-tight flex items-center gap-2 flex-wrap">
              <span className={group.isCurrent ? "text-[#002FA7]" : "text-foreground"}>
                {group.title}
              </span>
              {group.isCurrent && (
                <span className="inline-flex text-[11px] font-semibold uppercase tracking-wide text-[#002FA7] bg-[#002FA7]/10 border border-[#002FA7]/20 px-2 py-0.5 rounded">
                  Mois en cours
                </span>
              )}
            </h2>
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {group.items.length} rappel{group.items.length > 1 ? "s" : ""}
            </span>
          </div>
          <div className="space-y-3">
            {group.items.map((d) => (
              <RappelCard key={d.id} d={d} {...cardProps} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export default function Rappels() {
  const [rappels, setRappels] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState("list"); // list | calendar
  const [filter, setFilter] = useState("open"); // open | waiting | done | mine | all
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [nowTick, setNowTick] = useState(() => new Date());
  const [emailLogs, setEmailLogs] = useState([]);
  const [smtpConfigured, setSmtpConfigured] = useState(null);
  const [mailStatus, setMailStatus] = useState(null);
  const navigate = useNavigate();
  const { isAdmin, hasPerm } = useAuth();
  const canEditRappels = hasPerm("rappels.edit");

  const load = async () => {
    setLoading(true);
    try {
      let params = {};
      if (viewMode === "list") {
        if (filter === "mine") {
          params = { mine: true };
        } else if (filter === "all") {
          params = {};
        } else if (filter === "waiting") {
          params = { statut: "en_attente" };
        } else if (filter === "done") {
          params = { done: true };
        } else {
          params = { done: false };
        }
      }
      // Calendrier : jeu complet, filtres côté client
      const [r, c] = await Promise.all([
        api.get("/rappels", { params }),
        api.get("/clients"),
      ]);
      setRappels(Array.isArray(r.data) ? r.data : []);
      setClients(Array.isArray(c.data) ? c.data : []);
    } catch {
      toast.error("Impossible de charger les rappels");
      setRappels([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, viewMode]);

  useEffect(() => {
    const id = setInterval(() => setNowTick(new Date()), 60000);
    return () => clearInterval(id);
  }, []);

  const openCreate = (opts = {}) => {
    setEditing(null);
    setForm({
      ...emptyForm,
      date: opts.date || "",
    });
    setDialogOpen(true);
  };

  const openEdit = (r) => {
    setEditing(r);
    setForm({
      client_id: r.client_id || "",
      titre: r.titre || "",
      description: r.description || "",
      date: (r.date || "").slice(0, 10),
      heure: r.heure || "",
      priorite: r.priorite || "normale",
      send_email: r.send_email !== false,
      notify_crm: r.notify_crm !== false,
    });
    setDialogOpen(true);
  };

  const save = async () => {
    if (!form.titre.trim()) {
      toast.error("Titre obligatoire");
      return;
    }
    if (!form.date) {
      toast.error("Date obligatoire");
      return;
    }
    if (!editing && !form.client_id) {
      toast.error("Client associé obligatoire");
      return;
    }
    if (!form.send_email && !form.notify_crm) {
      toast.error("Activez au moins l'e-mail ou la notification CRM");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        titre: form.titre.trim(),
        description: form.description.trim() || null,
        date: form.date,
        heure: form.heure || null,
        priorite: form.priorite || "normale",
        client_id: form.client_id || undefined,
        send_email: !!form.send_email,
        notify_crm: !!form.notify_crm,
      };
      if (editing) {
        await api.patch(`/rappels/${editing.id}`, payload);
        toast.success("Rappel modifié");
      } else {
        await api.post("/rappels", payload);
        toast.success("Rappel ajouté");
      }
      setDialogOpen(false);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Enregistrement impossible");
    } finally {
      setSaving(false);
    }
  };

  const setStatut = async (rappel, statut) => {
    try {
      if (statut === "termine") {
        await api.post(`/rappels/${rappel.id}/effectuer`);
      } else {
        await api.patch(`/rappels/${rappel.id}`, { statut, done: false });
      }
      toast.success(
        statut === "en_attente"
          ? "Rappel mis en attente"
          : statut === "termine"
            ? "Rappel effectué"
            : "Rappel à faire",
      );
      await load();
    } catch {
      toast.error("Impossible de mettre à jour le statut");
    }
  };

  const markDone = async (rappel, done = true) => {
    await setStatut(rappel, done ? "termine" : "a_faire");
  };

  const postponeRappel = async (rappel) => {
    try {
      const res = await api.post(`/rappels/${rappel.id}/reporter`, { days: 14 });
      const nextDate = formatDateFr(res.data?.date || "");
      toast.success(
        nextDate
          ? `Rappel reporté de 14 jours — nouvelle échéance le ${nextDate}`
          : "Rappel reporté de 14 jours",
      );
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Report impossible");
    }
  };

  const loadEmailLogs = async () => {
    if (!isAdmin) return;
    try {
      const res = await api.get("/admin/email-logs", { params: { limit: 50, type: "rappel" } });
      setEmailLogs(Array.isArray(res.data) ? res.data : []);
    } catch {
      try {
        const res = await api.get("/rappel-email-logs", { params: { limit: 50 } });
        const rows = Array.isArray(res.data) ? res.data : [];
        setEmailLogs(rows.filter((r) => !r.type || r.type === "rappel"));
      } catch {
        setEmailLogs([]);
      }
    }
  };

  useEffect(() => {
    if (isAdmin) loadEmailLogs();
    api.get("/rappels/email-status")
      .then((res) => {
        setMailStatus(res.data || null);
        setSmtpConfigured(Boolean(res.data?.smtp_configured));
      })
      .catch(() => {
        setMailStatus(null);
        setSmtpConfigured(null);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  const remove = async (rappel) => {
    if (!window.confirm("Supprimer ce rappel ?")) return;
    try {
      await api.delete(`/rappels/${rappel.id}`);
      toast.success("Rappel supprimé");
      await load();
    } catch {
      toast.error("Suppression impossible");
    }
  };

  const sortedClients = useMemo(
    () =>
      [...clients].sort((a, b) =>
        `${a.nom} ${a.prenom}`.localeCompare(`${b.nom} ${b.prenom}`, "fr"),
      ),
    [clients],
  );

  const todoRappels = useMemo(
    () => rappels.filter((r) => rappelStoredStatut(r) === "a_faire"),
    [rappels],
  );
  const waitingRappels = useMemo(
    () => rappels.filter((r) => rappelStoredStatut(r) === "en_attente"),
    [rappels],
  );
  const doneRappels = useMemo(
    () => rappels.filter((r) => rappelStoredStatut(r) === "termine"),
    [rappels],
  );
  const todoGroups = useMemo(() => groupRappelsByMonth(todoRappels), [todoRappels]);
  const waitingGroups = useMemo(() => groupRappelsByMonth(waitingRappels), [waitingRappels]);
  const doneGroups = useMemo(() => groupRappelsByMonth(doneRappels), [doneRappels]);

  const cardProps = {
    canEdit: canEditRappels,
    now: nowTick,
    onNavigate: (clientId) => navigate(`/clients/${clientId}`),
    onStatut: setStatut,
    onDone: markDone,
    onPostpone: postponeRappel,
    onEdit: openEdit,
    onRemove: remove,
  };

  return (
    <Layout>
      <div className={`animate-fade-up ${viewMode === "calendar" ? "max-w-6xl" : "max-w-3xl"}`}>
        <div className="flex items-start justify-between gap-4 flex-wrap mb-2">
          <div className="flex items-center gap-2.5">
            <Bell className="h-6 w-6 text-[#002FA7]" />
            <h1 className="font-display font-black text-3xl tracking-tight">Rappels</h1>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex rounded-lg border border-border p-0.5 bg-secondary/40" data-testid="rappels-view-toggle">
              <button
                type="button"
                onClick={() => setViewMode("list")}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  viewMode === "list" ? "bg-[#002FA7] text-white shadow-sm" : "text-muted-foreground hover:text-foreground"
                }`}
                data-testid="rappels-view-list"
              >
                <List className="h-3.5 w-3.5" /> Liste
              </button>
              <button
                type="button"
                onClick={() => setViewMode("calendar")}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  viewMode === "calendar" ? "bg-[#002FA7] text-white shadow-sm" : "text-muted-foreground hover:text-foreground"
                }`}
                data-testid="rappels-view-calendar"
              >
                <CalendarDays className="h-3.5 w-3.5" /> Calendrier
              </button>
            </div>
            {canEditRappels && (
              <Button onClick={() => openCreate()} className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5" data-testid="rappel-add">
                <Plus className="h-4 w-4" /> Ajouter un rappel
              </Button>
            )}
          </div>
        </div>
        <p className="text-muted-foreground mb-6">
          {viewMode === "calendar"
            ? "Visualisez vos rappels sur le calendrier. Cliquez une pastille pour modifier, ou une date vide pour en créer un."
            : "Planifiez vos appels et relances. Les rappels du mois en cours s'affichent en premier ; les autres mois restent regroupés en dessous. Les rappels en attente restent visibles dans leur propre section."}
        </p>
        {smtpConfigured === false && (
          <Card className="p-4 mb-5 border-amber-300 bg-amber-50 text-amber-950">
            <p className="text-sm font-semibold">Les e-mails ne partent pas encore</p>
            <p className="text-sm mt-1">
              La boîte d&apos;envoi SMTP n&apos;est pas configurée sur le serveur
              (variables <code className="text-xs">SMTP_HOST</code>, <code className="text-xs">SMTP_FROM</code>,{" "}
              <code className="text-xs">SMTP_USER</code>, <code className="text-xs">SMTP_PASSWORD</code>).
              Les rappels s&apos;affichent ici, mais aucun e-mail ne part pour le moment.
            </p>
          </Card>
        )}
        {smtpConfigured === true && mailStatus && (
          <Card className="p-4 mb-5 border-emerald-200 bg-emerald-50/60 text-emerald-950">
            <p className="text-sm font-semibold">Boîte d&apos;envoi active (rappels)</p>
            <p className="text-sm mt-1 text-emerald-900/80">
              Expéditeur : <span className="font-medium">{mailStatus.smtp_from || "—"}</span>
              {" · "}Chaque rappel est envoyé à l&apos;adresse e-mail de la personne qui l&apos;a créé.
            </p>
          </Card>
        )}

        {viewMode === "list" && (
        <div className="flex gap-2 mb-5 flex-wrap">
          {[
            { id: "open", label: "À faire" },
            { id: "waiting", label: "En attente" },
            { id: "done", label: "Terminés" },
            { id: "mine", label: "Mes rappels" },
            { id: "all", label: "Tous" },
          ].map((f) => (
            <Button
              key={f.id}
              size="sm"
              variant={filter === f.id ? "default" : "outline"}
              className={filter === f.id ? "bg-[#002FA7] hover:bg-[#00248a]" : ""}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </Button>
          ))}
        </div>
        )}

        {viewMode === "calendar" ? (
          loading ? (
            <p className="text-sm text-muted-foreground">Chargement…</p>
          ) : (
            <RappelsCalendar
              rappels={rappels}
              now={nowTick}
              canEdit={canEditRappels}
              onSelectRappel={openEdit}
              onCreateForDate={(date) => openCreate({ date })}
            />
          )
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : rappels.length === 0 ? (
          <Card className="p-10 text-center text-sm text-muted-foreground">
            Aucun rappel {filter === "open" ? "à faire" : filter === "waiting" ? "en attente" : filter === "done" ? "terminé" : filter === "mine" ? "créé par vous" : ""}.
          </Card>
        ) : (
          <div className="space-y-10">
            {(filter === "open" || filter === "all" || filter === "mine") && todoRappels.length > 0 && (
              <MonthSections groups={todoGroups} sectionKey="todo" cardProps={cardProps} />
            )}
            {(filter === "open" || filter === "waiting" || filter === "all" || filter === "mine") && waitingRappels.length > 0 && (
              <section data-testid="rappel-section-attente">
                <div className="flex items-baseline justify-between gap-3 mb-4">
                  <h2 className="font-display font-bold text-xl tracking-tight text-amber-800 flex items-center gap-2">
                    <PauseCircle className="h-5 w-5" />
                    En attente
                  </h2>
                  <span className="text-xs text-muted-foreground">
                    {waitingRappels.length} rappel{waitingRappels.length > 1 ? "s" : ""} mis de côté
                  </span>
                </div>
                <MonthSections groups={waitingGroups} sectionKey="waiting" cardProps={cardProps} />
              </section>
            )}
            {(filter === "done" || filter === "all" || filter === "mine") && doneRappels.length > 0 && (
              <section data-testid="rappel-section-termines">
                {(filter === "all" || filter === "mine") && (
                  <h2 className="font-display font-bold text-xl tracking-tight text-slate-700 mb-4">
                    Terminés
                  </h2>
                )}
                <MonthSections groups={doneGroups} sectionKey="done" cardProps={cardProps} />
              </section>
            )}
          </div>
        )}

        {isAdmin && (
          <div className="mt-10">
            <h2 className="font-display font-bold text-lg mb-3">Historique des e-mails</h2>
            <p className="text-xs text-muted-foreground mb-3">
              Uniquement les notifications de rappels (envoyées au créateur du rappel).
            </p>
            {emailLogs.length === 0 ? (
              <Card className="p-6 text-sm text-muted-foreground text-center">
                Aucun e-mail enregistré pour le moment.
              </Card>
            ) : (
              <Card className="divide-y divide-border overflow-hidden">
                {emailLogs.map((log) => {
                  const ok = log.status === "sent";
                  const isRelance = log.kind === "relance";
                  const typeLabel =
                    log.type === "demande_offre"
                      ? "Demande d'offre"
                      : log.type === "rappel"
                        ? (isRelance ? "Relance auto" : "Rappel")
                        : log.type || "E-mail";
                  return (
                    <div key={log.id} className="px-4 py-3 text-sm flex flex-wrap gap-x-4 gap-y-1 items-center">
                      <span className="text-muted-foreground min-w-[140px]">
                        {log.sent_at || log.created_at
                          ? new Date(log.sent_at || log.created_at).toLocaleString("fr-CH")
                          : "—"}
                      </span>
                      <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${
                        isRelance ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-700"
                      }`}>
                        {typeLabel}
                      </span>
                      <span className="font-medium">{log.to || log.to_email}</span>
                      <span
                        className={`inline-flex text-xs font-medium px-2 py-0.5 rounded ${
                          ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"
                        }`}
                      >
                        {ok ? "Envoyé" : "Erreur"}
                      </span>
                      <span className="text-muted-foreground truncate flex-1 min-w-[120px]">
                        {log.subject}
                        {log.rappel_count > 1 ? ` (${log.rappel_count})` : ""}
                      </span>
                      {log.from ? (
                        <span className="text-[11px] text-muted-foreground w-full sm:w-auto">
                          De : {log.from}
                        </span>
                      ) : null}
                      {!ok && log.error ? (
                        <span className="text-[11px] text-red-700 w-full">{log.error}</span>
                      ) : null}
                    </div>
                  );
                })}
              </Card>
            )}
          </div>
        )}
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display">{editing ? "Modifier le rappel" : "Nouveau rappel"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Client associé</Label>
              <Select value={form.client_id || "_none"} onValueChange={(v) => setForm({ ...form, client_id: v === "_none" ? "" : v })}>
                <SelectTrigger data-testid="rappel-client"><SelectValue placeholder="Choisir un client" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">— Choisir —</SelectItem>
                  {sortedClients.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.prenom} {c.nom}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Titre</Label>
              <Input
                data-testid="rappel-titre"
                value={form.titre}
                onChange={(e) => setForm({ ...form, titre: e.target.value })}
                placeholder="Ex. Rappeler Monsieur Dupont"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Description (optionnel)</Label>
              <Textarea
                rows={2}
                className="resize-none"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Date</Label>
                <Input type="date" data-testid="rappel-date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Heure</Label>
                <Input type="time" data-testid="rappel-heure" value={form.heure} onChange={(e) => setForm({ ...form, heure: e.target.value })} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Priorité</Label>
              <Select value={form.priorite} onValueChange={(v) => setForm({ ...form, priorite: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="faible">Faible</SelectItem>
                  <SelectItem value="normale">Normale</SelectItem>
                  <SelectItem value="haute">Haute</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2.5 pt-1">
              <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                <Checkbox
                  checked={!!form.send_email}
                  onCheckedChange={(v) => setForm({ ...form, send_email: v === true })}
                  data-testid="rappel-send-email"
                />
                <span>Envoyer un e-mail</span>
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                <Checkbox
                  checked={!!form.notify_crm}
                  onCheckedChange={(v) => setForm({ ...form, notify_crm: v === true })}
                  data-testid="rappel-notify-crm"
                />
                <span>Afficher une notification dans le CRM</span>
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Annuler</Button>
            <Button onClick={save} disabled={saving} className="bg-[#002FA7] hover:bg-[#00248a]">
              {saving ? "…" : editing ? "Enregistrer" : "Ajouter"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
