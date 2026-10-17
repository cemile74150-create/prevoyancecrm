import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import LamalShell, { StatusBadge, formatChf } from "./LamalShell";

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/lamal/dashboard")
      .then((res) => setData(res.data))
      .catch((error) => toast.error(error?.response?.data?.detail || "Tableau de bord indisponible"))
      .finally(() => setLoading(false));
  }, []);

  const cards = [
    ["Clients domiciliés en Suisse", data?.swiss_clients],
    ["Clients analysés", data?.analysed],
    ["Dossiers incomplets", data?.incomplete],
    ["Économies potentielles", data?.with_savings],
    ["Économies annuelles cumulées", data?.savings_year_total == null ? "—" : `${formatChf(data.savings_year_total)} CHF`],
    ["E-mails prêts", data?.emails_ready],
    ["E-mails envoyés", data?.emails_sent],
    ["Suivis en cours", data?.followed],
  ];

  return (
    <LamalShell
      title="Comparateur LAMal"
      subtitle="Primes 2027 de l'assurance obligatoire des soins, pour les personnes domiciliées en Suisse. Les montants proviennent des fichiers officiels de l'OFSP."
    >
      {loading ? <p className="text-sm text-muted-foreground">Chargement des indicateurs…</p> : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {cards.map(([label, value]) => (
              <Card key={label} className="p-4">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="font-display font-black text-2xl mt-2">{value ?? "—"}</p>
              </Card>
            ))}
          </div>
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => navigate("/lamal/comparaison")}>Nouvelle comparaison</Button>
          </div>
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-secondary/60 text-left">
                <tr>
                  {["Client", "Commune", "Caisse actuelle", "Économie annuelle", "Statut"].map((label) => (
                    <th key={label} className="px-4 py-3 font-medium">{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.items || []).map((row) => (
                  <tr key={row.id} className="border-t border-border">
                    <td className="px-4 py-3">{row.prenom} {row.nom}</td>
                    <td className="px-4 py-3">{row.commune || "À compléter"}</td>
                    <td className="px-4 py-3">{row.insurer || "À compléter"}</td>
                    <td className="px-4 py-3">{row.savings_year ? `${formatChf(row.savings_year)} CHF` : "—"}</td>
                    <td className="px-4 py-3"><StatusBadge status={row.status} label={row.status_label} /></td>
                  </tr>
                ))}
                {!data?.items?.length && (
                  <tr><td colSpan={5} className="px-4 py-8 text-muted-foreground">Aucun client domicilié en Suisse à afficher pour le moment.</td></tr>
                )}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </LamalShell>
  );
}
