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
import { Plus, KeyRound, UserX, UserCheck, Pencil, Settings2, Shield, Eye, Upload, Download, Mail } from "lucide-react";
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

const ORIGIN_LABELS = {
  inherited: "Hérité du rôle",
  granted: "Accès supplémentaire",
  revoked: "Accès retiré",
};

const ORIGIN_BADGE_CLASS = {
  inherited: "bg-slate-100 text-slate-700",
  granted: "bg-emerald-100 text-emerald-800",
  revoked: "bg-amber-100 text-amber-900",
};

function pruneOverridesForRole(overrides, rolePermissions) {
  const next = {};
  Object.entries(overrides || {}).forEach(([key, value]) => {
    if (Boolean(value) !== Boolean(rolePermissions?.[key])) {
      next[key] = value === true;
    }
  });
  return next;
}

function originForKey(key, rolePermissions, overrides) {
  if (!(key in (overrides || {}))) return "inherited";
  const inherited = Boolean(rolePermissions?.[key]);
  const ov = Boolean(overrides[key]);
  if (ov === inherited) return "inherited";
  return ov ? "granted" : "revoked";
}

function effectivePerm(key, rolePermissions, overrides, fallbackPermissions) {
  if (key in (overrides || {})) return overrides[key] === true;
  if (rolePermissions && key in rolePermissions) return rolePermissions[key] === true;
  return Boolean(fallbackPermissions?.[key]);
}

const emptyForm = () => ({
  prenom: "",
  nom: "",
  email: "",
  telephone: "",
  password: "",
  send_activation: true,
  role: "conseiller",
  conseiller: "",
  finma_number: "",
  entreprise_id: "",
  receive_conseiller_rappel_copies: false,
  see_all_dossiers: false,
  permissions: defaultPermissions("conseiller"),
  role_permissions: defaultPermissions("conseiller"),
  permission_overrides: {},
});

function formFromUser(u, roleDefaultsMap) {
  const role = u.role || "conseiller";
  const fromDefaults = roleDefaultsMap?.[role]?.permissions;
  const rolePermissions = {
    ...defaultPermissions(role),
    ...(fromDefaults || {}),
    ...(u.role_permissions || {}),
  };
  let permission_overrides = { ...(u.permission_overrides || {}) };
  // Compat pré-Phase 4 : si pas d'overrides stockés, dériver les écarts snapshot ↔ rôle.
  if (Object.keys(permission_overrides).length === 0 && u.permissions) {
    PERMISSION_KEYS.forEach((key) => {
      if (key === "lamal_module_access") return;
      if (!(key in u.permissions)) return;
      const inherited = Boolean(rolePermissions[key]);
      const snap = Boolean(u.permissions[key]);
      if (snap !== inherited) permission_overrides[key] = snap;
    });
  }
  const permissions = { ...rolePermissions };
  Object.entries(permission_overrides).forEach(([key, value]) => {
    permissions[key] = value === true;
  });
  return {
    prenom: u.prenom || "",
    nom: u.nom || "",
    email: u.email || "",
    telephone: u.telephone || "",
    password: "",
    send_activation: false,
    role,
    conseiller: u.conseiller || "",
    finma_number: u.finma_number || "",
    entreprise_id: u.entreprise_id || "",
    receive_conseiller_rappel_copies: !!u.receive_conseiller_rappel_copies,
    see_all_dossiers: u.see_all_dossiers === true || (u.see_all_dossiers == null && defaultSeeAllDossiers(u.role)),
    permissions,
    role_permissions: rolePermissions,
    permission_overrides,
  };
}

export default function Utilisateurs() {
  const { isAdmin, user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [catalog, setCatalog] = useState(PERMISSION_CATALOG);
  const [roleDefaults, setRoleDefaults] = useState(null);
  const [conseillers, setConseillers] = useState([]);
  const [entreprises, setEntreprises] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(() => emptyForm());
  const [pwdDialog, setPwdDialog] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [importPreview, setImportPreview] = useState(null);
  const [importing, setImporting] = useState(false);

  const selectedEntreprise = useMemo(
    () => entreprises.find((e) => e.id === form.entreprise_id) || null,
    [entreprises, form.entreprise_id],
  );

  // Phase 4 : exceptions individuelles — roles.manage / LAMal hors matrice user.
  const editableCatalog = useMemo(
    () => (catalog || []).filter((g) => g.id !== "roles" && g.id !== "lamal"),
    [catalog],
  );

  const overrideCount = useMemo(
    () => Object.keys(form.permission_overrides || {}).length,
    [form.permission_overrides],
  );

  const load = async () => {
    setLoading(true);
    try {
      const [u, r, c, cat, ent] = await Promise.all([
        api.get("/users"),
        api.get("/users/roles"),
        api.get("/users/conseillers"),
        api.get("/users/permissions-catalog").catch(() => ({ data: null })),
        api.get("/entreprises").catch(() => ({ data: [] })),
      ]);
      setUsers(u.data || []);
      setRoles(r.data || []);
      setConseillers(conseillerNames(c.data));
      setEntreprises(ent.data || []);
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

  const applyRoleDefaults = (role, current, { keepOverrides = true } = {}) => {
    const d = roleDefaults?.[role];
    const rolePermissions = d?.permissions ? { ...d.permissions } : defaultPermissions(role);
    const permission_overrides = keepOverrides
      ? pruneOverridesForRole(current.permission_overrides, rolePermissions)
      : {};
    return {
      ...current,
      role,
      see_all_dossiers: d ? !!d.see_all_dossiers : defaultSeeAllDossiers(role),
      role_permissions: rolePermissions,
      permissions: { ...rolePermissions },
      permission_overrides,
    };
  };

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setDialog(true);
  };

  const openEdit = (u) => {
    setEditing(u);
    setForm(formFromUser(u, roleDefaults));
    setDialog(true);
  };

  const setPerm = (key, value) => {
    setForm((prev) => {
      const inherited = Boolean(prev.role_permissions?.[key]);
      const desired = value === true;
      const nextOverrides = { ...(prev.permission_overrides || {}) };
      if (desired === inherited) {
        delete nextOverrides[key];
      } else {
        nextOverrides[key] = desired;
      }
      return {
        ...prev,
        permission_overrides: nextOverrides,
        permissions: {
          ...prev.permissions,
          [key]: desired,
        },
      };
    });
  };

  const setGroup = (group, value) => {
    setForm((prev) => {
      const nextOverrides = { ...(prev.permission_overrides || {}) };
      const nextPermissions = { ...prev.permissions };
      group.items.forEach((item) => {
        if (editingSelf && item.key === "users.manage") return;
        const inherited = Boolean(prev.role_permissions?.[item.key]);
        const desired = value === true;
        nextPermissions[item.key] = desired;
        if (desired === inherited) {
          delete nextOverrides[item.key];
        } else {
          nextOverrides[item.key] = desired;
        }
      });
      return {
        ...prev,
        permission_overrides: nextOverrides,
        permissions: nextPermissions,
      };
    });
  };

  const resetExceptions = () => {
    setForm((prev) => ({
      ...prev,
      permission_overrides: {},
      permissions: { ...(prev.role_permissions || defaultPermissions(prev.role)) },
    }));
  };

  const save = async () => {
    if (!form.prenom.trim() || !form.nom.trim() || !form.email.trim()) {
      toast.error("Prénom, nom et e-mail obligatoires");
      return;
    }
    if (!editing && !form.send_activation && (!form.password || form.password.length < 6)) {
      toast.error("Mot de passe obligatoire (min. 6) ou cochez l'activation par e-mail");
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
        entreprise_id: form.entreprise_id || null,
        receive_conseiller_rappel_copies:
          form.role === "admin" ? !!form.receive_conseiller_rappel_copies : false,
        see_all_dossiers: !!form.see_all_dossiers,
      };
      if (editing) {
        // Phase 4 : exceptions via permission_overrides (snapshot réeligné côté backend).
        // see_all_dossiers reste indépendant de la matrice modules.
        const overridesPayload = form.permission_overrides || {};
        const hadServerOverrides = Object.keys(editing.permission_overrides || {}).length > 0;
        await api.put(`/users/${editing.user_id || editing.account_id}`, {
          ...payload,
          permission_overrides: overridesPayload,
          // Journal dédié si on vide toutes les exceptions (bouton reset ou retour au template).
          reset_permission_overrides:
            Object.keys(overridesPayload).length === 0 && hadServerOverrides,
        });
        toast.success("Accès enregistrés");
      } else {
        const res = await api.post("/users", {
          ...payload,
          permissions: form.permissions,
          password: form.send_activation ? undefined : form.password,
          send_activation: !!form.send_activation,
        });
        if (res.data?.activation?.activation_link) {
          toast.success("Compte créé — lien d'activation à transmettre (SMTP indisponible)");
        } else {
          toast.success(form.send_activation ? "Compte créé — e-mail d'activation envoyé" : "Utilisateur créé");
        }
      }
      setDialog(false);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur d'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  const sendActivation = async (u) => {
    try {
      const res = await api.post(`/users/${u.user_id || u.account_id}/send-activation`);
      if (res.data?.email_sent) toast.success("Lien d'activation envoyé");
      else if (res.data?.activation_link) {
        await navigator.clipboard?.writeText(res.data.activation_link);
        toast.success("Lien copié (e-mail non envoyé)");
      } else toast.message("Activation préparée");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossible");
    }
  };

  const onImportFile = async (file) => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setImporting(true);
    try {
      const res = await api.post("/users-import/preview", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImportPreview(res.data);
      toast.success(`Aperçu : ${res.data?.counts?.ok || 0} prêt(s)`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import impossible");
    } finally {
      setImporting(false);
    }
  };

  const applyImport = async () => {
    if (!importPreview?.can_apply) {
      toast.error("Corrigez les erreurs avant d'importer");
      return;
    }
    setImporting(true);
    try {
      const res = await api.post("/users-import/apply", {
        rows: importPreview.rows,
        send_activation_emails: true,
      });
      toast.success(
        `Import : ${res.data.created} créé(s), ${res.data.activations_emailed} e-mail(s), ${res.data.activations_pending_admin_link} lien(s) admin`,
      );
      setImportPreview(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import refusé");
    } finally {
      setImporting(false);
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
    { id: "ceo", label: "Direction" },
    { id: "gestionnaire_offres", label: "Gestionnaire offres" },
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
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              className="gap-2"
              onClick={async () => {
                try {
                  const res = await api.get("/users-import/template.xlsx", { responseType: "blob" });
                  const url = URL.createObjectURL(res.data);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "modele_import_conseillers_leosoft.xlsx";
                  a.click();
                  URL.revokeObjectURL(url);
                } catch (e) {
                  toast.error("Téléchargement du modèle impossible");
                }
              }}
            >
              <Download className="h-4 w-4" /> Modèle Excel
            </Button>
            <label className="inline-flex items-center gap-2 px-3 py-2 rounded-md border border-border cursor-pointer hover:bg-secondary text-sm">
              <Upload className="h-4 w-4" /> Importer Excel
              <input
                type="file"
                accept=".xlsx,.xlsm"
                className="hidden"
                disabled={importing}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  onImportFile(f);
                }}
              />
            </label>
            <Button onClick={openCreate} className="bg-[#002FA7] hover:bg-[#00248a] gap-2" data-testid="new-user-btn">
              <Plus className="h-4 w-4" /> Nouvel utilisateur
            </Button>
          </div>
        </div>

        {importPreview && (
          <div className="mb-6 rounded-md border border-border bg-card p-4 text-sm space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium">
                Aperçu import — OK {importPreview.counts?.ok || 0} / {importPreview.counts?.total || 0}
                {(importPreview.unknown_entreprises || []).length > 0 && (
                  <span className="text-amber-700">
                    {" "}· entreprises inconnues : {(importPreview.unknown_entreprises || []).map((x) => x.nom).join(", ")}
                  </span>
                )}
              </p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setImportPreview(null)}>Fermer</Button>
                <Button
                  size="sm"
                  className="bg-[#002FA7] hover:bg-[#00248a]"
                  disabled={!importPreview.can_apply || importing}
                  onClick={applyImport}
                >
                  Valider l&apos;import
                </Button>
              </div>
            </div>
            <div className="max-h-48 overflow-auto border border-border rounded">
              <table className="w-full text-xs">
                <thead className="bg-secondary/50 sticky top-0">
                  <tr>
                    <th className="px-2 py-1 text-left">Ligne</th>
                    <th className="px-2 py-1 text-left">Nom</th>
                    <th className="px-2 py-1 text-left">E-mail</th>
                    <th className="px-2 py-1 text-left">Entreprise</th>
                    <th className="px-2 py-1 text-left">FINMA</th>
                    <th className="px-2 py-1 text-left">Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {(importPreview.rows || []).map((r) => (
                    <tr key={`${r.ligne}-${r.email}`} className="border-t border-border">
                      <td className="px-2 py-1">{r.ligne}</td>
                      <td className="px-2 py-1">{r.prenom} {r.nom}</td>
                      <td className="px-2 py-1">{r.email}</td>
                      <td className="px-2 py-1">{r.entreprise}</td>
                      <td className="px-2 py-1">{r.entreprise_finma || "—"}</td>
                      <td className="px-2 py-1">{r.status}{(r.errors || []).length ? ` (${r.errors.join(", ")})` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {loading ? (
          <p className="text-muted-foreground">Chargement…</p>
        ) : (
          <div className="border border-border rounded-md overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-secondary/60 text-left">
                <tr>
                  <th className="px-4 py-3 font-medium">Nom</th>
                  <th className="px-4 py-3 font-medium">E-mail</th>
                  <th className="px-4 py-3 font-medium">Entreprise</th>
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
                    <td className="px-4 py-3 text-muted-foreground">{u.entreprise_nom || "—"}</td>
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
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${u.active === false ? "bg-slate-100 text-slate-600" : u.activation_pending ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-emerald-800"}`}>
                        {u.active === false ? "Désactivé" : u.activation_pending ? "Activation" : "Actif"}
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
                        <button title="Renvoyer activation" onClick={() => sendActivation(u)} className="p-2 rounded-md hover:bg-secondary">
                          <Mail className="h-4 w-4" />
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
                ? "Rôle, droits hérités et exceptions individuelles (sans changer le template du rôle). L'accès dossiers reste séparé."
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
            <div className="space-y-1.5">
              <Label className="text-xs">Entreprise</Label>
              <Select
                value={form.entreprise_id || "__none__"}
                onValueChange={(v) => setForm({ ...form, entreprise_id: v === "__none__" ? "" : v })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Sélectionner…" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— Aucune —</SelectItem>
                  {entreprises.map((e) => (
                    <SelectItem key={e.id} value={e.id}>{e.nom}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">FINMA entreprise</Label>
              <Input value={selectedEntreprise?.finma_number || editing?.entreprise_finma || ""} readOnly className="bg-secondary/40" />
            </div>
            {!editing && (
              <>
                <div className="col-span-2 flex items-center gap-2 rounded-md border border-border px-3 py-2">
                  <Checkbox
                    checked={!!form.send_activation}
                    onCheckedChange={(v) => setForm({ ...form, send_activation: v === true })}
                    id="send-activation"
                  />
                  <Label htmlFor="send-activation" className="text-xs font-normal cursor-pointer">
                    Envoyer un lien d&apos;activation (l&apos;utilisateur définit son mot de passe)
                  </Label>
                </div>
                {!form.send_activation && (
                  <div className="space-y-1.5 col-span-2">
                    <Label className="text-xs">Mot de passe *</Label>
                    <PasswordInput
                      value={form.password}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                      autoComplete="new-password"
                    />
                  </div>
                )}
              </>
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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold">Permissions par fonctionnalité</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Héritées du rôle
                    {form.role ? ` « ${roleOptions.find((r) => r.id === form.role)?.label || form.role} »` : ""}
                    {editing && overrideCount > 0
                      ? ` — ${overrideCount} exception(s) individuelle(s)`
                      : " — cochez pour ajouter ou retirer une exception"}
                    . L&apos;accès dossiers (ci-dessus) est indépendant.
                  </p>
                </div>
                <div className="flex flex-wrap gap-3">
                  {editing && (
                    <button
                      type="button"
                      className="text-xs text-[#002FA7] underline underline-offset-2"
                      onClick={resetExceptions}
                      disabled={overrideCount === 0}
                    >
                      Réinitialiser les exceptions
                    </button>
                  )}
                  {!editing && (
                    <button
                      type="button"
                      className="text-xs text-[#002FA7] underline underline-offset-2"
                      onClick={() => setForm((prev) => applyRoleDefaults(prev.role, prev, { keepOverrides: false }))}
                    >
                      Réinitialiser selon le rôle
                    </button>
                  )}
                </div>
              </div>
              {editableCatalog.map((group) => {
                const allOn = group.items.every((i) =>
                  effectivePerm(i.key, form.role_permissions, form.permission_overrides, form.permissions),
                );
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
                        const checked = effectivePerm(
                          item.key,
                          form.role_permissions,
                          form.permission_overrides,
                          form.permissions,
                        );
                        const origin = originForKey(item.key, form.role_permissions, form.permission_overrides);
                        return (
                          <label
                            key={item.key}
                            className={`flex items-start gap-2 text-sm cursor-pointer select-none ${locked ? "opacity-70" : ""}`}
                          >
                            <Checkbox
                              checked={checked}
                              disabled={locked}
                              onCheckedChange={(v) => setPerm(item.key, v === true)}
                              className="mt-0.5"
                            />
                            <span className="min-w-0">
                              <span className="block leading-snug">{item.label}</span>
                              {editing && (
                                <span
                                  className={`inline-flex mt-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${ORIGIN_BADGE_CLASS[origin]}`}
                                >
                                  {ORIGIN_LABELS[origin]}
                                </span>
                              )}
                            </span>
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
