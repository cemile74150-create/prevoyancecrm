import React, { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import api, { downloadAuthenticatedBlob } from "@/lib/api";
import { toast } from "sonner";
import {
  Activity, Cloud, Database, Server, Archive, CheckCircle2, FileDown, Shield, RefreshCw, AlertTriangle, Mail,
} from "lucide-react";

const GLOBAL_STATUS = {
  ok: { emoji: "🟢", label: "Conforme", pill: "bg-emerald-50 border-emerald-200 text-emerald-800", dot: "bg-emerald-500" },
  warning: { emoji: "🟠", label: "Attention", pill: "bg-amber-50 border-amber-200 text-amber-900", dot: "bg-amber-500" },
  problem: { emoji: "🔴", label: "Problème", pill: "bg-red-50 border-red-200 text-red-800", dot: "bg-red-500" },
  unavailable: { emoji: "⚪", label: "Contrôle impossible à effectuer", pill: "bg-slate-100 border-slate-200 text-slate-700", dot: "bg-slate-400" },
};

/** Retire toute fuite éventuelle de secret dans un message d'erreur affiché. */
function sanitizeMailError(raw) {
  if (!raw) return null;
  let text = String(raw);
  text = text.replace(/SMTP_PASSWORD[=:\s]+\S+/gi, "SMTP_PASSWORD=***");
  text = text.replace(/password[=:\s]+\S+/gi, "password=***");
  text = text.replace(/pass[=:\s]+\S+/gi, "pass=***");
  return text.slice(0, 500);
}

function resolveGlobalStatus(data) {
  const s = (data?.global_status || "ok").toLowerCase();
  if (s === "warning") return GLOBAL_STATUS.warning;
  if (s === "unavailable") return GLOBAL_STATUS.unavailable;
  if (s === "problem" || s === "error") return GLOBAL_STATUS.problem;
  return GLOBAL_STATUS.ok;
}

function rowStatus(status) {
  const s = (status || "ok").toLowerCase();
  if (s === "warning") return GLOBAL_STATUS.warning;
  if (s === "unavailable") return GLOBAL_STATUS.unavailable;
  if (s === "problem" || s === "error") return GLOBAL_STATUS.problem;
  return GLOBAL_STATUS.ok;
}

function StatusPill({ status, label, className = "" }) {
  const s = rowStatus(status);
  const text = label || s.label;
  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium border ${s.pill} ${className}`}>
      <span className={`h-2.5 w-2.5 rounded-full ${s.dot}`} />
      {text}
    </span>
  );
}

function SectionCard({ title, icon: Icon, children, accent = "bg-blue-100 text-blue-700" }) {
  return (
    <Card className="p-6 border-border">
      <div className="flex items-center gap-3 mb-5">
        <div className={`h-10 w-10 rounded-md flex items-center justify-center ${accent}`}>
          <Icon className="h-5 w-5" strokeWidth={1.75} />
        </div>
        <h2 className="font-display font-bold text-lg tracking-tight">{title}</h2>
      </div>
      {children}
    </Card>
  );
}

function Metric({ label, value, large }) {
  return (
    <div className="py-2">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={`font-display font-bold tracking-tight mt-1 ${large ? "text-2xl" : "text-base"}`}>{value ?? "—"}</p>
    </div>
  );
}

function CheckItem({ label, ok }) {
  const s = ok ? GLOBAL_STATUS.ok : GLOBAL_STATUS.problem;
  return (
    <div className="flex items-center gap-2 py-1">
      <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${s.dot}`} />
      <span className="text-sm">{label}</span>
    </div>
  );
}

function formatDateFr(iso) {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

function formatHistoryDate(row) {
  if (row.checked_at) {
    try {
      return new Date(row.checked_at).toLocaleString("fr-CH", {
        day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
      });
    } catch {
      /* fall through */
    }
  }
  return formatDateFr(row.audit_day || row.date);
}

function cellStatus(row, key) {
  const block = row[key];
  if (typeof block === "string") return block;
  return block?.status || row[key] || "ok";
}

export default function SuiviTechnique() {
  const { isAdmin, user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [mailStatus, setMailStatus] = useState(null);
  const [testEmailTo, setTestEmailTo] = useState("");
  const [smtpTesting, setSmtpTesting] = useState(false);
  const [smtpTestResult, setSmtpTestResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/admin/tech-status");
      setData(res.data);
    } catch {
      toast.error("Impossible de charger le suivi technique");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMailStatus = useCallback(async () => {
    try {
      const res = await api.get("/rappels/email-status");
      setMailStatus(res.data || null);
    } catch {
      setMailStatus(null);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) {
      load();
      loadMailStatus();
    }
  }, [isAdmin, load, loadMailStatus]);

  useEffect(() => {
    if (user?.email && !testEmailTo) {
      setTestEmailTo(user.email);
    }
  }, [user?.email, testEmailTo]);

  const runSmtpTest = async () => {
    const dest = (testEmailTo || "").trim();
    if (!dest || !dest.includes("@")) {
      toast.error("Saisissez une adresse e-mail valide");
      return;
    }
    setSmtpTesting(true);
    setSmtpTestResult(null);
    try {
      const res = await api.post(`/admin/smtp-test`, null, { params: { to: dest } });
      const body = res.data || {};
      const connectionOk = Boolean(body.connection_ok);
      const sent = Boolean(body.test_email_sent);
      const err = sanitizeMailError(body.test_email_error || body.connection_error);
      const result = {
        ok: connectionOk && sent,
        connectionOk,
        sent,
        to: body.test_email_to || dest,
        from: body.smtp_from || mailStatus?.smtp_from || "noreply@leosoft.ch",
        host: body.smtp_host || mailStatus?.smtp_host,
        error: err,
      };
      setSmtpTestResult(result);
      if (result.ok) {
        toast.success(`E-mail de test envoyé à ${result.to}`);
      } else if (!connectionOk) {
        toast.error(err || "Connexion SMTP échouée");
      } else {
        toast.error(err || "Envoi de l'e-mail de test échoué");
      }
      await loadMailStatus();
    } catch (e) {
      const detail = sanitizeMailError(e?.response?.data?.detail || e?.message || "Erreur lors du test SMTP");
      setSmtpTestResult({
        ok: false,
        connectionOk: false,
        sent: false,
        to: dest,
        from: mailStatus?.smtp_from,
        error: detail,
      });
      toast.error(detail);
    } finally {
      setSmtpTesting(false);
    }
  };

  const downloadPdf = async () => {
    setPdfLoading(true);
    try {
      const stamp = new Date().toISOString().slice(0, 10);
      await downloadAuthenticatedBlob("/admin/tech-status/audit-report.pdf", `Audit_LeoSoft_${stamp}.pdf`);
      toast.success("Rapport PDF téléchargé");
    } catch {
      toast.error("Échec de la génération du PDF");
    } finally {
      setPdfLoading(false);
    }
  };

  const runAudit = async () => {
    setAuditLoading(true);
    const baselineAt = data?.last_control_at || null;
    try {
      const res = await api.post("/admin/tech-status/run-audit?force=true");
      const body = res.data || {};

      if (body.skipped) {
        toast.info(body.message || "Un contrôle a déjà été enregistré aujourd'hui.");
        if (body.status) setData(body.status);
        setAuditLoading(false);
        return;
      }

      if (body.started === false && body.running) {
        toast.info(body.message || "Un contrôle est déjà en cours…");
        if (body.status) setData(body.status);
      } else {
        toast.info(body.message || "Contrôle production en cours (1 à 3 min)…");
      }

      const waitUntil = body.await_control_after ?? baselineAt;
      const startedAt = Date.now();

      const poll = async () => {
        try {
          const statusRes = await api.get("/admin/tech-status");
          const payload = statusRes.data || {};
          setData(payload);

          const running = Boolean(payload.audit_running);
          const lastAt = payload.last_control_at || null;
          const updated = Boolean(lastAt && lastAt !== waitUntil);
          const elapsed = Date.now() - startedAt;

          if (updated && !running) {
            const gs = payload.global_status;
            toast.success(
              gs === "ok"
                ? "Contrôle terminé — Conforme"
                : `Contrôle terminé — ${payload.global_status_label || gs}`,
            );
            setAuditLoading(false);
            return;
          }

          if (elapsed > 300000) {
            toast.warning("Contrôle toujours en cours — rechargez la page dans quelques instants");
            setAuditLoading(false);
            return;
          }

          setTimeout(poll, 3000);
        } catch {
          toast.error("Impossible de suivre l'avancement du contrôle");
          setAuditLoading(false);
        }
      };

      setTimeout(poll, 2000);
    } catch {
      toast.error("Échec du lancement du contrôle technique");
      setAuditLoading(false);
    }
  };

  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  const global = resolveGlobalStatus(data);
  const storage = data?.storage || {};
  const backup = data?.backup || {};
  const mongo = data?.mongodb || {};
  const hosting = data?.hosting || {};
  const emergent = data?.emergent || {};
  const tests = data?.functional_tests || {};
  const history = data?.history || [];
  const anomalies = data?.anomalies || [];
  const hasAnomaly = anomalies.length > 0 && global.label === "Problème";
  const hasWarning = global.label === "Attention" || (anomalies.length > 0 && global.label !== "Problème" && global.label !== "Contrôle impossible à effectuer");

  return (
    <Layout>
      <div className="max-w-6xl mx-auto space-y-8 animate-fade-up">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight">Suivi technique</h1>
            <p className="text-muted-foreground mt-1 max-w-2xl">
              État du stockage, des sauvegardes, de la base de données et de l&apos;infrastructure du CRM
            </p>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <Button
              variant="outline"
              onClick={() => runAudit()}
              disabled={auditLoading || loading}
              className="gap-2"
              data-testid="btn-run-audit"
            >
              <RefreshCw className={`h-4 w-4 ${auditLoading ? "animate-spin" : ""}`} />
              {auditLoading ? "Contrôle…" : "Lancer un contrôle"}
            </Button>
            <Button
              onClick={downloadPdf}
              disabled={pdfLoading || loading}
              className="bg-[#002FA7] hover:bg-[#00248a] gap-2"
              data-testid="btn-audit-pdf"
            >
              <FileDown className="h-4 w-4" />
              {pdfLoading ? "Génération…" : "Générer le rapport PDF"}
            </Button>
          </div>
        </div>

        <Card className={`p-6 border-border bg-gradient-to-br ${hasAnomaly ? "from-red-50/80" : hasWarning ? "from-amber-50/80" : "from-emerald-50/80"} to-white`}>
          <div className="flex flex-col gap-4">
            <div className="flex items-start gap-3">
              <Activity className={`h-8 w-8 shrink-0 ${hasAnomaly ? "text-red-600" : hasWarning ? "text-amber-600" : "text-emerald-600"}`} strokeWidth={1.75} />
              <div className="space-y-2 flex-1">
                <p className="text-lg font-display font-bold">
                  {global.emoji} {global.label}
                </p>
                <p className="text-sm text-muted-foreground">
                  Dernier contrôle : {data?.last_control_label || formatDateFr(data?.last_control_date)}
                </p>
                <p className="text-sm text-muted-foreground">
                  Prochain contrôle : {data?.next_control_label || "demain"}
                </p>
              </div>
            </div>
            {hasAnomaly && (
              <div className="rounded-md border border-red-200 bg-red-50/90 p-4">
                <p className="font-medium text-red-900 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  Une anomalie nécessite votre attention
                </p>
                <ul className="mt-2 space-y-1 text-sm text-red-900/90 list-disc list-inside">
                  {anomalies.map((a, i) => (
                    <li key={`${i}-${a.slice(0, 40)}`}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
            {hasWarning && !hasAnomaly && (
              <div className="rounded-md border border-amber-200 bg-amber-50/90 p-4">
                <p className="font-medium text-amber-900 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  Point d&apos;attention
                </p>
                <ul className="mt-2 space-y-1 text-sm text-amber-900/90 list-disc list-inside">
                  {anomalies.map((a, i) => (
                    <li key={`${i}-${a.slice(0, 40)}`}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Card>

        <SectionCard title="Envoi d'e-mails (SMTP Infomaniak)" icon={Mail} accent="bg-[#002FA7]/10 text-[#002FA7]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              {mailStatus?.smtp_configured ? (
                <StatusPill status="ok" label="SMTP configuré" />
              ) : (
                <StatusPill status="problem" label="SMTP non configuré" />
              )}
              <p className="text-sm text-muted-foreground">
                Expéditeur :{" "}
                <span className="font-medium text-foreground">
                  {mailStatus?.smtp_from || "noreply@leosoft.ch"}
                </span>
                {mailStatus?.smtp_host ? (
                  <>
                    {" · "}
                    {mailStatus.smtp_host}
                    {mailStatus.smtp_port ? `:${mailStatus.smtp_port}` : ""}
                  </>
                ) : null}
              </p>
            </div>

            <p className="text-sm text-muted-foreground">
              Envoie un véritable e-mail de test depuis la boîte professionnelle Infomaniak.
              Le mot de passe SMTP n&apos;est jamais affiché.
            </p>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex-1 space-y-1.5 min-w-0">
                <Label htmlFor="smtp-test-to">Adresse destinataire</Label>
                <Input
                  id="smtp-test-to"
                  type="email"
                  autoComplete="email"
                  placeholder="ex. vous@agencemendes.ch"
                  value={testEmailTo}
                  onChange={(e) => setTestEmailTo(e.target.value)}
                  disabled={smtpTesting}
                  data-testid="smtp-test-email-input"
                />
              </div>
              <Button
                onClick={runSmtpTest}
                disabled={smtpTesting || !(testEmailTo || "").trim()}
                className="bg-[#002FA7] hover:bg-[#00248a] gap-2 shrink-0"
                data-testid="smtp-test-send-btn"
              >
                {smtpTesting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                {smtpTesting ? "Envoi…" : "Tester l'envoi d'e-mail"}
              </Button>
            </div>

            {smtpTestResult && (
              <div
                className={`rounded-md border p-4 ${
                  smtpTestResult.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-950"
                    : "border-red-200 bg-red-50 text-red-950"
                }`}
                data-testid="smtp-test-result"
              >
                {smtpTestResult.ok ? (
                  <>
                    <p className="font-semibold flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 shrink-0" />
                      Test réussi
                    </p>
                    <p className="text-sm mt-1">
                      E-mail envoyé à <span className="font-medium">{smtpTestResult.to}</span>
                      {smtpTestResult.from ? (
                        <>
                          {" "}depuis <span className="font-medium">{smtpTestResult.from}</span>
                        </>
                      ) : null}
                      . Vérifiez la boîte de réception (et les indésirables).
                    </p>
                  </>
                ) : (
                  <>
                    <p className="font-semibold flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 shrink-0" />
                      Test échoué
                    </p>
                    <p className="text-sm mt-1">
                      {!smtpTestResult.connectionOk
                        ? "La connexion au serveur SMTP Infomaniak a échoué."
                        : "La connexion SMTP est OK, mais l'envoi de l'e-mail a échoué."}
                    </p>
                    {smtpTestResult.error && (
                      <p className="text-sm mt-2 font-mono bg-white/60 rounded px-2 py-1.5 break-words">
                        {smtpTestResult.error}
                      </p>
                    )}
                    {smtpTestResult.error && /Railway|Hobby|timeout|Timeout/i.test(smtpTestResult.error) && (
                      <p className="text-sm mt-3">
                        <strong>Action :</strong> dans Railway → Settings → passez en plan{" "}
                        <strong>Pro</strong> (SMTP sortant autorisé), puis{" "}
                        <strong>Redeploy</strong> le service <code>prevoyance-frontend</code>,
                        et relancez ce test. La config Infomaniak (user / mot de passe) est déjà correcte.
                      </p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </SectionCard>

        {loading && (
          <p className="text-muted-foreground text-center py-8">Chargement du suivi technique…</p>
        )}

        {!loading && data && (
          <>
            <div className="grid gap-6 md:grid-cols-2">
              <SectionCard title="Stockage des documents" icon={Cloud}>
                <StatusPill status={storage.status} label={storage.status === "ok" ? "OK" : undefined} className="mb-4" />
                <div className="grid grid-cols-2 gap-x-6 gap-y-1">
                  <Metric label="Fournisseur" value={storage.provider || "Infomaniak S3"} />
                  <Metric label="Bucket" value={storage.bucket_display || "—"} />
                  <Metric label="Documents actifs vérifiés" value={`${storage.active_docs_verified ?? "—"} / ${storage.active_docs_total ?? "—"}`} large />
                  <Metric label="Documents manquants" value={storage.missing_docs ?? 0} />
                  <Metric label="Échecs de lecture S3" value={storage.s3_read_failures ?? 0} />
                  <Metric label="Références actives non-S3" value={storage.non_s3_active_refs ?? 0} />
                  <Metric label="Dernière vérification" value={formatDateFr(storage.last_verification)} />
                </div>
              </SectionCard>

              <SectionCard title="Sauvegardes" icon={Archive} accent="bg-violet-100 text-violet-700">
                <StatusPill status={backup.status} label={backup.status === "ok" ? "DERNIÈRE SAUVEGARDE OK" : undefined} className="mb-4" />
                <div className="space-y-1">
                  <Metric label="Dernière sauvegarde" value={`${formatDateFr(backup.last_date)} à ${backup.last_time || "—"}`} />
                  <Metric label="Nom" value={backup.filename || "—"} />
                  <Metric label="Taille" value={backup.size_label || "—"} />
                  <Metric label="Restaurabilité" value={backup.restorable ? "Vérifiée" : "—"} />
                  <Metric label="Emplacement" value={backup.location || "Infomaniak S3"} />
                </div>
              </SectionCard>

              <SectionCard title="Base de données" icon={Database} accent="bg-amber-100 text-amber-800">
                <StatusPill status={mongo.status} className="mb-4" />
                <div className="grid grid-cols-2 gap-x-6">
                  <Metric label="MongoDB" value={mongo.environment || "Production"} />
                  <Metric label="Volume" value={mongo.volume_gb != null ? `${mongo.volume_gb} Go` : "—"} large />
                  <Metric label="Espace libre" value={mongo.free_space_label || "—"} />
                  <Metric label="Documents" value={mongo.documents ?? "—"} large />
                  <Metric label="Index" value={`${mongo.indexes_present ?? "—"} / ${mongo.indexes_expected ?? 16}`} large />
                </div>
              </SectionCard>

              <SectionCard title="Hébergement (Railway)" icon={Server} accent="bg-sky-100 text-sky-700">
                <StatusPill status={hosting.status === "operational" ? "ok" : hosting.status} label="OPÉRATIONNEL" className="mb-4" />
                <div className="grid grid-cols-2 gap-x-6">
                  <Metric label="Plateforme" value={hosting.platform || "Railway"} />
                  <Metric label="Health check" value={hosting.health_ok !== false ? "OK" : "Échec"} />
                  <Metric label="Stockage" value={hosting.storage_label || "Infomaniak S3"} />
                  <Metric label="Base de données" value={hosting.database_label || "MongoDB"} />
                </div>
              </SectionCard>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <SectionCard title="Emergent" icon={Shield} accent="bg-slate-100 text-slate-600">
                <StatusPill status={emergent.status} label={emergent.required === false ? "Non requis" : undefined} className="mb-4" />
                <Metric label="Dépendance runtime" value={emergent.runtime_dependency ?? 0} />
                <Metric label="Documents actifs hors S3 (legacy)" value={emergent.active_docs_on_emergent ?? 0} />
                <Metric label="Stockage actuel" value={emergent.current_storage || "Infomaniak S3"} />
              </SectionCard>

              <SectionCard title="Tests fonctionnels" icon={CheckCircle2} accent="bg-emerald-100 text-emerald-700">
                <div className="space-y-1 mb-4">
                  {(tests.items || []).map((item) => (
                    <CheckItem key={item.key || item.label} label={item.label} ok={item.ok !== false} />
                  ))}
                </div>
                <Metric label="Date du dernier test" value={formatDateFr(tests.last_date)} />
              </SectionCard>
            </div>

            <SectionCard title="Historique des contrôles quotidiens" icon={Activity} accent="bg-indigo-100 text-indigo-700">
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse min-w-[720px]">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      <th className="py-3 pr-3 font-medium">Date / heure</th>
                      <th className="py-3 pr-3 font-medium">Railway</th>
                      <th className="py-3 pr-3 font-medium">MongoDB</th>
                      <th className="py-3 pr-3 font-medium">S3</th>
                      <th className="py-3 pr-3 font-medium">Sauvegarde</th>
                      <th className="py-3 pr-3 font-medium">Emergent</th>
                      <th className="py-3 font-medium">Résultat</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.length === 0 && (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-muted-foreground">
                          Aucun contrôle enregistré pour le moment.
                        </td>
                      </tr>
                    )}
                    {history.map((row) => {
                      const g = rowStatus(row.global_status);
                      return (
                        <tr key={row.id || row.audit_day || row.date} className="border-b border-border/60 align-top">
                          <td className="py-3 pr-3 whitespace-nowrap">{formatHistoryDate(row)}</td>
                          <td className="py-3 pr-3"><StatusPill status={cellStatus(row, "railway")} /></td>
                          <td className="py-3 pr-3">
                            <div className="space-y-1">
                              <StatusPill status={cellStatus(row, "mongodb")} />
                              {row.mongodb?.free_space_label && (
                                <p className="text-xs text-muted-foreground">{row.mongodb.free_space_label}</p>
                              )}
                              {row.mongodb?.indexes_present != null && (
                                <p className="text-xs text-muted-foreground">
                                  Index {row.mongodb.indexes_present}/{row.mongodb.indexes_expected ?? 16}
                                </p>
                              )}
                            </div>
                          </td>
                          <td className="py-3 pr-3">
                            <div className="space-y-1">
                              <StatusPill status={cellStatus(row, "storage")} />
                              {row.storage?.active_docs_verified != null && (
                                <p className="text-xs text-muted-foreground">
                                  {row.storage.active_docs_verified} refs · {row.storage.missing_docs ?? 0} manquant(s)
                                </p>
                              )}
                            </div>
                          </td>
                          <td className="py-3 pr-3"><StatusPill status={cellStatus(row, "backup")} /></td>
                          <td className="py-3 pr-3"><StatusPill status={cellStatus(row, "emergent")} /></td>
                          <td className="py-3 font-medium whitespace-nowrap">
                            {g.emoji} {row.result || g.label}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          </>
        )}
      </div>
    </Layout>
  );
}
