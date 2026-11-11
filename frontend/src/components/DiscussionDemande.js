import React, { useCallback, useEffect, useRef, useState } from "react";
import api, { openAuthenticatedBlob } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTimeFr } from "@/lib/demandesOffres";
import {
  DISCUSSION_ACCEPT,
  canSendDiscussion,
  mergeDiscussionFiles,
} from "@/lib/discussionDemande";
import { FileText, Loader2, MessageSquare, Paperclip, Send, X } from "lucide-react";
import { toast } from "sonner";

const ROLE_STYLE = {
  agent: "border-sky-200 bg-sky-50 text-sky-900",
  gestionnaire: "border-violet-200 bg-violet-50 text-violet-900",
};

const MARQUER_LU_APRES_MS = 3000;

function MessageDocs({ documents }) {
  const list = Array.isArray(documents) ? documents.filter((d) => d?.id) : [];
  if (!list.length) return null;
  return (
    <ul className="mt-2 space-y-1" data-testid="discussion-message-docs">
      {list.map((doc) => (
        <li key={doc.id}>
          <button
            type="button"
            className="flex max-w-full items-center gap-1.5 text-left text-xs text-[#002FA7] hover:underline"
            title="Télécharger"
            onClick={() => openAuthenticatedBlob(`/demandes-offres/documents/${doc.id}/download`)}
          >
            <FileText className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{doc.original_filename || "Document"}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Fil agent / gestionnaire d'une demande d'offre (texte + pièces jointes). */
export default function DiscussionDemande({ demandeId }) {
  const [messages, setMessages] = useState([]);
  const [nonLus, setNonLus] = useState(0);
  const [peutEcrire, setPeutEcrire] = useState(false);
  const [loading, setLoading] = useState(true);
  const [texte, setTexte] = useState("");
  const [files, setFiles] = useState([]);
  const [erreur, setErreur] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef(null);
  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/demandes-offres/${demandeId}/messages`, { params: { marquer_lu: false } });
      setMessages(res.data?.messages || []);
      setNonLus(Number(res.data?.non_lus) || 0);
      setPeutEcrire(Boolean(res.data?.peut_ecrire));
    } catch {
      setMessages([]);
      setPeutEcrire(false);
    } finally {
      setLoading(false);
    }
  }, [demandeId]);

  useEffect(() => { load(); }, [load]);

  // Le badge reste affiché pendant la visite ; la lecture n'est enregistrée qu'après affichage effectif.
  useEffect(() => {
    if (!nonLus) return undefined;
    const timer = setTimeout(() => {
      api.get(`/demandes-offres/${demandeId}/messages`, { params: { marquer_lu: true } }).catch(() => {});
    }, MARQUER_LU_APRES_MS);
    return () => clearTimeout(timer);
  }, [nonLus, demandeId]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages]);

  const onPickFiles = (incoming) => {
    const { files: next, errors } = mergeDiscussionFiles(files, incoming);
    setFiles(next);
    if (errors.length) {
      toast.error(errors[0]);
      setErreur(errors[0]);
    } else if (erreur) {
      setErreur("");
    }
  };

  const envoyer = async () => {
    if (busy) return;
    if (!canSendDiscussion(texte, files)) {
      setErreur("Écrivez un message ou joignez un document.");
      return;
    }
    setErreur("");
    setBusy(true);
    try {
      let res;
      if (files.length > 0) {
        const fd = new FormData();
        fd.append("contenu", texte);
        files.forEach((file) => fd.append("documents", file));
        res = await api.post(`/demandes-offres/${demandeId}/messages`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      } else {
        res = await api.post(`/demandes-offres/${demandeId}/messages`, { contenu: texte });
      }
      setMessages(res.data?.messages || []);
      setTexte("");
      setFiles([]);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Envoi impossible");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5 space-y-3" data-testid="discussion-demande">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display font-bold flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-[#002FA7]" /> Fil de discussion
        </h2>
        {nonLus > 0 && (
          <span className="rounded-full bg-[#002FA7] px-2 py-0.5 text-[11px] font-semibold text-white" data-testid="discussion-non-lus">
            {nonLus} nouveau{nonLus > 1 ? "x" : ""} message{nonLus > 1 ? "s" : ""}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">Échanges entre l&apos;agent et le service Offres sur cette demande.</p>
      {loading ? (
        <p className="text-sm text-muted-foreground"><Loader2 className="inline h-4 w-4 animate-spin mr-1" /> Chargement…</p>
      ) : messages.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="discussion-vide">Aucun message pour l&apos;instant.</p>
      ) : (
        <ol ref={listRef} className="max-h-96 space-y-2 overflow-y-auto pr-1" data-testid="discussion-messages">
          {messages.map((m) => (
            <li key={m.id} className={`flex ${m.mine ? "justify-end" : "justify-start"}`}>
              <div className={`w-full max-w-[85%] rounded-md border px-3 py-2 text-sm ${ROLE_STYLE[m.expediteur_role] || ROLE_STYLE.agent}`}>
                <p className="text-[11px] font-semibold">
                  {m.expediteur_nom} · {m.expediteur_role_label}
                </p>
                <p className="mt-1 whitespace-pre-wrap break-words text-slate-900">{m.contenu}</p>
                <MessageDocs documents={m.documents} />
                <p className="mt-1 text-[10px] text-slate-500">{formatDateTimeFr(m.created_at)}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
      {peutEcrire && (
        <div className="space-y-2">
          <Textarea
            rows={3}
            value={texte}
            onChange={(e) => { setTexte(e.target.value); if (erreur) setErreur(""); }}
            placeholder="Écrire un message…"
            data-testid="discussion-saisie"
          />
          {files.length > 0 && (
            <ul className="space-y-1" data-testid="discussion-pj-pending">
              {files.map((file, index) => (
                <li
                  key={`${file.name}-${file.size}-${index}`}
                  className="flex items-center justify-between gap-2 rounded-md border bg-slate-50 px-2 py-1 text-xs"
                >
                  <span className="min-w-0 truncate flex items-center gap-1.5">
                    <Paperclip className="h-3.5 w-3.5 shrink-0 text-[#002FA7]" />
                    {file.name}
                  </span>
                  <button
                    type="button"
                    className="shrink-0 text-rose-700 hover:underline"
                    onClick={() => setFiles((prev) => prev.filter((_, i) => i !== index))}
                    aria-label={`Retirer ${file.name}`}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {erreur && <p className="text-xs text-rose-700" data-testid="discussion-erreur">{erreur}</p>}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={DISCUSSION_ACCEPT}
                className="hidden"
                data-testid="discussion-joindre-input"
                onChange={(e) => {
                  onPickFiles(Array.from(e.target.files || []));
                  e.target.value = "";
                }}
              />
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                className="border-slate-300"
                data-testid="discussion-joindre"
                onClick={() => fileInputRef.current?.click()}
              >
                <Paperclip className="h-4 w-4 mr-2 text-[#002FA7]" />
                Joindre
              </Button>
            </div>
            <Button
              onClick={envoyer}
              disabled={busy || !canSendDiscussion(texte, files)}
              className="bg-[#002FA7] hover:bg-[#00248a]"
              data-testid="discussion-envoyer"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
              Envoyer
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
