import { NavLink, useLocation } from "react-router-dom";
import Layout from "@/components/Layout";

const LINKS = [
  { to: "/lamal", label: "Tableau de bord", end: true },
  { to: "/lamal/comparaison", label: "Comparaison individuelle" },
  { to: "/lamal/clients", label: "Comparaisons clients" },
  { to: "/lamal/campagnes", label: "Campagnes e-mails" },
  { to: "/lamal/historique", label: "Historique" },
  { to: "/lamal/parametres", label: "Paramètres et données OFSP" },
];

export default function LamalShell({ title, subtitle, children }) {
  const location = useLocation();
  return (
    <Layout>
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        <header className="space-y-3">
          <p className="text-xs uppercase tracking-[0.16em] text-[#002FA7] font-semibold">Assurance obligatoire des soins</p>
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight">{title}</h1>
            {subtitle && <p className="text-sm text-muted-foreground mt-1 max-w-3xl">{subtitle}</p>}
          </div>
          <nav className="flex flex-wrap gap-2">
            {LINKS.map((link) => {
              const active = link.end ? location.pathname === link.to : location.pathname.startsWith(link.to);
              return (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                    active ? "bg-[#002FA7] text-white border-[#002FA7]" : "bg-white text-muted-foreground border-border hover:text-foreground"
                  }`}
                >
                  {link.label}
                </NavLink>
              );
            })}
          </nav>
        </header>
        {children}
      </div>
    </Layout>
  );
}

export function StatusBadge({ status, label }) {
  const tone = {
    economie_identifiee: "bg-emerald-50 text-emerald-800 border-emerald-200",
    aucune_economie: "bg-slate-50 text-slate-700 border-slate-200",
    informations_manquantes: "bg-amber-50 text-amber-900 border-amber-200",
    pret_pour_analyse: "bg-sky-50 text-sky-900 border-sky-200",
    email_a_valider: "bg-indigo-50 text-indigo-900 border-indigo-200",
    email_envoye: "bg-emerald-50 text-emerald-900 border-emerald-200",
  }[status] || "bg-secondary text-foreground border-border";
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs font-medium ${tone}`}>{label || status}</span>;
}

export function formatChf(value) {
  if (value == null || value === "") return "—";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return new Intl.NumberFormat("fr-CH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(number);
}
