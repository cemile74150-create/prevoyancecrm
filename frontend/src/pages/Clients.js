import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUT_COLORS } from "@/lib/constants";
import { Plus, Search, Mail, Phone, AlertTriangle, ChevronRight } from "lucide-react";

export default function Clients() {
  const [clients, setClients] = useState([]);
  const [q, setQ] = useState("");
  const [dialog, setDialog] = useState(false);
  const navigate = useNavigate();
const handleSaved = async () => {
  await load();
  setDialog(false);
};
  const load = async () => {
    const res = await api.get("/clients", { params: q ? { q } : {} });
    setClients(res.data);
  };
  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <Layout>
      <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
        <div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Clients</h1>
          <p className="text-muted-foreground mt-1">{clients.length} dossier{clients.length > 1 ? "s" : ""}</p>
        </div>
        <Button data-testid="clients-new-btn" onClick={() => setDialog(true)} className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
          <Plus className="h-4 w-4" /> Nouveau client
        </Button>
      </div>

      <div className="relative max-w-sm mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input data-testid="clients-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrer par nom, tél, email, n° dossier…" className="pl-10" />
      </div>

      <Card className="overflow-hidden">
        <div className="hidden md:grid grid-cols-12 gap-4 px-6 h-12 items-center border-b border-border text-xs font-semibold text-muted-foreground uppercase tracking-wide">
          <div className="col-span-3">Client</div>
          <div className="col-span-2">N° dossier</div>
          <div className="col-span-3">Contact</div>
          <div className="col-span-3">Statut</div>
          <div className="col-span-1"></div>
        </div>
        {clients.length === 0 ? (
          <p className="text-sm text-muted-foreground py-16 text-center">Aucun client trouvé.</p>
        ) : (
          clients.map((c) => (
            <button
              key={c.id}
              data-testid={`client-row-${c.id}`}
              onClick={() => navigate(`/clients/${c.id}`)}
              className="w-full grid grid-cols-1 md:grid-cols-12 gap-2 md:gap-4 px-6 py-4 items-center border-b border-border last:border-0 hover:bg-secondary text-left transition-colors group"
            >
              <div className="col-span-3 flex items-center gap-3">
                <div className="h-9 w-9 rounded-full bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center font-semibold text-sm flex-shrink-0">
                  {c.prenom?.[0]}{c.nom?.[0]}
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-sm truncate flex items-center gap-1.5">
                    {c.prenom} {c.nom}
                    {c.priorite === "urgent" && <AlertTriangle className="h-3.5 w-3.5 text-red-600" />}
                  </p>
                  {c.ville && <p className="text-xs text-muted-foreground">{c.ville}</p>}
                </div>
              </div>
              <div className="col-span-2 text-sm text-muted-foreground font-mono">{c.numero_dossier}</div>
              <div className="col-span-3 text-sm text-muted-foreground space-y-0.5">
                {c.email && <p className="flex items-center gap-1.5 truncate"><Mail className="h-3 w-3" />{c.email}</p>}
                {c.telephone && <p className="flex items-center gap-1.5"><Phone className="h-3 w-3" />{c.telephone}</p>}
              </div>
              <div className="col-span-3">
                <span className={`inline-block text-xs font-medium px-2.5 py-1 rounded-full border ${STATUT_COLORS[c.statut]}`}>{c.statut}</span>
              </div>
              <div className="col-span-1 flex justify-end">
                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </button>
          ))
        )}
      </Card>

    <ClientFormDialog
  open={dialog}
  onOpenChange={setDialog}
  onSaved={handleSaved}
/>
    </Layout>
  );
}
