import React, { useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, KeyRound, UserX, UserCheck, Pencil, Settings2, Shield, Eye } from "lucide-react";
import PasswordInput from "@/components/PasswordInput";
import ConseillerCombobox from "@/components/ConseillerCombobox";
import { conseillerNames } from "@/lib/conseillers";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import {
  PERMISSION_CATALOG,
  defaultPermissions,
  defaultSeeAllDossiers,
  dossierAccessLabel,
  enabledPermissionCount,
  PERMISSION_KEYS,
} from "@/lib/permissions";

const emptyForm = () => ({
  prenom: "",
  nom: "",
  email: "",
  telephone: "",
  password: "",
  role: "conseiller",
  conseiller: "",
  finma_number: "",
  receive_conseiller_rappel_copies: false,
  see_all_dossiers: false,
  permissions: defaultPermissions("conseiller"),
});

function formFromUser(u) {
  return {
    prenom: u.prenom || "",
    nom: u.nom || "",
    email: u.email || "",
    telephone: u.telephone || "",
    password: "",
    role: u.role || "conseiller",
    conseiller: u.conseiller || "",
    finma_number: u.finma_number || "",
    receive_conseiller_rappel_copies: !!u.receive_conseiller_rappel_copies,
    see_all_dossiers: u.see_all_dossiers === true || (u.see_all_dossiers == null && defaultSeeAllDossiers(u.role)),
    permissions: { ...defaultPermissions(u.role || "conseiller"), ...(u.permissions || {}) },
  };
}

export default function Utilisateurs() {
  const { isAdmin, user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [catalog, setCatalog] = useState(PERMISSION_CATALOG);
  const [roleDefaults, setRoleDefaults] = useState(null);
  const [conseillers, setConseillers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(() => emptyForm());
  const [pwdDialog, setPwdDialog] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [u, r, c, cat] = await Promise.all([
        api.get("/users"),
        api.get("/users/roles"),
        api.get("/users/conseillers"),
        api.get("/users/permissions-catalog").catch(() => ({ data: null })),
      ]);
      setUsers(u.data || []);
      setRoles(r.data || []);
      setConseillers(conseillerNames(c.data));
      if (cat.data?.catalog?.length) setCatalog(cat.data.catalog);
      if (cat.data?.defaults) setRoleDefaults(cat.data.defaults);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible de charger les utilisateurs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  const applyRoleDefaults = (role, current) => {
    const d = roleDefaults?.[role];
    return {
      ...current,
      role,
      see_all_dossiers: d ? !!d.see_all_dossiers : defaultSeeAllDossiers(role),
      permissions: d?.permissions ? { ...d.permissions } : defaultPermissions(role),
    };
  };

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setDialog(true);
  };

  const openEdit = (u) => {
    setEditing(u);
    setForm(formFromUser(u));
    setDialog(true);
  };

  const setPerm = (key, value) => {
    setForm((prev) => ({
      ...prev,
      permissions: { ...prev.permissions, [key]: value === true },
    }));
  };

  const setGroup = (group, value) => {
    const next = { ...form.permissions };
    group.items.forEach((item) => {
      if (editingSelf && item.key === "users.manage") return;
      next[item.key] = value;
    });
    setForm({ ...form, permissions: next });
  };

  const save = async () => {
    if (!form.prenom.trim() || !form.nom.trim() || !form.email.trim()) {
      toast.error("Prénom, nom et e-mail obligatoires");
      return;
    }
    if (!editing && (!form.password || form.password.length < 6)) {
      toast.error("Mot de passe obligatoire (min. 6 caractères)");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        prenom: form.prenom,
        nom: form.nom,
        email: form.email,
        telephone: form.telephone || null,
        role: form.role,
        conseiller: form.role === "conseiller"
          ? (form.conseiller || `${form.prenom} ${form.nom}`.trim())
          : form.conseiller || null,
        finma_number: form.finma_number || null,
        receive_conseiller_rappel_copies:
          form.role === "admin" ? !!form.receive_conseiller_rappel_copies : false,
        see_all_dossiers: !!form.see_all_dossiers,
        permissions: form.permissions,
      };
      if (editing) {
        await api.put(`/users/${editing.user_id || editing.account_id}`, payload);
        toast.success("Accès enregistrés");
      } else {
        await api.post("/users", { ...payload, password: form.password });
        toast.success("Utilisateur créé");
      }
      setDialog(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur d'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  const resetPassword = async () => {
    if (!newPassword || newPassword.length < 6) {
      toast.error("Mot de passe trop court (min. 6)");
      return;
    }
    try {
      await api.post(`/users/${pwdDialog.user_id || pwdDialog.account_id}/reset-password`, {
        password: newPassword,
      });
      toast.success("Mot de passe réinitialisé");
      setPwdDialog(null);
      setNewPassword("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur");
    }
  };

  const toggleActive = async (u) => {
    try {
      if (u.active === false) {
        await api.put(`/users/${u.user_id || u.account_id}`, { active: true });
        toast.success("Compte réactivé");
      } else {
        await api.post(`/users/${u.user_id || u.account_id}/deactivate`);
        toast.success("Compte désactivé");
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action impossible");
    }
  };

  const roleOptions = useMemo(() => roles.length ? roles : [
    { id: "admin", label: "Administrateur" },
    { id: "ceo", label: "CEO / Direction" },
    { id: "gestionnaire_offres", label: "Gestionnaire d'offres" },
    { id: "conseiller", label: "Conseiller" },
  ], [roles]);

  const editingSelf = editing && (editing.user_id === me?.user_id || editing.account_id === me?.account_id || editing.email === me?.email);

  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  return (
    <Layout>
      <div className="animate-fade-up max-w-6xl">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-8">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
              <Settings2 className="h-7 w-7 text-[#002FA7]" /> Utilisateurs
            </h1>
            <p className="text-muted-foreground mt-1">
              Comptes, rôles et droits d&apos;accès — ouvrez une fiche pour voir exactement à quoi chaque personne a accès.
            </p>
          </div>
          <Button onClick={openCreate} className="bg-[#002FA7] hover:bg-[#00248a] gap-2" data-testid="new-user-btn">
            <Plus className="h-4 w-4" /> Nouvel utilisateur
          </Button>
        </div>

        {loading ? (
          <p className="text-muted-foreground">Chargement…</p>
        ) : (
          <div className="border border-border rounded-md overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-secondary/60 text-left">
                <tr>
                  <th className="px-4 py-3 font-medium">Nom</th>
                  <th className="px-4 py-3 font-medium">E-mail</th>
                  <th className="px-4 py-3 font-medium">Rôle</th>
                  <th className="px-4 py-3 font-medium">Accès dossiers</th>
                  <th className="px-4 py-3 font-medium">Droits</th>
                  <th className="px-4 py-3 font-medium">Statut</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr
                    key={u.user_id || u.account_id}
                    className="border-t border-border hover:bg-secondary/40 cursor-pointer"
                    onClick={() => openEdit(u)}
                  >
                    <td className="px-4 py-3 font-medium">{u.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                    <td className="px-4 py-3">{u.role_label || u.role}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                        u.see_all_dossiers ? "bg-[#002FA7]/10 text-[#002FA7]" : "bg-slate-100 text-slate-700"
                      }`}>
                        {dossierAccessLabel(u)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {enabledPermissionCount(u)}/{PERMISSION_KEYS.length} actifs
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${u.active === false ? "bg-slate-100 text-slate-600" : "bg-emerald-100 text-emerald-800"}`}>
                        {u.active === false ? "Désactivé" : "Actif"}
                      </span>
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex justify-end gap-1">
                        <button title="Voir les accès" onClick={() => openEdit(u)} className="p-2 rounded-md hover:bg-secondary text-[#002FA7]">
                          <Eye className="h-4 w-4" />
                        </button>
                        <button title="Modifier" onClick={() => openEdit(u)} className="p-2 rounded-md hover:bg-secondary">
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button title="Réinitialiser MDP" onClick={() => { setPwdDialog(u); setNewPassword(""); }} className="p-2 rounded-md hover:bg-secondary">
                          <KeyRound className="h-4 w-4" />
                        </button>
                        <button title={u.active === false ? "Réactiver" : "Désactiver"} onClick={() => toggleActive(u)} className="p-2 rounded-md hover:bg-secondary">
                          {u.active === false ? <UserCheck className="h-4 w-4" /> : <UserX className="h-4 w-4" />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Dialog open={dialog} onOpenChange={setDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-[#002FA7]" />
              {editing ? `Accès de ${editing.name}` : "Nouvel utilisateur"}
            </DialogTitle>
            <DialogDescription>
              {editing
                ? "Consultez et modifiez exactement les dossiers et fonctionnalités auxquels cette personne a accès."
                : "Créez le compte, puis définissez le périmètre dossiers et les permissions."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Prénom *</Label>
              <Input value={form.prenom} onChange={(e) => setForm({ ...form, prenom: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nom *</Label>
              <Input value={form.nom} onChange={(e) => setForm({ ...form, nom: e.target.value })} />
            </div>
            <div className="space-y-1.5 col-span-2">
              <Label className="text-xs">E-mail *</Label>
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="space-y-1.5 col-span-2">
              <Label className="text-xs">Téléphone</Label>
              <Input value={form.telephone} onChange={(e) => setForm({ ...form, telephone: e.target.value })} />
            </div>
            {!editing && (
              <div className="space-y-1.5 col-span-2">
                <Label className="text-xs">Mot de passe *</Label>
                <PasswordInput
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  autoComplete="new-password"
                />
              </div>
            )}
            <div className="space-y-1.5">
              <Label className="text-xs">Rôle *</Label>
              <Select
                value={form.role}
                onValueChange={(v) => setForm((prev) => applyRoleDefaults(v, prev))}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {roleOptions.map((r) => (
                    <SelectItem key={r.id} value={r.id}>{r.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Conseiller responsable</Label>
              <ConseillerCombobox
                value={form.conseiller || ""}
                onChange={(v) => setForm({ ...form, conseiller: v })}
                options={[
                  `${form.prenom || ""} ${form.nom || ""}`.trim(),
                  ...conseillers,
                ].filter(Boolean)}
                placeholder="Nom du conseiller (liste ou saisie)"
                data-testid="user-field-conseiller"
              />
              <p className="text-[11px] text-muted-foreground">
                Sert à filtrer les dossiers lorsque l&apos;accès global est désactivé.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">N° FINMA</Label>
              <Input
                data-testid="user-field-finma"
                value={form.finma_number || ""}
                onChange={(e) => setForm({ ...form, finma_number: e.target.value })}
                placeholder="Ex. 123456"
              />
              <p className="text-[11px] text-muted-foreground">
                Associé au conseiller — prérempli sur les fiches clients.
              </p>
            </div>

            <div className="col-span-2 rounded-lg border border-border bg-secondary/40 p-4 space-y-2">
              <p className="text-sm font-semibold flex items-center gap-2">
                <Shield className="h-4 w-4 text-[#002FA7]" /> Accès aux dossiers
              </p>
              <label className="flex items-start gap-3 cursor-pointer select-none">
                <Switch
                  checked={!!form.see_all_dossiers}
                  onCheckedChange={(v) => setForm({ ...form, see_all_dossiers: v === true })}
                  className="mt-0.5 data-[state=checked]:bg-[#002FA7]"
                />
                <span className="text-sm">
                  Accès à tous les dossiers du cabinet
                  <span className="block text-xs text-muted-foreground mt-0.5">
                    Par défaut, un conseiller ne voit que les dossiers à son nom
                    {form.conseiller ? ` (ex. ${form.conseiller})` : ""}. Un administrateur voit tout.
                    Activez cette option pour donner une vue globale.
                  </span>
                </span>
              </label>
            </div>

            {form.role === "admin" && (
              <div className="col-span-2">
                <label className="flex items-start gap-2 text-sm cursor-pointer select-none">
                  <Checkbox
                    checked={!!form.receive_conseiller_rappel_copies}
                    onCheckedChange={(v) =>
                      setForm({ ...form, receive_conseiller_rappel_copies: v === true })
                    }
                    className="mt-0.5"
                  />
                  <span>
                    Recevoir une copie des e-mails de rappel des conseillers
                    <span className="block text-xs text-muted-foreground mt-0.5">
                      L&apos;administrateur est mis en copie (Cc) des rappels envoyés aux conseillers.
                    </span>
                  </span>
                </label>
              </div>
            )}

            <div className="col-span-2 space-y-3 pt-1">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">Permissions par fonctionnalité</p>
                <button
                  type="button"
                  className="text-xs text-[#002FA7] underline underline-offset-2"
                  onClick={() => setForm((prev) => applyRoleDefaults(prev.role, prev))}
                >
                  Réinitialiser selon le rôle
                </button>
              </div>
              {catalog.map((group) => {
                const allOn = group.items.every((i) => form.permissions?.[i.key]);
                return (
                  <div key={group.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.label}</p>
                      <button
                        type="button"
                        className="text-[11px] text-[#002FA7]"
                        onClick={() => setGroup(group, !allOn)}
                      >
                        {allOn ? "Tout décocher" : "Tout cocher"}
                      </button>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-2">
                      {group.items.map((item) => {
                        const locked = editingSelf && item.key === "users.manage";
                        return (
                          <label
                            key={item.key}
                            className={`flex items-center gap-2 text-sm cursor-pointer select-none ${locked ? "opacity-70" : ""}`}
                          >
                            <Checkbox
                              checked={!!form.permissions?.[item.key]}
                              disabled={locked}
                              onCheckedChange={(v) => setPerm(item.key, v === true)}
                            />
                            <span>{item.label}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialog(false)}>Annuler</Button>
            <Button onClick={save} disabled={saving} className="bg-[#002FA7] hover:bg-[#00248a]" data-testid="save-user-permissions">
              {saving ? "Enregistrement…" : "Enregistrer les modifications"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!pwdDialog} onOpenChange={(o) => !o && setPwdDialog(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Réinitialiser le mot de passe</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">{pwdDialog?.name}</p>
          <PasswordInput
            placeholder="Nouveau mot de passe"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setPwdDialog(null)}>Annuler</Button>
            <Button onClick={resetPassword} className="bg-[#002FA7] hover:bg-[#00248a]">Valider</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
