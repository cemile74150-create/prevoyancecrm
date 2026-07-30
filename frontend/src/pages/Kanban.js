import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUTS, STATUT_DOT, normalizeStatut } from "@/lib/constants";
import { Plus, AlertTriangle, MoreHorizontal, Folder, User } from "lucide-react";
import { toast } from "sonner";

function isMarriedEtat(etat) {
  const v = (etat || "").toLowerCase();
  return v.includes("mari") || v.includes("partenariat");
}

function pickGroupStatut(members) {
  if (!members?.length) return "";
  if (members.length === 1) return normalizeStatut(members[0].statut);

  const counts = members.reduce((acc, m) => {
    const key = normalizeStatut(m.statut);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  let bestStatut = normalizeStatut(members[0].statut);
  let bestCount = -1;
  Object.entries(counts).forEach(([statut, count]) => {
    if (count > bestCount) {
      bestStatut = statut;
      bestCount = count;
      return;
    }
    if (count === bestCount) {
      if (STATUTS.indexOf(statut) < STATUTS.indexOf(bestStatut)) bestStatut = statut;
    }
  });

  return bestStatut;
}

function pickVille(members) {
  for (const m of members || []) {
    if (m?.ville) return m.ville;
  }
  return "";
}

function buildKanbanGroups(clients) {
  const byId = {};
  (clients || []).forEach((c) => { byId[c.id] = c; });

  const groups = {};
  const processed = new Set();

  (clients || []).forEach((c) => {
    if (!c || processed.has(c.id)) return;

    const spouseId = c.linked_spouse_id;
    const spouse = spouseId ? byId[spouseId] : null;
    const isFamily = Boolean(
      spouse &&
      isMarriedEtat(c.etat_civil) &&
      isMarriedEtat(spouse.etat_civil)
    );

    if (isFamily) {
      const key = c.dossier_id || spouse.dossier_id || c.id;
      const members = [c, spouse].slice().sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));

      processed.add(c.id);
      processed.add(spouse.id);

      const urgent = members.some((m) => m.priorite === "urgent");
      const groupStatut = pickGroupStatut(members);

      groups[key] = {
        key,
        type: "family",
        dossier_id: key,
        dossier_label: members[0]?.dossier_label || c.dossier_label || spouse.dossier_label || `Famille ${c.nom}`,
        numero_dossier: members[0]?.numero_dossier || c.numero_dossier || spouse.numero_dossier,
        priorite: urgent ? "urgent" : (members[0]?.priorite || "normale"),
        statut: groupStatut,
        ville: pickVille(members),
        memberIds: members.map((m) => m.id),
        members,
      };
    } else {
      processed.add(c.id);
      groups[c.id] = {
        key: c.id,
        type: "client",
        dossier_id: c.dossier_id,
        dossier_label: null,
        numero_dossier: c.numero_dossier,
        priorite: c.priorite,
        statut: normalizeStatut(c.statut),
        ville: c.ville || "",
        memberIds: [c.id],
        representativeId: c.id,
        members: [c],
      };
    }
  });

  return Object.values(groups);
}

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

  const groups = buildKanbanGroups(clients);

  const filteredGroups = groups.filter((g) => {
    if (selectedStatut && g.statut !== selectedStatut) return false;
    if (selectedPriority && g.priorite !== selectedPriority) return false;
    return true;
  });

  const onDrop = async (statut) => {
    setOverCol(null);
    const id = dragId;
    setDragId(null);
    if (!id) return;
    const nowGroups = buildKanbanGroups(clients);
    const g = nowGroups.find((x) => x.key === id);
    if (!g || g.statut === statut) return;

    setClients((prev) => prev.map((x) => (g.memberIds.includes(x.id) ? { ...x, statut } : x)));
    try {
      await Promise.all(g.memberIds.map((clientId) => api.patch(`/clients/${clientId}/statut`, { statut })));
      toast.success(`Dossier déplacé vers « ${statut} »`);
    } catch (e) {
      toast.error("Erreur lors du déplacement");
      load();
    }
  };

  return (
    <Layout>
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <h1 className="font-display font-black text-2xl sm:text-3xl tracking-tight">Dossiers</h1>
          <p className="text-muted-foreground text-sm mt-0.5">Glissez-déposez pour changer de statut</p>
        </div>
        <Button data-testid="kanban-new-dossier-btn" size="sm" onClick={() => setDialog(true)} className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5 h-8">
          <Plus className="h-3.5 w-3.5" /> Nouveau dossier
        </Button>
      </div>

      {(selectedStatut || selectedPriority) && (
        <div className="mb-3 rounded-md border border-[#002FA7]/20 bg-[#002FA7]/5 px-3 py-2 text-xs text-[#002FA7]">
          Affichage filtré : {selectedStatut || `priorité ${selectedPriority}`}
        </div>
      )}

      <div className="flex gap-2.5 overflow-x-auto pb-3 -mx-1 px-1" data-testid="kanban-board">
        {STATUTS.map((statut) => {
          const items = filteredGroups.filter((g) => g.statut === statut);
          return (
            <div
              key={statut}
              data-testid={`kanban-col-${statut}`}
              onDragOver={(e) => { e.preventDefault(); setOverCol(statut); }}
              onDragLeave={() => setOverCol((v) => (v === statut ? null : v))}
              onDrop={() => onDrop(statut)}
              className={`w-[220px] min-w-[200px] max-w-[240px] flex-shrink-0 rounded-lg bg-secondary/60 transition-colors ${
                overCol === statut ? "ring-2 ring-[#002FA7]/40 bg-[#002FA7]/5" : ""
              }`}
            >
              <div className="flex items-center justify-between px-2.5 h-9">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className={`h-2 w-2 rounded-full shrink-0 ${STATUT_DOT[statut]}`} />
                  <span className="text-xs font-semibold truncate">{statut}</span>
                </div>
                <span className="text-[10px] font-medium text-muted-foreground bg-background/80 rounded-full px-1.5 py-0.5 tabular-nums">
                  {items.length}
                </span>
              </div>
              <div className="px-1.5 pb-1.5 space-y-1 min-h-[80px] max-h-[calc(100vh-11rem)] overflow-y-auto">
                {items.map((c) => {
                  const title = c.type === "family"
                    ? c.dossier_label
                    : `${c.members[0]?.prenom || ""} ${c.members[0]?.nom || ""}`.trim();
                  return (
                    <div
                      key={c.key}
                      draggable
                      onDragStart={(e) => {
                        setDragId(c.key);
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      onDragEnd={() => setDragId(null)}
                      onClick={() => navigate(
                        c.type === "family"
                          ? `/dossiers/${c.dossier_id}`
                          : `/clients/${c.representativeId}`
                      )}
                      data-testid={`kanban-card-${c.key}`}
                      className={`group relative bg-card border border-border/80 rounded-md px-2 py-1.5 cursor-pointer select-none
                        hover:border-[#002FA7]/50 hover:bg-white hover:shadow-sm transition-all duration-150
                        active:cursor-grabbing ${dragId === c.key ? "opacity-40 scale-[0.98]" : ""}`}
                    >
                      <div className="flex items-start gap-1.5">
                        <span className="mt-0.5 text-muted-foreground/70 shrink-0">
                          {c.type === "family"
                            ? <Folder className="h-3.5 w-3.5" />
                            : <User className="h-3.5 w-3.5" />}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-1">
                            <p className="text-[13px] font-semibold leading-snug truncate pr-1" title={title}>
                              {title || "Sans nom"}
                            </p>
                            <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground/0 group-hover:text-muted-foreground/60 shrink-0 mt-0.5 transition-colors" />
                          </div>
                          <div className="flex items-center gap-1.5 mt-0.5 text-[11px] text-muted-foreground leading-tight">
                            {c.numero_dossier && (
                              <span className="font-mono truncate">{c.numero_dossier}</span>
                            )}
                            {c.ville && (
                              <>
                                <span className="text-muted-foreground/40">·</span>
                                <span className="truncate">{c.ville}</span>
                              </>
                            )}
                            {c.priorite === "urgent" && (
                              <span className="inline-flex items-center text-red-600 shrink-0" title="Urgent">
                                <AlertTriangle className="h-3 w-3" />
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
                {items.length === 0 && (
                  <p className="text-[11px] text-muted-foreground/50 text-center py-3">Aucun dossier</p>
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
