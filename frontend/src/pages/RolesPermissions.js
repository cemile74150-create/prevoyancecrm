import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { KeyRound, Loader2, Pencil, Plus, Shield, Trash2, Users } from "lucide-react";
import { PERMISSION_CATALOG } from "@/lib/permissions";

const ACCENT = "#002FA7";

function emptyCreateForm() {
  return { label: "", see_all_dossiers_default: false };
}

export default function RolesPermissions() {
  const { hasPerm } = useAuth();
  // Bootstrap : visible si roles.manage OU users.manage (API reste roles.manage).
  const canOpen = hasPerm("roles.manage") || hasPerm("users.manage");
  const canManage = hasPerm("roles.manage");

  const [roles, setRoles] = useState([]);
  const [catalog, setCatalog] = useState(PERMISSION_CATALOG);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [draftPerms, setDraftPerms] = useState({});
  const [draftLabel, setDraftLabel] = useState("");
  const [draftSeeAll, setDraftSeeAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState(() => emptyCreateForm());
  const [dirty, setDirty] = useState(false);

  const selected = useMemo(
    () => roles.find((r) => r.id === selectedId) || null,
    [roles, selectedId],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/roles");
      const list = Array.isArray(res.data?.roles) ? res.data.roles : [];
      setRoles(list);
      if (res.data?.catalog?.length) setCatalog(res.data.catalog);
      setSelectedId((prev) => {
        if (prev && list.some((r) => r.id === prev)) return prev;
        return list[0]?.id || null;
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible de charger les rôles");
      setRoles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (canManage) load();
    else if (canOpen) setLoading(false);
  }, [canManage, canOpen, load]);

  useEffect(() => {
    if (!selected) {
      setDraftPerms({});
      setDraftLabel("");
      setDraftSeeAll(false);
      setDirty(false);
      return;
    }
    setDraftPerms({ ...(selected.permissions || {}) });
    setDraftLabel(selected.label || "");
    setDraftSeeAll(!!selected.see_all_dossiers_default);
    setDirty(false);
  }, [selected]);

  const togglePerm = (key) => {
    if (!canManage) return;
    setDraftPerms((prev) => ({ ...prev, [key]: !prev[key] }));
    setDirty(true);
  };

  const saveSelected = async () => {
    if (!selected || !canManage) return;
    setSaving(true);
    try {
      const res = await api.put(`/roles/${selected.id}`, {
        label: draftLabel.trim() || selected.label,
        permissions: draftPerms,
        see_all_dossiers_default: draftSeeAll,
      });
      const propagated = res.data?.propagation?.users_updated ?? 0;
      toast.success(
        propagated > 0
          ? `Rôle enregistré — ${propagated} utilisateur(s) mis à jour (overrides respectés)`
          : "Rôle enregistré",
      );
      setDirty(false);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Enregistrement impossible");
    } finally {
      setSaving(false);
    }
  };

  const createRole = async () => {
    if (!canManage) return;
    const label = createForm.label.trim();
    if (!label) {
      toast.error("Libellé obligatoire");
      return;
    }
    setSaving(true);
    try {
      const res = await api.post("/roles", {
        label,
        see_all_dossiers_default: !!createForm.see_all_dossiers_default,
      });
      toast.success("Rôle créé");
      setCreateOpen(false);
      setCreateForm(emptyCreateForm());
      await load();
      if (res.data?.id) setSelectedId(res.data.id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Création impossible");
    } finally {
      setSaving(false);
    }
  };

  const disableRole = async (role) => {
    if (!canManage || !role || role.system) return;
    if (!window.confirm(`Désactiver le rôle « ${role.label} » ?`)) return;
    setSaving(true);
    try {
      await api.delete(`/roles/${role.id}`);
      toast.success("Rôle désactivé");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suppression impossible");
    } finally {
      setSaving(false);
    }
  };

  if (!canOpen) return <Navigate to="/dashboard" replace />;

  return (
    <Layout>
      <div className="animate-fade-up max-w-6xl">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-8">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
              <KeyRound className="h-7 w-7" style={{ color: ACCENT }} /> Rôles et permissions
            </h1>
            <p className="text-muted-foreground mt-1">
              Templates de droits par rôle — une modification se propage aux utilisateurs du rôle
              sans écraser les exceptions individuelles déjà enregistrées.
            </p>
          </div>
          {canManage && (
            <Button
              onClick={() => setCreateOpen(true)}
              className="gap-2 bg-[#002FA7] hover:bg-[#00248a]"
              data-testid="new-role-btn"
            >
              <Plus className="h-4 w-4" /> Nouveau rôle
            </Button>
          )}
        </div>

        {!canManage && (
          <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Votre compte peut ouvrir cette page (droit utilisateurs), mais l&apos;API Rôles exige
            « roles.manage ». Demandez un backfill Phase 3 ou reconnectez-vous après mise à jour
            des droits administrateur.
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-muted-foreground py-16 justify-center">
            <Loader2 className="h-5 w-5 animate-spin" /> Chargement des rôles…
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
            <aside className="space-y-2">
              {roles.map((role) => {
                const active = role.id === selectedId;
                return (
                  <button
                    key={role.id}
                    type="button"
                    onClick={() => setSelectedId(role.id)}
                    className={`w-full text-left rounded-md border px-3 py-3 transition ${
                      active
                        ? "border-[#002FA7] bg-[#002FA7]/[0.06] shadow-sm"
                        : "border-border bg-card hover:bg-secondary/60"
                    } ${role.active === false ? "opacity-60" : ""}`}
                    data-testid={`role-row-${role.id}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold text-sm flex items-center gap-1.5">
                          <Shield className="h-3.5 w-3.5 text-[#002FA7]" />
                          {role.label}
                        </div>
                        <div className="text-xs text-muted-foreground mt-0.5 font-mono">{role.id}</div>
                      </div>
                      {role.system && (
                        <span className="text-[10px] uppercase tracking-wide text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                          Système
                        </span>
                      )}
                    </div>
                    <div className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Users className="h-3.5 w-3.5" />
                      {role.user_count ?? 0} utilisateur{(role.user_count || 0) > 1 ? "s" : ""}
                      {role.active === false ? " · inactif" : ""}
                    </div>
                  </button>
                );
              })}
              {!roles.length && (
                <p className="text-sm text-muted-foreground p-3">Aucun rôle en base.</p>
              )}
            </aside>

            <section className="rounded-md border border-border bg-card p-5 min-h-[420px]">
              {!selected ? (
                <p className="text-muted-foreground text-sm">Sélectionnez un rôle.</p>
              ) : (
                <>
                  <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
                    <div className="space-y-3 flex-1 min-w-[220px]">
                      <div>
                        <Label htmlFor="role-label">Libellé</Label>
                        <Input
                          id="role-label"
                          className="mt-1 max-w-md"
                          value={draftLabel}
                          disabled={!canManage}
                          onChange={(e) => {
                            setDraftLabel(e.target.value);
                            setDirty(true);
                          }}
                        />
                      </div>
                      <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <Checkbox
                          checked={draftSeeAll}
                          disabled={!canManage}
                          onCheckedChange={(v) => {
                            setDraftSeeAll(!!v);
                            setDirty(true);
                          }}
                        />
                        Voir tous les dossiers par défaut
                      </label>
                      <p className="text-xs text-muted-foreground">
                        Identifiant : <span className="font-mono">{selected.id}</span>
                        {selected.system ? " · rôle système (non supprimable)" : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {canManage && !selected.system && (
                        <Button
                          variant="outline"
                          className="gap-2 text-rose-700 border-rose-200 hover:bg-rose-50"
                          disabled={saving || (selected.user_count || 0) > 0}
                          onClick={() => disableRole(selected)}
                          title={
                            (selected.user_count || 0) > 0
                              ? "Des utilisateurs sont encore rattachés"
                              : "Désactiver le rôle"
                          }
                        >
                          <Trash2 className="h-4 w-4" /> Désactiver
                        </Button>
                      )}
                      {canManage && (
                        <Button
                          className="gap-2 bg-[#002FA7] hover:bg-[#00248a]"
                          disabled={!dirty || saving}
                          onClick={saveSelected}
                          data-testid="save-role-btn"
                        >
                          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pencil className="h-4 w-4" />}
                          Enregistrer
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="space-y-5">
                    {(catalog || []).map((group) => (
                      <div key={group.id}>
                        <h3 className="text-sm font-semibold text-slate-800 mb-2 border-b border-border pb-1">
                          {group.label}
                        </h3>
                        <div className="grid sm:grid-cols-2 gap-2">
                          {(group.items || []).map((item) => (
                            <label
                              key={item.key}
                              className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-secondary/50 text-sm cursor-pointer"
                            >
                              <Checkbox
                                className="mt-0.5"
                                checked={!!draftPerms[item.key]}
                                disabled={!canManage}
                                onCheckedChange={() => togglePerm(item.key)}
                              />
                              <span>
                                <span className="block">{item.label}</span>
                                <span className="block text-[11px] text-muted-foreground font-mono">
                                  {item.key}
                                </span>
                              </span>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>
          </div>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nouveau rôle</DialogTitle>
            <DialogDescription>
              Crée un template personnalisé (supprimable s&apos;il n&apos;a aucun utilisateur).
              Les droits sensibles ne sont pas accordés automatiquement.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label htmlFor="new-role-label">Libellé</Label>
              <Input
                id="new-role-label"
                className="mt-1"
                value={createForm.label}
                onChange={(e) => setCreateForm((f) => ({ ...f, label: e.target.value }))}
                placeholder="Ex. Assistant commercial"
              />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={!!createForm.see_all_dossiers_default}
                onCheckedChange={(v) =>
                  setCreateForm((f) => ({ ...f, see_all_dossiers_default: !!v }))
                }
              />
              Voir tous les dossiers par défaut
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Annuler</Button>
            <Button
              className="bg-[#002FA7] hover:bg-[#00248a]"
              disabled={saving}
              onClick={createRole}
            >
              Créer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
