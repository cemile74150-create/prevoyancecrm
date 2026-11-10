import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  LEAVE_TYPES, currentMonth, entriesForDay, leaveErrorMessage, monthGrid, monthLabel, shiftMonth,
} from "@/lib/conges";
import { fetchLeaveCalendar, fetchLeaveEmployees } from "@/lib/congesApi";
import { LeaveDetailDialog } from "@/components/conges/LeaveShared";

const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const PART_SHORT = { morning: " · matin", afternoon: " · ap.-midi", full: "" };
const MAX_PER_CELL = 3;

function entryClass(entry) {
  if (entry.status === "pending") return "border border-dashed border-amber-400 bg-amber-50 text-amber-900";
  if (entry.status === "cancellation_requested") return "bg-violet-100 text-violet-900";
  return "bg-[#002FA7]/10 text-[#002FA7]";
}

export default function CalendrierEquipe({ manager, refreshKey }) {
  const [month, setMonth] = useState(currentMonth());
  const [includePending, setIncludePending] = useState(false);
  const [employeeId, setEmployeeId] = useState("all");
  const [leaveType, setLeaveType] = useState("all");
  const [employees, setEmployees] = useState([]);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    if (!manager) return;
    fetchLeaveEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, [manager]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchLeaveCalendar({
        month,
        include_pending: manager && includePending ? true : null,
        employee_id: employeeId,
        leave_type: manager ? leaveType : null,
      });
      setItems(res.items || []);
      setError("");
    } catch (e) {
      setError(leaveErrorMessage(e, "Impossible de charger le calendrier."));
    } finally {
      setLoading(false);
    }
  }, [month, includePending, employeeId, leaveType, manager]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const weeks = useMemo(() => monthGrid(month), [month]);
  const today = new Date().toLocaleDateString("sv-SE");

  return (
    <div className="space-y-4" data-testid="calendrier-equipe">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => setMonth((m) => shiftMonth(m, -1))} data-testid="cal-prev">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <p className="font-display font-bold text-lg w-48 text-center" data-testid="cal-month">{monthLabel(month)}</p>
          <Button variant="outline" size="icon" className="h-9 w-9" onClick={() => setMonth((m) => shiftMonth(m, 1))} data-testid="cal-next">
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setMonth(currentMonth())}>Aujourd'hui</Button>
        </div>
        {manager && (
          <>
            <Select value={employeeId} onValueChange={setEmployeeId}>
              <SelectTrigger className="h-9 w-[200px]" data-testid="cal-employee"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous les collaborateurs</SelectItem>
                {employees.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={leaveType} onValueChange={setLeaveType}>
              <SelectTrigger className="h-9 w-[180px]" data-testid="cal-type"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous types</SelectItem>
                {LEAVE_TYPES.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <Switch id="cal-pending" checked={includePending} onCheckedChange={setIncludePending} data-testid="cal-include-pending" />
              <Label htmlFor="cal-pending" className="text-sm">Afficher les demandes en attente</Label>
            </div>
          </>
        )}
        {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      </div>

      <p className="text-xs text-muted-foreground">
        {manager
          ? "Absences validées (et en attente si l'option est active). Cliquez sur une absence pour ouvrir la demande."
          : "Absences validées de l'équipe. Les demandes en attente, motifs et commentaires ne sont pas affichés."}
      </p>

      {error ? (
        <Card className="p-10 text-sm text-amber-800 text-center">{error}</Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="grid grid-cols-7 border-b border-border bg-secondary/40">
            {WEEKDAYS.map((d) => (
              <div key={d} className="px-2 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{d}</div>
            ))}
          </div>
          {weeks.map((week) => (
            <div key={week[0].iso} className="grid grid-cols-7 border-b border-border last:border-0">
              {week.map((day) => {
                const entries = day.inMonth ? entriesForDay(items, day.iso) : [];
                const absentCount = new Set(entries.map((e) => e.employee_id)).size;
                return (
                  <div
                    key={day.iso}
                    data-testid={`cal-day-${day.iso}`}
                    className={`min-h-[104px] border-r border-border last:border-0 p-1.5 ${
                      !day.inMonth ? "bg-secondary/30 text-muted-foreground/50" : day.weekend ? "bg-secondary/20" : ""
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-xs font-medium ${day.iso === today ? "bg-[#002FA7] text-white rounded-full px-1.5" : ""}`}>
                        {day.day}
                      </span>
                      {absentCount > 1 && (
                        <span className="text-[10px] font-semibold text-red-700 bg-red-50 rounded px-1" data-testid={`cal-count-${day.iso}`}>
                          {absentCount} absents
                        </span>
                      )}
                    </div>
                    <div className="space-y-0.5">
                      {entries.slice(0, MAX_PER_CELL).map((e, i) => (
                        <button
                          type="button"
                          key={`${e.id || e.employee_id}-${i}`}
                          disabled={!e.id}
                          onClick={() => e.id && setOpenId(e.id)}
                          title={`${e.employee_name} — ${manager ? `${e.leave_type_label} (${e.status_label})` : e.label}`}
                          className={`w-full text-left truncate rounded px-1 py-0.5 text-[11px] leading-tight ${entryClass(e)} ${e.id ? "hover:opacity-80" : "cursor-default"}`}
                        >
                          {e.employee_name}{PART_SHORT[e.part]}
                        </button>
                      ))}
                      {entries.length > MAX_PER_CELL && (
                        <p className="text-[10px] text-muted-foreground px-1" title={entries.map((e) => e.employee_name).join(", ")}>
                          +{entries.length - MAX_PER_CELL} autre(s)
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </Card>
      )}

      {manager && (
        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded bg-[#002FA7]/10" /> Validée</span>
          <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded border border-dashed border-amber-400 bg-amber-50" /> En attente</span>
          <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded bg-violet-100" /> Annulation demandée</span>
        </div>
      )}

      <LeaveDetailDialog
        leaveId={openId}
        open={Boolean(openId)}
        onOpenChange={(o) => { if (!o) setOpenId(null); }}
        onChanged={load}
      />
    </div>
  );
}
