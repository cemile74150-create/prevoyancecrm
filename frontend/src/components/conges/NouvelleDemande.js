import React, { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  CALCULATION_NOTE,
  LEAVE_TYPES,
  computeWorkingDays,
  formatDays,
  leaveErrorMessage,
  newClientRequestId,
  periodLabel,
  validateLeaveForm,
} from "@/lib/conges";
import { createLeave, previewLeave } from "@/lib/congesApi";

const EMPTY = { leaveType: "paid", startDate: "", endDate: "", singlePart: "full", startPart: "full", endPart: "full", comment: "" };

function ReadOnly({ label, value, testid }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input value={value || ""} readOnly disabled data-testid={testid} className="bg-secondary/60" />
    </div>
  );
}

export default function NouvelleDemande({ meta, onCreated }) {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(null);
  const requestId = useRef(newClientRequestId());

  const single = form.startDate && form.startDate === form.endDate;
  const startPart = single ? form.singlePart : form.startPart;
  const endPart = single ? form.singlePart : form.endPart;
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v?.target ? v.target.value : v }));

  const localError = useMemo(
    () => (form.startDate && form.endDate
      ? validateLeaveForm({ leaveType: form.leaveType, startDate: form.startDate, endDate: form.endDate, startPart, endPart })
      : ""),
    [form.leaveType, form.startDate, form.endDate, startPart, endPart],
  );
  const days = form.startDate && form.endDate && !localError
    ? computeWorkingDays(form.startDate, form.endDate, startPart, endPart)
    : null;

  const body = useMemo(() => ({
    leave_type: form.leaveType,
    start_date: form.startDate,
    end_date: form.endDate,
    start_day_part: startPart,
    end_day_part: endPart,
    comment: form.comment.trim() || null,
  }), [form.leaveType, form.startDate, form.endDate, startPart, endPart, form.comment]);

  useEffect(() => {
    setConflict(null);
    if (!form.startDate || !form.endDate || localError) return undefined;
    const t = setTimeout(async () => {
      try {
        const res = await previewLeave(body);
        setConflict(res.conflict || null);
      } catch {
        // Le contrôle définitif est fait à l'envoi.
      }
    }, 300);
    return () => clearTimeout(t);
  }, [body, form.startDate, form.endDate, localError]);

  const onStartChange = (e) => {
    const v = e.target.value;
    setForm((f) => ({ ...f, startDate: v, endDate: !f.endDate || f.endDate < v ? v : f.endDate }));
  };

  const submit = async (e) => {
    e?.preventDefault();
    if (saving) return;
    const msg = validateLeaveForm({ leaveType: form.leaveType, startDate: form.startDate, endDate: form.endDate, startPart, endPart });
    if (msg) {
      setError(msg);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const created = await createLeave({ ...body, client_request_id: requestId.current });
      toast.success("Demande envoyée : elle est en attente de validation RH.");
      requestId.current = newClientRequestId();
      setForm(EMPTY);
      onCreated?.(created);
    } catch (err) {
      setError(leaveErrorMessage(err, "Envoi impossible."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="grid gap-5 lg:grid-cols-[1fr_320px]" data-testid="nouvelle-demande">
      <Card className="p-5 space-y-5">
        <div className="grid gap-4 sm:grid-cols-3">
          <ReadOnly label="Nom" value={meta?.employee?.name} testid="leave-employee-name" />
          <ReadOnly label="Identifiant" value={meta?.employee?.id} testid="leave-employee-id" />
          <ReadOnly label="E-mail" value={meta?.employee?.email} testid="leave-employee-email" />
        </div>

        <div className="space-y-1.5 max-w-xs">
          <Label className="text-xs">Type d'absence</Label>
          <Select value={form.leaveType} onValueChange={set("leaveType")}>
            <SelectTrigger data-testid="leave-type"><SelectValue /></SelectTrigger>
            <SelectContent>
              {LEAVE_TYPES.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs" htmlFor="leave-start">Date de début</Label>
            <Input id="leave-start" type="date" data-testid="leave-start" value={form.startDate} onChange={onStartChange} required />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs" htmlFor="leave-end">Date de fin</Label>
            <Input id="leave-end" type="date" data-testid="leave-end" value={form.endDate} min={form.startDate || undefined}
              onChange={set("endDate")} required />
          </div>
        </div>

        {form.startDate && form.endDate && (single ? (
          <div className="space-y-1.5 max-w-xs">
            <Label className="text-xs">Durée</Label>
            <Select value={form.singlePart} onValueChange={set("singlePart")}>
              <SelectTrigger data-testid="leave-single-part"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="full">Journée entière</SelectItem>
                <SelectItem value="morning">Demi-journée — matin</SelectItem>
                <SelectItem value="afternoon">Demi-journée — après-midi</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Premier jour</Label>
              <Select value={form.startPart} onValueChange={set("startPart")}>
                <SelectTrigger data-testid="leave-start-part"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="full">Journée entière</SelectItem>
                  <SelectItem value="afternoon">À partir de l'après-midi</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Dernier jour</Label>
              <Select value={form.endPart} onValueChange={set("endPart")}>
                <SelectTrigger data-testid="leave-end-part"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="full">Journée entière</SelectItem>
                  <SelectItem value="morning">Jusqu'à midi (matin)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        ))}

        <div className="space-y-1.5">
          <Label className="text-xs" htmlFor="leave-comment">Commentaire (facultatif)</Label>
          <Textarea id="leave-comment" data-testid="leave-comment" rows={3} maxLength={1000} value={form.comment} onChange={set("comment")} />
        </div>

        {(error || localError) && (
          <p className="text-sm text-destructive" data-testid="leave-form-error">{error || localError}</p>
        )}

        <div className="flex justify-end">
          <Button type="submit" disabled={saving || Boolean(localError) || Boolean(conflict)}
            data-testid="leave-submit" className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
            <Send className="h-4 w-4" /> {saving ? "Envoi…" : "Envoyer la demande"}
          </Button>
        </div>
      </Card>

      <Card className="p-5 space-y-3 h-fit">
        <p className="text-xs uppercase tracking-wide text-muted-foreground font-semibold">Nombre de jours</p>
        <p className="font-display font-black text-4xl" data-testid="leave-days">{days === null ? "—" : formatDays(days)}</p>
        <p className="text-xs text-muted-foreground">{meta?.calculation_note || CALCULATION_NOTE}</p>
        <p className="text-xs text-muted-foreground">Aucun solde ni compteur annuel n'est calculé.</p>
        {conflict ? (
          <div className="flex gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md p-3" data-testid="leave-conflict">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>Chevauche votre demande {conflict.status_label?.toLowerCase()} du {periodLabel(conflict)}.</span>
          </div>
        ) : days ? (
          <div className="flex gap-2 text-sm text-emerald-800">
            <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" /> Aucune demande en conflit.
          </div>
        ) : null}
      </Card>
    </form>
  );
}
