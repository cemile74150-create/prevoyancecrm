import React from "react";
import { ShieldCheck, ArrowRight } from "lucide-react";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export default function Login() {
 const handleGoogleLogin = () => {
  window.location.href = "/dashboard";
};
  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background">
      {/* Left / form */}
      <div className="flex flex-col justify-between p-8 lg:p-14">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-md bg-[#002FA7] flex items-center justify-center">
            <ShieldCheck className="h-5 w-5 text-white" strokeWidth={2} />
          </div>
          <span className="font-display font-black text-lg tracking-tight">Prévoyance<span className="text-[#002FA7]">CRM</span></span>
        </div>

        <div className="max-w-md w-full mx-auto lg:mx-0 animate-fade-up">
          <p className="text-[#002FA7] font-semibold text-sm uppercase tracking-wider mb-3">Cabinet de prévoyance</p>
          <h1 className="font-display font-black text-4xl sm:text-5xl tracking-tight leading-[1.05] mb-4">
            Gérez vos dossiers de retraite en toute clarté.
          </h1>
          <p className="text-muted-foreground text-base mb-8">
            Centralisez vos clients, suivez chaque dossier visuellement et gagnez du temps sur vos analyses de prévoyance.
          </p>

          <button
            data-testid="google-login-btn"
            onClick={handleGoogleLogin}
            className="group w-full flex items-center justify-center gap-3 bg-white border border-border rounded-md px-5 py-3.5 font-medium text-foreground hover:border-[#002FA7] hover:shadow-sm transition-all duration-200"
          >
            <img src="https://www.svgrepo.com/show/475656/google-color.svg" alt="Google" className="h-5 w-5" />
            Se connecter avec Google
            <ArrowRight className="h-4 w-4 ml-auto opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
          </button>

          <p className="text-xs text-muted-foreground mt-4">
            En vous connectant, vous acceptez nos conditions d'utilisation et notre politique de confidentialité.
          </p>
        </div>

        <p className="text-xs text-muted-foreground">© 2026 PrévoyanceCRM — Conçu pour les conseillers suisses.</p>
      </div>

      {/* Right / image */}
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
