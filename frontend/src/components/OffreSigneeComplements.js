import React, { useEffect, useState } from "react";
import api, { openAuthenticatedBlob } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FilePicker } from "@/components/TransmettreOffreDialogs";
import { formatDateFr } from "@/lib/demandesOffres";
import { mergeSignatureFiles, signatureEntries } from "@/lib/offreSignee";
import { FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";

function DocLink({ doc }) {
  return (
    <button
      type="button"
      className="flex w-full min-w-0 items-center gap-1.5 text-left text-[#002FA7] hover:underline"
      title="Ouvrir"
      onClick={() => openAuthenticatedBlob(`/demandes-offres/documents/${doc.id}/download`)}
    >
      <FileText className="h-3 w-3 shrink-0" />
      <span className="truncate">{doc.original_filename || "Document"}</span>
    </button>
  );
}

/** Commentaires et pièces liés à la signature, visibles agent et gestionnaire. */
export function OffreSigneeDetails({ demande }) {
  const entries = signatureEntries(demande?.signature);
  if (!entries.length) return null;
  return (
    <ul className="space-y-2 pt-1" data-testid="offre-signee-details">
      {entries.map((entry) => (
        <li key={entry.key} className="rounded-md border border-emerald-200 bg-white p-2 space-y-1">
          <p className="text-[11px] text-slate-500">
            {entry.initial ? "À la signature" : "Complément"}
            {entry.at ? ` · ${formatDateFr(entry.at)}` : ""}
            {entry.by ? ` · ${entry.by}` : ""}
          </p>
          {entry.commentaire ? (
            <p className="whitespace-pre-wrap text-xs text-slate-800">{entry.commentaire}</p>
          ) : null}
          {entry.documents.length > 0 && (
            <div className="space-y-0.5 text-xs">
              {entry.documents.map((doc) => <DocLink key={doc.id} doc={doc} />)}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Après « Offre signée » : l'agent ajoute des documents et/ou un commentaire. */
export function ComplementSignatureDialog({ open, onOpenChange, demandeId, onSaved }) {
  const [files, setFiles] = useState([]);
  const [commentaire, setCommentaire] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setFiles([]);
      setCommentaire("");
    }
  }, [open]);

  const canSave = files.length > 0 || commentaire.trim().length > 0;

  const save = async () => {
    if (!canSave) return;
    const fd = new FormData();
    if (commentaire.trim()) fd.append("commentaire", commentaire.trim());
    files.forEach((file) => fd.append("documents", file));
    setBusy(true);
    try {
      const res = await api.post(`/demandes-offres/${demandeId}/signature/complements`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onSaved?.(res.data);
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Enregistrement impossible");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Compléter l&apos;offre signée</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Documents</p>
            <FilePicker
              files={files}
              onAdd={(incoming) => setFiles((prev) => mergeSignatureFiles(prev, incoming))}
              onRemove={(index) => setFiles((prev) => prev.filter((_, i) => i !== index))}
              testId="complement-signature-files"
              label="Ajouter des documents"
            />
          </div>
          <div className="space-y-1.5">
            <p className="text-sm font-medium">Commentaire</p>
            <Textarea
              value={commentaire}
              onChange={(e) => setCommentaire(e.target.value)}
              placeholder="Information utile pour le gestionnaire…"
              data-testid="complement-signature-commentaire"
            />
          </div>
          <p className="text-[11px] text-muted-foreground">
            Ajoutez au moins un document ou un commentaire. Visible par le gestionnaire et conservé dans l&apos;historique.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button
            className="bg-emerald-700 hover:bg-emerald-800"
            onClick={save}
            disabled={busy || !canSave}
            data-testid="confirm-complement-signature-btn"
          >
            {busy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
            Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
