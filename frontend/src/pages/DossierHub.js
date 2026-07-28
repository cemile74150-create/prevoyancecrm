import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ArrowLeft, ChevronRight, FileText, StickyNote, Users2 } from "lucide-react";

function fmtDate(s) {
  if (!s) return "";
  try {
    return new Date(s).toLocaleString("fr-CH", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return s;
  }
}

export default function DossierHub() {
  const { dossierId } = useParams();
  const navigate = useNavigate();
  const [dossier, setDossier] = useState(null);

  useEffect(() => {
    api.get(`/dossiers/${dossierId}`)
      .then((res) => setDossier(res.data))
      .catch(() => setDossier({ members: [], documents: [], notes: [] }));
  }, [dossierId]);

  if (!dossier) {
    return (
      <Layout>
        <div className="animate-pulse text-muted-foreground">Chargement…</div>
      </Layout>
    );
  }
  if (!dossier.members?.length) {
    return (
      <Layout>
        <p className="text-muted-foreground">Dossier introuvable.</p>
      </Layout>
    );
  }

  const docs = dossier.documents || [];
  const notes = dossier.notes || [];

  return (
    <Layout>
      <Button variant="ghost" onClick={() => navigate("/clients")} className="mb-4 gap-2" data-testid="dossier-back">
        <ArrowLeft className="h-4 w-4" /> Retour aux clients
      </Button>

      <div className="mb-6">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-full bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center">
            <Users2 className="h-6 w-6" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Dossier familial</p>
            <h1 className="font-display font-black text-3xl tracking-tight">{dossier.dossier_label}</h1>
            <p className="text-sm text-muted-foreground font-mono mt-0.5">{dossier.numero_dossier}</p>
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-3 max-w-2xl">
          Choisissez la personne à consulter. Les documents, notes et l’historique sont partagés au niveau du dossier.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 mb-8">
        {dossier.members.map((member) => (
          <button
            key={member.id}
            data-testid={`dossier-member-${member.id}`}
            onClick={() => navigate(`/clients/${member.id}`)}
            className="rounded-lg border border-border bg-background p-5 text-left hover:border-[#002FA7] hover:bg-[#002FA7]/5 transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-full bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center font-display font-black text-lg">
                {member.prenom?.[0]}{member.nom?.[0]}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-display font-bold text-lg truncate">{member.prenom} {member.nom}</p>
                <p className="text-xs text-muted-foreground">
                  {[member.date_naissance, member.email || member.telephone, member.statut].filter(Boolean).join(" · ")}
                </p>
              </div>
              <ChevronRight className="h-5 w-5 text-muted-foreground" />
            </div>
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="h-4 w-4 text-[#002FA7]" />
            <p className="text-sm font-semibold">Documents du dossier</p>
          </div>
          {docs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun document pour le moment.</p>
          ) : (
            <ul className="space-y-2">
              {docs.slice(0, 8).map((d) => (
                <li key={d.id} className="text-sm flex items-center justify-between gap-2 border-b border-border last:border-0 pb-2 last:pb-0">
                  <span className="truncate">{d.original_filename || d.category}</span>
                  <span className="text-xs text-muted-foreground shrink-0">{fmtDate(d.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <StickyNote className="h-4 w-4 text-[#002FA7]" />
            <p className="text-sm font-semibold">Notes du dossier</p>
          </div>
          {notes.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune note pour le moment.</p>
          ) : (
            <ul className="space-y-2">
              {notes.slice(0, 6).map((n) => (
                <li key={n.id} className="text-sm border-b border-border last:border-0 pb-2 last:pb-0">
                  <p className="line-clamp-2">{n.content}</p>
                  <p className="text-xs text-muted-foreground mt-1">{n.author} · {fmtDate(n.created_at)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </Layout>
  );
}
