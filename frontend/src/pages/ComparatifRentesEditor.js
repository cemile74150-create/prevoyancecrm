import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { ComparatifRentesApp } from "@/analyse-prevoyance/components/ComparatifRentesApp";
import { toast } from "sonner";

export default function ComparatifRentesEditor() {
  const { id } = useParams();
  const [record, setRecord] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.get(`/comparatifs-rentes/${id}`)
      .then((res) => {
        if (!cancelled) setRecord(res.data);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.response?.data?.detail || "Comparatif introuvable");
      });
    return () => { cancelled = true; };
  }, [id]);

  if (error) {
    return (
      <Layout>
        <div className="p-6">
          <p className="text-sm text-destructive">{typeof error === "string" ? error : "Comparatif introuvable"}</p>
          <Link to="/comparatif-rentes" className="text-sm text-[#002FA7] underline">Retour</Link>
        </div>
      </Layout>
    );
  }

  if (!record) {
    return (
      <Layout>
        <div className="p-6 text-muted-foreground">Chargement du comparatif…</div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="min-h-screen bg-[#f4f5f7]">
        <div className="mx-auto max-w-[1680px] px-4 pt-3">
          <Link to="/comparatif-rentes" className="text-sm text-[#002FA7] underline">← Comparatifs</Link>
        </div>
        <ComparatifRentesApp
          key={record.updatedAt || record.id}
          initialRecord={record}
          onSaved={() => toast.success("Comparatif enregistré")}
        />
      </div>
    </Layout>
  );
}
