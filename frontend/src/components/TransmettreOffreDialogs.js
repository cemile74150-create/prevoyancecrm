import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AUTRE_COMPAGNIE_VALUE, resolveCompagnieSaisie, zurichTodayIso } from "@/lib/demandesOffres";
import {
  VARIANTE_PIECES,
  emptyVariante,
  messageTransmission,
  newClientToken,
  parseNbVariantes,
  resizeVariantes,
  traitementFormData,
  traitementManquantes,
  variantesFormData,
  variantesManquantes,
} from "@/lib/transmissionOffre";
import { AlertTriangle, Loader2, Paperclip, Send } from "lucide-react";
import { toast } from "sonner";

function errorDetail(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback;
}

function FieldBlock({ label, required, children, className = "" }) {
  return (
    <div className={`space-y-1.5 ${className}`}>
      <p className="text-sm font-medium">{label}{required ? <span className="text-rose-600"> *</span> : null}</p>
      {children}
    </div>
  );
}

function CompagnieField({ options, value, autre, onChange, onAutre, testId }) {
  return (
    <FieldBlock label="Compagnie d'assurance" required>
      <Select value={value || "__none"} onValueChange={(v) => onChange(v === "__none" ? "" : v)}>
        <SelectTrigger data-testid={testId}><SelectValue placeholder="Sélectionner" /></SelectTrigger>
        <SelectContent>
          <SelectItem value="__none">Sélectionner</SelectItem>
          {options.map((name) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
          <SelectItem value={AUTRE_COMPAGNIE_VALUE}>Autre compagnie…</SelectItem>
        </SelectContent>
      </Select>
      {value === AUTRE_COMPAGNIE_VALUE && (
        <Input className="mt-2" value={autre} placeholder="Nom de la compagnie" onChange={(e) => onAutre(e.target.value)} />
      )}
    </FieldBlock>
  );
}

export function FilePicker({ files, onAdd, onRemove, testId, label = "Choisir un fichier" }) {
  return (
    <div className="space-y-1.5">
      <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border bg-white px-3 py-1.5 text-sm hover:bg-slate-50">
        <Paperclip className="h-4 w-4 text-[#002FA7]" />
        {label}
        <input
          type="file"
          multiple
          className="hidden"
          data-testid={testId}
          onChange={(e) => {
            const incoming = Array.from(e.target.files || []);
            if (incoming.length) onAdd(incoming);
            e.target.value = "";
          }}
        />
      </label>
      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.size}-${index}`} className="flex items-center justify-between gap-2 rounded-md border bg-white px-2 py-1 text-xs">
              <span className="min-w-0 truncate">{file.name}</span>
              <button type="button" className="shrink-0 text-rose-700" onClick={() => onRemove(index)}>Retirer</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Réponses compagnies : compagnie, date de réception, N variantes (Offre, CGA, Autre document). */
export function TransmettreVariantesDialog({ open, onOpenChange, demandeId, compagnieInitiale, companyOptions, onTransmitted }) {
  const [compagnie, setCompagnie] = useState("");
  const [autre, setAutre] = useState("");
  const [dateReception, setDateReception] = useState(zurichTodayIso());
  const [nbInput, setNbInput] = useState("1");
  const [nbError, setNbError] = useState("");
  const [variantes, setVariantes] = useState([emptyVariante()]);
  const [pendingShrink, setPendingShrink] = useState(null);
  const [errors, setErrors] = useState([]);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");

  useEffect(() => {
    if (!open) return;
    setCompagnie(compagnieInitiale && companyOptions.includes(compagnieInitiale) ? compagnieInitiale : (compagnieInitiale ? AUTRE_COMPAGNIE_VALUE : ""));
    setAutre(compagnieInitiale && !companyOptions.includes(compagnieInitiale) ? compagnieInitiale : "");
    setDateReception(zurichTodayIso());
    setNbInput("1");
    setNbError("");
    setVariantes([emptyVariante()]);
    setPendingShrink(null);
    setErrors([]);
    setToken(newClientToken());
  }, [open, compagnieInitiale]); // eslint-disable-line react-hooks/exhaustive-deps

  const changeNb = (raw) => {
    setNbInput(raw);
    const n = parseNbVariantes(raw);
    if (n === null) {
      setNbError("Indiquez un nombre entier positif (1 à 20).");
      return;
    }
    setNbError("");
    if (n === variantes.length) {
      setPendingShrink(null);
      return;
    }
    const resized = resizeVariantes(variantes, n);
    if (n < variantes.length && resized.fichiersPerdus > 0) {
      setPendingShrink({ n, ...resized });
      return;
    }
    setPendingShrink(null);
    setVariantes(resized.variantes);
  };

  const confirmShrink = () => {
    if (!pendingShrink) return;
    setVariantes(pendingShrink.variantes);
    setPendingShrink(null);
  };

  const cancelShrink = () => {
    setNbInput(String(variantes.length));
    setPendingShrink(null);
  };

  const updatePiece = (index, piece, updater) => {
    setVariantes((prev) => prev.map((v, i) => (i === index ? { ...v, [piece]: updater(v[piece] || []) } : v)));
  };

  const submit = async () => {
    if (busy) return;
    const name = resolveCompagnieSaisie(compagnie, autre, companyOptions);
    const problems = [];
    if (!name) problems.push("Compagnie d'assurance");
    if (!dateReception) problems.push("Date de réception");
    if (nbError) problems.push(nbError);
    if (pendingShrink) problems.push("Confirmez ou annulez la réduction du nombre de variantes");
    problems.push(...variantesManquantes(variantes));
    setErrors(problems);
    if (problems.length) {
      toast.error("Transmission incomplète");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post(
        `/demandes-offres/${demandeId}/offre`,
        variantesFormData({ compagnie: name, dateReception, variantes, clientToken: token }),
      );
      onTransmitted(res.data, messageTransmission(res.data));
      onOpenChange(false);
    } catch (error) {
      toast.error(errorDetail(error, "Transmission impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="transmettre-variantes-dialog">
        <DialogHeader>
          <DialogTitle>Transmettre une offre</DialogTitle>
          <DialogDescription>
            Chaque variante reçoit son offre (CGA facultatives). Les documents déjà transmis ne sont jamais remplacés.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <CompagnieField
            options={companyOptions}
            value={compagnie}
            autre={autre}
            onChange={setCompagnie}
            onAutre={setAutre}
            testId="variantes-compagnie"
          />
          <FieldBlock label="Date de réception" required>
            <Input type="date" value={dateReception} onChange={(e) => setDateReception(e.target.value)} data-testid="variantes-date" />
          </FieldBlock>
          <FieldBlock label="Nombre de variantes" required>
            <Input
              type="number"
              min="1"
              max="20"
              step="1"
              inputMode="numeric"
              value={nbInput}
              onChange={(e) => changeNb(e.target.value)}
              data-testid="variantes-nombre"
            />
            {nbError ? <p className="text-xs text-rose-700">{nbError}</p> : <p className="text-[11px] text-muted-foreground">Vide = 1 variante.</p>}
          </FieldBlock>
        </div>

        {pendingShrink && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950" data-testid="variantes-reduction-alerte">
            <p className="font-semibold flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Fichiers sélectionnés supprimés</p>
            <p className="mt-1">
              Passer à {pendingShrink.n} variante{pendingShrink.n > 1 ? "s" : ""} retire {pendingShrink.variantesRetirees} bloc{pendingShrink.variantesRetirees > 1 ? "s" : ""} et
              {" "}{pendingShrink.fichiersPerdus} fichier{pendingShrink.fichiersPerdus > 1 ? "s" : ""} déjà sélectionné{pendingShrink.fichiersPerdus > 1 ? "s" : ""}.
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="outline" onClick={cancelShrink} data-testid="variantes-reduction-annuler">Garder les variantes</Button>
              <Button size="sm" className="bg-amber-700 hover:bg-amber-800" onClick={confirmShrink} data-testid="variantes-reduction-confirmer">Supprimer ces fichiers</Button>
            </div>
          </div>
        )}

        <div className="space-y-3">
          {variantes.map((variante, index) => (
            <section key={index} className="rounded-lg border border-slate-200 p-3 sm:p-4" data-testid={`variante-bloc-${index + 1}`}>
              <h3 className="text-xs font-bold uppercase tracking-wide text-[#002FA7]">Variante {index + 1}</h3>
              <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-3">
                {VARIANTE_PIECES.map((piece) => (
                  <FieldBlock key={piece.id} label={piece.required ? piece.label : `${piece.label} (facultatif)`} required={piece.required}>
                    <FilePicker
                      files={variante[piece.id] || []}
                      testId={`variante-${index + 1}-${piece.id}`}
                      onAdd={(files) => updatePiece(index, piece.id, (prev) => [...prev, ...files])}
                      onRemove={(i) => updatePiece(index, piece.id, (prev) => prev.filter((_, k) => k !== i))}
                    />
                  </FieldBlock>
                ))}
              </div>
            </section>
          ))}
        </div>

        {errors.length > 0 && (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" data-testid="variantes-erreurs">
            <p className="font-semibold">À compléter</p>
            <ul className="mt-1 list-disc list-inside">{errors.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Fermer</Button>
          <Button onClick={submit} disabled={busy} className="bg-violet-700 hover:bg-violet-800" data-testid="variantes-valider">
            {busy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            Valider la transmission
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Traitement : compagnie, date, Offre / CGA / Autre document, commentaire. */
export function TransmettreOffreSimpleDialog({ open, onOpenChange, demandeId, companyOptions, onTransmitted }) {
  const [compagnie, setCompagnie] = useState("");
  const [autre, setAutre] = useState("");
  const [dateReception, setDateReception] = useState(zurichTodayIso());
  const [pieces, setPieces] = useState(emptyVariante());
  const [commentaire, setCommentaire] = useState("");
  const [errors, setErrors] = useState([]);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");

  useEffect(() => {
    if (!open) return;
    setCompagnie("");
    setAutre("");
    setDateReception(zurichTodayIso());
    setPieces(emptyVariante());
    setCommentaire("");
    setErrors([]);
    setToken(newClientToken());
  }, [open]);

  const updatePiece = (piece, updater) => {
    setPieces((prev) => ({ ...prev, [piece]: updater(prev[piece] || []) }));
  };

  const submit = async () => {
    if (busy) return;
    const name = resolveCompagnieSaisie(compagnie, autre, companyOptions);
    const problems = [];
    if (!name) problems.push("Compagnie");
    if (!dateReception) problems.push("Date");
    problems.push(...traitementManquantes(pieces));
    setErrors(problems);
    if (problems.length) {
      toast.error("Transmission incomplète");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post(
        `/demandes-offres/${demandeId}/offre`,
        traitementFormData({ compagnie: name, dateReception, pieces, commentaire, clientToken: token }),
      );
      onTransmitted(res.data, messageTransmission(res.data));
      onOpenChange(false);
    } catch (error) {
      toast.error(errorDetail(error, "Transmission impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent className="max-w-2xl" data-testid="transmettre-simple-dialog">
        <DialogHeader>
          <DialogTitle>Transmettre une offre</DialogTitle>
          <DialogDescription>
            Joignez l&apos;offre (CGA facultatives). Les documents déjà transmis ne sont jamais remplacés.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3" data-testid="transmettre-simple-champs">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <CompagnieField
              options={companyOptions}
              value={compagnie}
              autre={autre}
              onChange={setCompagnie}
              onAutre={setAutre}
              testId="simple-compagnie"
            />
            <FieldBlock label="Date" required>
              <Input type="date" value={dateReception} onChange={(e) => setDateReception(e.target.value)} data-testid="simple-date" />
            </FieldBlock>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="simple-pieces">
            {VARIANTE_PIECES.map((piece) => (
              <FieldBlock key={piece.id} label={piece.required ? piece.label : `${piece.label} (facultatif)`} required={piece.required}>
                <FilePicker
                  files={pieces[piece.id] || []}
                  testId={`simple-${piece.id}`}
                  onAdd={(files) => updatePiece(piece.id, (prev) => [...prev, ...files])}
                  onRemove={(i) => updatePiece(piece.id, (prev) => prev.filter((_, k) => k !== i))}
                />
              </FieldBlock>
            ))}
          </div>
          <FieldBlock label="Commentaire">
            <Textarea rows={3} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} data-testid="simple-commentaire" />
          </FieldBlock>
        </div>
        {errors.length > 0 && (
          <p className="text-sm text-rose-700" data-testid="simple-erreurs">À compléter : {errors.join(", ")}</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Fermer</Button>
          <Button onClick={submit} disabled={busy} className="bg-violet-700 hover:bg-violet-800" data-testid="simple-valider">
            {busy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            Valider
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
