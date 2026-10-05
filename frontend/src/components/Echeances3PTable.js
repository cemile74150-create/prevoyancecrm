import React from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  clientLabel,
  formatEcheanceDate,
  formatDaysLeft,
  getDaysLeft,
  getUrgency,
  echeanceRowKey,
} from "@/lib/echeances3p";
import { ExternalLink } from "lucide-react";

export default function Echeances3PTable({ items = [], emptyLabel = "Aucune échéance." }) {
  const navigate = useNavigate();

  if (!items.length) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">{emptyLabel}</p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full text-sm">
        <thead className="bg-secondary/60 text-left">
          <tr>
            <th className="px-3 py-2.5 font-medium text-muted-foreground whitespace-nowrap w-8" />
            <th className="px-3 py-2.5 font-medium text-muted-foreground">Client</th>
            <th className="px-3 py-2.5 font-medium text-muted-foreground">Compagnie</th>
            <th className="px-3 py-2.5 font-medium text-muted-foreground">Police</th>
            <th className="px-3 py-2.5 font-medium text-muted-foreground whitespace-nowrap">Échéance</th>
            <th className="px-3 py-2.5 font-medium text-muted-foreground whitespace-nowrap">Délai</th>
            <th className="px-3 py-2.5 font-medium text-muted-foreground text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((e, idx) => {
            const urgency = getUrgency(e);
            const days = getDaysLeft(e);
            const cid = e.client_id || e.id;
            return (
              <tr
                key={echeanceRowKey(e, idx)}
                data-testid={`echeance-3p-row-${cid}-${idx}`}
                className={`border-t border-border hover:bg-secondary/40 transition-colors ${urgency?.row || ""}`}
              >
                <td className="px-3 py-2.5">
                  {urgency && (
                    <span
                      title={urgency.hint}
                      className={`inline-block h-2.5 w-2.5 rounded-full ${urgency.dot}`}
                    />
                  )}
                </td>
                <td className="px-3 py-2.5 font-medium">
                  <button
                    type="button"
                    onClick={() => cid && navigate(`/clients/${cid}`)}
                    className="hover:text-[#002FA7] text-left"
                  >
                    {clientLabel(e)}
                  </button>
                  {e.numero_dossier && (
                    <p className="text-[11px] text-muted-foreground font-normal">{e.numero_dossier}</p>
                  )}
                </td>
                <td className="px-3 py-2.5 text-muted-foreground">{e.company || "—"}</td>
                <td className="px-3 py-2.5 font-mono text-xs">{e.policy_number || "—"}</td>
                <td className="px-3 py-2.5 whitespace-nowrap tabular-nums">
                  {formatEcheanceDate(e.echeance_3p)}
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  {urgency ? (
                    <span className={`inline-flex text-[11px] font-medium px-2 py-0.5 rounded border ${urgency.badge}`}>
                      {formatDaysLeft(days)}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">{formatDaysLeft(days)}</span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1.5 text-xs"
                    onClick={() => cid && navigate(`/clients/${cid}`)}
                    data-testid={`echeance-3p-open-${cid}-${idx}`}
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Ouvrir
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
