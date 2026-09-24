import React, { useState, useEffect } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { LayoutDashboard, KanbanSquare, Users, CalendarDays, Files, Search, LogOut, ShieldCheck, Menu, Bell, Settings2, KeyRound, Shield, FileSpreadsheet, Activity, Pencil, Mail, UserCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import PasswordInput from "@/components/PasswordInput";
import NotificationBell from "@/components/NotificationBell";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { APP_NAME } from "@/lib/brand";
import {
  formatRappelAttributionLine,
  formatRappelDateFr,
  RAPPEL_STATUT_LABEL,
  rappelStatutEffectif,
} from "@/lib/rappels";

const nav = [
  { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard, testid: "nav-dashboard" },
  { to: "/dossiers", label: "Dossiers", icon: KanbanSquare, testid: "nav-dossiers", perm: "dossiers.view" },
  { to: "/clients", label: "Clients", icon: Users, testid: "nav-clients", perm: "clients.view" },
  { to: "/suivi-3p", label: "Fiscalité, 3e pilier & Fortune 2026", icon: Shield, testid: "nav-suivi-3p", perm: "suivi_3p.view" },
  { to: "/demandes-offres", label: "Demandes d'offres", icon: FileSpreadsheet, testid: "nav-demandes-offres", perm: "demandes_offres.view" },
  { to: "/modifier-offre", label: "Modifier une offre", icon: Pencil, testid: "nav-modifier-offre", perm: "demandes_offres.edit" },
  { to: "/gestion-reponses-offres", label: "Gestion réponses offres", icon: FileSpreadsheet, testid: "nav-gestion-offres", perm: "demandes_offres.process" },
  { to: "/historique-emails", label: "Historique des e-mails", icon: Mail, testid: "nav-historique-emails", anyOf: ["users.manage"] },
  { to: "/rappels", label: "Rappels", icon: Bell, testid: "nav-rappels", perm: "rappels.view" },
  { to: "/agenda", label: "Ordre du jour", icon: CalendarDays, testid: "nav-agenda", perm: "agenda.view" },
  { to: "/formulaires", label: "Formulaires", icon: Files, testid: "nav-formulaires", perm: "formulaires.view" },
  { to: "/suivi-technique", label: "Suivi technique", icon: Activity, testid: "nav-suivi-technique", perm: "users.manage" },
  { to: "/utilisateurs", label: "Utilisateurs", icon: Settings2, testid: "nav-users", perm: "users.manage" },
];

export default function Layout({ children }) {
  const { user, logout, hasPerm } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [pwdOpen, setPwdOpen] = useState(false);
  const [espaceOpen, setEspaceOpen] = useState(false);
  const [mesRappels, setMesRappels] = useState([]);
  const [mesRappelsLoading, setMesRappelsLoading] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPwd, setSavingPwd] = useState(false);

  const navItems = nav.filter((n) => {
    if (n.anyOf?.length) return n.anyOf.some((k) => hasPerm(k));
    if (n.perm) return hasPerm(n.perm);
    return true;
  });
  const canSearch = hasPerm("clients.view") || hasPerm("dossiers.view");
  const canViewRappels = hasPerm("rappels.view");

  useEffect(() => {
    if (!espaceOpen || !canViewRappels) return;
    let cancelled = false;
    setMesRappelsLoading(true);
    api.get("/rappels/mine")
      .then((res) => {
        if (!cancelled) setMesRappels(Array.isArray(res.data) ? res.data : []);
      })
      .catch(() => {
        if (!cancelled) {
          setMesRappels([]);
          toast.error("Impossible de charger Mes rappels");
        }
      })
      .finally(() => {
        if (!cancelled) setMesRappelsLoading(false);
      });
    return () => { cancelled = true; };
  }, [espaceOpen, canViewRappels]);

  useEffect(() => {
    if (!canSearch || !q.trim()) { setResults([]); return; }
    const t = setTimeout(async () => {
      const res = await api.get("/clients", { params: { q } });
      setResults(res.data.slice(0, 6));
      setOpen(true);
    }, 250);
    return () => clearTimeout(t);
  }, [q, canSearch]);

  const changePassword = async () => {
    if (!currentPassword || !newPassword) {
      toast.error("Remplissez tous les champs");
      return;
    }
    if (newPassword.length < 6) {
      toast.error("Nouveau mot de passe trop court (min. 6)");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("La confirmation ne correspond pas");
      return;
    }
    setSavingPwd(true);
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success("Mot de passe modifié");
      setPwdOpen(false);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Modification impossible");
    } finally {
      setSavingPwd(false);
    }
  };

  const SidebarInner = () => (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-border">
        <div className="h-8 w-8 rounded-md bg-[#002FA7] flex items-center justify-center">
          <ShieldCheck className="h-4.5 w-4.5 text-white" strokeWidth={2} />
        </div>
        <span className="font-display font-black tracking-tight">
          Leo<span className="text-[#002FA7]">Soft</span>
        </span>
        <span className="sr-only">{APP_NAME}</span>
      </div>
      <nav className="flex-1 px-3 py-5 space-y-1">
        {navItems.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            data-testid={n.testid}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-200 ${
                isActive ? "bg-[#002FA7] text-white" : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              }`
            }
          >
            <n.icon className="h-4.5 w-4.5" strokeWidth={1.75} />
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3 border-t border-border">
        <div className="flex items-center gap-2 px-2 py-2">
          <button
            type="button"
            title="Mon espace"
            data-testid="mon-espace-btn"
            onClick={() => setEspaceOpen(true)}
            className="flex items-center gap-2 flex-1 min-w-0 rounded-md hover:bg-secondary p-1 -m-1 text-left transition-colors"
          >
            {user?.picture ? (
              <img src={user.picture} alt="" className="h-9 w-9 rounded-full object-cover shrink-0" />
            ) : (
              <div className="h-9 w-9 rounded-full bg-secondary flex items-center justify-center text-sm font-semibold shrink-0">
                {user?.name?.[0] || "U"}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {user?.role_label || user?.role || user?.email}
              </p>
            </div>
          </button>
          <button
            title="Changer mon mot de passe"
            data-testid="change-password-btn"
            onClick={() => setPwdOpen(true)}
            className="p-2 rounded-md hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
          >
            <KeyRound className="h-4 w-4" />
          </button>
          <button data-testid="logout-btn" onClick={logout} className="p-2 rounded-md hover:bg-secondary text-muted-foreground hover:text-destructive transition-colors">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background">
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-64 bg-card border-r border-border flex-col z-30">
        <SidebarInner />
      </aside>

      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-card border-r border-border">
            <SidebarInner />
          </aside>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 h-16 bg-card/90 backdrop-blur border-b border-border flex items-center gap-4 px-4 lg:px-8">
          <button className="lg:hidden p-2" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-btn">
            <Menu className="h-5 w-5" />
          </button>
          {canSearch && (
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              data-testid="global-search-input"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onFocus={() => q && setOpen(true)}
              onBlur={() => setTimeout(() => setOpen(false), 200)}
              placeholder="Rechercher un client (nom, tél, email, n° dossier)…"
              className="w-full h-10 pl-10 pr-4 rounded-md bg-secondary border border-transparent focus:border-[#002FA7] focus:bg-white focus:ring-2 focus:ring-[#002FA7]/20 outline-none text-sm transition-all"
            />
            {open && results.length > 0 && (
              <div className="absolute top-12 left-0 right-0 bg-card border border-border rounded-md shadow-lg overflow-hidden z-30">
                {results.map((c) => (
                  <button
                    key={c.id}
                    data-testid={`search-result-${c.id}`}
                    onMouseDown={() => { navigate(`/clients/${c.id}`); setQ(""); setOpen(false); }}
                    className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-secondary text-left transition-colors"
                  >
                    <span className="text-sm font-medium">{c.prenom} {c.nom}</span>
                    <span className="text-xs text-muted-foreground">{c.numero_dossier}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          )}
          {hasPerm("rappels.view") && <NotificationBell />}
        </header>

        <main className="p-4 lg:p-8">{children}</main>
      </div>

      <Dialog open={espaceOpen} onOpenChange={setEspaceOpen}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2">
              <UserCircle className="h-5 w-5 text-[#002FA7]" />
              Mon espace
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="rounded-md border border-border bg-secondary/30 px-3 py-2.5">
              <p className="text-sm font-medium">{user?.name}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{user?.email}</p>
            </div>
            {canViewRappels && (
              <div data-testid="mes-rappels-section">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <h3 className="text-sm font-semibold flex items-center gap-1.5">
                    <Bell className="h-4 w-4 text-[#002FA7]" />
                    Mes rappels
                  </h3>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => {
                      setEspaceOpen(false);
                      navigate("/rappels");
                    }}
                  >
                    Voir tous
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mb-3">
                  Uniquement les rappels que vous avez créés. Cliquez pour ouvrir la fiche client.
                </p>
                {mesRappelsLoading ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">Chargement…</p>
                ) : mesRappels.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4 text-center border border-dashed border-border rounded-md">
                    Aucun rappel créé par vous pour le moment.
                  </p>
                ) : (
                  <ul className="space-y-2 max-h-72 overflow-y-auto">
                    {mesRappels.slice(0, 40).map((r) => {
                      const effectif = rappelStatutEffectif(r);
                      return (
                        <li key={r.id}>
                          <button
                            type="button"
                            data-testid={`mes-rappel-${r.id}`}
                            disabled={!r.client_id}
                            onClick={() => {
                              if (!r.client_id) return;
                              setEspaceOpen(false);
                              navigate(`/clients/${r.client_id}`);
                            }}
                            className="w-full text-left rounded-md border border-border px-3 py-2.5 hover:border-[#002FA7]/40 hover:bg-secondary/40 transition-colors disabled:opacity-60"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-sm font-medium truncate">
                                {r.client_name || "Client"}
                                {r.numero_dossier ? (
                                  <span className="ml-1.5 text-[11px] font-normal text-muted-foreground font-mono">
                                    {r.numero_dossier}
                                  </span>
                                ) : null}
                              </p>
                              <span className="text-[11px] text-muted-foreground shrink-0">
                                {RAPPEL_STATUT_LABEL[effectif] || effectif}
                              </span>
                            </div>
                            <p className="text-sm mt-0.5 truncate">{r.titre}</p>
                            <p className="text-xs text-muted-foreground mt-1">
                              Échéance {formatRappelDateFr(r.date)}
                              {r.heure ? ` · ${r.heure}` : ""}
                            </p>
                            <p className="text-[11px] text-muted-foreground mt-0.5">
                              {formatRappelAttributionLine(r)}
                            </p>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEspaceOpen(false)}>Fermer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={pwdOpen} onOpenChange={setPwdOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Changer mon mot de passe</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1.5">
              <Label className="text-xs">Mot de passe actuel</Label>
              <PasswordInput
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nouveau mot de passe</Label>
              <PasswordInput
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Confirmer</Label>
              <PasswordInput
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPwdOpen(false)}>Annuler</Button>
            <Button onClick={changePassword} disabled={savingPwd} className="bg-[#002FA7] hover:bg-[#00248a]">
              {savingPwd ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
