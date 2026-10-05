import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Bell, Check, CalendarClock, FileSpreadsheet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "sonner";

function formatWhen(date, heure) {
  if (!date) return "—";
  try {
    const d = new Date(`${String(date).slice(0, 10)}T12:00:00`).toLocaleDateString("fr-CH");
    return heure ? `${d} · ${heure}` : d;
  } catch {
    return date;
  }
}

export default function NotificationBell() {
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const canProcess = hasPerm("demandes_offres.process");
  const [open, setOpen] = useState(false);
  const [rappelCount, setRappelCount] = useState(0);
  const [rappelItems, setRappelItems] = useState([]);
  const [offreCount, setOffreCount] = useState(0);
  const [offreItems, setOffreItems] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [rappelsRes, offresRes] = await Promise.all([
        api.get("/notifications/rappels").catch(() => ({ data: { count: 0, items: [] } })),
        api.get("/notifications/offres", { params: { limit: 20 } }).catch(() => ({ data: { count: 0, items: [] } })),
      ]);
      setRappelCount(Number(rappelsRes.data?.count) || 0);
      setRappelItems(Array.isArray(rappelsRes.data?.items) ? rappelsRes.data.items : []);
      const offresData = offresRes.data;
      const items = Array.isArray(offresData) ? offresData : (offresData?.items || []);
      const unread = Array.isArray(offresData)
        ? items.filter((x) => !x.read).length
        : (Number(offresData?.count) || items.filter((x) => !x.read).length);
      setOffreCount(unread);
      setOffreItems(items);
    } catch {
      // silencieux
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (open) {
      setLoading(true);
      load().finally(() => setLoading(false));
    }
  }, [open, load]);

  const totalCount = rappelCount + offreCount;

  const markDone = async (id, e) => {
    e?.stopPropagation?.();
    try {
      await api.post(`/rappels/${id}/effectuer`);
      toast.success("Rappel marqué effectué");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Action impossible");
    }
  };

  const openOffreNotif = async (n) => {
    try {
      if (n?.id && !n.read) await api.post(`/notifications/offres/${n.id}/read`);
    } catch {
      // ignore
    }
    setOpen(false);
    if (n?.demande_id) {
      navigate(canProcess ? `/demandes-offres/${n.demande_id}?from=gestion` : `/demandes-offres/${n.demande_id}`);
    } else {
      navigate(canProcess ? "/gestion-reponses-offres" : "/demandes-offres");
    }
    load();
  };

  const goClient = (clientId) => {
    if (!clientId) return;
    setOpen(false);
    navigate(`/clients/${clientId}`);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-testid="notification-bell"
          title="Notifications"
          className="relative p-2 rounded-md hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
        >
          <Bell className="h-5 w-5" />
          {totalCount > 0 && (
            <span
              data-testid="notification-bell-count"
              className="absolute -top-0.5 -right-0.5 min-w-[1.15rem] h-[1.15rem] px-1 rounded-full bg-[#002FA7] text-white text-[10px] font-bold flex items-center justify-center"
            >
              {totalCount > 99 ? "99+" : totalCount}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[380px] p-0">
        <div className="px-4 py-3 border-b border-border">
          <p className="text-sm font-semibold">Notifications</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">Rappels et demandes d&apos;offres</p>
        </div>
        <div className="max-h-[420px] overflow-y-auto">
          {loading ? (
            <p className="text-sm text-muted-foreground p-4">Chargement…</p>
          ) : (
            <>
              {offreItems.length > 0 && (
                <div>
                  <p className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Offres</p>
                  {offreItems.slice(0, 8).map((n) => (
                    <button
                      key={n.id}
                      type="button"
                      onClick={() => openOffreNotif(n)}
                      className={`w-full text-left px-4 py-3 border-b border-border transition-colors ${
                        n.read ? "hover:bg-secondary/40" : "bg-[#002FA7]/5 hover:bg-[#002FA7]/10"
                      }`}
                    >
                      <div className="flex gap-2">
                        <FileSpreadsheet className="h-4 w-4 text-[#002FA7] shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{n.title || "Notification offre"}</p>
                          {n.message && <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{n.message}</p>}
                          <p className="text-[11px] text-muted-foreground mt-1">{formatWhen(n.created_at)}</p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <div className="px-4 pt-3 pb-1 flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Rappels</p>
                <button
                  type="button"
                  className="text-xs text-[#002FA7] hover:underline"
                  onClick={() => { setOpen(false); navigate("/rappels"); }}
                >
                  Tout voir
                </button>
              </div>
              {rappelItems.length === 0 ? (
                <p className="text-sm text-muted-foreground px-4 pb-4">Aucun rappel à traiter.</p>
              ) : (
                rappelItems.map((r) => (
                  <div
                    key={r.id}
                    className={`px-4 py-3 border-b border-border last:border-0 transition-colors ${
                      r.priorite === "haute" ? "bg-red-50/70 hover:bg-red-50" : "hover:bg-secondary/40"
                    }`}
                  >
                    <button type="button" className="w-full text-left" onClick={() => goClient(r.client_id)}>
                      <p className="text-sm font-medium text-foreground truncate">{r.titre || "Rappel"}</p>
                      <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                        <CalendarClock className="h-3 w-3" />
                        {formatWhen(r.date_echeance || r.date, r.heure)}
                      </p>
                    </button>
                    <div className="mt-2 flex justify-end">
                      <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={(e) => markDone(r.id, e)}>
                        <Check className="h-3 w-3" /> Effectué
                      </Button>
                    </div>
                  </div>
                ))
              )}
              {offreItems.length === 0 && rappelItems.length === 0 && !loading && (
                <p className="text-sm text-muted-foreground p-4 text-center">Aucune notification.</p>
              )}
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
