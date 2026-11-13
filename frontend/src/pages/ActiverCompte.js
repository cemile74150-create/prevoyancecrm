import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { APP_NAME } from "@/lib/brand";
import PasswordInput from "@/components/PasswordInput";
import { Button } from "@/components/ui/button";

export default function ActiverCompte() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!token) {
      setChecking(false);
      setStatus({ ok: false, error: "missing" });
      return;
    }
    api
      .get("/auth/activation/status", { params: { token } })
      .then((res) => setStatus(res.data))
      .catch(() => setStatus({ ok: false, error: "invalid_or_expired" }))
      .finally(() => setChecking(false));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (password !== confirm) {
      toast.error("Les mots de passe ne correspondent pas");
      return;
    }
    if (password.length < 8) {
      toast.error("Mot de passe trop court (min. 8 caractères)");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/activation/complete", { token, password });
      toast.success("Mot de passe enregistré — vous pouvez vous connecter");
      navigate("/login", { replace: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Activation impossible");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-6">
      <div className="w-full max-w-md animate-fade-up">
        <p className="text-[#002FA7] font-semibold text-sm uppercase tracking-wider mb-2">{APP_NAME}</p>
        <h1 className="font-display font-black text-3xl tracking-tight mb-2">Activer votre compte</h1>
        <p className="text-muted-foreground text-sm mb-6">
          Définissez votre mot de passe personnel. Ce lien est personnel et à durée limitée.
        </p>
        {checking ? (
          <p className="text-muted-foreground">Vérification du lien…</p>
        ) : !status?.ok ? (
          <div className="rounded-md border border-border bg-card p-4 text-sm">
            <p className="font-medium">Lien invalide ou expiré</p>
            <p className="text-muted-foreground mt-1">
              Demandez à votre administrateur un nouvel e-mail d&apos;activation.
            </p>
            <Link to="/login" className="text-[#002FA7] underline mt-3 inline-block">
              Retour à la connexion
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4 border border-border rounded-md bg-card p-5">
            <p className="text-sm">
              Compte : <strong>{status.email}</strong>
            </p>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Nouveau mot de passe</label>
              <PasswordInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5"
                autoComplete="new-password"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Confirmer</label>
              <PasswordInput
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="mt-1.5"
                autoComplete="new-password"
              />
            </div>
            <Button type="submit" disabled={loading} className="w-full bg-[#002FA7] hover:bg-[#00248a]">
              {loading ? "Enregistrement…" : "Enregistrer mon mot de passe"}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
