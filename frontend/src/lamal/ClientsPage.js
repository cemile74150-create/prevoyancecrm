import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { downloadAuthenticatedBlob } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import LamalShell, { StatusBadge, formatChf } from "./LamalShell";

export default function ClientsPage() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [canton, setCanton] = useState("");
  const [status, setStatus] = useState("");
  const navigate = useNavigate();

  const load = useCallback(() => {
    api.get("/lamal/clients", { params: { q, canton, status, year: 2027 } })
      .then((res) => setItems(res.data.items || []))
      .catch((error) => toast.error(error?.response?.data?.detail || "Liste indisponible"));
  }, [q, canton, status]);

  useEffect(() => { load(); }, [load]);

  return (
    <LamalShell title="Comparaisons clients" subtitle="Seuls les clients domiciliés en Suisse apparaissent. Les personnes domiciliées en France sont exclues.">
      <div className="flex flex-wrap gap-2">
        <Input className="max-w-xs" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nom, commune, identifiant" />
        <Input className="max-w-[120px]" value={canton} onChange={(e) => setCanton(e.target.value.toUpperCase())} placeholder="Canton" />
        <select className="h-10 rounded-md border px-3 text-sm bg-white" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Tous les statuts</option>
          <option value="informations_manquantes">Informations manquantes</option>
          <option value="pret_pour_analyse">Prêt pour analyse</option>
          <option value="economie_identifiee">Économie identifiée</option>
          <option value="aucune_economie">Aucune économie identifiée</option>
          <option value="email_a_valider">E-mail à valider</option>
        </select>
        <Button variant="outline" onClick={load}>Filtrer</Button>
        <Button variant="outline" onClick={() => downloadAuthenticatedBlob("/lamal/export.xlsx?year=2027", "lamal-comparaisons-2027.xlsx")}>Export Excel</Button>
      </div>
      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-secondary/60 text-left">
            <tr>{["Client", "Commune", "Caisse actuelle", "Économie annuelle", "Statut", ""].map((label) => <th key={label} className="px-4 py-3 font-medium">{label}</th>)}</tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.id} className="border-t">
                <td className="px-4 py-3">{row.prenom} {row.nom}</td>
                <td className="px-4 py-3">{row.commune || "À compléter"}</td>
                <td className="px-4 py-3">{row.insurer || "À compléter"}</td>
                <td className="px-4 py-3">{row.savings_year ? `${formatChf(row.savings_year)} CHF` : "—"}</td>
                <td className="px-4 py-3"><StatusBadge status={row.status} label={row.status_label} /></td>
                <td className="px-4 py-3 text-right">
                  <button className="text-[#002FA7] text-sm" type="button" onClick={() => navigate(`/lamal/comparaison?client=${row.id}`)}>Comparer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </LamalShell>
  );
}
