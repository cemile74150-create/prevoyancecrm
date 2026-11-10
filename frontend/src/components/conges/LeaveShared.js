import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  CALCULATION_NOTE,
  EVENT_LABELS,
  STATUS_META,
  formatDateTimeFr,
  formatDays,
  leaveErrorMessage,
  periodLabel,
} from "@/lib/conges";
import {
  approveLeave,
  cancelLeave,
  fetchLeave,
  rejectLeave,
  requestLeaveCancellation,
  resolveLeaveCancellation,
} from "@/lib/congesApi";

export function StatusBadge({ status }) {
  const meta = STATUS_META[status] || { label: status, className: "bg-secondary text-foreground border-border" };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${meta.className}`}>
      {meta.label}
    </span>
  );
}

export function KpiCard({ label, value, tone = "text-foreground", testid, active, onClick }) {
  const Comp = onClick ? "button" : "div";
  return (
    <Card className={`p-0 overflow-hidden ${active ? "ring-2 ring-[#002FA7]" : ""}`}>
      <Comp
        type={onClick ? "button" : undefined}
        onClick={onClick}
        data-testid={testid}
        className={`w-full text-left p-4 ${onClick ? "hover:bg-secondary transition-colors" : ""}`}
      >
        <p className="text-xs uppercase tracking-wide text-muted-foreground font-semibold">{label}</p>
        <p className={`font-display font-black text-3xl mt-1 ${tone}`}>{value ?? 0}</p>
      </Comp>
    </Card>
  );
}

const ACTIONS = {
  cancel: {
    title: "Annuler cette demande ?",
    help: "La demande en attente sera retirée. Vous pourrez en déposer une nouvelle.",
    confirm: "Annuler la demande",
    reasonLabel: "Commentaire (facultatif)",
    run: (id, body) => cancelLeave(id, body),
    done: "Demande annulée",
  },
  request_cancellation: {
    title: "Demander l'annulation de ce congé validé ?",
    help: "Le congé reste validé tant que la RH n'a pas accepté l'annulation.",
    confirm: "Envoyer la demande d'annulation",
    reasonLabel: "Commentaire (facultatif)",
    run: (id, body) => requestLeaveCancellation(id, body),
    done: "Demande d'annulation envoyée",
  },
  approve: {
    title: "Valider cette demande ?",
    help: "Le collaborateur sera notifié. La décision ne pourra plus être modifiée.",
    confirm: "Valider",
    run: (id, body) => approveLeave(id, body),
    done: "Demande validée",
  },
  reject: {
    title: "Refuser cette demande ?",
    help: "Le motif est communiqué au collaborateur.",
    confirm: "Refuser",
    reasonLabel: "Motif du refus (obligatoire)",
    reasonRequired: true,
    destructive: true,
    run: (id, body) => rejectLeave(id, body),
    done: "Demande refusée",
  },
  accept_cancellation: {
    title: "Accepter l'annulation ?",
    help: "Le congé sera annulé et retiré du calendrier.",
    confirm: "Accepter l'annulation",
    reasonLabel: "Commentaire (facultatif)",
    run: (id, body) => resolveLeaveCancellation(id, { ...body, decision: "accept" }),
    done: "Annulation acceptée",
  },
  refuse_cancellation: {
    title: "Refuser l'annulation ?",
    help: "Le congé reste validé. Le motif est communiqué au collaborateur.",
    confirm: "Refuser l'annulation",
    reasonLabel: "Motif (obligatoire)",
    reasonRequired: true,
    destructive: true,
    run: (id, body) => resolveLeaveCancellation(id, { ...body, decision: "refuse" }),
    done: "Annulation refusée",
  },
};

function Field({ label, children }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground font-semibold">{label}</p>
      <div className="text-sm mt-0.5">{children}</div>
    </div>
  );
}

export function LeaveDetailDialog({ leaveId, open, onOpenChange, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState(null);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const closeRef = useRef(onOpenChange);
  closeRef.current = onOpenChange;

  const load = useCallback(async () => {
    if (!leaveId) return;
    setLoading(true);
    try {
      setDetail(await fetchLeave(leaveId));
    } catch (e) {
      toast.error(leaveErrorMessage(e, "Impossible de charger la demande"));
      closeRef.current(false);
    } finally {
      setLoading(false);
    }
  }, [leaveId]);

  useEffect(() => {
    if (open) {
      setMode(null);
      setReason("");
      setError("");
      setDetail(null);
      load();
    }
  }, [open, load]);

  const action = mode ? ACTIONS[mode] : null;

  const submit = async () => {
    if (!action || !detail) return;
    if (action.reasonRequired && !reason.trim()) {
      setError("Le motif est obligatoire.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await action.run(detail.id, { reason: reason.trim() || null, expected_version: detail.version });
      toast.success(action.done);
      onChanged?.();
      onOpenChange(false);
    } catch (e) {
      setError(leaveErrorMessage(e, "Action impossible"));
      if (e?.response?.status === 409) load();
    } finally {
      setSaving(false);
    }
  };

  const startAction = (m) => {
    setMode(m);
    setReason("");
    setError("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto" data-testid="leave-detail-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Demande de congé</DialogTitle>
          <DialogDescription>{detail ? `Déposée le ${formatDateTimeFr(detail.created_at)}` : "Chargement…"}</DialogDescription>
        </DialogHeader>

        {loading || !detail ? (
          <div className="py-10 flex justify-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Collaborateur">
                <span className="font-medium">{detail.employee_name}</span>
                <span className="block text-xs text-muted-foreground">{detail.employee_email}</span>
              </Field>
              <Field label="Statut"><StatusBadge status={detail.status} /></Field>
              <Field label="Période">{periodLabel(detail)}</Field>
              <Field label="Durée indicative">{formatDays(detail.days_count)}</Field>
              <Field label="Type">{detail.leave_type_label}</Field>
              {detail.reviewed_by_name && (
                <Field label="Décision">
                  {detail.reviewed_by_name}
                  <span className="block text-xs text-muted-foreground">{formatDateTimeFr(detail.reviewed_at)}</span>
                </Field>
              )}
            </div>
            {detail.comment && <Field label="Commentaire"><p className="whitespace-pre-wrap">{detail.comment}</p></Field>}
            {detail.rejection_reason && (
              <Field label="Motif du refus"><p className="whitespace-pre-wrap text-red-700">{detail.rejection_reason}</p></Field>
            )}
            {detail.cancellation_reason && (
              <Field label="Commentaire d'annulation"><p className="whitespace-pre-wrap">{detail.cancellation_reason}</p></Field>
            )}
            {detail.cancellation_decision_reason && (
              <Field label="Réponse à l'annulation"><p className="whitespace-pre-wrap">{detail.cancellation_decision_reason}</p></Field>
            )}
            <p className="text-[11px] text-muted-foreground">{detail.calculation_note || CALCULATION_NOTE}</p>

            <div>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground font-semibold mb-2">Historique</p>
              <ol className="space-y-2 border-l border-border pl-4" data-testid="leave-history">
                {(detail.events || []).map((ev) => (
                  <li key={ev.id} className="text-sm">
                    <span className="font-medium">{EVENT_LABELS[ev.event] || ev.event}</span>
                    <span className="text-muted-foreground"> · {ev.actor_name} · {formatDateTimeFr(ev.created_at)}</span>
                    {ev.reason && <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">« {ev.reason} »</p>}
                  </li>
                ))}
              </ol>
            </div>

            {action && (
              <div className="rounded-md border border-border bg-secondary/40 p-4 space-y-3" data-testid="leave-action-panel">
                <div>
                  <p className="font-medium text-sm">{action.title}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">{action.help}</p>
                </div>
                {action.reasonLabel && (
                  <div className="space-y-1.5">
                    <Label className="text-xs">{action.reasonLabel}</Label>
                    <Textarea
                      data-testid="leave-action-reason"
                      value={reason}
                      maxLength={1000}
                      rows={3}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </div>
                )}
                {error && <p className="text-xs text-destructive" data-testid="leave-action-error">{error}</p>}
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setMode(null)} disabled={saving}>Retour</Button>
                  <Button
                    size="sm"
                    data-testid="leave-action-confirm"
                    onClick={submit}
                    disabled={saving}
                    className={action.destructive ? "bg-red-600 hover:bg-red-700" : "bg-[#002FA7] hover:bg-[#00248a]"}
                  >
                    {saving ? "Envoi…" : action.confirm}
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {detail && !action && (
          <DialogFooter className="gap-2 sm:gap-2 flex-wrap">
            {detail.can_cancel && (
              <Button variant="outline" data-testid="leave-cancel-btn" onClick={() => startAction("cancel")}>Annuler la demande</Button>
            )}
            {detail.can_request_cancellation && (
              <Button variant="outline" data-testid="leave-request-cancel-btn" onClick={() => startAction("request_cancellation")}>
                Demander l'annulation
              </Button>
            )}
            {detail.can_decide && (
              <>
                <Button variant="outline" className="text-red-700" data-testid="leave-reject-btn" onClick={() => startAction("reject")}>Refuser</Button>
                <Button className="bg-[#002FA7] hover:bg-[#00248a]" data-testid="leave-approve-btn" onClick={() => startAction("approve")}>Valider</Button>
              </>
            )}
            {detail.can_resolve_cancellation && (
              <>
                <Button variant="outline" className="text-red-700" data-testid="leave-refuse-cancel-btn" onClick={() => startAction("refuse_cancellation")}>
                  Refuser l'annulation
                </Button>
                <Button className="bg-[#002FA7] hover:bg-[#00248a]" data-testid="leave-accept-cancel-btn" onClick={() => startAction("accept_cancellation")}>
                  Accepter l'annulation
                </Button>
              </>
            )}
            <Button variant="ghost" onClick={() => onOpenChange(false)}>Fermer</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
