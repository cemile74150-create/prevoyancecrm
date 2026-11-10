import React, { useCallback, useEffect, useState } from "react";
import { Eye, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  STATUS_META, formatDateFr, formatDateTimeFr, formatDays, leaveErrorMessage, yearOptions,
} from "@/lib/conges";
import { fetchMyLeaves } from "@/lib/congesApi";
import { KpiCard, LeaveDetailDialog, StatusBadge } from "@/components/conges/LeaveShared";

const partSuffix = (part, which) => {
  if (which === "start" && part === "afternoon") return " (ap.-midi)";
  if (which === "end" && part === "morning") return " (matin)";
  return "";
};

export function dayCell(item, which) {
  const iso = which === "start" ? item.start_date : item.end_date;
  if (item.start_date === item.end_date && item.start_day_part !== "full") {
    return `${formatDateFr(iso)} (${item.start_day_part === "morning" ? "matin" : "ap.-midi"})`;
  }
  return formatDateFr(iso) + partSuffix(which === "start" ? item.start_day_part : item.end_day_part, which);
}

export default function MesConges({ onNewRequest, refreshKey }) {
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [status, setStatus] = useState("all");
  const [data, setData] = useState({ items: [], kpis: {}, years: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchMyLeaves({ year: year === "all" ? null : year, status }));
      setError("");
    } catch (e) {
      setError(leaveErrorMessage(e, "Impossible de charger vos demandes."));
    } finally {
      setLoading(false);
    }
  }, [year, status]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const kpis = data.kpis || {};
  const toggleStatus = (s) => setStatus((cur) => (cur === s ? "all" : s));

  return (
    <div className="space-y-5" data-testid="mes-conges">
      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard label="En attente" value={kpis.pending} tone="text-amber-700" testid="kpi-mes-pending"
          active={status === "pending"} onClick={() => toggleStatus("pending")} />
        <KpiCard label="Validées" value={kpis.approved} tone="text-emerald-700" testid="kpi-mes-approved"
          active={status === "approved"} onClick={() => toggleStatus("approved")} />
        <KpiCard label="Refusées" value={kpis.rejected} tone="text-red-700" testid="kpi-mes-rejected"
          active={status === "rejected"} onClick={() => toggleStatus("rejected")} />
      </div>
      <p className="text-xs text-muted-foreground -mt-2">Nombre de demandes (pas de jours) sur la période filtrée.</p>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={year} onValueChange={setYear}>
          <SelectTrigger className="h-9 w-[140px]" data-testid="mes-conges-year"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toutes années</SelectItem>
            {yearOptions(data.years).map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="h-9 w-[200px]" data-testid="mes-conges-status"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tous statuts</SelectItem>
            {Object.entries(STATUS_META).map(([id, m]) => <SelectItem key={id} value={id}>{m.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="flex-1" />
        <Button onClick={onNewRequest} data-testid="mes-conges-new" className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
          <Plus className="h-4 w-4" /> Nouvelle demande
        </Button>
      </div>

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
                <TableHead>Demandée le</TableHead>
                <TableHead>Début</TableHead>
                <TableHead>Fin</TableHead>
                <TableHead className="text-right">Jours</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Statut</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((item) => (
                <TableRow key={item.id} data-testid={`mes-conge-${item.id}`} className="cursor-pointer" onClick={() => setOpenId(item.id)}>
                  <TableCell className="text-muted-foreground">{formatDateTimeFr(item.created_at)}</TableCell>
                  <TableCell>{dayCell(item, "start")}</TableCell>
                  <TableCell>{dayCell(item, "end")}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatDays(item.days_count)}</TableCell>
                  <TableCell>{item.leave_type_label}</TableCell>
                  <TableCell><StatusBadge status={item.status} /></TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" className="h-8 gap-1" onClick={(e) => { e.stopPropagation(); setOpenId(item.id); }}>
                      <Eye className="h-3.5 w-3.5" /> Détail
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <LeaveDetailDialog
        leaveId={openId}
        open={Boolean(openId)}
        onOpenChange={(o) => { if (!o) setOpenId(null); }}
        onChanged={load}
      />
    </div>
  );
}
