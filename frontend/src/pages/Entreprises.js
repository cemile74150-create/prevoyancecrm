import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Building2, Plus, Pencil } from "lucide-react";

const empty = () => ({ nom: "", finma_number: "", email_domains: "" });

export default function Entreprises() {
  const { isAdmin } = useAuth();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const [mendesPreview, setMendesPreview] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [e, m] = await Promise.all([
        api.get("/entreprises"),
        api.get("/entreprises/mendes-attachment-preview").catch(() => ({ data: null })),
      ]);
      setRows(e.data || []);
      setMendesPreview(m.data || null);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Chargement impossible");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  const openCreate = () => {
    setEditing(null);
    setForm(empty());
    setDialog(true);
  };

  const openEdit = (row) => {
    setEditing(row);
    setForm({
      nom: row.nom || "",
      finma_number: row.finma_number || "",
      email_domains: (row.email_domains || []).map((d) => `@${d}`).join(", "),
    });
    setDialog(true);
  };

  const parseDomains = (raw) =>
    String(raw || "")
      .split(/[,;\s]+/)
      .map((d) => d.trim())
      .filter(Boolean);

  const save = async () => {
    if (!form.nom.trim() || !form.finma_number.trim()) {
      toast.error("Nom et numéro FINMA obligatoires");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        nom: form.nom.trim(),
        finma_number: form.finma_number.trim(),
        email_domains: parseDomains(form.email_domains),
      };
      if (editing) {
        await api.put(`/entreprises/${editing.id}`, payload);
        toast.success("Entreprise mise à jour");
      } else {
        await api.post("/entreprises", payload);
        toast.success("Entreprise créée");
      }
      setDialog(false);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Enregistrement impossible");
    } finally {
      setSaving(false);
    }
  };

  const ensureMendes = async () => {
    try {
      await api.post("/entreprises/ensure-agence-mendes");
      toast.success("Agence Mendes prête");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur");
    }
  };

  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  return (
    <Layout>
      <div className="animate-fade-up max-w-5xl">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-8">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
              <Building2 className="h-7 w-7 text-[#002FA7]" /> Entreprises
            </h1>
            <p className="text-muted-foreground mt-1">
              FINMA et domaines e-mail partagés — une fiche par cabinet, plusieurs collaborateurs.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={ensureMendes}>
              Assurer Agence Mendes
            </Button>
            <Button onClick={openCreate} className="bg-[#002FA7] hover:bg-[#00248a] gap-2">
              <Plus className="h-4 w-4" /> Nouvelle entreprise
            </Button>
          </div>
        </div>

        {mendesPreview && mendesPreview.count > 0 && (
          <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm">
            <p className="font-medium text-amber-900">
              {mendesPreview.count} compte(s) @agencemendes.ch peuvent être rattachés à{" "}
              {mendesPreview.entreprise?.nom} (FINMA {mendesPreview.entreprise?.finma_number}).
            </p>
            <p className="text-amber-800 mt-1">
              Aperçu uniquement — le rattachement en production attend votre GO explicite.
            </p>
          </div>
        )}

        {loading ? (
          <p className="text-muted-foreground">Chargement…</p>
        ) : (
          <div className="border border-border rounded-md overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-secondary/60 text-left">
                <tr>
                  <th className="px-4 py-3 font-medium">Entreprise</th>
                  <th className="px-4 py-3 font-medium">FINMA</th>
                  <th className="px-4 py-3 font-medium">Domaines e-mail</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-border hover:bg-secondary/40">
                    <td className="px-4 py-3 font-medium">{r.nom}</td>
                    <td className="px-4 py-3">{r.finma_number}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {(r.email_domains || []).map((d) => `@${d}`).join(", ") || "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button type="button" className="p-2 rounded-md hover:bg-secondary" onClick={() => openEdit(r)}>
                        <Pencil className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                      Aucune entreprise — créez Agence Mendes pour commencer.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Modifier l'entreprise" : "Nouvelle entreprise"}</DialogTitle>
            <DialogDescription>
              Le numéro FINMA est unique à l&apos;entreprise et s&apos;affiche automatiquement sur les fiches utilisateurs.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Nom *</Label>
              <Input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Numéro FINMA *</Label>
              <Input
                value={form.finma_number}
                onChange={(e) => setForm({ ...form, finma_number: e.target.value })}
                placeholder="F01101452"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Domaines e-mail</Label>
              <Input
                value={form.email_domains}
                onChange={(e) => setForm({ ...form, email_domains: e.target.value })}
                placeholder="@agencemendes.ch"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(false)}>Annuler</Button>
            <Button onClick={save} disabled={saving} className="bg-[#002FA7] hover:bg-[#00248a]">
              {saving ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
