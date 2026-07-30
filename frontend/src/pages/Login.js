import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, ArrowRight, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function Login() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) {
      toast.error("Saisissez votre e-mail et mot de passe");
      return;
    }
    setLoading(true);
    try {
      const res = await api.post("/auth/login", {
        email: email.trim(),
        password,
      });
      setUser(res.data.user);
      toast.success(`Bienvenue ${res.data.user.name}`);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail || "Connexion impossible";
      toast.error(typeof detail === "string" ? detail : "Email ou mot de passe incorrect");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      <div className="flex flex-col justify-between p-8 lg:p-14">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-md bg-[#002FA7] flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-white" strokeWidth={2} />
          </div>
          <span className="font-display font-black text-lg tracking-tight">
            Prévoyance<span className="text-[#002FA7]">CRM</span>
          </span>
        </div>

        <div className="max-w-md w-full mx-auto lg:mx-0 animate-fade-up">
          <p className="text-[#002FA7] font-semibold text-sm uppercase tracking-wider mb-3">
            Connexion sécurisée
          </p>
          <h1 className="font-display font-black text-4xl sm:text-5xl tracking-tight leading-[1.05] mb-4">
            Accédez à votre espace de travail.
          </h1>
          <p className="text-muted-foreground text-base mb-8">
            Chaque conseiller ne voit que ses dossiers. Les administrateurs disposent de la vue globale.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground" htmlFor="login-email">
                Adresse e-mail
              </label>
              <input
                id="login-email"
                data-testid="login-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full h-11 px-3 rounded-md border border-border bg-white text-sm outline-none focus:border-[#002FA7] focus:ring-2 focus:ring-[#002FA7]/20"
                placeholder="prenom.nom@cabinet.ch"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground" htmlFor="login-password">
                Mot de passe
              </label>
              <input
                id="login-password"
                data-testid="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full h-11 px-3 rounded-md border border-border bg-white text-sm outline-none focus:border-[#002FA7] focus:ring-2 focus:ring-[#002FA7]/20"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              data-testid="login-submit"
              disabled={loading}
              className="group w-full flex items-center justify-center gap-3 bg-[#002FA7] text-white rounded-md px-5 py-3.5 font-medium hover:bg-[#00248a] transition-all duration-200 disabled:opacity-60"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Se connecter
              {!loading && (
                <ArrowRight className="h-4 w-4 ml-auto opacity-70 group-hover:opacity-100 transition-opacity" />
              )}
            </button>
          </form>
        </div>

        <p className="text-xs text-muted-foreground">© 2026 PrévoyanceCRM — Conçu pour les conseillers suisses.</p>
      </div>

      <div className="hidden lg:block relative">
        <img
          src="https://images.pexels.com/photos/17057591/pexels-photo-17057591.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
          alt="Architecture suisse moderne"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-[#002FA7]/30 mix-blend-multiply" />
        <div className="absolute bottom-0 left-0 right-0 p-12 bg-gradient-to-t from-[#0F172A]/90 to-transparent">
          <p className="font-display font-bold text-white text-2xl tracking-tight max-w-sm">
            De la prise de contact au rapport final, sur une seule plateforme.
          </p>
        </div>
      </div>
    </div>
  );
}
