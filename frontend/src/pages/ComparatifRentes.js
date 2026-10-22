import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { Search } from "lucide-react";
import { toast } from "sonner";

function clientName(c) {
  return `${c?.prenom || ""} ${c?.nom || ""}`.trim() || "Client";
}

export default function ComparatifRentes() {
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const canEdit = hasPerm("analyses.edit");
  const [query, setQuery] = useState("");
  const [clients, setClients] = useState([]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [removingId, setRemovingId] = useState("");

  useEffect(() => {
    const term = query.trim();
    if (term.length < 1) {
      setClients([]);
      return undefined;
    }
    const t = setTimeout(async () => {
      try {
        const res = await api.get("/clients", { params: { q: term } });
        const list = Array.isArray(res.data) ? res.data : res.data?.items || [];
        setClients(list.slice(0, 12));
      } catch {
        setClients([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    api.get("/comparatifs-rentes")
      .then((res) => setRows(res.data?.items || []))
      .catch(() => toast.error("Impossible de charger les comparatifs"))
      .finally(() => setLoading(false));
  }, []);

  async function openForClient(client) {
    if (!canEdit || !client?.id) return;
    setCreating(true);
    try {
      const res = await api.post("/comparatifs-rentes", { clientId: client.id });
      navigate(`/comparatif-rentes/${res.data.id}`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const existing = detail?.comparatifId;
      if (e?.response?.status === 409 && existing) {
        navigate(`/comparatif-rentes/${existing}`);
        return;
      }
      const message = typeof detail === "string" ? detail : detail?.message;
      toast.error(message || "Création impossible");
      setCreating(false);
    }
  }

  async function removeComparatif(row) {
    if (!canEdit || !row?.id) return;
    const name = row.clientName || "ce comparatif";
    const ok = window.confirm(
      `Supprimer le comparatif « ${name} » ? Le document intégré sera aussi retiré du dossier client.`
    );
    if (!ok) return;
    setRemovingId(row.id);
    try {
      await api.delete(`/comparatifs-rentes/${row.id}`);
      setRows((prev) => prev.filter((item) => item.id !== row.id));
      toast.success("Comparatif supprimé");
    } catch {
      toast.error("Suppression impossible");
    } finally {
      setRemovingId("");
    }
  }

  async function openBlank() {
    if (!canEdit) return;
    setCreating(true);
    try {
      const res = await api.post("/comparatifs-rentes", {});
      navigate(`/comparatif-rentes/${res.data.id}`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : detail?.message;
      toast.error(message || "Création impossible");
      setCreating(false);
    }
  }

  return (
    <Layout>
      <div className="mx-auto max-w-6xl space-y-8 p-6">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Comparatif des rentes</h1>
          <p className="mt-1 text-muted-foreground">
            Même fiche client que « Effectuer une planification ». Ici, seul le tableau des offres de rente est calculé, avec l&apos;impôt sur l&apos;offre et l&apos;impôt sur la fortune année par année.
          </p>
        </header>

        <section className="space-y-4 rounded-xl border bg-card p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[240px] flex-1 space-y-2">
              <label className="text-sm font-medium" htmlFor="comparatif-client-search">
                Rechercher un client existant
              </label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  id="comparatif-client-search"
                  data-testid="comparatif-client-search"
                  className="pl-9"
                  placeholder="Nom, prénom…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={!canEdit || creating}
              onClick={openBlank}
              data-testid="comparatif-fiche-vide"
            >
              Fiche vide
            </Button>
          </div>
          {query.trim() && (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-left">
                  <tr>
                    <th className="px-3 py-2">Client</th>
                    <th className="px-3 py-2">Ville</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {clients.length === 0 ? (
                    <tr>
                      <td className="px-3 py-3 text-muted-foreground" colSpan={3}>Aucun client</td>
                    </tr>
                  ) : clients.map((client) => (
                    <tr key={client.id} className="border-t">
                      <td className="px-3 py-2">{clientName(client)}</td>
                      <td className="px-3 py-2">{client.ville || "—"}</td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          type="button"
                          size="sm"
                          className="bg-[#002FA7] hover:bg-[#00248a]"
                          disabled={!canEdit || creating}
                          onClick={() => openForClient(client)}
                        >
                          Ouvrir le comparatif
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Comparatifs enregistrés</h2>
          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucun comparatif pour le moment.</p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-left">
                  <tr>
                    <th className="px-3 py-2">Client</th>
                    <th className="px-3 py-2">Commune</th>
                    <th className="px-3 py-2">Statut</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-t">
                      <td className="px-3 py-2">{row.clientName || "Fiche sans client"}</td>
                      <td className="px-3 py-2">{row.ville || "—"}</td>
                      <td className="px-3 py-2">{row.status === "calculee" ? "Calculé" : "Brouillon"}</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex justify-end gap-2">
                          <Button type="button" size="sm" variant="outline" onClick={() => navigate(`/comparatif-rentes/${row.id}`)}>
                            Ouvrir
                          </Button>
                          {canEdit && (
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="text-destructive hover:text-destructive"
                              disabled={removingId === row.id}
                              data-testid={`comparatif-supprimer-${row.id}`}
                              onClick={() => removeComparatif(row)}
                            >
                              Supprimer
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}
