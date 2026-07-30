import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ClientFormDialog from "@/components/ClientFormDialog";
import {
  STATUTS, STATUT_DOT, normalizeStatut, CONSEILLERS, UNASSIGNED_CONSEILLER,
} from "@/lib/constants";
import {
  Plus, AlertTriangle, MoreHorizontal, Folder, User, Users, Trophy, UserX,
} from "lucide-react";
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

function normalizeConseillerName(raw) {
  const name = (raw || "").trim();
  if (!name) return UNASSIGNED_CONSEILLER;
  const known = CONSEILLERS.find((c) => c.casefold?.() === name.casefold() || c.toLowerCase() === name.toLowerCase());
  return known || name;
}

function pickGroupConseiller(members) {
  const names = (members || [])
    .map((m) => (m?.conseiller || "").trim())
    .filter(Boolean);
  if (!names.length) return UNASSIGNED_CONSEILLER;
  // Plus fréquent, sinon premier non vide
  const counts = {};
  names.forEach((n) => {
    const key = normalizeConseillerName(n);
    counts[key] = (counts[key] || 0) + 1;
  });
  return Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0][0];
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
        conseiller: pickGroupConseiller(members),
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
        conseiller: normalizeConseillerName(c.conseiller),
        ville: c.ville || "",
        memberIds: [c.id],
        representativeId: c.id,
        members: [c],
      };
    }
  });

  return Object.values(groups);
}

function buildConseillerStats(groups) {
  const byName = {};
  (groups || []).forEach((g) => {
    const name = g.conseiller || UNASSIGNED_CONSEILLER;
    if (!byName[name]) {
      byName[name] = {
        name,
        total: 0,
        byStatut: Object.fromEntries(STATUTS.map((s) => [s, 0])),
      };
    }
    byName[name].total += 1;
    const st = normalizeStatut(g.statut);
    if (byName[name].byStatut[st] !== undefined) byName[name].byStatut[st] += 1;
  });

  // Toujours afficher les conseillers connus même à 0
  CONSEILLERS.forEach((name) => {
    if (!byName[name]) {
      byName[name] = {
        name,
        total: 0,
        byStatut: Object.fromEntries(STATUTS.map((s) => [s, 0])),
      };
    }
  });
  if (!byName[UNASSIGNED_CONSEILLER]) {
    byName[UNASSIGNED_CONSEILLER] = {
      name: UNASSIGNED_CONSEILLER,
      total: 0,
      byStatut: Object.fromEntries(STATUTS.map((s) => [s, 0])),
    };
  }

  const list = Object.values(byName).sort((a, b) => {
    if (a.name === UNASSIGNED_CONSEILLER) return 1;
    if (b.name === UNASSIGNED_CONSEILLER) return -1;
    if (b.total !== a.total) return b.total - a.total;
    return a.name.localeCompare(b.name, "fr");
  });

  const assigned = list.filter((c) => c.name !== UNASSIGNED_CONSEILLER);
  const top = assigned.reduce((best, cur) => (!best || cur.total > best.total ? cur : best), null);
  const unassigned = byName[UNASSIGNED_CONSEILLER]?.total || 0;

  return {
    list,
    total: (groups || []).length,
    top,
    unassigned,
  };
}

const STATUT_EMOJI = {
  "Nouveau": "🟢",
  "Documents en attente": "🟡",
  "Analyse en cours": "🔵",
  "Stand-by": "🟠",
  "À présenter": "🟣",
  "Clôturé": "⚫",
};

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
  const selectedConseiller = params.get("conseiller") || "Tous";

  const setConseillerFilter = (value) => {
    const next = new URLSearchParams(location.search);
    if (!value || value === "Tous") next.delete("conseiller");
    else next.set("conseiller", value);
    const qs = next.toString();
    navigate(`/dossiers${qs ? `?${qs}` : ""}`, { replace: true });
  };

  const groups = useMemo(() => buildKanbanGroups(clients), [clients]);
  const conseillerStats = useMemo(() => buildConseillerStats(groups), [groups]);

  const conseillerOptions = useMemo(() => {
    const fromData = groups
      .map((g) => g.conseiller)
      .filter((n) => n && n !== UNASSIGNED_CONSEILLER);
    return Array.from(new Set([...CONSEILLERS, ...fromData])).sort((a, b) => a.localeCompare(b, "fr"));
  }, [groups]);

  const filteredGroups = groups.filter((g) => {
    if (selectedStatut && g.statut !== selectedStatut) return false;
    if (selectedPriority && g.priorite !== selectedPriority) return false;
    if (selectedConseiller && selectedConseiller !== "Tous" && g.conseiller !== selectedConseiller) return false;
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

      {/* Résumé charge conseillers */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-3" data-testid="conseiller-summary">
        <Card className="p-3 border-border/80">
          <p className="text-[11px] text-muted-foreground">Total dossiers</p>
          <p className="font-display font-bold text-xl tabular-nums mt-0.5">{conseillerStats.total}</p>
        </Card>
        <Card className="p-3 border-border/80">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1"><Users className="h-3 w-3" /> Conseillers actifs</p>
          <p className="font-display font-bold text-xl tabular-nums mt-0.5">
            {conseillerStats.list.filter((c) => c.name !== UNASSIGNED_CONSEILLER && c.total > 0).length}
          </p>
        </Card>
        <Card className="p-3 border-border/80">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1"><Trophy className="h-3 w-3" /> Plus de dossiers</p>
          <p className="font-semibold text-sm mt-1 truncate" title={conseillerStats.top?.name}>
            {conseillerStats.top && conseillerStats.top.total > 0
              ? `${conseillerStats.top.name} (${conseillerStats.top.total})`
              : "—"}
          </p>
        </Card>
        <Card className="p-3 border-border/80">
          <p className="text-[11px] text-muted-foreground flex items-center gap-1"><UserX className="h-3 w-3" /> Non attribués</p>
          <p className="font-display font-bold text-xl tabular-nums mt-0.5">{conseillerStats.unassigned}</p>
        </Card>
      </div>

      <div className="mb-3">
        <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
          <h2 className="text-sm font-semibold text-[#002FA7]">Répartition des dossiers par conseiller</h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Conseiller</span>
            <Select value={selectedConseiller} onValueChange={setConseillerFilter}>
              <SelectTrigger data-testid="conseiller-filter" className="h-8 w-[200px] text-xs">
                <SelectValue placeholder="Tous" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Tous">Tous</SelectItem>
                {conseillerOptions.map((name) => (
                  <SelectItem key={name} value={name}>{name}</SelectItem>
                ))}
                <SelectItem value={UNASSIGNED_CONSEILLER}>{UNASSIGNED_CONSEILLER}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-2.5" data-testid="conseiller-cards">
          {conseillerStats.list.filter((c) => c.total > 0 || CONSEILLERS.includes(c.name)).map((c) => {
            const active = selectedConseiller === c.name;
            return (
              <button
                key={c.name}
                type="button"
                data-testid={`conseiller-card-${c.name}`}
                onClick={() => setConseillerFilter(active ? "Tous" : c.name)}
                className={`text-left rounded-lg border bg-card p-3 transition-all hover:border-[#002FA7]/40 hover:shadow-sm ${
                  active ? "border-[#002FA7] ring-1 ring-[#002FA7]/30" : "border-border/80"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="h-7 w-7 rounded-full bg-secondary flex items-center justify-center text-xs font-semibold shrink-0">
                      {(c.name === UNASSIGNED_CONSEILLER ? "?" : c.name.split(" ").map((p) => p[0]).join("").slice(0, 2)).toUpperCase()}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">{c.name}</p>
                      <p className="text-[11px] text-muted-foreground">📂 {c.total} dossier{c.total === 1 ? "" : "s"}</p>
                    </div>
                  </div>
                </div>
                <div className="mt-2.5 grid grid-cols-2 gap-x-2 gap-y-1">
                  {STATUTS.map((s) => (
                    <div key={s} className="flex items-center justify-between gap-1 text-[11px]">
                      <span className="text-muted-foreground truncate">
                        <span className="mr-1">{STATUT_EMOJI[s]}</span>
                        {s === "Documents en attente" ? "Docs attente" : s === "Analyse en cours" ? "Analyse" : s === "À présenter" ? "Présenter" : s === "Clôturé" ? "Clôturés" : s}
                      </span>
                      <span className="font-medium tabular-nums">{c.byStatut[s] || 0}</span>
                    </div>
                  ))}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {(selectedStatut || selectedPriority || (selectedConseiller && selectedConseiller !== "Tous")) && (
        <div className="mb-3 rounded-md border border-[#002FA7]/20 bg-[#002FA7]/5 px-3 py-2 text-xs text-[#002FA7] flex items-center justify-between gap-2 flex-wrap">
          <span>
            Affichage filtré :
            {[selectedConseiller && selectedConseiller !== "Tous" ? selectedConseiller : null, selectedStatut, selectedPriority ? `priorité ${selectedPriority}` : null]
              .filter(Boolean)
              .join(" · ")}
          </span>
          <button
            type="button"
            className="underline underline-offset-2"
            onClick={() => navigate("/dossiers", { replace: true })}
          >
            Réinitialiser
          </button>
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
