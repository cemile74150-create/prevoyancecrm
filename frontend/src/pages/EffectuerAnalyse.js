import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/context/AuthContext";
import { parseClientDuplicateError } from "@/lib/clientDuplicate";
import { toIsoDate, toSwissDate } from "@/lib/dates";
import { MoreHorizontal, Plus, Search } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";

const ETATS_CIVIL = ["Célibataire", "Marié(e)", "Divorcé(e)", "Veuf(ve)", "Partenariat enregistré", "Séparé(e)"];

const STATUS_LABELS = {
  brouillon: "Brouillon",
  calculee: "Calculée",
  finalisee: "Finalisée",
  annulee: "Annulée",
};

const STATUS_BADGE = {
  brouillon: "bg-stone-100 text-stone-700",
  calculee: "bg-[#002FA7]/10 text-[#002FA7]",
  finalisee: "bg-emerald-50 text-emerald-800",
  annulee: "bg-rose-50 text-rose-700",
};

const FILTERS = [
  { id: "toutes", label: "Toutes" },
  { id: "brouillon", label: "Brouillons" },
  { id: "calculee", label: "Calculées" },
  { id: "finalisee", label: "Finalisées" },
  { id: "annulee", label: "Annulées" },
];

function isActiveStatus(status) {
  return status === "brouillon" || status === "calculee" || status === "finalisee";
}

function pickPrimary(group) {
  const active = group.filter((row) => isActiveStatus(row.status));
  const pool = active.length ? active : group;
  const advanced = pool.filter((row) => row.status === "calculee" || row.status === "finalisee");
  const ranked = (advanced.length ? advanced : pool)
    .slice()
    .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
  return ranked[0] || null;
}

function groupByClient(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = row.clientId || `sans-client:${row.id}`;
    const list = groups.get(key) || [];
    list.push(row);
    groups.set(key, list);
  }
  return [...groups.values()];
}

function clientName(c) {
  return `${c?.prenom || ""} ${c?.nom || ""}`.trim() || "Client";
}

function formatDateTimeFr(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const day = new Intl.DateTimeFormat("fr-CH", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
  const time = new Intl.DateTimeFormat("fr-CH", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
  return `${day} à ${time}`;
}

const emptyNewClient = {
  prenom: "",
  nom: "",
  date_naissance: "",
  sexe: "",
  etat_civil: "",
  email: "",
  telephone: "",
  adresse: "",
  npa: "",
  ville: "",
  pays_residence: "Suisse",
  salaire_annuel: "",
  conseiller: "",
};

function Field({ label, k, type = "text", placeholder, form, setField, required }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground" htmlFor={`new-client-${k}`}>
        {label}{required ? " *" : ""}
      </Label>
      <Input
        id={`new-client-${k}`}
        data-testid={`new-client-${k}`}
        type={type}
        value={form[k] ?? ""}
        placeholder={placeholder}
        onChange={(e) => setField(k, e.target.value)}
      />
    </div>
  );
}

function NewClientAnalyseDialog({ open, onOpenChange, onCreated, onUseExisting }) {
  const { user } = useAuth();
  const [form, setForm] = useState(emptyNewClient);
  const [saving, setSaving] = useState(false);
  const [duplicate, setDuplicate] = useState(null);

  useEffect(() => {
    if (!open) return;
    const defaultCons = user?.role === "conseiller" ? (user.conseiller || user.name || "") : "";
    setForm({ ...emptyNewClient, conseiller: defaultCons });
    setDuplicate(null);
  }, [open, user]);

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e) {
    e.preventDefault();
    if (!form.prenom.trim() || !form.nom.trim()) {
      toast.error("Le prénom et le nom sont obligatoires");
      return;
    }
    setSaving(true);
    setDuplicate(null);
    try {
      const payload = {
        prenom: form.prenom.trim(),
        nom: form.nom.trim(),
        date_naissance: toIsoDate(form.date_naissance) || null,
        sexe: form.sexe || null,
        etat_civil: form.etat_civil || null,
        email: form.email.trim() || null,
        telephone: form.telephone.trim() || null,
        adresse: form.adresse.trim() || null,
        npa: form.npa.trim() || null,
        ville: form.ville.trim() || null,
        pays_residence: form.pays_residence.trim() || null,
        salaire_annuel: form.salaire_annuel ? parseFloat(form.salaire_annuel) : null,
        conseiller: form.conseiller.trim() || null,
        nationalite: "Suisse",
        statut: "Nouveau",
        priorite: "normale",
        nombre_enfants: 0,
        activites: ["prevoyance"],
      };
      const res = await api.post("/clients", payload);
      toast.success("Client ajouté à LeoSoft");
      onOpenChange(false);
      await onCreated(res.data);
    } catch (err) {
      const dup = parseClientDuplicateError(err);
      if (dup.isDuplicate) {
        setDuplicate(dup);
        toast.error(dup.message);
      } else {
        toast.error(dup.message || "Création du client impossible");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Nouveau client et analyse</DialogTitle>
          <DialogDescription>
            Le client est créé dans LeoSoft (même contrôle de doublon que la fiche Clients).
            L'analyse s'ouvre ensuite, préremplie avec ce que vous venez de saisir.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={submit}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Prénom" k="prenom" form={form} setField={setField} required />
            <Field label="Nom" k="nom" form={form} setField={setField} required />
            <Field label="Date de naissance" k="date_naissance" placeholder="jj.mm.aaaa" form={form} setField={setField} />
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground" htmlFor="new-client-sexe">Sexe</Label>
              <select
                id="new-client-sexe"
                data-testid="new-client-sexe"
                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                value={form.sexe}
                onChange={(e) => setField("sexe", e.target.value)}
              >
                <option value="">Non renseigné</option>
                <option value="Homme">Homme</option>
                <option value="Femme">Femme</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground" htmlFor="new-client-etat">État civil</Label>
              <select
                id="new-client-etat"
                data-testid="new-client-etat_civil"
                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                value={form.etat_civil}
                onChange={(e) => setField("etat_civil", e.target.value)}
              >
                <option value="">Non renseigné</option>
                {ETATS_CIVIL.map((etat) => (
                  <option key={etat} value={etat}>{etat}</option>
                ))}
              </select>
            </div>
            <Field label="Salaire annuel (CHF)" k="salaire_annuel" type="number" form={form} setField={setField} />
            <Field label="Adresse" k="adresse" form={form} setField={setField} />
            <Field label="NPA" k="npa" form={form} setField={setField} />
            <Field label="Ville" k="ville" form={form} setField={setField} />
            <Field label="Pays" k="pays_residence" form={form} setField={setField} />
            <Field label="Téléphone" k="telephone" form={form} setField={setField} />
            <Field label="E-mail" k="email" type="email" form={form} setField={setField} />
            <Field label="Conseiller" k="conseiller" form={form} setField={setField} />
          </div>
          {duplicate && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-3 text-sm space-y-2" data-testid="new-client-duplicate">
              <p>{duplicate.message}</p>
              {duplicate.existing?.id && (
                <Button
                  type="button"
                  className="bg-[#002FA7] hover:bg-[#00248a]"
                  onClick={() => onUseExisting(duplicate.existing)}
                >
                  <Plus className="h-4 w-4" />
                  Nouvelle analyse pour ce client
                </Button>
              )}
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
            <Button type="submit" disabled={saving} className="bg-[#002FA7] hover:bg-[#00248a]" data-testid="new-client-submit">
              {saving ? "Création…" : "Créer le client et l'analyse"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function EffectuerAnalyse() {
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const canEdit = hasPerm("analyses.edit");
  const canCreateClient = hasPerm("clients.create");
  const [query, setQuery] = useState("");
  const [clients, setClients] = useState([]);
  const [selected, setSelected] = useState(null);
  const [searching, setSearching] = useState(false);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newClientOpen, setNewClientOpen] = useState(false);
  const [listQuery, setListQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("toutes");
  const [existsPrompt, setExistsPrompt] = useState(null);
  const [pendingCancel, setPendingCancel] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [acting, setActing] = useState(false);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 1) {
      setClients([]);
      setSearching(false);
      return undefined;
    }
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const res = await api.get("/clients", { params: { q: term } });
        const list = Array.isArray(res.data) ? res.data : res.data?.items || [];
        setClients(list.slice(0, 20));
      } catch {
        setClients([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  function reloadAnalyses() {
    return api.get("/analyses-prevoyance")
      .then((res) => setRows(res.data?.items || []))
      .catch(() => toast.error("Impossible de charger les analyses"));
  }

  useEffect(() => {
    reloadAnalyses().finally(() => setLoading(false));
  }, []);

  function primaryForClient(clientId) {
    if (!clientId) return null;
    const group = rows.filter((row) => row.clientId === clientId && isActiveStatus(row.status));
    return pickPrimary(group);
  }

  async function createAnalyse(clientId, clientLabel) {
    if (!clientId) return;
    const existing = primaryForClient(clientId);
    if (existing) {
      setExistsPrompt({
        id: existing.id,
        name: clientLabel || existing.clientName || "ce client",
      });
      setNewClientOpen(false);
      return;
    }
    setCreating(true);
    try {
      const res = await api.post("/analyses-prevoyance", { clientId });
      setNewClientOpen(false);
      navigate(`/effectuer-une-analyse/${res.data.id}`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const analyseId = detail?.analyseId;
      if (e?.response?.status === 409 && analyseId) {
        setNewClientOpen(false);
        setExistsPrompt({
          id: analyseId,
          name: clientLabel || "ce client",
        });
      } else {
        const message = typeof detail === "string" ? detail : detail?.message;
        toast.error(message || "Création impossible");
      }
      setCreating(false);
    }
  }

  async function onClientCreated(client) {
    if (!client?.id) {
      toast.error("Le client a été créé sans identifiant");
      return;
    }
    await createAnalyse(client.id, clientName(client));
  }

  async function confirmCancel() {
    if (!pendingCancel?.id) return;
    setActing(true);
    try {
      await api.post(`/analyses-prevoyance/${pendingCancel.id}/annuler`);
      toast.success("Analyse annulée");
      setPendingCancel(null);
      await reloadAnalyses();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Annulation impossible");
    } finally {
      setActing(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete?.id) return;
    setActing(true);
    try {
      await api.delete(`/analyses-prevoyance/${pendingDelete.id}`);
      toast.success("Analyse supprimée");
      setPendingDelete(null);
      await reloadAnalyses();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suppression impossible");
    } finally {
      setActing(false);
    }
  }

  const groups = groupByClient(rows);
  const cards = groups
    .map((group) => {
      const active = group.filter((row) => isActiveStatus(row.status));
      const cancelled = group.filter((row) => row.status === "annulee");
      const primary = statusFilter === "annulee"
        ? pickPrimary(cancelled)
        : pickPrimary(active.length ? active : group);
      if (!primary) return null;
      return { primary, extras: group.filter((row) => row.id !== primary.id) };
    })
    .filter(Boolean);

  const duplicateGroups = groups
    .map((group) => ({ group, primary: pickPrimary(group.filter((row) => isActiveStatus(row.status)) ) || pickPrimary(group) }))
    .filter((item) => item.group.length > 1 && item.primary);

  const visibleCards = cards.filter(({ primary }) => {
    if (statusFilter !== "toutes" && statusFilter !== "annulee" && primary.status !== statusFilter) return false;
    if (statusFilter === "annulee" && primary.status !== "annulee") return false;
    const haystack = `${primary.clientName || ""} ${primary.conseillerNom || ""} ${primary.ville || ""}`.toLowerCase();
    const term = listQuery.trim().toLowerCase();
    return !term || haystack.includes(term);
  });

  return (
    <Layout>
      <div className="p-6 max-w-6xl mx-auto space-y-8">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Effectuer une analyse</h1>
          <p className="text-muted-foreground mt-1">
            Client déjà dans LeoSoft : recherchez-le, les informations de la fiche remplissent l'analyse.
            Nouveau client : créez-le ici, il est ajouté aux Clients, et l'analyse s'ouvre tout de suite.
          </p>
        </header>

        <section className="rounded-xl border bg-card p-4 space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[240px] space-y-2">
              <label className="text-sm font-medium" htmlFor="client-search">Rechercher un client existant</label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  id="client-search"
                  data-testid="client-search"
                  className="pl-9"
                  placeholder="Nom, prénom…"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setSelected(null);
                  }}
                />
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              className="border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7]/5"
              disabled={!canEdit || !canCreateClient}
              onClick={() => setNewClientOpen(true)}
              data-testid="new-client-analyse-btn"
            >
              <Plus className="h-4 w-4" />
              Nouveau client et analyse
            </Button>
          </div>

          {query.trim().length > 0 && (
            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-left">
                  <tr>
                    <th className="px-3 py-2 w-10" />
                    <th className="px-3 py-2">Client</th>
                    <th className="px-3 py-2">Naissance</th>
                    <th className="px-3 py-2">Ville</th>
                    <th className="px-3 py-2">Conseiller</th>
                  </tr>
                </thead>
                <tbody>
                  {clients.map((c) => (
                    <tr
                      key={c.id}
                      data-testid={`client-result-${c.id}`}
                      className={`border-t cursor-pointer ${selected?.id === c.id ? "bg-[#002FA7]/10" : ""}`}
                      onClick={() => setSelected(c)}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="radio"
                          name="client-pick"
                          checked={selected?.id === c.id}
                          onChange={() => setSelected(c)}
                          aria-label={`Sélectionner ${clientName(c)}`}
                        />
                      </td>
                      <td className="px-3 py-2 font-medium">{clientName(c)}</td>
                      <td className="px-3 py-2">{toSwissDate(c.date_naissance) || c.date_naissance || "—"}</td>
                      <td className="px-3 py-2">{[c.npa, c.ville].filter(Boolean).join(" ") || "—"}</td>
                      <td className="px-3 py-2">{c.conseiller || "—"}</td>
                    </tr>
                  ))}
                  {!searching && clients.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">Aucun client trouvé.</td>
                    </tr>
                  )}
                  {searching && clients.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">Recherche…</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {selected && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#002FA7]/30 bg-[#002FA7]/5 px-4 py-3">
              <div className="min-w-0">
                <p className="font-medium">{clientName(selected)}</p>
                <p className="text-sm text-muted-foreground">
                  Nom, prénom, date de naissance, état civil, salaire, NPA et ville, conseiller :
                  repris depuis la fiche. Vous complétez AVS, LPP, 3e piliers, libre passage et hypothèses.
                </p>
              </div>
              <Button
                type="button"
                className="bg-[#002FA7] hover:bg-[#00248a]"
                disabled={!canEdit || creating}
                onClick={() => createAnalyse(selected.id, clientName(selected))}
                data-testid="new-analyse-for-client-btn"
              >
                <Plus className="h-4 w-4" />
                {creating ? "Création…" : "Nouvelle analyse pour ce client"}
              </Button>
            </div>
          )}
        </section>

        <section className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Mes analyses</h2>
              <p className="text-sm text-muted-foreground">
                Un client, une analyse active. Enregistrer met à jour cette analyse.
              </p>
            </div>
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Rechercher une analyse..."
                value={listQuery}
                onChange={(e) => setListQuery(e.target.value)}
                data-testid="analyse-list-search"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                data-testid={`analyse-filter-${filter.id}`}
                className={`rounded-full border px-3 py-1 text-sm transition ${
                  statusFilter === filter.id
                    ? "border-[#002FA7] bg-[#002FA7] text-white"
                    : "border-border bg-background text-muted-foreground hover:bg-muted/50"
                }`}
                onClick={() => setStatusFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {duplicateGroups.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950 space-y-2" data-testid="analyse-duplicates">
              <p className="font-medium">Doublons déjà présents — aucune analyse n’a été supprimée</p>
              <p>
                La carte affiche, pour chaque client, l’analyse à conserver : la plus récemment modifiée parmi les analyses calculées ou finalisées, sinon le brouillon le plus récent. Les autres restent en base jusqu’à votre accord.
              </p>
              <ul className="space-y-1">
                {duplicateGroups.map(({ group, primary }) => (
                  <li key={primary.clientId || primary.id}>
                    <span className="font-medium">{primary.clientName || "Client"}</span>
                    {" — "}
                    {group.length} analyses. Proposition : conserver celle du {formatDateTimeFr(primary.updatedAt)} ({STATUS_LABELS[primary.status] || primary.status}) et laisser les {group.length - 1} autres de côté.
                  </li>
                ))}
              </ul>
            </div>
          )}

          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement…</p>
          ) : visibleCards.length === 0 ? (
            <p className="text-sm text-muted-foreground">Aucune analyse pour le moment.</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {visibleCards.map(({ primary, extras }) => (
                <article
                  key={primary.id}
                  className="rounded-2xl border bg-card p-5 shadow-sm flex flex-col gap-4"
                  data-testid={`analyse-card-${primary.id}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-lg font-semibold truncate">{primary.clientName || "Client"}</h3>
                      <span className={`mt-2 inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_BADGE[primary.status] || STATUS_BADGE.brouillon}`}>
                        {STATUS_LABELS[primary.status] || primary.status || "Brouillon"}
                      </span>
                    </div>
                  </div>
                  <div className="text-sm text-muted-foreground space-y-1">
                    <p>Dernière modification : {formatDateTimeFr(primary.updatedAt)}</p>
                    <p>Conseiller : {primary.conseillerNom || "—"}</p>
                    {extras.length > 0 && (
                      <p>{extras.length} autre{extras.length > 1 ? "s" : ""} analyse{extras.length > 1 ? "s" : ""} conservée{extras.length > 1 ? "s" : ""}, non affichée{extras.length > 1 ? "s" : ""} ici.</p>
                    )}
                  </div>
                  <div className="mt-auto flex items-center gap-2">
                    <Button
                      className="bg-[#002FA7] hover:bg-[#00248a]"
                      onClick={() => navigate(`/effectuer-une-analyse/${primary.id}`)}
                    >
                      Ouvrir l'analyse
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="outline" size="icon" aria-label={`Actions pour ${primary.clientName || "l'analyse"}`}>
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => navigate(`/effectuer-une-analyse/${primary.id}`)}>
                          Ouvrir
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          disabled={!canEdit || primary.status === "annulee"}
                          onClick={() => setPendingCancel(primary)}
                        >
                          Annuler l'analyse
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          disabled={!canEdit}
                          className="text-rose-700 focus:text-rose-700"
                          onClick={() => setPendingDelete(primary)}
                        >
                          Supprimer
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      <NewClientAnalyseDialog
        open={newClientOpen}
        onOpenChange={setNewClientOpen}
        onCreated={onClientCreated}
        onUseExisting={(existing) => createAnalyse(existing.id, clientName(existing))}
      />

      <Dialog open={!!existsPrompt} onOpenChange={(open) => !open && setExistsPrompt(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Analyse déjà existante</DialogTitle>
            <DialogDescription>
              Une analyse existe déjà pour ce client. Voulez-vous l'ouvrir ?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setExistsPrompt(null)}>Fermer</Button>
            <Button
              type="button"
              className="bg-[#002FA7] hover:bg-[#00248a]"
              onClick={() => navigate(`/effectuer-une-analyse/${existsPrompt.id}`)}
            >
              Ouvrir l'analyse
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!pendingCancel} onOpenChange={(open) => !open && !acting && setPendingCancel(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Annuler l'analyse</DialogTitle>
            <DialogDescription>
              Annuler l'analyse de {pendingCancel?.clientName || "ce client"} ? Elle reste conservée et passe au statut Annulée.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={acting} onClick={() => setPendingCancel(null)}>Retour</Button>
            <Button type="button" disabled={acting} onClick={confirmCancel}>
              {acting ? "Annulation…" : "Annuler l'analyse"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!pendingDelete} onOpenChange={(open) => !open && !acting && setPendingDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Supprimer l'analyse</DialogTitle>
            <DialogDescription>
              Supprimer définitivement cette analyse ? Cette action est irréversible. Le client LeoSoft n'est pas supprimé.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" disabled={acting} onClick={() => setPendingDelete(null)}>Retour</Button>
            <Button type="button" variant="destructive" disabled={acting} onClick={confirmDelete}>
              {acting ? "Suppression…" : "Supprimer définitivement"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
