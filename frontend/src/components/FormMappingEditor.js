import React, { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Loader2, Settings2, Sparkles, ZoomIn, ZoomOut } from "lucide-react";

const EMPTY_SOURCE = "__none__";

function sourceLabel(sources, key) {
  if (!key) return "— Non associé —";
  return sources.find((s) => s.key === key)?.label || key;
}

export default function FormMappingEditor({
  open,
  onOpenChange,
  formId,
  sources,
  onSaved,
}) {
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState(null);
  const [mappingDraft, setMappingDraft] = useState({});
  const [selectedId, setSelectedId] = useState("");
  const [pageUrls, setPageUrls] = useState([]);
  const [zoom, setZoom] = useState(1);
  const [saving, setSaving] = useState(false);
  const [clients, setClients] = useState([]);
  const [testClientId, setTestClientId] = useState("");
  const [testing, setTesting] = useState(false);
  const listRefs = useRef({});
  const pageBlobUrls = useRef([]);

  const widgets = useMemo(() => form?.widgets || [], [form]);
  const selected = widgets.find((w) => w.id === selectedId) || null;
  const pageCount = form?.page_count || pageUrls.length || 1;

  const nameCounts = useMemo(() => {
    const counts = {};
    widgets.forEach((w) => {
      const n = w.original_name || w.id;
      counts[n] = (counts[n] || 0) + 1;
    });
    return counts;
  }, [widgets]);

  const occurrenceOf = (widget) => {
    const name = widget.original_name || widget.id;
    if ((nameCounts[name] || 0) <= 1) return null;
    let n = 0;
    for (const w of widgets) {
      if ((w.original_name || w.id) === name) {
        n += 1;
        if (w.id === widget.id) return n;
      }
    }
    return null;
  };

  const revokePageUrls = () => {
    pageBlobUrls.current.forEach((u) => URL.revokeObjectURL(u));
    pageBlobUrls.current = [];
  };

  const loadPages = async (id, count) => {
    revokePageUrls();
    const urls = [];
    for (let i = 0; i < count; i += 1) {
      const res = await api.get(`/form-library/${id}/pages/${i}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      urls.push(url);
    }
    pageBlobUrls.current = urls;
    setPageUrls(urls);
  };

  const loadEditor = async () => {
    if (!formId) return;
    setLoading(true);
    try {
      const [formRes, clientsRes] = await Promise.all([
        api.get(`/form-library/${formId}`),
        api.get("/clients"),
      ]);
      const data = formRes.data;
      setForm(data);
      setMappingDraft(data.field_mapping || {});
      setSelectedId(data.widgets?.[0]?.id || "");
      setClients(clientsRes.data || []);
      if ((clientsRes.data || []).length && !testClientId) {
        setTestClientId(clientsRes.data[0].id);
      }
      await loadPages(formId, data.page_count || 1);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Impossible d'ouvrir l'éditeur");
      onOpenChange(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && formId) {
      setZoom(1);
      loadEditor();
    }
    if (!open) {
      revokePageUrls();
      setForm(null);
      setPageUrls([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, formId]);

  useEffect(() => () => revokePageUrls(), []);

  useEffect(() => {
    if (selectedId && listRefs.current[selectedId]) {
      listRefs.current[selectedId].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selectedId]);

  const selectWidget = (id) => {
    setSelectedId(id);
    const w = widgets.find((x) => x.id === id);
    if (w) {
      const el = document.getElementById(`map-page-${w.page}`);
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  };

  const setSource = (widgetId, value) => {
    setMappingDraft((prev) => ({
      ...prev,
      [widgetId]: value === EMPTY_SOURCE ? "" : value,
    }));
  };

  const saveMapping = async () => {
    setSaving(true);
    try {
      const res = await api.patch(`/form-library/${formId}`, {
        field_mapping: mappingDraft,
      });
      toast.success("Mapping enregistré");
      onSaved?.(res.data);
      onOpenChange(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Enregistrement impossible");
    } finally {
      setSaving(false);
    }
  };

  const testFill = async () => {
    if (!testClientId) {
      toast.error("Choisissez un client pour le test");
      return;
    }
    setTesting(true);
    try {
      const res = await api.post(
        `/form-library/${formId}/test-fill`,
        { client_id: testClientId, field_mapping: mappingDraft },
        { responseType: "blob" },
      );
      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      toast.success("Aperçu généré");
    } catch (err) {
      toast.error("Échec du test de remplissage");
    } finally {
      setTesting(false);
    }
  };

  const mappedCount = Object.values(mappingDraft).filter(Boolean).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[98vw] w-[98vw] h-[94vh] p-0 gap-0 flex flex-col overflow-hidden sm:rounded-lg">
        <DialogHeader className="px-4 py-3 border-b border-border shrink-0">
          <DialogTitle className="font-display text-lg">
            Éditeur de mapping{form?.name ? ` — ${form.name}` : ""}
          </DialogTitle>
          <DialogDescription>
            Cliquez un champ dans la liste ou sur le PDF. Associez-le à une donnée CRM, puis enregistrez.
            {widgets.length ? ` · ${mappedCount}/${widgets.length} associés` : ""}
          </DialogDescription>
        </DialogHeader>

        {loading || !form ? (
          <div className="flex-1 flex items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            Analyse et aperçu du PDF…
          </div>
        ) : (
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[260px_1fr_280px]">
            {/* Liste des champs */}
            <aside className="border-r border-border overflow-y-auto bg-secondary/20 p-2 space-y-1">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground px-2 py-1">Champs ({widgets.length})</p>
              {widgets.length === 0 ? (
                <p className="text-sm text-muted-foreground px-2">Aucun champ détecté.</p>
              ) : (
                widgets.map((w) => {
                  const occ = occurrenceOf(w);
                  const mapped = Boolean(mappingDraft[w.id]);
                  const active = selectedId === w.id;
                  return (
                    <button
                      key={w.id}
                      type="button"
                      ref={(el) => { listRefs.current[w.id] = el; }}
                      data-testid={`map-list-${w.id}`}
                      onClick={() => selectWidget(w.id)}
                      className={`w-full text-left rounded-md px-2 py-2 border transition-colors ${
                        active
                          ? "border-[#002FA7] bg-[#002FA7]/10"
                          : "border-transparent hover:bg-background"
                      }`}
                    >
                      <span className="block text-sm font-medium truncate">
                        {w.original_name || w.id}
                        {occ ? ` #${occ}` : ""}
                      </span>
                      <span className="block text-[11px] text-muted-foreground truncate">
                        Page {w.page + 1}
                        {mapped ? ` · ${sourceLabel(sources, mappingDraft[w.id])}` : " · non associé"}
                      </span>
                    </button>
                  );
                })
              )}
            </aside>

            {/* Aperçu PDF */}
            <section className="min-h-0 flex flex-col bg-[#e8e8e8]">
              <div className="flex items-center justify-center gap-2 py-2 border-b border-border bg-background shrink-0">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setZoom((z) => Math.max(0.5, Math.round((z - 0.1) * 10) / 10))}
                  data-testid="map-zoom-out"
                >
                  <ZoomOut className="h-4 w-4" />
                </Button>
                <span className="text-xs font-mono w-14 text-center">{Math.round(zoom * 100)}%</span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setZoom((z) => Math.min(2.5, Math.round((z + 0.1) * 10) / 10))}
                  data-testid="map-zoom-in"
                >
                  <ZoomIn className="h-4 w-4" />
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setZoom(1)}>
                  100%
                </Button>
              </div>
              <div className="flex-1 overflow-auto p-4">
                <div
                  className="mx-auto origin-top"
                  style={{
                    transform: `scale(${zoom})`,
                    width: `${100 / zoom}%`,
                    maxWidth: `${100 / zoom}%`,
                  }}
                >
                  {Array.from({ length: pageCount }).map((_, pageIndex) => (
                    <div
                      key={pageIndex}
                      id={`map-page-${pageIndex}`}
                      className="relative mb-6 shadow-md bg-white mx-auto"
                      style={{ width: "min(100%, 820px)" }}
                    >
                      {pageUrls[pageIndex] ? (
                        <img
                          src={pageUrls[pageIndex]}
                          alt={`Page ${pageIndex + 1}`}
                          className="w-full h-auto block select-none"
                          draggable={false}
                        />
                      ) : (
                        <div className="aspect-[1/1.4] flex items-center justify-center text-sm text-muted-foreground">
                          Chargement page {pageIndex + 1}…
                        </div>
                      )}
                      {widgets
                        .filter((w) => w.page === pageIndex)
                        .map((w) => {
                          const r = w.rect || { x: 0, y: 0, w: 0, h: 0 };
                          const active = selectedId === w.id;
                          const mapped = Boolean(mappingDraft[w.id]);
                          return (
                            <button
                              key={w.id}
                              type="button"
                              data-testid={`map-overlay-${w.id}`}
                              title={w.original_name}
                              onClick={(e) => {
                                e.stopPropagation();
                                selectWidget(w.id);
                              }}
                              className={`absolute border-2 transition-colors ${
                                active
                                  ? "border-[#002FA7] bg-[#002FA7]/35 z-20"
                                  : mapped
                                    ? "border-emerald-500/80 bg-emerald-400/20 hover:bg-emerald-400/35 z-10"
                                    : "border-amber-500/80 bg-amber-300/25 hover:bg-amber-300/40 z-10"
                              }`}
                              style={{
                                left: `${(r.x || 0) * 100}%`,
                                top: `${(r.y || 0) * 100}%`,
                                width: `${Math.max((r.w || 0) * 100, 1.2)}%`,
                                height: `${Math.max((r.h || 0) * 100, 0.8)}%`,
                              }}
                            />
                          );
                        })}
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {/* Propriétés */}
            <aside className="border-l border-border overflow-y-auto p-4 space-y-4 bg-background">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">Champ sélectionné</p>
                {selected ? (
                  <div className="space-y-3">
                    <div>
                      <p className="text-sm font-semibold">{selected.original_name}</p>
                      <p className="text-xs text-muted-foreground">
                        Page {selected.page + 1}
                        {occurrenceOf(selected) ? ` · occurrence #${occurrenceOf(selected)}` : ""}
                        {" · "}{selected.field_type || "text"}
                      </p>
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Donnée CRM</Label>
                      <Select
                        value={mappingDraft[selected.id] || EMPTY_SOURCE}
                        onValueChange={(v) => setSource(selected.id, v)}
                      >
                        <SelectTrigger data-testid="map-source-select">
                          <SelectValue placeholder="Choisir…" />
                        </SelectTrigger>
                        <SelectContent>
                          {sources.map((s) => (
                            <SelectItem key={s.key || EMPTY_SOURCE} value={s.key || EMPTY_SOURCE}>
                              {s.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Sélectionnez un champ.</p>
                )}
              </div>

              <div className="border-t border-border pt-4 space-y-2">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Tester le remplissage</p>
                <Select value={testClientId} onValueChange={setTestClientId}>
                  <SelectTrigger data-testid="map-test-client">
                    <SelectValue placeholder="Client de test…" />
                  </SelectTrigger>
                  <SelectContent>
                    {clients.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.prenom} {c.nom}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="outline"
                  className="w-full gap-1.5"
                  onClick={testFill}
                  disabled={testing || !testClientId}
                  data-testid="map-test-fill"
                >
                  {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Tester le remplissage
                </Button>
                <p className="text-[11px] text-muted-foreground">
                  Génère un aperçu avec les données du client choisi (mapping actuel, même non enregistré).
                </p>
              </div>

              <div className="text-[11px] text-muted-foreground space-y-1 border-t border-border pt-3">
                <p className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 bg-[#002FA7]/40 border-2 border-[#002FA7]" /> Sélectionné</p>
                <p className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 bg-emerald-400/30 border-2 border-emerald-500" /> Associé</p>
                <p className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 bg-amber-300/30 border-2 border-amber-500" /> À mapper</p>
              </div>
            </aside>
          </div>
        )}

        <DialogFooter className="px-4 py-3 border-t border-border shrink-0">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Fermer</Button>
          <Button
            onClick={saveMapping}
            disabled={saving || loading}
            data-testid="library-mapping-save"
            className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Settings2 className="h-4 w-4" />}
            Enregistrer le mapping
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
