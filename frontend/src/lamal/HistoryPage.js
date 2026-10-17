import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import LamalShell from "./LamalShell";

export default function HistoryPage() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    api.get("/lamal/clients").then(async (res) => {
      const withHistory = (res.data.items || []).filter((row) => row.comparison_id);
      const details = await Promise.all(withHistory.slice(0, 30).map((row) => api.get(`/lamal/clients/${row.id}/history`).then((response) => response.data.items || [])));
      setItems(details.flat());
    }).catch(() => setItems([]));
  }, []);

  return (
    <LamalShell title="Historique" subtitle="Les comparaisons restent conservées avec la version des tarifs utilisée. Un nouveau calcul n'efface pas les précédents.">
      <div className="space-y-3">
        {items.map((item) => (
          <Card key={item.id} className="p-4 text-sm space-y-1">
            <p className="font-medium">{item.created_at} · année {item.year}</p>
            <p className="text-muted-foreground">Jeu {item.dataset_id} · client {item.client_id}</p>
            <p>Région {item.result?.region || "—"} · économie fiable : {item.result?.savings_reliable ? "oui" : "non"}</p>
          </Card>
        ))}
        {!items.length && <p className="text-sm text-muted-foreground">Aucune comparaison enregistrée.</p>}
      </div>
    </LamalShell>
  );
}
