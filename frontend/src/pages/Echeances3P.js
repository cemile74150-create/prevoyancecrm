import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Echeances3PTable from "@/components/Echeances3PTable";
import {
  URGENCY,
  URGENCY_ORDER,
  filterAlertEcheances,
  sortByUrgency,
  countByUrgency,
  matchesEcheanceSearch,
  getUrgency,
} from "@/lib/echeances3p";
import { ArrowLeft, Search, Shield } from "lucide-react";

export default function Echeances3P() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [urgencyFilter, setUrgencyFilter] = useState("all");

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await api.get("/echeances-3p");
        setItems(sortByUrgency(filterAlertEcheances(res.data || [])));
      } catch {
        setItems([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const counts = useMemo(() => countByUrgency(items), [items]);

  const filtered = useMemo(() => {
    return items.filter((item) => {
      if (!matchesEcheanceSearch(item, q)) return false;
      if (urgencyFilter === "all") return true;
      return getUrgency(item)?.id === urgencyFilter;
    });
  }, [items, q, urgencyFilter]);

  return (
    <Layout>
      <div className="animate-fade-up max-w-6xl">
        <div className="flex items-start justify-between flex-wrap gap-4 mb-6">
          <div>
            <button
              type="button"
              onClick={() => navigate("/agenda")}
              className="text-xs text-muted-foreground hover:text-[#002FA7] flex items-center gap-1 mb-2"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Ordre du jour
            </button>
            <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
              <Shield className="h-7 w-7 text-[#002FA7]" /> Échéances 3e pilier
            </h1>
            <p className="text-muted-foreground mt-1">
              Toutes les échéances à moins d&apos;un an, triées par priorité.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-5">
          <button
            type="button"
            onClick={() => setUrgencyFilter("all")}
            className={`text-xs px-3 py-1.5 rounded-md border transition-colors ${
              urgencyFilter === "all"
                ? "border-[#002FA7] bg-[#002FA7]/5 text-[#002FA7] font-medium"
                : "border-border hover:bg-secondary"
            }`}
          >
            Toutes · {items.length}
          </button>
          {URGENCY_ORDER.map((id) => {
            const u = URGENCY[id];
            const n = counts[id] || 0;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setUrgencyFilter(id)}
                className={`text-xs px-3 py-1.5 rounded-md border transition-colors flex items-center gap-1.5 ${
                  urgencyFilter === id
                    ? `${u.badge} font-medium`
                    : "border-border hover:bg-secondary"
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${u.dot}`} />
                {n} {u.short}
              </button>
            );
          })}
        </div>

        <Card className="p-4 mb-4">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              data-testid="echeances-3p-search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Rechercher un client, une compagnie, un n° de police…"
              className="pl-10"
            />
          </div>
        </Card>

        <Card className="p-0 overflow-hidden">
          {loading ? (
            <p className="text-sm text-muted-foreground p-8 text-center">Chargement…</p>
          ) : (
            <Echeances3PTable
              items={filtered}
              emptyLabel={q || urgencyFilter !== "all" ? "Aucun résultat pour ces filtres." : "Aucune échéance dans l'année."}
            />
          )}
        </Card>

        <div className="mt-4 flex justify-end">
          <Button variant="outline" onClick={() => navigate("/agenda")}>
            Retour à l&apos;ordre du jour
          </Button>
        </div>
      </div>
    </Layout>
  );
}
