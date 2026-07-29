import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ClipboardList, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

export default function Demandes() {
  const [demandes, setDemandes] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get("/demandes", { params: { done: false } });
      setDemandes(Array.isArray(res.data) ? res.data : []);
    } catch {
      toast.error("Impossible de charger les demandes");
      setDemandes([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const markDone = async (demande) => {
    try {
      await api.patch(`/demandes/${demande.id}`, { done: true });
      setDemandes((list) => list.filter((d) => d.id !== demande.id));
      toast.success("Demande marquée comme traitée");
    } catch {
      toast.error("Impossible de mettre à jour la demande");
    }
  };

  return (
    <Layout>
      <div className="animate-fade-up max-w-3xl">
        <div className="flex items-center gap-2.5 mb-2">
          <ClipboardList className="h-6 w-6 text-[#002FA7]" />
          <h1 className="font-display font-black text-3xl tracking-tight">Demandes à faire</h1>
        </div>
        <p className="text-muted-foreground mb-8">
          Toutes les actions encore à réaliser sur vos dossiers. Cochez « Traité » pour les retirer de cette liste.
        </p>

        {loading ? (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        ) : demandes.length === 0 ? (
          <Card className="p-10 text-center text-sm text-muted-foreground">
            Aucune demande en attente. Tout est à jour.
          </Card>
        ) : (
          <div className="space-y-3">
            {demandes.map((d) => (
              <Card
                key={d.id}
                data-testid={`demande-global-${d.id}`}
                className="p-4 flex items-start gap-3 hover:border-[#002FA7]/40 transition-colors"
              >
                <Checkbox
                  checked={false}
                  onCheckedChange={() => markDone(d)}
                  data-testid={`demande-global-check-${d.id}`}
                  className="mt-1"
                />
                <div className="flex-1 min-w-0">
                  <button
                    type="button"
                    onClick={() => d.client_id && navigate(`/clients/${d.client_id}`)}
                    className="text-left w-full group"
                  >
                    <p className="text-sm font-semibold text-foreground group-hover:text-[#002FA7] transition-colors">
                      {d.client_name || "Client"}
                      {d.numero_dossier ? (
                        <span className="ml-2 text-xs font-normal text-muted-foreground font-mono">
                          {d.numero_dossier}
                        </span>
                      ) : null}
                    </p>
                    <p className="text-sm mt-1 flex items-start gap-1.5">
                      <span className="text-muted-foreground shrink-0">➜</span>
                      <span className="font-medium">{d.titre}</span>
                    </p>
                  </button>
                  {d.description ? (
                    <p className="text-xs text-muted-foreground mt-1.5 whitespace-pre-wrap">{d.description}</p>
                  ) : null}
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    {d.priorite === "haute" && (
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 border border-red-100 px-2 py-0.5 rounded">
                        <AlertTriangle className="h-3 w-3" /> Haute priorité
                      </span>
                    )}
                    {d.author && (
                      <span className="text-xs text-muted-foreground">Créé par {d.author}</span>
                    )}
                    {d.created_at && (
                      <span className="text-xs text-muted-foreground">
                        · {new Date(d.created_at).toLocaleDateString("fr-CH")}
                      </span>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
