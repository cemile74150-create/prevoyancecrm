import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ClientFormDialog from "@/components/ClientFormDialog";
import ClotureDossierDialog from "@/components/ClotureDossierDialog";
import SuiviDossiersStats from "@/components/SuiviDossiersStats";
import { STATUTS, STATUT_DOT, normalizeStatut } from "@/lib/constants";
import { Plus, AlertTriangle, MoreHorizontal, Folder, User, UserCheck, Search } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { conseillerNames as toConseillerNameList } from "@/lib/conseillers";
import {
  NON_ATTRIBUE,
  groupConseillers,
  groupMatchesConseiller,
  kanbanConseillerOptions,
  sameConseiller,
} from "@/lib/kanbanConseiller";
import {
  clotureCardClass,
  clotureMotifLabel,
  groupMatchesSearch,
  pickGroupCloture,
} from "@/lib/dossierCloture";

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

function dossierCreatedAt(group) {
  const stamps = (group?.members || [])
    .map((member) => member?.created_at)
    .filter(Boolean)
    .sort();
  return stamps[0] || "";
}

function formatDossierDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("fr-CH", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function dossierTitle(group) {
  if (group.type === "family") return group.dossier_label || "Sans nom";
  return `${group.members[0]?.prenom || ""} ${group.members[0]?.nom || ""}`.trim() || "Sans nom";
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
  const [search, setSearch] = useState("");
  const [cloturePending, setCloturePending] = useState(null);
  const [clotureSaving, setClotureSaving] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { hasPerm } = useAuth();
  const canCreate = hasPerm("dossiers.create");
  const canEdit = hasPerm("dossiers.edit");

  const load = async () => {
    const res = await api.get("/clients", { params: { scope: "dossiers" } });
    setClients(res.data);
  };
  useEffect(() => { load(); }, []);

  const [activeConseillers, setActiveConseillers] = useState([]);
  useEffect(() => {
    api.get("/users/conseillers").then((r) => setActiveConseillers(toConseillerNameList(r.data))).catch(() => {});
  }, []);

  const params = new URLSearchParams(location.search);
  const selectedStatut = params.get("statut");
  const selectedPriority = params.get("priorite");
  const selectedConseiller = params.get("conseiller");

  const groups = buildKanbanGroups(clients);
  const conseillerOptions = kanbanConseillerOptions(activeConseillers, groups);
  if (
    selectedConseiller &&
    selectedConseiller !== NON_ATTRIBUE &&
    !conseillerOptions.some((n) => sameConseiller(n, selectedConseiller))
  ) {
    conseillerOptions.push(selectedConseiller);
  }
  const conseillerSelectValue = !selectedConseiller
    ? "all"
    : selectedConseiller === NON_ATTRIBUE
      ? NON_ATTRIBUE
      : conseillerOptions.find((n) => sameConseiller(n, selectedConseiller));

  const onConseillerChange = (value) => {
    const next = new URLSearchParams(location.search);
    if (!value || value === "all") next.delete("conseiller");
    else next.set("conseiller", value);
    const qs = next.toString();
    navigate(qs ? `/dossiers?${qs}` : "/dossiers", { replace: true });
  };

  const filteredGroups = groups.filter((g) => {
    if (selectedStatut && g.statut !== selectedStatut) return false;
    if (selectedPriority && g.priorite !== selectedPriority) return false;
    if (!groupMatchesConseiller(g, selectedConseiller)) return false;
    if (!groupMatchesSearch(g, search)) return false;
    return true;
  });

  const applyStatut = async (group, statut, cloture = null) => {
    const payload = cloture
      ? { statut, cloture_date: cloture.cloture_date, cloture_motif: cloture.cloture_motif }
      : { statut };

    setClients((prev) => prev.map((x) => (
      group.memberIds.includes(x.id)
        ? {
            ...x,
            statut,
            ...(cloture
              ? { cloture_date: cloture.cloture_date, cloture_motif: cloture.cloture_motif }
              : {}),
          }
        : x
    )));
    try {
      await Promise.all(group.memberIds.map((clientId) => api.patch(`/clients/${clientId}/statut`, payload)));
      toast.success(
        cloture
          ? `Dossier clôturé (${clotureMotifLabel(cloture.cloture_motif)})`
          : `Dossier déplacé vers « ${statut} »`
      );
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur lors du déplacement");
      load();
    }
  };

  const onDrop = async (statut) => {
    setOverCol(null);
    const id = dragId;
    setDragId(null);
    if (!id || !canEdit) return;
    const nowGroups = buildKanbanGroups(clients);
    const g = nowGroups.find((x) => x.key === id);
    if (!g || g.statut === statut) return;

    if (statut === "Clôturé") {
      const existing = pickGroupCloture(g);
      setCloturePending({ group: g, initialDate: existing.clotureDate, initialMotif: existing.clotureMotif || "" });
      return;
    }

    await applyStatut(g, statut);
  };

  const confirmCloture = async ({ cloture_date, cloture_motif }) => {
    if (!cloturePending?.group) return;
    setClotureSaving(true);
    try {
      await applyStatut(cloturePending.group, "Clôturé", { cloture_date, cloture_motif });
      setCloturePending(null);
    } finally {
      setClotureSaving(false);
    }
  };

  const hasBoardFilters = selectedStatut || selectedPriority || selectedConseiller || search.trim();

  return (
    <Layout>
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <h1 className="font-display font-black text-2xl sm:text-3xl tracking-tight">Suivi de vos dossiers</h1>
          <p className="text-muted-foreground text-sm mt-0.5">
            Prévoyance uniquement — glissez-déposez pour changer de statut
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher (nom, référence…)"
              className="h-8 w-[220px] pl-7 text-xs"
              data-testid="kanban-search"
            />
          </div>
          <Select value={conseillerSelectValue} onValueChange={onConseillerChange}>
            <SelectTrigger className="w-[220px] h-8 text-xs" data-testid="kanban-filter-conseiller" aria-label="Conseiller">
              <SelectValue placeholder="Tous les conseillers" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tous les conseillers</SelectItem>
              <SelectItem value={NON_ATTRIBUE}>{NON_ATTRIBUE}</SelectItem>
              {conseillerOptions.map((n) => (
                <SelectItem key={n} value={n}>{n}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {canCreate && (
          <Button data-testid="kanban-new-dossier-btn" size="sm" onClick={() => setDialog(true)} className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5 h-8">
            <Plus className="h-3.5 w-3.5" /> Nouveau dossier
          </Button>
          )}
        </div>
      </div>

      {hasBoardFilters && (
        <div className="mb-3 rounded-md border border-[#002FA7]/20 bg-[#002FA7]/5 px-3 py-2 text-xs text-[#002FA7] flex items-center justify-between gap-2">
          <span>
            Affichage filtré : {[
              selectedConseiller,
              selectedStatut,
              selectedPriority ? `priorité ${selectedPriority}` : null,
              search.trim() ? `recherche « ${search.trim()} »` : null,
            ].filter(Boolean).join(" · ")}
          </span>
          <button
            type="button"
            className="underline"
            onClick={() => {
              setSearch("");
              navigate("/dossiers", { replace: true });
            }}
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
                  <span className="text-xs font-semibold truncate" title={statut}>{statut}</span>
                </div>
                <span className="text-[10px] font-medium text-muted-foreground bg-background/80 rounded-full px-1.5 py-0.5 tabular-nums">
                  {items.length}
                </span>
              </div>
              <div className="px-1.5 pb-1.5 space-y-1 min-h-[80px] max-h-[calc(100vh-11rem)] overflow-y-auto">
                {items.map((c) => {
                  const title = dossierTitle(c);
                  const createdLabel = formatDossierDate(dossierCreatedAt(c));
                  const conseillerLabel = groupConseillers(c).join(" · ");
                  const cloture = pickGroupCloture(c);
                  const colorClass = clotureCardClass(c.statut, cloture.clotureMotif);
                  return (
                    <div
                      key={c.key}
                      draggable={canEdit}
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
                      data-cloture-motif={c.statut === "Clôturé" ? (cloture.clotureMotif || "non_renseigne") : undefined}
                      className={`group relative bg-card border border-border/80 rounded-md px-2 py-1.5 cursor-pointer select-none
                        hover:border-[#002FA7]/50 hover:bg-white hover:shadow-sm transition-all duration-150
                        active:cursor-grabbing ${dragId === c.key ? "opacity-40 scale-[0.98]" : ""} ${colorClass}`}
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
                          <p className="mt-0.5 text-[11px] text-muted-foreground" data-testid={`kanban-date-${c.key}`}>
                            {createdLabel}
                          </p>
                          {c.statut === "Clôturé" && (
                            <p
                              className="mt-0.5 text-[11px] font-medium"
                              data-testid={`kanban-cloture-${c.key}`}
                              title={cloture.clotureDate ? `Clôturé le ${cloture.clotureDate}` : undefined}
                            >
                              {cloture.clotureMotifLabel}
                            </p>
                          )}
                          <p
                            className={`mt-0.5 flex items-center gap-1 text-[11px] leading-tight ${conseillerLabel ? "text-[#002FA7]/80" : "text-muted-foreground/60 italic"}`}
                            data-testid={`kanban-conseiller-${c.key}`}
                            title={conseillerLabel ? `Conseiller : ${conseillerLabel}` : "Aucun conseiller attribué"}
                          >
                            <UserCheck className="h-3 w-3 shrink-0" />
                            <span className="truncate">{conseillerLabel || NON_ATTRIBUE}</span>
                          </p>
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

      <SuiviDossiersStats conseillerOptions={conseillerOptions} />

      <ClotureDossierDialog
        open={Boolean(cloturePending)}
        onOpenChange={(open) => { if (!open && !clotureSaving) setCloturePending(null); }}
        description={cloturePending?.group ? `Dossier : ${dossierTitle(cloturePending.group)}` : undefined}
        initialDate={cloturePending?.initialDate}
        initialMotif={cloturePending?.initialMotif}
        onConfirm={confirmCloture}
        saving={clotureSaving}
      />

      <ClientFormDialog
        open={dialog}
        onOpenChange={setDialog}
        defaultActivites={["prevoyance"]}
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
