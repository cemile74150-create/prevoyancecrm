import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { formatChf } from "./LamalShell";

export default function ClientHistory({ clientId }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!clientId) return;
    api.get(`/lamal/clients/${clientId}/history`)
      .then((res) => setItems(res.data.items || []))
      .catch(() => setError("Historique LAMal indisponible"));
  }, [clientId]);

  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-bold">Historique LAMal</h2>
        <Link className="text-sm text-[#002FA7]" to={`/lamal/comparaison?client=${clientId}`}>Nouvelle comparaison</Link>
      </div>
      {error && <p className="text-sm text-amber-800">{error}</p>}
      {items.map((item) => (
        <article key={item.id} className="border rounded-md p-3 text-sm">
          <p>{item.created_at} · primes {item.year}</p>
          <p className="text-muted-foreground">Source {item.result?.dataset?.sha256?.slice(0, 12) || item.dataset_id}</p>
          <p>Économie annuelle : {item.result?.best_equivalent_alternative ? `${formatChf(item.result.best_equivalent_alternative.year)} CHF` : "—"}</p>
        </article>
      ))}
      {!items.length && !error && <p className="text-sm text-muted-foreground">Aucune comparaison LAMal pour ce client.</p>}
    </Card>
  );
}
