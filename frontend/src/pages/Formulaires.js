import React, { useEffect, useRef, useState } from "react";
import api, { apiBaseUrl } from "@/lib/api";
import Layout from "@/components/Layout";
import FormMappingEditor from "@/components/FormMappingEditor";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Files, Loader2, Plus, Trash2, Upload, FileText, Settings2 } from "lucide-react";

export default function Formulaires() {
  const [forms, setForms] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [formName, setFormName] = useState("");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [mappingFormId, setMappingFormId] = useState(null);
  const fileRef = useRef();

  const load = async () => {
    setLoading(true);
    try {
      const [formsRes, sourcesRes] = await Promise.all([
        api.get("/form-library"),
        api.get("/form-library/field-sources"),
      ]);
      setForms(formsRes.data || []);
      setSources(sourcesRes.data || []);
    } catch (err) {
      toast.error("Impossible de charger la bibliothèque");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openUpload = () => {
    setFormName("");
    setFile(null);
    setUploadOpen(true);
  };

  const submitUpload = async () => {
    if (!file) {
      toast.error("Choisissez un PDF");
      return;
    }
    if (!formName.trim()) {
      toast.error("Donnez un nom au formulaire");
      return;
    }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", formName.trim());
      const res = await api.post("/form-library", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadOpen(false);
      await load();
      if (!(res.data?.widgets || []).length && !(res.data?.field_names || []).length) {
        toast.warning("PDF ajouté, mais aucun champ remplissable détecté");
      } else {
        toast.success("PDF ajouté — configurez le mapping visuel");
        setMappingFormId(res.data.id);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de l'ajout");
    } finally {
      setUploading(false);
    }
  };

  const removeForm = async (id) => {
    if (!window.confirm("Supprimer ce formulaire de la bibliothèque ?")) return;
    try {
      await api.delete(`/form-library/${id}`);
      toast.success("Formulaire supprimé");
      setForms((prev) => prev.filter((f) => f.id !== id));
    } catch (err) {
      toast.error("Suppression impossible");
    }
  };

  const mappedCount = (form) =>
    Object.values(form.field_mapping || {}).filter((v) => v).length;

  return (
    <Layout>
      <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight flex items-center gap-3">
            <Files className="h-8 w-8 text-[#002FA7]" />
            Bibliothèque de formulaires
          </h1>
          <p className="text-muted-foreground mt-1">
            Importez un PDF, associez chaque champ visuellement à une donnée CRM, puis générez-le depuis le dossier client.
          </p>
        </div>
        <Button
          onClick={openUpload}
          data-testid="upload-library-form-btn"
          className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5 shrink-0"
        >
          <Plus className="h-4 w-4" />
          Télécharger un nouveau formulaire
        </Button>
      </div>

      <Card className="p-6">
        {loading ? (
          <p className="text-sm text-muted-foreground py-8 text-center">Chargement…</p>
        ) : forms.length === 0 ? (
          <div className="py-12 text-center space-y-3">
            <Upload className="h-10 w-10 text-muted-foreground mx-auto" />
            <p className="text-sm text-muted-foreground">Aucun formulaire dans la bibliothèque.</p>
            <Button variant="outline" onClick={openUpload} className="gap-1.5">
              <Plus className="h-4 w-4" />Ajouter le premier
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {forms.map((f) => (
              <div
                key={f.id}
                data-testid={`library-form-${f.id}`}
                className="flex items-center gap-3 rounded-md border border-border px-3 py-3 bg-background"
              >
                <FileText className="h-5 w-5 text-[#002FA7] shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{f.name}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {f.original_filename}
                    {typeof f.field_count === "number" ? ` · ${f.field_count} champ(s)` : ""}
                    {` · ${mappedCount(f)} mappé(s)`}
                    {!f.mapping_configured ? " · configuration à confirmer" : ""}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 shrink-0"
                  onClick={() => setMappingFormId(f.id)}
                  data-testid={`library-form-map-${f.id}`}
                >
                  <Settings2 className="h-3.5 w-3.5" />
                  Mapping
                </Button>
                <a
                  href={`${apiBaseUrl}/form-library/${f.id}/download`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-[#002FA7] hover:underline shrink-0"
                >
                  Voir
                </a>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-destructive hover:text-destructive"
                  onClick={() => removeForm(f.id)}
                  data-testid={`library-form-delete-${f.id}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display">Nouveau formulaire</DialogTitle>
            <DialogDescription>
              Après l&apos;import, l&apos;éditeur visuel s&apos;ouvre pour associer chaque champ du PDF.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Nom du formulaire</Label>
              <Input
                data-testid="library-form-name"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="Ex: Décompte libre passage Pictet"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Fichier PDF</Label>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                data-testid="library-form-file"
              />
              <Button
                type="button"
                variant="outline"
                className="w-full gap-1.5 justify-start"
                onClick={() => fileRef.current?.click()}
              >
                <Upload className="h-4 w-4" />
                {file ? file.name : "Choisir un PDF…"}
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setUploadOpen(false)}>Annuler</Button>
            <Button
              onClick={submitUpload}
              disabled={uploading}
              data-testid="library-form-save"
              className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
            >
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Continuer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <FormMappingEditor
        open={Boolean(mappingFormId)}
        onOpenChange={(v) => { if (!v) setMappingFormId(null); }}
        formId={mappingFormId}
        sources={sources}
        onSaved={(updated) => {
          setForms((prev) => prev.map((f) => (f.id === updated.id ? { ...f, ...updated } : f)));
        }}
      />
    </Layout>
  );
}
