import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { AnalysePrevoyanceApp } from "@/analyse-prevoyance/components/AnalysePrevoyanceApp";
import { toast } from "sonner";

export default function EffectuerAnalyseEditor() {
  const { id } = useParams();
  const [record, setRecord] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.get(`/analyses-prevoyance/${id}`)
      .then((res) => {
        if (!cancelled) setRecord(res.data);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || "Analyse introuvable");
      });
    return () => { cancelled = true; };
  }, [id]);

  if (error) {
    return (
      <Layout>
        <div className="p-6">
          <p className="text-sm text-destructive">{error}</p>
          <Link to="/effectuer-une-analyse" className="text-sm underline">Retour</Link>
        </div>
      </Layout>
    );
  }

  if (!record) {
    return (
      <Layout>
        <div className="p-6 text-muted-foreground">Chargement de l'analyse…</div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="analyse-module" style={{ ["--ap-accent"]: "#002FA7" }}>
        <div className="mx-auto max-w-6xl px-4 pt-3">
          <Link to="/effectuer-une-analyse" className="text-sm underline text-[#002FA7]">← Analyses</Link>
        </div>
        <AnalysePrevoyanceApp
          key={record.updatedAt || record.id}
          initialRecord={record}
          linkedClientId={record.clientId}
          onSaved={() => {
            toast.success("Analyse enregistrée");
          }}
        />
      </div>
    </Layout>
  );
}
