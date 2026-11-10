import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, ChevronLeft, ChevronRight, ClipboardCheck, ExternalLink, ListChecks, Loader2, Plus, Search, Users,
} from "lucide-react";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { STATUT_COLORS, normalizeStatut } from "@/lib/constants";
import { clientCountLabel, eligibilityErrorMessage, filterListsByName } from "@/lib/eligibility";
import {
  createEligibilityList,
  fetchEligibilityListClients,
  fetchEligibilityLists,
} from "@/lib/eligibilityApi";

const PAGE_SIZE = 50;

function useRefreshOnFocus(refresh) {
  useEffect(() => {
    const onFocus = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [refresh]);
}

function CreateListDialog({ open, onOpenChange, onCreated }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setName("");
      setError("");
    }
  }, [open]);

  const submit = async (e) => {
    e?.preventDefault();
    const clean = name.trim();
    if (!clean) {
      setError("Indiquez le nom de la liste.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const created = await createEligibilityList(clean);
      toast.success(`Liste « ${created.name} » créée`);
      onCreated(created);
      onOpenChange(false);
    } catch (err) {
      setError(eligibilityErrorMessage(err, "Création impossible."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle className="font-display">Ajouter une liste</DialogTitle>
            <DialogDescription>
              La liste apparaîtra dans l'onglet Éligibilité de chaque fiche client.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-4">
            <Label htmlFor="eligibility-new-name" className="text-xs">Nom de la liste</Label>
            <Input
              id="eligibility-new-name"
              data-testid="eligibility-new-name"
              value={name}
              maxLength={120}
              autoFocus
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex. Rachat LPP"
            />
            {error && <p className="text-xs text-destructive" data-testid="eligibility-new-error">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
            <Button
              type="submit"
              disabled={saving}
              data-testid="eligibility-new-submit"
              className="bg-[#002FA7] hover:bg-[#00248a]"
            >
              {saving ? "Création…" : "Créer la liste"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ListsOverview() {
  const navigate = useNavigate();
  const [data, setData] = useState({ lists: [], total: 0, can_create: false });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      setData(await fetchEligibilityLists());
      setError("");
    } catch (e) {
      if (!silent) setError(eligibilityErrorMessage(e, "Impossible de charger les listes."));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);
  useRefreshOnFocus(useCallback(() => load({ silent: true }), [load]));

  const visible = filterListsByName(data.lists, q);

  return (
    <>
      <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
        <div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Éligibilité</h1>
          <p className="text-muted-foreground mt-1">
            {data.total} liste{data.total > 1 ? "s" : ""} · clients éligibles par produit
          </p>
        </div>
        {data.can_create && (
          <Button
            data-testid="eligibility-add-list"
            onClick={() => setCreateOpen(true)}
            className="bg-[#002FA7] hover:bg-[#00248a] gap-2"
          >
            <Plus className="h-4 w-4" /> Ajouter une liste
          </Button>
        )}
      </div>

      <div className="relative max-w-sm mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          data-testid="eligibility-lists-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Rechercher une liste…"
          className="pl-10"
        />
      </div>

      {loading ? (
        <Card className="p-10 text-sm text-muted-foreground flex items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
        </Card>
      ) : error ? (
        <Card className="p-10 text-sm text-amber-800 text-center">{error}</Card>
      ) : visible.length === 0 ? (
        <Card className="p-10 text-sm text-muted-foreground text-center">
          {data.lists.length === 0 ? "Aucune liste d'éligibilité pour le moment." : "Aucune liste ne correspond à cette recherche."}
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((list) => (
            <Card key={list.id} className="overflow-hidden">
              <button
                type="button"
                data-testid={`eligibility-list-${list.id}`}
                onClick={() => navigate(`/eligibilite/${list.id}`)}
                className="w-full h-full text-left p-5 flex items-start gap-4 hover:bg-secondary transition-colors group"
              >
                <div className="h-10 w-10 rounded-md bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center shrink-0">
                  <ListChecks className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium leading-snug">{list.name}</p>
                  <p className="text-sm text-muted-foreground mt-1 flex items-center gap-1.5">
                    <Users className="h-3.5 w-3.5" /> {clientCountLabel(list.client_count)}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground mt-1 opacity-0 group-hover:opacity-100" />
              </button>
            </Card>
          ))}
        </div>
      )}

      <CreateListDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => load({ silent: true })}
      />
    </>
  );
}

function ListClients({ listId }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(q.trim());
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      setData(await fetchEligibilityListClients(listId, { q: query, page, pageSize: PAGE_SIZE }));
      setError("");
    } catch (e) {
      if (!silent) {
        setData(null);
        setError(eligibilityErrorMessage(e, "Impossible de charger les clients de cette liste."));
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [listId, query, page]);

  useEffect(() => {
    load();
  }, [load]);
  useRefreshOnFocus(useCallback(() => load({ silent: true }), [load]));

  const list = data?.list;
  const items = data?.items || [];
  const total = data?.total || 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <button
        type="button"
        onClick={() => navigate("/eligibilite")}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="h-4 w-4" /> Toutes les listes
      </button>
      <div className="flex items-start gap-3 mb-6">
        <ClipboardCheck className="h-7 w-7 text-[#002FA7] mt-1 shrink-0" />
        <div>
          <h1 className="font-display font-black text-2xl sm:text-3xl tracking-tight">
            {list?.name || (loading ? "Chargement…" : "Liste")}
          </h1>
          {list && (
            <p className="text-muted-foreground mt-1">{clientCountLabel(list.client_count)} éligible{list.client_count > 1 ? "s" : ""}</p>
          )}
        </div>
      </div>

      <div className="relative max-w-sm mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          data-testid="eligibility-clients-search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Nom, prénom ou n° de dossier…"
          className="pl-10"
        />
      </div>

      {error ? (
        <Card className="p-10 text-sm text-amber-800 text-center">{error}</Card>
      ) : (
        <Card className="overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nom prénom</TableHead>
                <TableHead>N° dossier</TableHead>
                <TableHead>Téléphone</TableHead>
                <TableHead>E-mail</TableHead>
                <TableHead>Statut du dossier</TableHead>
                <TableHead className="text-right"><span className="sr-only">Action</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && !data ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin inline mr-2" />Chargement…
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-10 text-center text-sm text-muted-foreground" data-testid="eligibility-clients-empty">
                    {query ? "Aucun client ne correspond à cette recherche." : "Aucun client dans cette liste pour le moment."}
                  </TableCell>
                </TableRow>
              ) : (
                items.map((c) => {
                  const statut = normalizeStatut(c.statut);
                  return (
                    <TableRow key={c.id} data-testid={`eligibility-client-${c.id}`}>
                      <TableCell className="font-medium">{[c.nom, c.prenom].filter(Boolean).join(" ") || "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{c.numero_dossier || "—"}</TableCell>
                      <TableCell className="whitespace-nowrap">{c.telephone || "—"}</TableCell>
                      <TableCell className="max-w-[16rem] truncate">{c.email || "—"}</TableCell>
                      <TableCell>
                        <span className={`text-xs font-medium px-2.5 py-1 rounded-full border whitespace-nowrap ${STATUT_COLORS[statut] || ""}`}>
                          {statut}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1.5"
                          onClick={() => navigate(`/clients/${c.id}?tab=eligibilite`)}
                        >
                          Voir le dossier <ExternalLink className="h-3.5 w-3.5" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
          {pages > 1 && (
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-border text-sm">
              <span className="text-muted-foreground">
                Page {page} / {pages} · {total} résultat{total > 1 ? "s" : ""}
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="outline" disabled={page >= pages || loading} onClick={() => setPage((p) => p + 1)}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}
    </>
  );
}

export default function Eligibilite() {
  const { listId } = useParams();
  return <Layout>{listId ? <ListClients key={listId} listId={listId} /> : <ListsOverview />}</Layout>;
}
