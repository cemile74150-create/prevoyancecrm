import React, { useCallback, useEffect, useState } from "react";
import { Eye, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { STATUS_META, formatDateTimeFr, formatDays, leaveErrorMessage, yearOptions } from "@/lib/conges";
import { fetchAdminLeaves, fetchLeaveEmployees } from "@/lib/congesApi";
import { KpiCard, LeaveDetailDialog, StatusBadge } from "@/components/conges/LeaveShared";
import { dayCell } from "@/components/conges/MesConges";

const EMPTY_FILTERS = {
  employee_id: "all",
  status: "all",
  year: String(new Date().getFullYear()),
  period_from: "",
  period_to: "",
  submitted_from: "",
  submitted_to: "",
};

export default function GestionDemandes({ refreshKey, onChanged }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [employees, setEmployees] = useState([]);
  const [data, setData] = useState({ items: [], kpis: {}, years: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    fetchLeaveEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchAdminLeaves(filters));
      setError("");
    } catch (e) {
      setError(leaveErrorMessage(e, "Impossible de charger les demandes."));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const set = (k) => (v) => setFilters((f) => ({ ...f, [k]: v?.target ? v.target.value : v }));
  const toggleStatus = (s) => setFilters((f) => ({ ...f, status: f.status === s ? "all" : s }));
  const kpis = data.kpis || {};

  return (
    <div className="space-y-5" data-testid="gestion-demandes">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="À traiter" value={kpis.pending} tone="text-amber-700" testid="kpi-rh-pending"
          active={filters.status === "pending"} onClick={() => toggleStatus("pending")} />
        <KpiCard label="Validées" value={kpis.approved} tone="text-emerald-700" testid="kpi-rh-approved"
          active={filters.status === "approved"} onClick={() => toggleStatus("approved")} />
        <KpiCard label="Refusées" value={kpis.rejected} tone="text-red-700" testid="kpi-rh-rejected"
          active={filters.status === "rejected"} onClick={() => toggleStatus("rejected")} />
        <KpiCard label="Annulations en attente" value={kpis.cancellation_requested} tone="text-violet-700"
          testid="kpi-rh-cancellations" active={filters.status === "cancellation_requested"}
          onClick={() => toggleStatus("cancellation_requested")} />
      </div>

      <Card className="p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 items-end">
          <div className="space-y-1">
            <Label className="text-xs">Collaborateur</Label>
            <Select value={filters.employee_id} onValueChange={set("employee_id")}>
              <SelectTrigger className="h-9" data-testid="rh-filter-employee"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous</SelectItem>
                {employees.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Statut</Label>
            <Select value={filters.status} onValueChange={set("status")}>
              <SelectTrigger className="h-9" data-testid="rh-filter-status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tous</SelectItem>
                {Object.entries(STATUS_META).map(([id, m]) => <SelectItem key={id} value={id}>{m.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Année</Label>
            <Select value={filters.year} onValueChange={set("year")}>
              <SelectTrigger className="h-9" data-testid="rh-filter-year"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Toutes</SelectItem>
                {yearOptions(data.years).map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Absence du</Label>
            <Input type="date" className="h-9" value={filters.period_from} onChange={set("period_from")} data-testid="rh-filter-period-from" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Absence au</Label>
            <Input type="date" className="h-9" value={filters.period_to} onChange={set("period_to")} data-testid="rh-filter-period-to" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Soumise du</Label>
            <Input type="date" className="h-9" value={filters.submitted_from} onChange={set("submitted_from")} data-testid="rh-filter-submitted-from" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Soumise au</Label>
            <Input type="date" className="h-9" value={filters.submitted_to} onChange={set("submitted_to")} data-testid="rh-filter-submitted-to" />
          </div>
        </div>
        <div className="flex justify-end mt-3">
          <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => setFilters(EMPTY_FILTERS)}>
            <RotateCcw className="h-3.5 w-3.5" /> Réinitialiser
          </Button>
        </div>
      </Card>

      <Card className="overflow-hidden">
        {loading ? (
          <div className="p-10 flex justify-center text-sm text-muted-foreground gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </div>
        ) : error ? (
          <p className="p-10 text-sm text-amber-800 text-center">{error}</p>
        ) : data.items.length === 0 ? (
          <p className="p-10 text-sm text-muted-foreground text-center">Aucune demande pour ces filtres.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Collaborateur</TableHead>
                <TableHead>Soumise le</TableHead>
                <TableHead>Début</TableHead>
                <TableHead>Fin</TableHead>
                <TableHead className="text-right">Jours</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((item) => {
                const waiting = item.status === "pending" || item.status === "cancellation_requested";
                return (
                  <TableRow key={item.id} data-testid={`rh-conge-${item.id}`} className={`cursor-pointer ${waiting ? "bg-amber-50/40" : ""}`}
                    onClick={() => setOpenId(item.id)}>
                    <TableCell className="font-medium">{item.employee_name}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTimeFr(item.created_at)}</TableCell>
                    <TableCell>{dayCell(item, "start")}</TableCell>
                    <TableCell>{dayCell(item, "end")}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatDays(item.days_count)}</TableCell>
                    <TableCell>{item.leave_type_label}</TableCell>
                    <TableCell><StatusBadge status={item.status} /></TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant={waiting ? "default" : "ghost"}
                        className={`h-8 gap-1 ${waiting ? "bg-[#002FA7] hover:bg-[#00248a]" : ""}`}
                        onClick={(e) => { e.stopPropagation(); setOpenId(item.id); }}>
                        <Eye className="h-3.5 w-3.5" /> {waiting ? "Traiter" : "Détail"}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      <LeaveDetailDialog
        leaveId={openId}
        open={Boolean(openId)}
        onOpenChange={(o) => { if (!o) setOpenId(null); }}
        onChanged={() => { load(); onChanged?.(); }}
      />
    </div>
  );
}
