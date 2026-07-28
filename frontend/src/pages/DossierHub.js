import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ArrowLeft, ChevronRight, Users2 } from "lucide-react";

export default function DossierHub() {
  const { dossierId } = useParams();
  const navigate = useNavigate();
  const [dossier, setDossier] = useState(null);

  useEffect(() => {
    api.get(`/dossiers/${dossierId}`).then((res) => setDossier(res.data)).catch(() => setDossier({ members: [] }));
  }, [dossierId]);

  if (!dossier) return <Layout><div className="animate-pulse text-muted-foreground">Chargement…</div></Layout>;
  if (!dossier.members?.length) return <Layout><p className="text-muted-foreground">Dossier introuvable.</p></Layout>;

  return (
    <Layout>
      <Button variant="ghost" onClick={() => navigate("/clients")} className="mb-4 gap-2">
        <ArrowLeft className="h-4 w-4" /> Retour aux clients
      </Button>
      <Card className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-11 w-11 rounded-full bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center"><Users2 className="h-5 w-5" /></div>
          <div>
            <h1 className="font-display font-black text-2xl">{dossier.dossier_label}</h1>
            <p className="text-sm text-muted-foreground font-mono">{dossier.numero_dossier}</p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {dossier.members.map((member) => (
            <button key={member.id} onClick={() => navigate(`/clients/${member.id}`)} className="rounded-md border border-border p-4 text-left hover:border-[#002FA7] hover:bg-[#002FA7]/5 transition-colors">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center font-display font-black">{member.prenom?.[0]}{member.nom?.[0]}</div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">{member.prenom} {member.nom}</p>
                  <p className="text-xs text-muted-foreground">{member.email || member.telephone || member.statut}</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </div>
            </button>
          ))}
        </div>
      </Card>
    </Layout>
  );
}
