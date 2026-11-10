import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ClipboardCheck, Loader2, Lock } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { eligibilityErrorMessage, setListChecked } from "@/lib/eligibility";
import { fetchClientEligibility, saveClientEligibility } from "@/lib/eligibilityApi";
import { formatDateFr } from "@/lib/dates";

export default function EligibilityClientTab({ clientId }) {
  const [lists, setLists] = useState([]);
  const [canEdit, setCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState({});
  const pendingRef = useRef({});

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!clientId) return;
    if (!silent) setLoading(true);
    try {
      const data = await fetchClientEligibility(clientId);
      if (Object.keys(pendingRef.current).length) return;
      setLists(Array.isArray(data?.lists) ? data.lists : []);
      setCanEdit(Boolean(data?.can_edit));
      setError("");
    } catch (e) {
      if (!silent) setError(eligibilityErrorMessage(e, "Éligibilité indisponible pour ce dossier."));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") load({ silent: true });
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  const toggle = async (list, checked) => {
    if (!canEdit || pendingRef.current[list.id]) return;
    pendingRef.current = { ...pendingRef.current, [list.id]: true };
    setPending(pendingRef.current);
    setLists((prev) => setListChecked(prev, list.id, checked));
    try {
      await saveClientEligibility(clientId, list.id, checked);
      toast.success(checked ? `Ajouté à « ${list.name} »` : `Retiré de « ${list.name} »`);
    } catch (e) {
      setLists((prev) => setListChecked(prev, list.id, !checked));
      toast.error(eligibilityErrorMessage(e, "Enregistrement impossible. La case a été remise à son état précédent."));
    } finally {
      const { [list.id]: _done, ...rest } = pendingRef.current;
      pendingRef.current = rest;
      setPending(rest);
    }
  };

  return (
    <Card className="p-6 space-y-5" data-testid="eligibility-tab">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display font-bold text-lg flex items-center gap-2">
            <ClipboardCheck className="h-5 w-5 text-[#002FA7]" />
            Éligibilité
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Cochez les listes auxquelles ce client est éligible. Chaque case est enregistrée immédiatement.
          </p>
        </div>
        {!loading && !error && !canEdit && (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground border border-border rounded-full px-2.5 py-1 shrink-0">
            <Lock className="h-3 w-3" /> Lecture seule
          </span>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
        </p>
      ) : error ? (
        <p className="text-sm text-amber-800">{error}</p>
      ) : lists.length === 0 ? (
        <p className="text-sm text-muted-foreground border border-dashed border-border rounded-md py-6 text-center">
          Aucune liste d'éligibilité active pour le moment.
        </p>
      ) : (
        <ul className="divide-y divide-border border border-border rounded-md">
          {lists.map((list) => {
            const inputId = `eligibility-${list.id}`;
            const busy = Boolean(pending[list.id]);
            return (
              <li key={list.id} className="flex items-center gap-3 px-4 py-3">
                <Checkbox
                  id={inputId}
                  data-testid={`eligibility-checkbox-${list.id}`}
                  checked={Boolean(list.checked)}
                  disabled={!canEdit || busy}
                  onCheckedChange={(v) => toggle(list, v === true)}
                />
                <label htmlFor={inputId} className={`flex-1 min-w-0 text-sm ${canEdit ? "cursor-pointer" : ""}`}>
                  <span className="font-medium">{list.name}</span>
                  {list.checked && list.added_at && (
                    <span className="block text-xs text-muted-foreground mt-0.5">
                      Ajouté le {formatDateFr(list.added_at)}
                      {list.added_by_name ? ` par ${list.added_by_name}` : ""}
                    </span>
                  )}
                </label>
                {busy && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                <Link
                  to={`/eligibilite/${list.id}`}
                  className="text-xs text-[#002FA7] hover:underline shrink-0"
                >
                  Voir la liste
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
