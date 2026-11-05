import React, { useEffect, useRef, useState } from "react";
import { Loader2, Mail, Paperclip, Send, X } from "lucide-react";
import { toast } from "sonner";
import api, { downloadAuthenticatedBlob, openAuthenticatedBlob } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTimeFr } from "@/lib/demandesOffres";
import {
  appendFiles,
  replaceFileAt,
  replyBlockReason,
  withoutFileAt,
} from "@/lib/complementsOffre";

const STATUS_STYLE = {
  en_attente: "border-amber-300 bg-amber-50 text-amber-950",
  reponse_recue: "border-emerald-300 bg-emerald-50 text-emerald-900",
  cloturee: "border-slate-200 bg-slate-100 text-slate-700",
};

function errorDetail(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback;
}

function DocumentLinks({ documents, title, downloadLabel = "Télécharger" }) {
  if (!documents?.length) return null;
  return (
    <div className="mt-2">
      {title ? <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p> : null}
      <ul className={`${title ? "mt-1" : ""} space-y-1`}>
        {documents.map((doc) => (
          <li key={doc.id} className="flex items-center justify-between gap-2 rounded-md border bg-white px-2 py-1.5">
            <span className="min-w-0 truncate text-sm flex items-center gap-1.5">
              <Paperclip className="h-3.5 w-3.5 shrink-0 text-[#002FA7]" />
              {doc.original_filename || "Document"}
            </span>
            <span className="flex shrink-0 gap-1">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => openAuthenticatedBlob(`/demandes-offres/documents/${doc.id}/download`)}
              >
                Ouvrir
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => downloadAuthenticatedBlob(
                  `/demandes-offres/documents/${doc.id}/download`,
                  doc.original_filename,
                )}
              >
                {downloadLabel}
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReplyForm({ note, demandeId, onUpdated, onCancel }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const lock = useRef(false);
  const reason = replyBlockReason(note, text, files);

  const submit = async () => {
    if (lock.current) return;
    const blocked = replyBlockReason(note, text, files);
    if (blocked) {
      toast.error(blocked);
      return;
    }
    lock.current = true;
    setSubmitting(true);
    try {
      const body = new FormData();
      body.append("commentaire", text.trim());
      files.forEach((file) => body.append("files", file));
      const res = await api.post(
        `/demandes-offres/${demandeId}/complements/${note.id}/reponse`,
        body,
      );
      onUpdated(res.data);
      if (res.data?.complement_email_sent) {
        toast.success("Réponse transmise");
      } else {
        toast.success("Réponse transmise");
        toast.warning("La réponse est enregistrée, mais l'e-mail au service des offres n'a pas été envoyé", {
          description: String(res.data?.complement_email_error || "Notification e-mail indisponible").slice(0, 200),
        });
      }
    } catch (error) {
      const status = error?.response?.status;
      toast.error(errorDetail(error, "Transmission impossible"));
      if (status === 409) {
        try {
          const fresh = await api.get(`/demandes-offres/${demandeId}`);
          onUpdated(fresh.data);
        } catch {
          /* la fiche sera rechargée par l'utilisateur */
        }
      }
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className="mt-3 space-y-3 rounded-md border border-[#002FA7]/20 bg-[#002FA7]/5 p-3" data-testid="complement-reply-form">
      <p className="text-sm font-medium text-[#002FA7]">
        {note?.retour_document ? "Déposer le document complété" : "Votre réponse"}
      </p>
      <Textarea
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Votre réponse (texte et/ou documents)…"
        disabled={submitting}
        data-testid="complement-reply-text"
      />
      <div>
        <p className="text-sm font-medium">
          {note?.retour_document ? "Déposer le document complété" : "Joindre des documents (facultatif)"}
        </p>
        <label className="mt-1 inline-flex cursor-pointer items-center gap-2 rounded-md border bg-white px-3 py-2 text-sm">
          <Paperclip className="h-4 w-4" />
          Choisir des fichiers
          <input
            type="file"
            multiple
            className="hidden"
            disabled={submitting}
            data-testid="complement-reply-files"
            onChange={(e) => {
              setFiles((prev) => appendFiles(prev, e.target.files));
              e.target.value = "";
            }}
          />
        </label>
        {files.length > 0 && (
          <ul className="mt-2 space-y-1">
            {files.map((file, index) => (
              <li key={`${file.name}-${file.size}-${index}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-white px-2 py-1.5 text-sm">
                <span className="min-w-0 truncate">{file.name}</span>
                <span className="flex gap-2">
                  <label className="cursor-pointer text-[#002FA7]">
                    Remplacer
                    <input
                      type="file"
                      className="hidden"
                      disabled={submitting}
                      onChange={(e) => {
                        const next = e.target.files?.[0];
                        if (next) setFiles((prev) => replaceFileAt(prev, index, next));
                        e.target.value = "";
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="text-rose-700"
                    disabled={submitting}
                    onClick={() => setFiles((prev) => withoutFileAt(prev, index))}
                  >
                    Retirer
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>Annuler</Button>
        <Button
          type="button"
          className="bg-[#002FA7] hover:bg-[#00248a]"
          onClick={submit}
          disabled={submitting || Boolean(reason)}
          data-testid="complement-reply-submit"
        >
          {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          {note?.retour_document ? "Soumettre le document" : "Transmettre ma réponse"}
        </Button>
      </div>
    </div>
  );
}

export function PendingComplementBadge({ count }) {
  const n = Number(count) || 0;
  if (n <= 0) return null;
  return (
    <span
      className="inline-flex items-center rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-950"
      data-testid="complements-pending-badge"
    >
      {n} réponse{n > 1 ? "s" : ""} en attente
    </span>
  );
}

export default function NotesConseiller({ demandeId, notes, canProcess, focusId, onUpdated }) {
  const [openId, setOpenId] = useState(null);
  const [closingId, setClosingId] = useState(null);
  const items = Array.isArray(notes) ? [...notes].reverse() : [];

  useEffect(() => {
    if (!focusId) return;
    const note = (notes || []).find((item) => item.id === focusId);
    if (note?.can_reply) setOpenId(focusId);
    const el = document.getElementById(`complement-${focusId}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusId, notes]);

  if (!items.length) return null;

  const closeComplement = async (noteId) => {
    if (!window.confirm("Clôturer cette demande sans réponse du conseiller ?")) return;
    setClosingId(noteId);
    try {
      const res = await api.post(`/demandes-offres/${demandeId}/complements/${noteId}/cloturer`);
      onUpdated(res.data);
      toast.success("Demande clôturée");
    } catch (error) {
      toast.error(errorDetail(error, "Clôture impossible"));
    } finally {
      setClosingId(null);
    }
  };

  return (
    <Card className="space-y-3 p-5" data-testid="notes-conseiller">
      <h2 className="font-display flex items-center gap-2 font-bold">
        <Mail className="h-5 w-5 text-[#002FA7]" /> Notes envoyées au conseiller
      </h2>
      <p className="text-xs text-muted-foreground">
        Conservées dans LeoSoft et transmises par e-mail au conseiller créateur.
        Une note avec réponse attendue n&apos;autorise qu&apos;une seule réponse (texte et/ou documents).
      </p>
      <ul className="space-y-3">
        {items.map((note) => {
          const complement = note.complement;
          const pending = complement?.status === "en_attente";
          const answered = complement?.status === "reponse_recue";
          const focused = focusId && focusId === note.id;
          return (
            <li
              key={note.id}
              id={`complement-${note.id}`}
              className={`rounded-md border bg-white px-3 py-3 text-sm ${focused ? "ring-2 ring-[#002FA7]" : ""}`}
              data-testid={`complement-note-${note.id}`}
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-700">
                  {note.by_name || "Service Offres"}
                </span>
                {note.reply_expected ? (
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[complement?.status] || STATUS_STYLE.en_attente}`}>
                    {complement?.status_label || "Réponse attendue"}
                  </span>
                ) : (
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-700">
                    Note informative
                  </span>
                )}
                {note.can_reply && (
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">Action requise</span>
                )}
              </div>
              {note.retour_document ? (
                <div className="rounded-md border border-[#002FA7]/30 bg-[#002FA7]/5 p-3" data-testid="document-a-retourner">
                  <p className="text-sm font-semibold text-[#002FA7]">📎 DOCUMENT À RETOURNER</p>
                  <p className="mt-1 whitespace-pre-wrap">{note.note}</p>
                  <DocumentLinks documents={note.documents} title="Documents à compléter" downloadLabel="Télécharger le document" />
                </div>
              ) : (
                <>
                  <p className="whitespace-pre-wrap">{note.note}</p>
                  <DocumentLinks documents={note.documents} title="Pièces jointes" downloadLabel="Télécharger le document" />
                </>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                {formatDateTimeFr(note.at)}
                {note.by_name ? ` · ${note.by_name}` : ""}
                {note.email_sent && note.email_to ? ` · envoyée à ${note.email_to}` : ""}
                {note.email_sent === false ? " · e-mail non envoyé" : ""}
              </p>
              {answered && complement?.reply && (
                <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50/70 px-3 py-2" data-testid="complement-reply-readonly">
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Réponse du conseiller</p>
                  {complement.reply.text ? (
                    <p className="mt-1 whitespace-pre-wrap">{complement.reply.text}</p>
                  ) : (
                    <p className="mt-1 text-muted-foreground">Aucun commentaire — documents uniquement.</p>
                  )}
                  <DocumentLinks documents={complement.reply.documents} title="Documents joints" />
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatDateTimeFr(complement.reply.at)}
                    {complement.reply.by_name ? ` · ${complement.reply.by_name}` : ""}
                  </p>
                </div>
              )}
              {complement?.status === "cloturee" && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Clôturée{complement.closed_by ? ` par ${complement.closed_by}` : ""}
                  {complement.closed_at ? ` · ${formatDateTimeFr(complement.closed_at)}` : ""}
                </p>
              )}
              {note.can_reply && openId !== note.id && (
                <Button
                  type="button"
                  className="mt-3 bg-[#002FA7] hover:bg-[#00248a]"
                  onClick={() => setOpenId(note.id)}
                  data-testid="complement-reply-open"
                >
                  {note.retour_document ? "Déposer le document complété" : "Répondre"}
                </Button>
              )}
              {canProcess && answered ? (
                <p className="mt-2 text-xs text-slate-500">
                  Pour demander une correction, envoyez une nouvelle note externe. Le document reçu reste attaché à cette demande.
                </p>
              ) : null}
              {note.can_reply && openId === note.id && (
                <ReplyForm
                  note={note}
                  demandeId={demandeId}
                  onUpdated={(data) => {
                    setOpenId(null);
                    onUpdated(data);
                  }}
                  onCancel={() => setOpenId(null)}
                />
              )}
              {canProcess && pending && (
                <Button
                  type="button"
                  variant="outline"
                  className="mt-3"
                  disabled={closingId === note.id}
                  onClick={() => closeComplement(note.id)}
                >
                  {closingId === note.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <X className="mr-2 h-4 w-4" />}
                  Clôturer sans réponse
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
