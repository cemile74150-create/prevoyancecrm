import React, { useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  EMAIL_TYPE_LABELS,
  emailTypeLabel,
  formatDateTimeFr,
} from "@/lib/demandesOffres";
import { Loader2, Mail, Paperclip, Search } from "lucide-react";
import { toast } from "sonner";

const ACCENT = "#002FA7";

function statusLabel(status) {
  const s = String(status || "").toLowerCase();
  if (s === "sent" || s === "ok" || s === "success") return "Envoyé";
  if (s === "error" || s === "failed" || s === "fail") return "Échec";
  if (s === "pending" || s === "en_cours" || s === "in_progress") return "En cours";
  if (s === "skipped") return "Ignoré";
  return status || "—";
}

function statusClass(status) {
  const s = String(status || "").toLowerCase();
  if (s === "sent" || s === "ok" || s === "success") {
    return "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200";
  }
  if (s === "error" || s === "failed" || s === "fail") {
    return "bg-rose-50 text-rose-800 ring-1 ring-inset ring-rose-200";
  }
  if (s === "pending" || s === "en_cours" || s === "in_progress") {
    return "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-200";
  }
  return "bg-slate-100 text-slate-700";
}

export default function HistoriqueEmails() {
  const { hasPerm } = useAuth();
  const canView = hasPerm("users.manage");

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [mailType, setMailType] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [selected, setSelected] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async () => {
    if (!canView) return;
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (mailType !== "all") params.type = mailType;
      if (statusFilter !== "all") params.status = statusFilter;
      if (qDebounced) params.q = qDebounced;
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      const res = await api.get("/emails", { params });
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setRows([]);
      toast.error(e?.response?.data?.detail || "Chargement des e-mails impossible");
    } finally {
      setLoading(false);
    }
  }, [canView, mailType, statusFilter, qDebounced, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const openDetail = async (row) => {
    setDetailLoading(true);
    setSelected({ ...row, _loading: true });
    try {
      const res = await api.get(`/emails/${row.id}`);
      setSelected(res.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Aperçu impossible");
      setSelected(row);
    } finally {
      setDetailLoading(false);
    }
  };

  if (!canView) {
    return (
      <Layout>
        <Card className="p-6 border-rose-200 bg-rose-50 max-w-xl">
          <h1 className="text-lg font-semibold text-rose-900">Accès restreint</h1>
          <p className="text-sm text-rose-700 mt-1">Vous n&apos;avez pas accès à l&apos;historique des e-mails.</p>
        </Card>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="animate-fade-up max-w-6xl space-y-5 pb-10" data-testid="historique-emails-page">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-800 flex items-center gap-3">
            <Mail className="h-8 w-8" style={{ color: ACCENT }} />
            Historique des e-mails
          </h1>
          <p className="text-base text-slate-500 mt-2 max-w-3xl leading-relaxed">
            Journal central de tous les e-mails envoyés par LeoSoft (offres, rappels, dossiers présentés, tests…). Cliquez sur une ligne pour le détail.
          </p>
        </div>

        <Card className="p-4 border-border/80">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Destinataire, expéditeur, client, objet, n° offre / dossier…"
                className="pl-9 h-11"
              />
            </div>
            <Select value={mailType} onValueChange={setMailType}>
              <SelectTrigger className="h-11 w-[200px]">
                <SelectValue placeholder="Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous les types</SelectItem>
                {Object.entries(EMAIL_TYPE_LABELS).map(([id, label]) => (
                  <SelectItem key={id} value={id}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-11 w-[160px]">
                <SelectValue placeholder="Statut" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous</SelectItem>
                <SelectItem value="sent">Envoyés</SelectItem>
                <SelectItem value="error">Échecs</SelectItem>
                <SelectItem value="pending">En cours</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Du</label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="h-11 w-[150px]"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Au</label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="h-11 w-[150px]"
              />
            </div>
          </div>
        </Card>

        <Card className="overflow-hidden border-border/80">
          {loading ? (
            <p className="p-8 text-sm text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
            </p>
          ) : rows.length === 0 ? (
            <p className="p-8 text-sm text-muted-foreground text-center">Aucun e-mail trouvé.</p>
          ) : (
            <div className="overflow-x-auto" data-testid="historique-emails-list">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50/80 text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-3 font-semibold whitespace-nowrap">Date</th>
                    <th className="px-4 py-3 font-semibold">Destinataire</th>
                    <th className="px-4 py-3 font-semibold">Client</th>
                    <th className="px-4 py-3 font-semibold min-w-[200px]">Objet</th>
                    <th className="px-4 py-3 font-semibold">Type</th>
                    <th className="px-4 py-3 font-semibold">Statut</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {rows.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => openDetail(r)}
                      className="cursor-pointer hover:bg-[#002FA7]/5 transition"
                    >
                      <td className="px-4 py-3 tabular-nums whitespace-nowrap text-slate-800 font-medium">
                        {formatDateTimeFr(r.sent_at || r.created_at)}
                      </td>
                      <td className="px-4 py-3 text-slate-700 max-w-[200px] truncate" title={r.to || ""}>
                        {r.to || "—"}
                      </td>
                      <td className="px-4 py-3 text-slate-800 font-medium max-w-[160px] truncate">
                        {r.client_label || "—"}
                      </td>
                      <td className="px-4 py-3 text-slate-900 max-w-[280px]">
                        <span className="line-clamp-2" title={r.subject || ""}>
                          {r.subject || "—"}
                        </span>
                        {r.numero ? (
                          <span className="block text-xs font-mono text-[#002FA7] mt-0.5">{r.numero}</span>
                        ) : r.numero_dossier ? (
                          <span className="block text-xs font-mono text-[#002FA7] mt-0.5">{r.numero_dossier}</span>
                        ) : null}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className="inline-flex rounded-full bg-slate-100 text-slate-800 px-2.5 py-0.5 text-xs font-semibold">
                          {emailTypeLabel(r.type)}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusClass(r.status)}`}>
                          {statusLabel(r.status)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Dialog open={Boolean(selected)} onOpenChange={(open) => { if (!open) setSelected(null); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5 text-[#002FA7]" />
              {selected ? emailTypeLabel(selected.type) : "Aperçu"}
            </DialogTitle>
          </DialogHeader>
          {detailLoading || selected?._loading ? (
            <p className="text-sm text-muted-foreground flex items-center gap-2 py-6">
              <Loader2 className="h-4 w-4 animate-spin" /> Chargement de l&apos;aperçu…
            </p>
          ) : selected ? (
            <div className="space-y-4 text-sm">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
                <dt className="text-muted-foreground">Date / heure</dt>
                <dd className="font-medium">{formatDateTimeFr(selected.sent_at || selected.created_at)}</dd>
                <dt className="text-muted-foreground">De</dt>
                <dd className="font-medium break-all">{selected.from || "—"}</dd>
                <dt className="text-muted-foreground">À</dt>
                <dd className="font-medium break-all">{selected.to || "—"}</dd>
                {(selected.cc || []).length > 0 && (
                  <>
                    <dt className="text-muted-foreground">Cc</dt>
                    <dd className="break-all">{selected.cc.join(", ")}</dd>
                  </>
                )}
                {(selected.bcc || []).length > 0 && (
                  <>
                    <dt className="text-muted-foreground">Cci</dt>
                    <dd className="break-all">{selected.bcc.join(", ")}</dd>
                  </>
                )}
                <dt className="text-muted-foreground">Client</dt>
                <dd className="font-medium">{selected.client_label || "—"}</dd>
                <dt className="text-muted-foreground">N° offre</dt>
                <dd className="font-mono font-medium text-[#002FA7]">{selected.numero || "—"}</dd>
                {selected.numero_dossier ? (
                  <>
                    <dt className="text-muted-foreground">N° dossier</dt>
                    <dd className="font-medium">{selected.numero_dossier}</dd>
                  </>
                ) : null}
                {selected.created_by ? (
                  <>
                    <dt className="text-muted-foreground">Déclenché par</dt>
                    <dd>{selected.created_by}</dd>
                  </>
                ) : null}
                <dt className="text-muted-foreground">Type</dt>
                <dd className="font-medium">{emailTypeLabel(selected.type)}</dd>
                <dt className="text-muted-foreground">Statut</dt>
                <dd>
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusClass(selected.status)}`}>
                    {statusLabel(selected.status)}
                  </span>
                </dd>
                <dt className="text-muted-foreground">Objet</dt>
                <dd className="font-medium">{selected.subject || "—"}</dd>
                {selected.message_id ? (
                  <>
                    <dt className="text-muted-foreground">Message-ID</dt>
                    <dd className="font-mono text-xs break-all">{selected.message_id}</dd>
                  </>
                ) : null}
                {selected.module ? (
                  <>
                    <dt className="text-muted-foreground">Module</dt>
                    <dd>{selected.module}</dd>
                  </>
                ) : null}
              </dl>

              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                  Contenu
                </p>
                {selected.body_html ? (
                  <div
                    className="rounded-md border bg-slate-50 p-3 text-sm prose prose-sm max-w-none max-h-80 overflow-y-auto"
                    dangerouslySetInnerHTML={{ __html: selected.body_html }}
                  />
                ) : (
                  <pre className="rounded-md border bg-slate-50 p-3 text-sm whitespace-pre-wrap font-sans max-h-80 overflow-y-auto">
                    {selected.body_text || selected.body_preview || "Aucun contenu enregistré pour cet e-mail."}
                  </pre>
                )}
              </div>

              {(selected.attachments || []).length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1">
                    <Paperclip className="h-3.5 w-3.5" /> Pièces jointes
                  </p>
                  <ul className="space-y-1">
                    {selected.attachments.map((a, i) => (
                      <li key={i} className="text-sm text-slate-700">
                        {typeof a === "string"
                          ? a
                          : `${a.filename || a.name || "Fichier"}${a.size != null ? ` (${a.size} o)` : ""}`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {(selected.status === "error" || selected.status === "failed") && selected.error && (
                <p className="text-sm text-rose-700 rounded-md border border-rose-200 bg-rose-50 p-3">
                  Erreur d&apos;envoi : {selected.error}
                </p>
              )}

              <div className="flex justify-end">
                <Button variant="outline" onClick={() => setSelected(null)}>Fermer</Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
