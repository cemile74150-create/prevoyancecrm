import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import LamalShell from "./LamalShell";

export default function CampaignsPage() {
  const [items, setItems] = useState([]);
  const [current, setCurrent] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get("/lamal/campaigns").then((res) => setItems(res.data.items || [])).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const prepare = async () => {
    setBusy(true);
    try {
      const res = await api.post("/lamal/campaigns", { year: 2027, client_ids: [] });
      toast.success("Campagne préparée, sans envoi");
      setCurrent(res.data);
      const detail = await api.get(`/lamal/campaigns/${res.data.id}`);
      setCurrent(detail.data);
      load();
    } catch (error) {
      toast.error(typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "Préparation impossible");
    } finally {
      setBusy(false);
    }
  };

  const sendBlocked = async () => {
    if (!current?.campaign?.id && !current?.id) return;
    const id = current.campaign?.id || current.id;
    try {
      await api.post(`/lamal/campaigns/${id}/send`, { confirm: "" });
    } catch (error) {
      toast.message(error?.response?.data?.detail || "Envoi bloqué");
    }
  };

  const emails = current?.emails || [];

  return (
    <LamalShell title="Campagnes LAMal" subtitle="Préparation annuelle. Un seul brouillon par client. Aucun e-mail n'est envoyé pendant cette phase.">
      <div className="flex gap-2">
        <Button className="bg-[#002FA7] hover:bg-[#00248a]" onClick={prepare} disabled={busy}>{busy ? "Préparation…" : "Préparer la campagne 2027"}</Button>
        <Button variant="outline" onClick={sendBlocked}>Tenter l'envoi</Button>
      </div>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-4 space-y-2">
          {items.map((item) => (
            <button key={item.id} type="button" className="block w-full text-left text-sm border rounded-md px-3 py-2" onClick={() => api.get(`/lamal/campaigns/${item.id}`).then((res) => setCurrent(res.data))}>
              {item.year} · {item.progress?.selected || 0} destinataires · {item.status}
            </button>
          ))}
          {!items.length && <p className="text-sm text-muted-foreground">Aucune campagne préparée.</p>}
        </Card>
        <Card className="p-4 space-y-3">
          {emails.map((email) => (
            <article key={email.id} className="border rounded-md p-3 text-sm space-y-1">
              <p className="font-medium">{email.subject}</p>
              <p className="text-muted-foreground">{email.to} · {email.status}</p>
              <pre className="whitespace-pre-wrap text-xs">{email.body}</pre>
            </article>
          ))}
          {!emails.length && <p className="text-sm text-muted-foreground">Sélectionnez une campagne pour relire les messages.</p>}
        </Card>
      </div>
    </LamalShell>
  );
}
