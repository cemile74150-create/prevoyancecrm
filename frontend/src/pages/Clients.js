import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUT_COLORS } from "@/lib/constants";
import { Plus, Search, Mail, Phone, AlertTriangle, ChevronRight, FolderOpen, User } from "lucide-react";

/**
 * Regroupe les clients par dossier familial.
 * Priorité : dossier_id partagé.
 * Fallback : linked_spouse_id (dossiers non encore fusionnés en base).
 */
function buildGroups(clients) {
  // Première passe : map id → client
  const byId = {};
  clients.forEach((c) => { byId[c.id] = c; });

  // Résoudre le dossier canonique pour chaque client
  // Si deux clients ont linked_spouse_id l'un vers l'autre, on les regroupe
  // sous le même dossier même si dossier_id diffère encore en base.
  const canonical = {}; // client.id → canonical dossier key
  clients.forEach((c) => {
    if (canonical[c.id]) return;
    const sid = c.linked_spouse_id;
    const spouse = sid ? byId[sid] : null;
    // Only group as couple if both exist AND at least one has a married état civil
    if (spouse && (isMarriedEtat(c.etat_civil) || isMarriedEtat(spouse.etat_civil))) {
      const key = c.dossier_id && spouse.dossier_id
        ? (c.dossier_id < spouse.dossier_id ? c.dossier_id : spouse.dossier_id)
        : c.dossier_id || spouse.dossier_id || c.id;
      canonical[c.id] = key;
      canonical[sid] = key;
    } else {
      canonical[c.id] = c.dossier_id || c.id;
    }
  });

  const groups = {};
  clients.forEach((c) => {
    const key = canonical[c.id] || c.id;
    if (!groups[key]) groups[key] = [];
    // Éviter les doublons
    if (!groups[key].find((m) => m.id === c.id)) groups[key].push(c);
  });

  return Object.values(groups);
}

function isMarriedEtat(etat) {
  const v = (etat || "").toLowerCase();
  return v.includes("mari") || v.includes("partenariat");
}

function isFamilyGroup(members) {
  if (members.length > 1) return true;
  const c = members[0];
  if (!isMarriedEtat(c?.etat_civil)) return false;
  return Boolean(c?.linked_spouse_id);
}

export default function Clients() {
  const [clients, setClients] = useState([]);
  const [q, setQ] = useState("");
  const [dialog, setDialog] = useState(false);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    const res = await api.get("/clients", {
      params: q ? { q } : {},
    });
    setClients(res.data);
  }, [q]);

  const handleSaved = async (createdClient, meta = {}) => {
    await load();
    setDialog(false);
    const hubId = createdClient?.dossier_id || createdClient?.id;
    if (meta.spouse || meta.isFamily) {
      navigate(`/dossiers/${hubId}`);
    }
  };

  useEffect(() => {
    const t = setTimeout(() => {
      load();
    }, 200);
    return () => clearTimeout(t);
  }, [load]);

  const groups = buildGroups(clients);

  return (
    <Layout>
      <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
        <div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Clients</h1>
          <p className="text-muted-foreground mt-1">
            {groups.length} dossier{groups.length > 1 ? "s" : ""} · {clients.length} client{clients.length > 1 ? "s" : ""}
          </p>
        </div>
        <Button data-testid="clients-new-btn" onClick={() => setDialog(true)} className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
          <Plus className="h-4 w-4" /> Nouveau client
        </Button>
      </div>

      <div className="relative max-w-sm mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input data-testid="clients-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrer par nom, tél, email, n° dossier…" className="pl-10" />
      </div>

      <div className="space-y-3">
        {groups.length === 0 ? (
          <Card className="p-10">
            <p className="text-sm text-muted-foreground text-center">Aucun client trouvé.</p>
          </Card>
        ) : (
          groups.map((members) => {
            const c = members[0];
            const family = isFamilyGroup(members);
            // Pour un couple, l'hubId = dossier_id du primary (premier par created_at)
            const sorted = [...members].sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
            const hubId = sorted[0]?.dossier_id || sorted[0]?.id || c.dossier_id || c.id;

            if (!family) {
              return (
                <Card key={hubId} className="overflow-hidden">
                  <button
                    data-testid={`client-row-${c.id}`}
                    onClick={() => navigate(`/clients/${c.id}`)}
                    className="w-full flex items-center gap-4 px-5 py-4 text-left hover:bg-secondary transition-colors group"
                  >
                    <div className="h-10 w-10 rounded-full bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center font-semibold text-sm flex-shrink-0">
                      {c.prenom?.[0]}{c.nom?.[0]}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-sm truncate flex items-center gap-1.5">
                        {c.prenom} {c.nom}
                        {c.priorite === "urgent" && <AlertTriangle className="h-3.5 w-3.5 text-red-600" />}
                      </p>
                      <p className="text-xs text-muted-foreground font-mono">{c.numero_dossier}</p>
                    </div>
                    <div className="hidden sm:block text-sm text-muted-foreground space-y-0.5 min-w-[10rem]">
                      {c.email && <p className="flex items-center gap-1.5 truncate"><Mail className="h-3 w-3" />{c.email}</p>}
                      {c.telephone && <p className="flex items-center gap-1.5"><Phone className="h-3 w-3" />{c.telephone}</p>}
                    </div>
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${STATUT_COLORS[c.statut]}`}>{c.statut}</span>
                    <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
                  </button>
                </Card>
              );
            }

            return (
              <Card key={hubId} className="overflow-hidden" data-testid={`dossier-row-${hubId}`}>
                <button
                  type="button"
                  onClick={() => navigate(`/dossiers/${hubId}`)}
                  className="w-full flex items-center gap-3 px-5 py-3 border-b border-border bg-[#002FA7]/5 text-left hover:bg-[#002FA7]/10 transition-colors"
                >
                  <FolderOpen className="h-5 w-5 text-[#002FA7] shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="font-display font-bold text-[#002FA7]">
                      {c.dossier_label || `Famille ${c.nom}`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      1 dossier · {members.length} client{members.length > 1 ? "s" : ""} distinct{members.length > 1 ? "s" : ""} · <span className="font-mono">{c.numero_dossier}</span>
                    </p>
                  </div>
                  <span className="text-xs text-[#002FA7] font-medium hidden sm:inline">Ouvrir le dossier</span>
                  <ChevronRight className="h-4 w-4 text-[#002FA7]" />
                </button>

                <div className="divide-y divide-border">
                  {members.map((member) => (
                    <button
                      key={member.id}
                      type="button"
                      data-testid={`client-row-${member.id}`}
                      onClick={() => navigate(`/clients/${member.id}`)}
                      className="w-full flex items-center gap-4 px-5 py-3.5 text-left hover:bg-secondary transition-colors group"
                    >
                      <div className="h-9 w-9 rounded-full bg-secondary text-foreground flex items-center justify-center shrink-0">
                        <User className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-sm truncate flex items-center gap-1.5">
                          {member.prenom} {member.nom}
                          {member.priorite === "urgent" && <AlertTriangle className="h-3.5 w-3.5 text-red-600" />}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Fiche client séparée
                          {member.date_naissance ? ` · né(e) ${member.date_naissance}` : ""}
                        </p>
                      </div>
                      <div className="hidden md:block text-sm text-muted-foreground space-y-0.5 min-w-[10rem]">
                        {member.email && <p className="flex items-center gap-1.5 truncate"><Mail className="h-3 w-3" />{member.email}</p>}
                        {member.telephone && <p className="flex items-center gap-1.5"><Phone className="h-3 w-3" />{member.telephone}</p>}
                      </div>
                      <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${STATUT_COLORS[member.statut]}`}>{member.statut}</span>
                      <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100" />
                    </button>
                  ))}
                  {members.length < 2 && (
                    <div className="px-5 py-3 text-xs text-amber-700 bg-amber-50 border-t border-amber-100">
                      Un seul client pour l’instant — créez la 2ᵉ fiche conjoint depuis le dossier ou la fiche.
                    </div>
                  )}
                </div>
              </Card>
            );
          })
        )}
      </div>

      <ClientFormDialog
        open={dialog}
        onOpenChange={setDialog}
        onSaved={handleSaved}
      />
    </Layout>
  );
}
