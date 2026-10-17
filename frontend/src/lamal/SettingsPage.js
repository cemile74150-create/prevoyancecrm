import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import LamalShell from "./LamalShell";

export default function SettingsPage() {
  const [meta, setMeta] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get("/lamal/meta").then((res) => setMeta(res.data)).catch((error) => toast.error(error?.response?.data?.detail || "Paramètres indisponibles")), []);
  useEffect(() => { load(); }, [load]);

  const importFiles = async () => {
    setBusy(true);
    try {
      const res = await api.post("/lamal/datasets/import");
      toast.success(res.data.idempotent ? "Ce jeu est déjà actif" : "Jeu officiel activé");
      load();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Import refusé : jeu incomplet ou incorrect");
    } finally {
      setBusy(false);
    }
  };

  return (
    <LamalShell title="Paramètres et données OFSP" subtitle="Les primes actives ne sont remplacées qu'après contrôle du fichier. Un jeu incomplet est rejeté.">
      <Card className="p-5 space-y-3 text-sm">
        <p>Source : {meta?.sources?.premiums}</p>
        <p>Régions : {meta?.sources?.regions}</p>
        <p>Publication des primes : {meta?.sources?.published}</p>
        <p>Jeu actif : {meta?.dataset ? `${meta.dataset.id} · ${meta.dataset.offer_count} offres` : "aucun"}</p>
        <p>Envoi réel : désactivé</p>
        <Button className="bg-[#002FA7] hover:bg-[#00248a]" onClick={importFiles} disabled={busy}>{busy ? "Contrôle des fichiers…" : "Actualiser depuis les fichiers officiels locaux"}</Button>
        <p className="text-muted-foreground">Déposez les fichiers OFSP dans backend/data/ofsp avant l'import : Praemien_CH.csv, Praemienregionen_2027.xlsx, ortschaften.zip, Tarife.csv, Einzugsgebiete.csv.</p>
      </Card>
    </LamalShell>
  );
}
