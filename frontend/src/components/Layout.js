import React, { useState, useEffect } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { LayoutDashboard, KanbanSquare, Users, CalendarDays, Files, Search, LogOut, ShieldCheck, Menu } from "lucide-react";

const nav = [
  { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard, testid: "nav-dashboard" },
  { to: "/dossiers", label: "Dossiers", icon: KanbanSquare, testid: "nav-dossiers" },
  { to: "/clients", label: "Clients", icon: Users, testid: "nav-clients" },
  { to: "/agenda", label: "Ordre du jour", icon: CalendarDays, testid: "nav-agenda" },
  { to: "/formulaires", label: "Formulaires", icon: Files, testid: "nav-formulaires" },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    const t = setTimeout(async () => {
      const res = await api.get("/clients", { params: { q } });
      setResults(res.data.slice(0, 6));
      setOpen(true);
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const SidebarInner = () => (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-border">
        <div className="h-8 w-8 rounded-md bg-[#002FA7] flex items-center justify-center">
          <ShieldCheck className="h-4.5 w-4.5 text-white" strokeWidth={2} />
        </div>
        <span className="font-display font-black tracking-tight">Prévoyance<span className="text-[#002FA7]">CRM</span></span>
      </div>
      <nav className="flex-1 px-3 py-5 space-y-1">
        {nav.map((n) => (
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
        <div className="flex items-center gap-3 px-2 py-2">
          {user?.picture ? (
            <img src={user.picture} alt="" className="h-9 w-9 rounded-full object-cover" />
          ) : (
            <div className="h-9 w-9 rounded-full bg-secondary flex items-center justify-center text-sm font-semibold">
              {user?.name?.[0] || "U"}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{user?.name}</p>
            <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
          </div>
          <button data-testid="logout-btn" onClick={logout} className="p-2 rounded-md hover:bg-secondary text-muted-foreground hover:text-destructive transition-colors">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar desktop */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-64 bg-card border-r border-border flex-col z-30">
        <SidebarInner />
      </aside>

      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-card border-r border-border">
            <SidebarInner />
          </aside>
        </div>
      )}

      <div className="lg:pl-64">
        {/* Header */}
        <header className="sticky top-0 z-20 h-16 bg-card/90 backdrop-blur border-b border-border flex items-center gap-4 px-4 lg:px-8">
          <button className="lg:hidden p-2" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-btn">
            <Menu className="h-5 w-5" />
          </button>
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
        </header>

        <main className="p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
