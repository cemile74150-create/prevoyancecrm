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
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, KeyRound, UserX, UserCheck, Pencil, Settings2 } from "lucide-react";
import PasswordInput from "@/components/PasswordInput";

const emptyForm = {
  prenom: "",
  nom: "",
  email: "",
  telephone: "",
  password: "",
  role: "conseiller",
  conseiller: "",
};

export default function Utilisateurs() {
  const { isAdmin } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [conseillers, setConseillers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialog, setDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [pwdDialog, setPwdDialog] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [u, r, c] = await Promise.all([
        api.get("/users"),
        api.get("/users/roles"),
        api.get("/users/conseillers"),
      ]);
      setUsers(u.data || []);
      setRoles(r.data || []);
      setConseillers(c.data || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible de charger les utilisateurs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setDialog(true);
  };

  const openEdit = (u) => {
    setEditing(u);
    setForm({
      prenom: u.prenom || "",
      nom: u.nom || "",
      email: u.email || "",
      telephone: u.telephone || "",
      password: "",
      role: u.role || "conseiller",
      conseiller: u.conseiller || "",
    });
    setDialog(true);
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
      if (editing) {
        await api.put(`/users/${editing.user_id || editing.account_id}`, {
          prenom: form.prenom,
          nom: form.nom,
          email: form.email,
          telephone: form.telephone || null,
          role: form.role,
          conseiller: form.role === "conseiller" ? (form.conseiller || `${form.prenom} ${form.nom}`.trim()) : form.conseiller || null,
        });
        toast.success("Utilisateur mis à jour");
      } else {
        await api.post("/users", {
          ...form,
          telephone: form.telephone || null,
          conseiller: form.role === "conseiller" ? (form.conseiller || `${form.prenom} ${form.nom}`.trim()) : form.conseiller || null,
        });
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
    { id: "conseiller", label: "Conseiller" },
  ], [roles]);

  if (!isAdmin) return <Navigate to="/dashboard" replace />;

  return (
    <Layout>
      <div className="animate-fade-up max-w-5xl">
        <div className="flex items-center justify-between flex-wrap gap-4 mb-8">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
              <Settings2 className="h-7 w-7 text-[#002FA7]" /> Utilisateurs
            </h1>
            <p className="text-muted-foreground mt-1">
              Créez des comptes, attribuez les rôles et contrôlez l'accès aux dossiers.
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
                  <th className="px-4 py-3 font-medium">Conseiller</th>
                  <th className="px-4 py-3 font-medium">Statut</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user_id || u.account_id} className="border-t border-border">
                    <td className="px-4 py-3 font-medium">{u.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                    <td className="px-4 py-3">{u.role_label || u.role}</td>
                    <td className="px-4 py-3 text-muted-foreground">{u.conseiller || "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${u.active === false ? "bg-slate-100 text-slate-600" : "bg-emerald-100 text-emerald-800"}`}>
                        {u.active === false ? "Désactivé" : "Actif"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? "Modifier l'utilisateur" : "Nouvel utilisateur"}</DialogTitle>
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
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v })}>
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
              <Select
                value={form.conseiller || "__self__"}
                onValueChange={(v) => setForm({
                  ...form,
                  conseiller: v === "__self__" ? `${form.prenom} ${form.nom}`.trim() : v,
                })}
              >
                <SelectTrigger><SelectValue placeholder="Nom du conseiller" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__self__">
                    {form.prenom || form.nom ? `${form.prenom} ${form.nom}`.trim() : "Nom de l'utilisateur"}
                  </SelectItem>
                  {conseillers.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
