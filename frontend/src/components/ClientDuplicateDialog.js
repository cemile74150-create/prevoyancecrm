import React from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { DUPLICATE_CLIENT_MESSAGE, clientDossierPath } from "@/lib/clientDuplicate";

/**
 * Dialogue affiché quand la création client est refusée (HTTP 409).
 */
export default function ClientDuplicateDialog({ open, onOpenChange, conflict, onOpenExisting }) {
  const navigate = useNavigate();
  const existing = conflict?.existing || null;
  const message = conflict?.message || DUPLICATE_CLIENT_MESSAGE;

  const openDossier = () => {
    if (!existing?.id) return;
    onOpenChange?.(false);
    if (onOpenExisting) {
      onOpenExisting(existing);
      return;
    }
    navigate(clientDossierPath(existing));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="client-duplicate-dialog">
        <DialogHeader>
          <DialogTitle className="font-display tracking-tight">Client déjà existant</DialogTitle>
          <DialogDescription className="text-sm leading-relaxed pt-1">
            {message}
          </DialogDescription>
        </DialogHeader>

        {existing && (
          <div className="rounded-md border bg-muted/40 px-4 py-3 space-y-1.5 text-sm">
            <div>
              <span className="text-muted-foreground">Nom : </span>
              <span className="font-medium">{existing.name || `${existing.prenom || ""} ${existing.nom || ""}`.trim() || "—"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">N° dossier : </span>
              <span className="font-medium">{existing.numero_dossier || "—"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Conseiller : </span>
              <span className="font-medium">{existing.conseiller || "—"}</span>
            </div>
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={() => onOpenChange?.(false)}>
            Fermer
          </Button>
          {existing?.id && (
            <Button
              type="button"
              className="bg-[#002FA7] hover:bg-[#00248a]"
              onClick={openDossier}
              data-testid="open-existing-dossier-btn"
            >
              Ouvrir le dossier
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
