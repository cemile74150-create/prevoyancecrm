import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { AnalysePrevoyanceApp } from "@/analyse-prevoyance/components/AnalysePrevoyanceApp";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function EffectuerAnalyseEditor() {
  const { id } = useParams();
  const [record, setRecord] = useState(null);
  const [versions, setVersions] = useState([]);
  const [error, setError] = useState("");
  const [restoring, setRestoring] = useState(false);

  const loadVersions = useCallback(() => {
    api.get(`/analyses-prevoyance/${id}/versions`)
      .then((res) => setVersions(res.data?.versions || []))
      .catch(() => {});
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    api.get(`/analyses-prevoyance/${id}`)
      .then((res) => {
        if (!cancelled) setRecord(res.data);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || "Analyse introuvable");
      });
    loadVersions();
    return () => { cancelled = true; };
  }, [id, loadVersions]);

  async function restoreVersion(index) {
    setRestoring(true);
    try {
      const res = await api.post(`/analyses-prevoyance/${id}/versions/${index}/restore`);
      setRecord(res.data);
      loadVersions();
      toast.success("Version restaurée");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Restauration impossible");
    } finally {
      setRestoring(false);
    }
  }

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
        <div className="border-b bg-muted/30">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-2 text-sm">
            <Link to="/effectuer-une-analyse" className="underline text-[#002FA7]">← Analyses</Link>
            <span className="text-muted-foreground">Statut : {record.status}</span>
            {record.clientId && (
              <Link to={`/clients/${record.clientId}`} className="underline">Fiche client</Link>
            )}
            <span className="text-muted-foreground">
              {versions.length} version{versions.length > 1 ? "s" : ""} précédente{versions.length > 1 ? "s" : ""}
            </span>
          </div>
          {versions.length > 0 && (
            <div className="mx-auto flex max-w-6xl flex-wrap gap-2 px-4 pb-2">
              {[...versions].reverse().slice(0, 8).map((version) => (
                <Button
                  key={`${version.index}-${version.at}`}
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={restoring}
                  onClick={() => restoreVersion(version.index)}
                >
                  Restaurer {version.at ? new Date(version.at).toLocaleString("fr-CH") : `v${version.index + 1}`}
                  {version.status ? ` · ${version.status}` : ""}
                </Button>
              ))}
            </div>
          )}
        </div>
        <AnalysePrevoyanceApp
          key={record.updatedAt || record.id}
          initialRecord={record}
          linkedClientId={record.clientId}
          onSaved={() => {
            toast.success("Analyse enregistrée");
            loadVersions();
          }}
        />
      </div>
    </Layout>
  );
}
