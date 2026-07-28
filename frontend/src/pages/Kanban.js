import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUTS, STATUT_DOT } from "@/lib/constants";
import { Plus, AlertTriangle, GripVertical } from "lucide-react";
import { toast } from "sonner";

export default function Kanban() {
  const [clients, setClients] = useState([]);
  const [dialog, setDialog] = useState(false);
  const [dragId, setDragId] = useState(null);
  const [overCol, setOverCol] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  const load = async () => {
    const res = await api.get("/clients");
    setClients(res.data);
  };
  useEffect(() => { load(); }, []);

  const params = new URLSearchParams(location.search);
  const selectedStatut = params.get("statut");
  const selectedPriority = params.get("priorite");

  const filteredClients = clients.filter((client) => {
    if (selectedStatut && client.statut !== selectedStatut) return false;
    if (selectedPriority && client.priorite !== selectedPriority) return false;
    return true;
  });

  const onDrop = async (statut) => {
    setOverCol(null);
    const id = dragId;
    setDragId(null);
    if (!id) return;
    const c = clients.find((x) => x.id === id);
    if (!c || c.statut === statut) return;
    setClients((prev) => prev.map((x) => (x.id === id ? { ...x, statut } : x)));
    try {
      await api.patch(`/clients/${id}/statut`, { statut });
      toast.success(`Dossier déplacé vers « ${statut} »`);
    } catch (e) {
      toast.error("Erreur lors du déplacement");
      load();
    }
  };

  return (
    <Layout>
      <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
        <div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Dossiers</h1>
          <p className="text-muted-foreground mt-1">Glissez-déposez les cartes pour changer de statut</p>
        </div>
        <Button data-testid="kanban-new-dossier-btn" onClick={() => setDialog(true)} className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
          <Plus className="h-4 w-4" /> Nouveau dossier
        </Button>
      </div>

      {(selectedStatut || selectedPriority) && (
        <div className="mb-4 rounded-md border border-[#002FA7]/20 bg-[#002FA7]/5 px-4 py-3 text-sm text-[#002FA7]">
          Affichage filtré : {selectedStatut || `priorité ${selectedPriority}`}
        </div>
      )}

      <div className="flex gap-4 overflow-x-auto pb-4" data-testid="kanban-board">
        {STATUTS.map((statut) => {
          const items = filteredClients.filter((c) => c.statut === statut);
          return (
            <div
              key={statut}
              data-testid={`kanban-col-${statut}`}
              onDragOver={(e) => { e.preventDefault(); setOverCol(statut); }}
              onDragLeave={() => setOverCol((v) => (v === statut ? null : v))}
              onDrop={() => onDrop(statut)}
              className={`min-w-[300px] w-[300px] flex-shrink-0 rounded-lg border bg-card transition-colors ${
                overCol === statut ? "border-[#002FA7] bg-[#002FA7]/5" : "border-border"
              }`}
            >
              <div className="flex items-center justify-between px-4 h-12 border-b border-border">
                <div className="flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${STATUT_DOT[statut]}`} />
                  <span className="text-sm font-semibold">{statut}</span>
                </div>
                <span className="text-xs font-medium text-muted-foreground bg-secondary rounded-full px-2 py-0.5">{items.length}</span>
              </div>
              <div className="p-3 space-y-2.5 min-h-[120px]">
                {items.map((c) => (
                  <div
                    key={c.id}
                    draggable
                    onDragStart={() => setDragId(c.id)}
                    onDragEnd={() => setDragId(null)}
                    onClick={() => navigate(
                      c.linked_spouse_id || (c.etat_civil || "").toLowerCase().includes("mari")
                        ? `/dossiers/${c.dossier_id || c.id}`
                        : `/clients/${c.id}`
                    )}
                    data-testid={`kanban-card-${c.id}`}
                    className={`group bg-white border border-border rounded-md p-3 cursor-grab active:cursor-grabbing hover:border-[#002FA7] hover:shadow-sm transition-all ${
                      dragId === c.id ? "opacity-40" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold truncate">{c.prenom} {c.nom}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{c.numero_dossier}</p>
                      </div>
                      <GripVertical className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground" />
                    </div>
                    <div className="flex items-center gap-2 mt-3">
                      {c.priorite === "urgent" && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-red-700 bg-red-100 rounded px-1.5 py-0.5">
                          <AlertTriangle className="h-3 w-3" /> Urgent
                        </span>
                      )}
                      {c.ville && <span className="text-[11px] text-muted-foreground">{c.ville}</span>}
                    </div>
                  </div>
                ))}
                {items.length === 0 && (
                  <p className="text-xs text-muted-foreground/60 text-center py-4">Aucun dossier</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <ClientFormDialog
        open={dialog}
        onOpenChange={setDialog}
        onSaved={(created, meta = {}) => {
          load();
          if (meta.spouse || meta.isFamily) {
            navigate(`/dossiers/${created.dossier_id || created.id}`);
          }
        }}
      />
    </Layout>
  );
}
