import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/context/AuthContext";
import {
  aUnePlanificationActive,
  planificationsDuClient,
} from "@/lib/planificationClient";
import { Calculator, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

const STATUS_LABELS = {
  brouillon: "Brouillon",
  calculee: "Calculée",
  finalisee: "Finalisée",
  annulee: "Annulée",
};

function formatDateTimeFr(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const day = new Intl.DateTimeFormat("fr-CH", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
  const time = new Intl.DateTimeFormat("fr-CH", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
  return `${day} à ${time}`;
}

/**
 * Liste les planifications déjà enregistrées pour cet identifiant client
 * et ouvre le module existant. La création reprend la fiche et le conjoint lié.
 */
export default function PlanificationClientTab({ client }) {
  const navigate = useNavigate();
  const { hasPerm } = useAuth();
  const canEdit = hasPerm("analyses.edit");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const clientId = client?.id;

  useEffect(() => {
    if (!clientId) return undefined;
    let cancelled = false;
    setLoading(true);
    api
      .get("/analyses-prevoyance", { params: { clientId } })
      .then((res) => {
        if (cancelled) return;
        setItems(planificationsDuClient(res.data?.items || [], clientId));
      })
      .catch((err) => {
        if (cancelled) return;
        const detail = err?.response?.data?.detail;
        toast.error(typeof detail === "string" ? detail : "Impossible de charger les planifications");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  function openPlanification(id) {
    if (!id) return;
    navigate(`/effectuer-une-analyse/${id}`);
  }

  async function createPlanification() {
    if (!clientId || creating) return;
    setCreating(true);
    try {
      const res = await api.post("/analyses-prevoyance", { clientId });
      navigate(`/effectuer-une-analyse/${res.data.id}`);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const analyseId = detail?.analyseId;
      if (err?.response?.status === 409 && analyseId) {
        navigate(`/effectuer-une-analyse/${analyseId}`);
        return;
      }
      const message = typeof detail === "string" ? detail : detail?.message;
      toast.error(message || "Création impossible");
      setCreating(false);
    }
  }

  const spouseLinked = Boolean(client?.linked_spouse_id);
  const canCreate = !aUnePlanificationActive(items);

  return (
    <Card className="p-6 space-y-4" data-testid="client-tab-planification">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="text-sm font-semibold text-[#002FA7]">Planification</p>
          <p className="text-xs text-muted-foreground mt-1 max-w-xl">
            {client?.prenom} {client?.nom} est déjà sélectionné. La planification s’ouvre dans le module existant, sans nouvelle recherche.
            {spouseLinked
              ? " Le conjoint rattaché à cette fiche est repris comme dans une planification créée depuis LeoSoft."
              : " Aucun conjoint n’est rattaché à cette fiche."}
          </p>
        </div>
        {!loading && canCreate && (
          <Button
            size="sm"
            onClick={createPlanification}
            disabled={!canEdit || creating}
            data-testid="create-planification-btn"
            className="h-8 gap-1.5 bg-[#002FA7] hover:bg-[#00248a]"
          >
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Créer une planification
          </Button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement des planifications…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="planification-empty">
          Aucune planification pour ce client. Créer une planification reprend le prénom, le nom et les informations déjà connues.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((row) => (
            <li
              key={row.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border px-3 py-2"
              data-testid={`planification-row-${row.id}`}
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">{row.clientName || `${client?.prenom || ""} ${client?.nom || ""}`.trim()}</p>
                <p className="text-xs text-muted-foreground">
                  {STATUS_LABELS[row.status] || row.status || "Brouillon"}
                  {" · "}
                  {formatDateTimeFr(row.updatedAt)}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 border-[#002FA7] text-[#002FA7]"
                onClick={() => openPlanification(row.id)}
                data-testid={`open-planification-${row.id}`}
              >
                <Calculator className="h-4 w-4" />
                Ouvrir
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
