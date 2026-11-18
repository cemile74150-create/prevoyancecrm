import React, { useCallback, useEffect, useMemo, useState } from "react";
import api, { downloadAuthenticatedPost, openAuthenticatedBlob } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { documentDisplayName } from "@/lib/documents";
import {
  moveOrderedId,
  normalizeDocumentIds,
  reorderOrderedIds,
  rapportDownloadName,
  sortDocumentsForRapport,
  toggleOrderedId,
} from "@/lib/rapportImprimer";
import {
  ArrowDown,
  ArrowUp,
  Eye,
  FileText,
  GripVertical,
  Loader2,
  Printer,
  Save,
} from "lucide-react";
import { toast } from "sonner";

export default function RapportImprimerTab({ client }) {
  const clientId = client?.id;
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [orderedIds, setOrderedIds] = useState([]);
  const [missingIds, setMissingIds] = useState([]);
  const [dragId, setDragId] = useState(null);

  const load = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    try {
      const res = await api.get(`/clients/${clientId}/rapport-imprimer`);
      const docs = sortDocumentsForRapport(res.data?.documents || []);
      setDocuments(docs);
      setOrderedIds(normalizeDocumentIds(res.data?.document_ids || []));
      setMissingIds(res.data?.missing_ids || []);
      if ((res.data?.missing_ids || []).length) {
        toast.warning("Certains documents enregistrés ne sont plus disponibles");
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Impossible de charger le rapport");
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    load();
  }, [load]);

  const byId = useMemo(() => {
    const map = new Map();
    for (const doc of documents) map.set(doc.id, doc);
    return map;
  }, [documents]);

  const selectedDocs = useMemo(
    () => orderedIds.map((id) => byId.get(id)).filter(Boolean),
    [orderedIds, byId],
  );

  const selectedSet = useMemo(() => new Set(orderedIds), [orderedIds]);

  function setChecked(docId, checked) {
    setOrderedIds((prev) => toggleOrderedId(prev, docId, checked));
  }

  function selectAll() {
    setOrderedIds(documents.map((d) => d.id));
  }

  function selectNone() {
    setOrderedIds([]);
  }

  async function saveSelection() {
    if (!clientId || saving) return;
    setSaving(true);
    try {
      await api.patch(`/clients/${clientId}/rapport-imprimer`, {
        document_ids: orderedIds,
      });
      setMissingIds([]);
      toast.success("Sélection enregistrée");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail?.missing_ids?.length) {
        setMissingIds(detail.missing_ids);
        toast.error(detail.message || "Documents manquants");
      } else {
        toast.error(typeof detail === "string" ? detail : "Enregistrement impossible");
      }
    } finally {
      setSaving(false);
    }
  }

  async function parseBlobError(err, fallback) {
    const data = err?.response?.data;
    if (data instanceof Blob) {
      try {
        const parsed = JSON.parse(await data.text());
        return parsed?.detail || fallback;
      } catch {
        return fallback;
      }
    }
    return err?.response?.data?.detail || fallback;
  }

  async function generatePdf({ download = false } = {}) {
    if (!clientId || generating) return;
    if (!orderedIds.length) {
      toast.error("Sélectionnez au moins un document");
      return;
    }
    setGenerating(true);
    try {
      const path = `/clients/${clientId}/rapport-imprimer/pdf${download ? "?download=1" : ""}`;
      const body = { document_ids: orderedIds };
      if (download) {
        await downloadAuthenticatedPost(path, body, rapportDownloadName(client));
        toast.success("Rapport téléchargé");
      } else {
        const res = await api.post(path, body, { responseType: "blob" });
        const url = URL.createObjectURL(res.data);
        window.open(url, "_blank", "noopener,noreferrer");
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
      setMissingIds([]);
    } catch (err) {
      const detail = await parseBlobError(err, "Génération impossible");
      if (detail?.missing_ids?.length) {
        setMissingIds(detail.missing_ids);
        toast.error(detail.message || "Document manquant : génération annulée");
      } else {
        toast.error(typeof detail === "string" ? detail : detail?.message || "Génération impossible");
      }
    } finally {
      setGenerating(false);
    }
  }

  function onDragStart(id) {
    setDragId(id);
  }

  function onDragOver(event) {
    event.preventDefault();
  }

  function onDrop(targetId) {
    if (!dragId || !targetId || dragId === targetId) {
      setDragId(null);
      return;
    }
    setOrderedIds((prev) => reorderOrderedIds(prev, dragId, targetId));
    setDragId(null);
  }

  if (loading) {
    return (
      <Card className="p-6">
        <p className="text-sm text-muted-foreground">Chargement des documents…</p>
      </Card>
    );
  }

  return (
    <Card className="p-6 space-y-5" data-testid="rapport-imprimer-tab">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-[#002FA7]">Rapport à imprimer</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-2xl">
            Cochez les PDF déjà présents dans le dossier, ordonnez-les, puis générez un seul document à imprimer.
            Les fichiers sources ne sont pas dupliqués.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={saveSelection}
            disabled={saving}
            data-testid="rapport-save-btn"
            className="gap-1.5"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Enregistrer la sélection
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => generatePdf({ download: false })}
            disabled={generating || !orderedIds.length}
            data-testid="rapport-preview-btn"
            className="gap-1.5"
          >
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            Aperçu
          </Button>
          <Button
            size="sm"
            onClick={() => generatePdf({ download: true })}
            disabled={generating || !orderedIds.length}
            data-testid="rapport-generate-btn"
            className="gap-1.5 bg-[#002FA7] hover:bg-[#00248a]"
          >
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Printer className="h-4 w-4" />}
            Générer le rapport PDF
          </Button>
        </div>
      </div>

      {missingIds.length > 0 && (
        <div
          className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
          data-testid="rapport-missing-alert"
        >
          Document(s) manquant(s) ou inaccessible(s) : la fusion est bloquée jusqu&apos;à correction de la sélection.
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={selectAll} data-testid="rapport-select-all">
          Tout sélectionner
        </Button>
        <Button size="sm" variant="outline" onClick={selectNone} data-testid="rapport-select-none">
          Tout désélectionner
        </Button>
        <span className="text-xs text-muted-foreground self-center">
          {orderedIds.length} sélectionné(s) · {documents.length} PDF disponible(s)
        </span>
      </div>

      {documents.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="rapport-empty">
          Aucun PDF dans ce dossier pour le moment.
        </p>
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Documents disponibles</p>
            <ul className="space-y-1.5 max-h-[28rem] overflow-y-auto pr-1">
              {documents.map((doc) => {
                const checked = selectedSet.has(doc.id);
                const category = doc.category || doc.checklist_item || "";
                return (
                  <li
                    key={doc.id}
                    className="flex items-start gap-2 rounded-md border px-2.5 py-2 bg-background"
                    data-testid={`rapport-doc-${doc.id}`}
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(v) => setChecked(doc.id, Boolean(v))}
                      className="mt-0.5"
                      data-testid={`rapport-check-${doc.id}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate flex items-center gap-1.5">
                        <FileText className="h-3.5 w-3.5 text-[#002FA7] shrink-0" />
                        {documentDisplayName(doc)}
                      </p>
                      {category ? (
                        <p className="text-xs text-muted-foreground truncate">{category}</p>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      className="text-xs text-[#002FA7] hover:underline shrink-0"
                      onClick={() => openAuthenticatedBlob(`/documents/${doc.id}/download`)}
                      data-testid={`rapport-preview-doc-${doc.id}`}
                    >
                      Voir
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Ordre du rapport (glisser-déposer)
            </p>
            {selectedDocs.length === 0 ? (
              <p className="text-sm text-muted-foreground">Aucun document sélectionné.</p>
            ) : (
              <ul className="space-y-1.5 max-h-[28rem] overflow-y-auto pr-1">
                {selectedDocs.map((doc, index) => (
                  <li
                    key={doc.id}
                    draggable
                    onDragStart={() => onDragStart(doc.id)}
                    onDragOver={onDragOver}
                    onDrop={() => onDrop(doc.id)}
                    className={`flex items-center gap-2 rounded-md border px-2.5 py-2 bg-background ${
                      dragId === doc.id ? "opacity-50" : ""
                    }`}
                    data-testid={`rapport-order-${doc.id}`}
                  >
                    <GripVertical className="h-4 w-4 text-muted-foreground shrink-0 cursor-grab" />
                    <span className="text-xs tabular-nums text-muted-foreground w-5 shrink-0">{index + 1}.</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{documentDisplayName(doc)}</p>
                      {(doc.category || doc.checklist_item) && (
                        <p className="text-xs text-muted-foreground truncate">
                          {doc.category || doc.checklist_item}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => setOrderedIds((prev) => moveOrderedId(prev, doc.id, "up"))}
                        disabled={index === 0}
                        data-testid={`rapport-up-${doc.id}`}
                      >
                        <ArrowUp className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={() => setOrderedIds((prev) => moveOrderedId(prev, doc.id, "down"))}
                        disabled={index === selectedDocs.length - 1}
                        data-testid={`rapport-down-${doc.id}`}
                      >
                        <ArrowDown className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
