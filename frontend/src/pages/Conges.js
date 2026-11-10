import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Layout from "@/components/Layout";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";
import { fetchLeavesMeta } from "@/lib/congesApi";
import MesConges from "@/components/conges/MesConges";
import NouvelleDemande from "@/components/conges/NouvelleDemande";
import CalendrierEquipe from "@/components/conges/CalendrierEquipe";
import GestionDemandes from "@/components/conges/GestionDemandes";
import { LeaveDetailDialog } from "@/components/conges/LeaveShared";

const TABS = ["mes-conges", "nouvelle", "calendrier", "gestion"];

export default function Conges() {
  const { hasPerm } = useAuth();
  const [params, setParams] = useSearchParams();
  const [meta, setMeta] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const manager = meta ? Boolean(meta.can_manage) : hasPerm("leaves.manage");

  const requested = params.get("tab");
  const tab = TABS.includes(requested) && (requested !== "gestion" || manager) ? requested : "mes-conges";
  const linkedId = params.get("demande");

  useEffect(() => {
    fetchLeavesMeta().then(setMeta).catch(() => setMeta(null));
  }, []);

  const setTab = useCallback((t) => {
    setParams((p) => {
      const next = new URLSearchParams(p);
      next.set("tab", t);
      next.delete("demande");
      return next;
    }, { replace: true });
  }, [setParams]);

  const closeLinked = useCallback((open) => {
    if (open) return;
    setParams((p) => {
      const next = new URLSearchParams(p);
      next.delete("demande");
      return next;
    }, { replace: true });
  }, [setParams]);

  const bump = () => setRefreshKey((k) => k + 1);

  return (
    <Layout>
      <div className="mb-6">
        <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Congés &amp; absences</h1>
        <p className="text-muted-foreground mt-1">
          Dépôt et suivi des demandes. Aucun solde ni compteur annuel n'est géré ici.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-5 flex-wrap h-auto">
          <TabsTrigger value="mes-conges" data-testid="tab-mes-conges">Mes congés</TabsTrigger>
          <TabsTrigger value="nouvelle" data-testid="tab-nouvelle">Nouvelle demande</TabsTrigger>
          <TabsTrigger value="calendrier" data-testid="tab-calendrier">Calendrier équipe</TabsTrigger>
          {manager && <TabsTrigger value="gestion" data-testid="tab-gestion">Gestion des demandes</TabsTrigger>}
        </TabsList>
        <TabsContent value="mes-conges">
          <MesConges onNewRequest={() => setTab("nouvelle")} refreshKey={refreshKey} />
        </TabsContent>
        <TabsContent value="nouvelle">
          <NouvelleDemande meta={meta} onCreated={() => { bump(); setTab("mes-conges"); }} />
        </TabsContent>
        <TabsContent value="calendrier">
          <CalendrierEquipe manager={manager} refreshKey={refreshKey} />
        </TabsContent>
        {manager && (
          <TabsContent value="gestion">
            <GestionDemandes refreshKey={refreshKey} onChanged={bump} />
          </TabsContent>
        )}
      </Tabs>

      <LeaveDetailDialog leaveId={linkedId} open={Boolean(linkedId)} onOpenChange={closeLinked} onChanged={bump} />
    </Layout>
  );
}
