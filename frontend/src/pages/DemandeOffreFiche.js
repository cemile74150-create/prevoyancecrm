import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { downloadAuthenticatedBlob, openAuthenticatedBlob } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  ACTIVITES_RISQUE, CIVILITES, COMPAGNIES_DEFAUT, ERREURS_INCOMPLETE_CATALOG, ERREURS_CHAMPS_CATALOG,
  EXONERATIONS, LANGUES, OUI_NON, PERIODICITES, SEXES, SITUATIONS, STATUTS_PRO,
  STATUT_STYLE, STEPS, TYPES_CLIENT, TYPES_PAIEMENT, TYPES_PILIER, emptyForm,
  formatChf, formatDateFr, demandeOrigineLabel, demandeOrigineKey, toIsoDate, toSwissDate,
  DEMANDE_ORIGINE_STYLE, typeClientLabel, buildDemandeResume,
  PRIORITE_STYLE, prioriteLabel, erreurLabel, erreurChampLabel, formatDateTimeFr,
  prefillSchemaPayloadFromClient,
} from "@/lib/demandesOffres";
import OffreSchemaForm, { SchemaReadOnlySummary, isFieldVisible } from "@/components/OffreSchemaForm";
import ClientSuggestInput from "@/components/ClientSuggestInput";
import {
  agentIdentityFromUser,
  missingFinmaMessage,
} from "@/lib/offreAgentIdentity";
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronLeft, ChevronRight,
  Download, ExternalLink, FileText, Loader2, Mail, Paperclip, Pencil, Plus,
  RotateCcw, Save, Send, ShieldCheck, StickyNote, Trash2, X, XCircle,
} from "lucide-react";
import { toast } from "sonner";

const EDITABLE_STATUSES = ["Brouillon", "En attente d'informations", "Demande incomplète"];
const REQUIRED = [
  ["agent_prenom", "Prénom de l'agent"], ["agent_nom", "Nom de l'agent"],
  ["agent_email", "E-mail de l'agent"], ["civilite", "Civilité"],
  ["prenom", "Prénom du preneur"], ["nom", "Nom du preneur"],
  ["date_naissance", "Date de naissance"], ["adresse", "Adresse"],
  ["ville", "Ville"], ["npa", "Code postal"], ["pays", "Pays"],
  ["statut_professionnel", "Statut professionnel"], ["type_pilier", "Type de pilier"],
  ["periodicite_prime", "Périodicité de la prime"], ["montant_prime", "Montant de la prime"],
  ["langue_offre", "Langue souhaitée"],
];

function errorMessage(e, fallback) {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((x) => x.msg).filter(Boolean).join(" · ") || fallback;
  return fallback;
}

function Badge({ statut }) {
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${STATUT_STYLE[statut] || ""}`}>{statut}</span>;
}

function Field({ label, required, children, className = "" }) {
  return <div className={`space-y-1.5 ${className}`}>
    <Label className="text-xs text-muted-foreground">{label}{required && <span className="text-rose-600"> *</span>}</Label>
    {children}
  </div>;
}

function Choice({ value, onChange, options, placeholder = "Sélectionner" }) {
  const normalized = value || "__none";
  return (
    <Select value={normalized} onValueChange={(v) => onChange(v === "__none" ? "" : v)}>
      <SelectTrigger><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        <SelectItem value="__none">Non renseigné</SelectItem>
        {options.map((option) => <SelectItem key={option} value={option}>{option}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

function CheckGrid({ options, selected, onToggle }) {
  return <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
    {options.map((option) => {
      const checked = selected.includes(option);
      return <label key={option} className={`flex items-center gap-2 rounded-md border p-2.5 text-sm cursor-pointer ${checked ? "border-[#002FA7]/40 bg-[#002FA7]/5" : "border-border"}`}>
        <input type="checkbox" checked={checked} onChange={() => onToggle(option)} className="accent-[#002FA7]" />
        {option}
      </label>;
    })}
  </div>;
}

export default function DemandeOffreFiche() {
  const { demandeId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fromGestion = searchParams.get("from") === "gestion";
  const backPath = fromGestion ? "/gestion-reponses-offres" : "/demandes-offres";
  const { hasPerm, user } = useAuth();
  const canEdit = hasPerm("demandes_offres.edit");
  const canProcess = hasPerm("demandes_offres.process");
  const canManageUsers = hasPerm("users.manage");
  const agentIdentity = useMemo(() => agentIdentityFromUser(user), [user]);
  const fileRef = useRef(null);
  const [demande, setDemande] = useState(null);
  const [meta, setMeta] = useState({});
  const [schema, setSchema] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [formPayload, setFormPayload] = useState({});
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [incompleteOpen, setIncompleteOpen] = useState(false);
  const [incompleteComment, setIncompleteComment] = useState("");
  const [incompleteDocs, setIncompleteDocs] = useState("");
  const [incompleteErreurs, setIncompleteErreurs] = useState({});
  const [noteOpen, setNoteOpen] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [offresCompletesOpen, setOffresCompletesOpen] = useState(false);
  const [offresCompletesNote, setOffresCompletesNote] = useState("");
  const [erreursOpen, setErreursOpen] = useState(false);
  const [erreursChecklist, setErreursChecklist] = useState(ERREURS_CHAMPS_CATALOG);
  const [erreursSelected, setErreursSelected] = useState({});
  const [erreursComment, setErreursComment] = useState("");
  const [offerOpen, setOfferOpen] = useState(false);
  const [signatureOpen, setSignatureOpen] = useState(false);
  const [signatureMode, setSignatureMode] = useState(true);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelComment, setCancelComment] = useState("");
  const [offer, setOffer] = useState({
    compagnie: "", date_reception: new Date().toISOString().slice(0, 10),
    reference: "", montant_prime: "", type_contrat: "", garanties: "", duree: "",
    commentaires: "", message_conseiller: "", files: [],
    _mode: "offre", _offreId: null,
  });
  const [incompleteCompagnie, setIncompleteCompagnie] = useState("");
  const [showFullForm, setShowFullForm] = useState(false);
  const [signature, setSignature] = useState({
    date_signature: new Date().toISOString().slice(0, 10),
    commentaire: "", date_relance: "", file: null,
  });
  const formDirtyRef = useRef(false);
  const autosaveTimerRef = useRef(null);

  const isLegacy = !demande?.form_type || demande.form_type === "pilier3_legacy";
  const finmaWarning = useMemo(
    () => missingFinmaMessage(user, isLegacy ? null : schema),
    [user, isLegacy, schema],
  );

  // Autofill agent depuis le profil session (legacy + sync CRM)
  useEffect(() => {
    if (!user || !agentIdentity) return;
    setForm((prev) => {
      const next = {
        ...prev,
        agent_prenom: agentIdentity.prenom || "",
        agent_nom: agentIdentity.nom || "",
        agent_email: agentIdentity.email || "",
        agent_finma: agentIdentity.finma || "",
      };
      if (
        next.agent_prenom === prev.agent_prenom
        && next.agent_nom === prev.agent_nom
        && next.agent_email === prev.agent_email
        && next.agent_finma === prev.agent_finma
      ) {
        return prev;
      }
      return next;
    });
  }, [user, agentIdentity]);

  const load = useCallback(async () => {
    setLoading(true);
    setShowFullForm(false);
    formDirtyRef.current = false;
    try {
      const [ficheRes, metaRes] = await Promise.all([
        api.get(`/demandes-offres/${demandeId}`),
        api.get("/demandes-offres/meta"),
      ]);
      const data = ficheRes.data;
      setDemande(data);
      setForm({
        ...emptyForm(),
        ...data,
        montant_prime: data.montant_prime ?? "",
        date_naissance: toSwissDate(data.date_naissance) || "",
      });
      setFormPayload(data.form_payload || {});
      setMeta(metaRes.data || {});
      if (data.form_type && data.form_type !== "pilier3_legacy") {
        try {
          const schemaRes = await api.get(`/demandes-offres/form-types/${data.form_type}`);
          setSchema(schemaRes.data);
        } catch {
          setSchema(null);
        }
      } else {
        setSchema(null);
      }
    } catch (e) {
      toast.error(errorMessage(e, "Demande introuvable"));
    } finally {
      setLoading(false);
    }
  }, [demandeId]);

  useEffect(() => { load(); }, [load]);

  const setValue = (key, value) => {
    if (!isLegacy && (key === "commentaires" || key === "client_id" || key === "type_client")) {
      formDirtyRef.current = true;
    }
    setForm((prev) => ({ ...prev, [key]: value }));
  };
  const toggleArray = (key, value) => setForm((prev) => ({
    ...prev,
    [key]: prev[key].includes(value) ? prev[key].filter((x) => x !== value) : [...prev[key], value],
  }));

  const updateFormPayload = useCallback((next) => {
    formDirtyRef.current = true;
    setFormPayload((prev) => (typeof next === "function" ? next(prev) : next));
  }, []);

  const legacyPayload = useMemo(() => {
    const clean = { ...form };
    delete clean.id; delete clean.numero; delete clean.statut; delete clean.documents;
    delete clean.historique; delete clean.offre; delete clean.offres; delete clean.offre_choisie_id;
    delete clean.signature; delete clean.envoi_client; delete clean.conclusion;
    delete clean.created_at; delete clean.updated_at; delete clean.created_by_name;
    delete clean.client_label; delete clean.agent_label; delete clean.incomplete_comment;
    delete clean.incomplete_at; delete clean.incomplete_by; delete clean.date_envoi;
    delete clean.email_sent; delete clean.email_error; delete clean.form_payload;
    delete clean.form_type; delete clean.form_type_label; delete clean.form_category;
    // conserver client_id pour le lien hub Clients
    clean.montant_prime = form.montant_prime === "" ? null : form.montant_prime;
    clean.date_naissance = toIsoDate(form.date_naissance) || null;
    return clean;
  }, [form]);

  const save = async ({ quiet = false } = {}) => {
    if (!canEdit) return null;
    setSaving(true);
    try {
      const body = isLegacy
        ? legacyPayload
        : {
            form_payload: formPayload,
            type_client: form.type_client || formPayload.type_client || "",
            client_id: form.client_id || null,
            commentaires: form.commentaires || "",
          };
      const res = await api.put(`/demandes-offres/${demandeId}`, body);
      formDirtyRef.current = false;
      setDemande(res.data);
      setForm((prev) => ({
        ...prev,
        ...res.data,
        montant_prime: res.data.montant_prime ?? "",
        date_naissance: toSwissDate(res.data.date_naissance) || "",
      }));
      setFormPayload(res.data.form_payload || {});
      if (!quiet) toast.success("Brouillon enregistré");
      return res.data;
    } catch (e) {
      toast.error(errorMessage(e, "Enregistrement impossible"));
      return null;
    } finally {
      setSaving(false);
    }
  };

  // Auto-save schema forms so F5 / Actualiser ne perd pas la saisie
  useEffect(() => {
    if (loading || isLegacy || !canEdit || !demande) return;
    if (!EDITABLE_STATUSES.includes(demande.statut)) return;
    if (!formDirtyRef.current) return;
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    autosaveTimerRef.current = setTimeout(() => {
      if (!formDirtyRef.current) return;
      save({ quiet: true });
    }, 1200);
    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formPayload, form.commentaires, form.client_id, form.type_client, loading, isLegacy, canEdit, demande?.statut, demandeId]);

  useEffect(() => {
    const onBeforeUnload = (e) => {
      if (!formDirtyRef.current) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  const moveStep = async (next) => {
    if (next > step && canEdit) {
      const saved = await save({ quiet: true });
      if (!saved) return;
    }
    setStep(Math.max(0, Math.min(STEPS.length - 1, next)));
  };

  const missing = useMemo(() => {
    let values;
    if (!isLegacy) {
      if (!schema) return finmaWarning ? [finmaWarning] : [];
      const isEmpty = (ftype, value) => {
        if (value === null || value === undefined) return true;
        if (Array.isArray(value)) {
          if (!value.length) return true;
          if (ftype === "list") {
            return !value.some((row) =>
              row && typeof row === "object"
                ? Object.values(row).some((v) => String(v || "").trim())
                : String(row || "").trim(),
            );
          }
          return false;
        }
        return String(value).trim() === "";
      };
      values = (schema.fields || [])
        .filter((f) => f.required && !["section", "html", "file"].includes(f.type))
        .filter((f) => isFieldVisible(f, formPayload || {}))
        .filter((f) => {
          const name = f.name || f.id;
          return isEmpty(f.type, formPayload?.[name]);
        })
        .map((f) => f.label || f.name);
    } else {
      values = REQUIRED.filter(([key]) => {
        const value = form[key];
        return value === null || value === undefined || String(value).trim() === "";
      }).map(([, label]) => label);
      if (!form.compagnies?.length) values.push("Au moins une compagnie");
      if (form.activites_risque && !form.activites_risque_liste?.length) values.push("Activités à risque (sélection)");
    }
    if (finmaWarning && !values.includes(finmaWarning)) {
      values = [...values, finmaWarning];
    }
    return values;
  }, [form, formPayload, isLegacy, schema, finmaWarning]);

  const refreshFromAction = (data, message) => {
    setDemande(data);
    setForm((prev) => ({
      ...prev,
      ...data,
      montant_prime: data.montant_prime ?? "",
      date_naissance: toSwissDate(data.date_naissance) || "",
    }));
    setFormPayload(data.form_payload || {});
    toast.success(message);
    if (data?.email_sent === true) {
      toast.message("E-mail de notification envoyé", {
        description: data.email_error || undefined,
      });
    } else if (data?.email_sent === false && data?.email_error) {
      toast.warning("Statut enregistré, mais e-mail non envoyé", {
        description: String(data.email_error).slice(0, 200),
      });
    }
  };

  const validateAndSend = async () => {
    if (missing.length) {
      toast.error("Complétez les champs obligatoires");
      return;
    }
    setActionBusy(true);
    try {
      await save({ quiet: true });
      if (demande.statut === "Demande incomplète" || demande.statut === "En attente d'informations") {
        const res = await api.post(`/demandes-offres/${demandeId}/completer-renvoyer`);
        refreshFromAction(res.data, "Informations complétées et demande renvoyée");
      } else {
        await api.post(`/demandes-offres/${demandeId}/validate`);
        const res = await api.post(`/demandes-offres/${demandeId}/envoyer`);
        refreshFromAction(res.data, "Demande validée et envoyée");
      }
    } catch (e) {
      toast.error(errorMessage(e, "Envoi impossible"));
    } finally {
      setActionBusy(false);
    }
  };

  const runAction = async (path, body, success) => {
    setActionBusy(true);
    try {
      const res = await api.post(`/demandes-offres/${demandeId}/${path}`, body);
      refreshFromAction(res.data, success);
      return true;
    } catch (e) {
      toast.error(errorMessage(e, "Action impossible"));
      return false;
    } finally {
      setActionBusy(false);
    }
  };

  const markIncomplete = async () => {
    if (!incompleteComment.trim()) return toast.error("Le message au conseiller est obligatoire");
    const erreurs = ERREURS_INCOMPLETE_CATALOG
      .filter((e) => incompleteErreurs[e.code]?.checked)
      .map((e) => ({
        code: e.code,
        label: e.label,
        detail: (incompleteErreurs[e.code]?.detail || "").trim() || null,
      }));
    if (await runAction("incomplete", {
      comment: incompleteComment.trim(),
      documents_manquants: incompleteDocs.trim() || null,
      erreurs,
      compagnie: incompleteCompagnie || null,
    }, "Offre incomplète notifiée — conseiller informé")) {
      setIncompleteOpen(false);
      setIncompleteComment("");
      setIncompleteDocs("");
      setIncompleteErreurs({});
      setIncompleteCompagnie("");
    }
  };

  const markCompanyIncomplete = async (compagnie) => {
    if (!compagnie) return;
    setActionBusy(true);
    try {
      const res = await api.post(`/demandes-offres/${demandeId}/compagnie-incomplete`, { compagnie });
      refreshFromAction(res.data, `${compagnie} marquée incomplète`);
    } catch (e) {
      toast.error(errorMessage(e, "Marquage impossible"));
    } finally {
      setActionBusy(false);
    }
  };

  const openIncompleteNotify = (compagnie) => {
    setIncompleteCompagnie(compagnie || "");
    setIncompleteOpen(true);
  };

  const addOffer = async () => {
    if (!offer.compagnie || !offer.date_reception) return toast.error("Compagnie et date requises");
    const fd = new FormData();
    Object.entries(offer).forEach(([key, value]) => {
      if (key.startsWith("_")) return;
      if (key === "files") return;
      if (value !== null && value !== "") fd.append(key, value);
    });
    // Toujours envoyer une liste multipart (1 ou N) sous files[] / documents[]
    const fileList = Array.isArray(offer.files)
      ? offer.files
      : (offer.files ? [offer.files] : []);
    fileList.forEach((f) => {
      if (!f) return;
      fd.append("files", f);
      fd.append("documents", f);
    });
    if (fileList[0]) fd.append("file", fileList[0]); // compat anciens clients mono-fichier
    setActionBusy(true);
    try {
      if (offer._mode === "add-docs" && offer._offreId) {
        const docFd = new FormData();
        fileList.forEach((f) => {
          if (!f) return;
          docFd.append("files", f);
          docFd.append("documents", f);
        });
        if (fileList[0]) docFd.append("file", fileList[0]);
        if (!fileList.length) return toast.error("Sélectionnez au moins un document");
        const res = await api.post(
          `/demandes-offres/${demandeId}/offres/${offer._offreId}/documents`,
          docFd,
        );
        refreshFromAction(res.data, "Documents ajoutés à l'offre");
      } else {
        // Ne pas forcer Content-Type : le navigateur doit poser la boundary multipart
        const res = await api.post(`/demandes-offres/${demandeId}/offre`, fd);
        refreshFromAction(res.data, "Offre compagnie enregistrée");
      }
      setOfferOpen(false);
      setOffer({
        compagnie: "", date_reception: new Date().toISOString().slice(0, 10),
        reference: "", montant_prime: "", type_contrat: "", garanties: "", duree: "",
        commentaires: "", message_conseiller: "", files: [],
        _mode: "offre", _offreId: null,
      });
    } catch (e) {
      toast.error(errorMessage(e, "Ajout de l'offre impossible"));
    } finally { setActionBusy(false); }
  };

  const deleteOfferDocument = async (offreId, doc) => {
    if (!window.confirm(`Retirer « ${doc.original_filename || "ce document"} » de l'offre ?`)) return;
    setActionBusy(true);
    try {
      const res = await api.delete(`/demandes-offres/${demandeId}/offres/${offreId}/documents/${doc.id}`);
      refreshFromAction(res.data, "Document retiré");
    } catch (e) {
      toast.error(errorMessage(e, "Suppression impossible"));
    } finally {
      setActionBusy(false);
    }
  };

  const openAddOffer = (compagnie = "") => {
    setOffer({
      compagnie: compagnie || "",
      date_reception: new Date().toISOString().slice(0, 10),
      reference: "", montant_prime: "", type_contrat: "", garanties: "", duree: "",
      commentaires: "", message_conseiller: "", files: [],
      _mode: "offre", _offreId: null,
    });
    setOfferOpen(true);
  };

  const openAddDocs = (card) => {
    setOffer({
      compagnie: card.compagnie || "",
      date_reception: card.date_reception
        ? String(card.date_reception).slice(0, 10)
        : new Date().toISOString().slice(0, 10),
      reference: card.reference || "",
      montant_prime: card.montant_prime ?? "",
      type_contrat: card.type_contrat || "",
      garanties: card.garanties || "",
      duree: card.duree || "",
      commentaires: card.commentaires || "",
      message_conseiller: "",
      files: [],
      _mode: "add-docs",
      _offreId: card.offre_id,
    });
    setOfferOpen(true);
  };

  const addInternalNote = async () => {
    if (!noteText.trim()) return toast.error("La note est obligatoire");
    if (await runAction("notes-internes", { note: noteText.trim() }, "Note interne enregistrée")) {
      setNoteOpen(false);
      setNoteText("");
    }
  };

  const markConclusion = async () => {
    await runAction("conclusion", {}, "Dossier passé en conclusion");
  };

  const markOffresCompletes = async () => {
    setOffresCompletesNote("");
    setOffresCompletesOpen(true);
  };

  const confirmOffresCompletes = async () => {
    const note = offresCompletesNote.trim();
    const ok = await runAction(
      "offres-completes",
      { message_conseiller: note || null, note: note || null },
      "Offres marquées complètes — conseiller notifié",
    );
    if (ok) {
      setOffresCompletesOpen(false);
      setOffresCompletesNote("");
    }
  };

  const openErreursDialog = async () => {
    setErreursSelected({});
    setErreursComment("");
    setErreursOpen(true);
    try {
      const res = await api.get(`/demandes-offres/${demandeId}/erreurs-checklist`);
      const items = res.data?.items || res.data?.catalog || ERREURS_CHAMPS_CATALOG;
      setErreursChecklist(Array.isArray(items) && items.length ? items : ERREURS_CHAMPS_CATALOG);
    } catch {
      setErreursChecklist(ERREURS_CHAMPS_CATALOG);
    }
  };

  const confirmErreurs = async () => {
    const fields = Object.entries(erreursSelected)
      .filter(([, on]) => on)
      .map(([code]) => {
        const item = erreursChecklist.find((e) => e.code === code);
        return { code, label: item?.label || erreurChampLabel(code) };
      });
    if (!fields.length) return toast.error("Sélectionnez au moins un champ en erreur");
    const ok = await runAction(
      "erreurs",
      { fields, comment: erreursComment.trim() || null },
      `${fields.length} erreur(s) enregistrée(s) pour l'agent`,
    );
    if (ok) {
      setErreursOpen(false);
      setErreursSelected({});
      setErreursComment("");
    }
  };

  const confirmCancel = async () => {
    const ok = await runAction(
      "annuler",
      { commentaire: cancelComment.trim() || null },
      "Demande / offre annulée",
    );
    if (ok) {
      setCancelOpen(false);
      setCancelComment("");
    }
  };

  const restoreDemande = async () => {
    if (!demande || demande.statut !== "Demande annulée") return;
    if (!(canEdit || canProcess)) return;
    const ok = await runAction("restaurer", {}, "Demande restaurée");
    return ok;
  };

  const deleteDemande = async () => {
    if (!demande) return;
    const st = demande.statut;
    if (!["Brouillon", "Demande annulée"].includes(st)) {
      toast.error("Annulez d'abord la demande, puis vous pourrez la supprimer.");
      return;
    }
    if (!window.confirm(`Supprimer définitivement ${demande.numero || "cette demande"} ? Cette action est irréversible.`)) return;
    setActionBusy(true);
    try {
      await api.delete(`/demandes-offres/${demandeId}`);
      toast.success("Demande supprimée");
      navigate("/demandes-offres");
    } catch (e) {
      toast.error(errorMessage(e, "Suppression impossible"));
    } finally {
      setActionBusy(false);
    }
  };

  const recordSignature = async () => {
    const fd = new FormData();
    fd.append("signee", String(signatureMode));
    if (signature.date_signature) fd.append("date_signature", signature.date_signature);
    if (signature.commentaire) fd.append("commentaire", signature.commentaire);
    if (signature.date_relance) fd.append("date_relance", signature.date_relance);
    if (signature.file) fd.append("file", signature.file);
    setActionBusy(true);
    try {
      const res = await api.post(`/demandes-offres/${demandeId}/signature`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      refreshFromAction(res.data, signatureMode ? "Offre marquée signée" : "Offre marquée non signée");
      setSignatureOpen(false);
    } catch (e) {
      toast.error(errorMessage(e, "Enregistrement impossible"));
    } finally { setActionBusy(false); }
  };

  const uploadDocument = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("category", "Pièce jointe");
      await api.post(`/demandes-offres/${demandeId}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Document ajouté");
      await load();
    } catch (e) {
      toast.error(errorMessage(e, "Ajout du document impossible"));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const deleteDocument = async (doc) => {
    if (!window.confirm(`Supprimer « ${doc.original_filename} » ?`)) return;
    try {
      await api.delete(`/demandes-offres/documents/${doc.id}`);
      setDemande((prev) => ({ ...prev, documents: prev.documents.filter((d) => d.id !== doc.id) }));
      toast.success("Document supprimé");
    } catch (e) { toast.error(errorMessage(e, "Suppression impossible")); }
  };

  const deleteBrouillon = async () => {
    if (!canEdit || demande.statut !== "Brouillon") return;
    if (!window.confirm(`Supprimer définitivement le brouillon ${demande.numero} ?`)) return;
    setActionBusy(true);
    try {
      await api.delete(`/demandes-offres/${demandeId}`);
      toast.success("Brouillon supprimé");
      navigate("/demandes-offres");
    } catch (e) {
      toast.error(errorMessage(e, "Suppression impossible"));
    } finally {
      setActionBusy(false);
    }
  };

  if (loading) return <Layout><p className="text-muted-foreground animate-pulse">Chargement de la demande…</p></Layout>;
  if (!demande) return <Layout><Button variant="outline" onClick={() => navigate(backPath)}>Retour</Button></Layout>;

  const editable = canEdit && EDITABLE_STATUSES.includes(demande.statut);
  const canDeleteDraft = canEdit && demande.statut === "Brouillon";
  const offresList = (demande.offres && demande.offres.length)
    ? demande.offres
    : (demande.offre ? [demande.offre] : []);
  const reponsesCompagnies = (demande.reponses_compagnies && demande.reponses_compagnies.length)
    ? demande.reponses_compagnies
    : (demande.variantes || []);
  const hasIncompleteCompany = reponsesCompagnies.some((c) => String(c.statut || "").toLowerCase().includes("incompl"));
  const variantes = demande.variantes || [];
  const notesInternes = canProcess ? (demande.notes_internes || []) : [];
  const erreursAgent = Array.isArray(demande.erreurs_agent) ? demande.erreurs_agent : [];
  const canFollowSignature = Boolean(demande.can_follow_signature);

  return (
    <Layout>
      <div className="animate-fade-up max-w-6xl space-y-5">
        <button onClick={() => navigate(backPath)} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-[#002FA7]">
          <ArrowLeft className="h-3.5 w-3.5" /> {fromGestion ? "Gestion réponses offres" : "Demandes d'offres"}
        </button>

        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight">
              {demande.client_label !== "—" ? demande.client_label : "Nouvelle demande"}
            </h1>
            <div className="mt-2 space-y-1.5">
              <div className="flex items-baseline gap-3 flex-wrap">
                <span className="font-mono text-base font-semibold text-[#002FA7] tracking-tight">
                  {demande.numero || "—"}
                </span>
                {demande.email_subject && (
                  <span className="text-sm text-slate-700 font-medium" title="Objet e-mail permanent">
                    {demande.email_subject}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Badge statut={demande.statut} />
                <span
                  className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${DEMANDE_ORIGINE_STYLE[demandeOrigineKey(demande.demande_origine)]}`}
                  title={demandeOrigineLabel(demande.demande_origine)}
                >
                  {demandeOrigineLabel(demande.demande_origine)}
                </span>
                {demande.type_client && (
                  <span className="text-xs rounded-full bg-secondary px-2.5 py-1 text-muted-foreground">
                    {typeClientLabel(demande.type_client)}
                  </span>
                )}
                {demande.priorite && (
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${PRIORITE_STYLE[demande.priorite] || ""}`}>
                    {prioriteLabel(demande.priorite)}
                    {typeof demande.jours_depuis === "number" ? ` · ${demande.jours_depuis} j` : ""}
                  </span>
                )}
                <span className="text-xs rounded-full bg-secondary px-2.5 py-1 text-muted-foreground">
                  {demande.form_type_label || "Formulaire"}
                </span>
                {(demande.compagnies?.length > 0) && (
                  <span className="text-xs rounded-full bg-indigo-50 text-indigo-800 px-2.5 py-1 ring-1 ring-inset ring-indigo-200">
                    {demande.compagnies.length} variante{demande.compagnies.length > 1 ? "s" : ""} sollicitée{demande.compagnies.length > 1 ? "s" : ""}
                  </span>
                )}
                {offresList.length > 0 && (
                  <span className="text-xs rounded-full bg-violet-50 text-violet-800 px-2.5 py-1 ring-1 ring-inset ring-violet-200">
                    {offresList.length} réponse{offresList.length > 1 ? "s" : ""} compagnie
                  </span>
                )}
              </div>
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              Conseiller : {demande.agent_label || "—"}
              {demande.date_envoi ? ` · Envoyée le ${formatDateFr(demande.date_envoi)}` : ""}
              {demande.created_at ? ` · Créée le ${formatDateFr(demande.created_at)}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {canDeleteDraft && (
              <Button
                variant="outline"
                onClick={deleteBrouillon}
                disabled={actionBusy}
                className="gap-2 text-rose-700 border-rose-200 hover:bg-rose-50"
              >
                <Trash2 className="h-4 w-4" /> Supprimer le brouillon
              </Button>
            )}
            {editable && (
              <Button variant="outline" onClick={() => save()} disabled={saving} className="gap-2">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Enregistrer
              </Button>
            )}
          </div>
        </div>

        {demande.incomplete_comment && (
          <Card className="p-4 border-amber-300 bg-amber-50 text-amber-950">
            <div className="flex gap-3"><AlertTriangle className="h-5 w-5 shrink-0" />
              <div>
                <p className="font-semibold text-sm">Informations complémentaires demandées</p>
                <p className="text-sm mt-1 whitespace-pre-wrap">{demande.incomplete_comment}</p>
                {demande.documents_manquants && (
                  <p className="text-sm mt-2"><span className="font-medium">Documents manquants :</span> {demande.documents_manquants}</p>
                )}
                {Array.isArray(demande.erreurs_incomplete) && demande.erreurs_incomplete.length > 0 && (
                  <ul className="mt-2 space-y-1 text-sm">
                    {demande.erreurs_incomplete.map((err, i) => (
                      <li key={`${err.code}-${i}`} className="flex gap-2">
                        <span className="font-medium">{err.label || erreurLabel(err.code)}</span>
                        {err.detail ? <span className="text-amber-800">— {err.detail}</span> : null}
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-xs mt-1 text-amber-800">{demande.incomplete_by ? `Par ${demande.incomplete_by}` : ""}{demande.incomplete_at ? ` · ${formatDateFr(demande.incomplete_at)}` : ""}</p>
              </div>
            </div>
          </Card>
        )}

        {demande.message_conseiller && ["Offres complètes", "Offre complète", "Offre reçue", "Offre choisie"].includes(demande.statut) && (
          <Card className="p-4 border-emerald-300 bg-emerald-50 text-emerald-950">
            <div className="flex gap-3"><CheckCircle2 className="h-5 w-5 shrink-0" />
              <div><p className="font-semibold text-sm">Message du gestionnaire d&apos;offres</p>
                <p className="text-sm mt-1 whitespace-pre-wrap">{demande.message_conseiller}</p>
              </div>
            </div>
          </Card>
        )}

        {(demande.date_envoi || demande.email_error) && (
          <div className={`rounded-md border px-4 py-3 text-sm ${demande.email_sent ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
            {demande.email_sent ? `E-mail envoyé le ${formatDateFr(demande.date_envoi)}` : `Demande enregistrée, mais e-mail non envoyé : ${demande.email_error || "configuration indisponible"}`}
          </div>
        )}

        {editable ? (
          isLegacy ? (
            <>
              <WizardProgress step={step} onStep={moveStep} />
              <Card className="p-5 sm:p-7 min-h-[420px]">
                {step === 0 && (
                  <ClientStep
                    form={form}
                    setValue={setValue}
                    onPickClient={(client) => applyHubClientToOffreForm(client, setValue, form)}
                    finmaWarning={finmaWarning}
                    canManageUsers={canManageUsers}
                  />
                )}
                {step === 1 && (
                  <CompagniesStep
                    form={form}
                    toggle={(v) => toggleArray("compagnies", v)}
                    meta={meta}
                  />
                )}
                {step === 2 && <SituationStep form={form} setValue={setValue} toggle={(v) => toggleArray("activites_risque_liste", v)} meta={meta} />}
                {step === 3 && <PilierStep form={form} setValue={setValue} meta={meta} />}
                {step === 4 && <Documents demande={demande} canEdit={canEdit} uploading={uploading} fileRef={fileRef} upload={uploadDocument} remove={deleteDocument} />}
                {step === 5 && <Verification form={form} missing={missing} demande={demande} />}
              </Card>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={() => moveStep(step - 1)} disabled={step === 0 || saving}><ChevronLeft className="h-4 w-4 mr-1" /> Précédent</Button>
                  {["Brouillon", "Demande annulée"].includes(demande.statut) && (
                    <Button variant="ghost" className="text-rose-700" onClick={deleteDemande} disabled={actionBusy}>
                      <Trash2 className="h-4 w-4 mr-2" /> Supprimer
                    </Button>
                  )}
                  {!["Offre signée", "Demande annulée"].includes(demande.statut) && (
                    <Button variant="outline" className="border-rose-300 text-rose-800" onClick={() => setCancelOpen(true)} disabled={actionBusy}>
                      <XCircle className="h-4 w-4 mr-2" /> Annuler l&apos;offre
                    </Button>
                  )}
                </div>
                {step < STEPS.length - 1 ? (
                  <Button onClick={() => moveStep(step + 1)} disabled={saving} className="bg-[#002FA7] hover:bg-[#00248a]">
                    {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null} Suivant <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                ) : (
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setStep(0)}><Pencil className="h-4 w-4 mr-1" /> Modifier</Button>
                    <Button onClick={validateAndSend} disabled={actionBusy || missing.length > 0} className="bg-[#002FA7] hover:bg-[#00248a]">
                      {actionBusy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
                      {demande.statut === "Brouillon" ? "Valider et envoyer" : "Informations complétées – Renvoyer"}
                    </Button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <Card className="p-5 sm:p-7">
                <TypeClientField value={form.type_client || formPayload.type_client || ""} onChange={(v) => {
                  setValue("type_client", v);
                  updateFormPayload((prev) => ({ ...prev, type_client: v }));
                }} />
                <div className="mt-6">
                  <SchemaClientLinker
                    form={form}
                    setValue={setValue}
                    schema={schema}
                    formPayload={formPayload}
                    onPrefillPayload={(next) => updateFormPayload(next)}
                  />
                </div>
                <div className="mt-6">
                  <SectionTitle title={demande.form_type_label || "Formulaire"} subtitle="Saisissez toutes les informations du formulaire intranet. Enregistrement automatique." />
                </div>
                <div className="mt-5">
                  <OffreSchemaForm
                    schema={schema}
                    values={formPayload}
                    onChange={updateFormPayload}
                    agentIdentity={agentIdentity}
                    persistKey={`${demandeId}:${schema?.id || demande.form_type || ""}`}
                    onPageChange={() => {
                      if (formDirtyRef.current) save({ quiet: true });
                    }}
                  />
                </div>
                {finmaWarning ? (
                  <div
                    className="mt-5 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-950"
                    data-testid="offre-finma-missing-warning"
                  >
                    <p className="font-semibold text-sm flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 shrink-0" /> Numéro FINMA manquant
                    </p>
                    <p className="text-sm mt-1">{finmaWarning}</p>
                    {canManageUsers ? (
                      <p className="text-sm mt-2">
                        <Link to="/utilisateurs" className="underline font-medium text-amber-900 hover:text-amber-950">
                          Ouvrir Utilisateurs
                        </Link>
                        {" "}pour compléter le N° FINMA sur votre profil.
                      </p>
                    ) : (
                      <p className="text-sm mt-2 text-amber-900/90">
                        Contactez un administrateur pour renseigner votre N° FINMA dans Utilisateurs.
                      </p>
                    )}
                  </div>
                ) : null}
                <div className="mt-6 space-y-2 border-t pt-5">
                  <SectionTitle
                    title="Commentaires / informations complémentaires"
                    subtitle="Zone libre pour le service Offres (hors champs du formulaire). Visible dans le résumé et l'e-mail récapitulatif."
                  />
                  <Textarea
                    rows={4}
                    value={form.commentaires || ""}
                    onChange={(e) => setValue("commentaires", e.target.value)}
                    placeholder="Précisions, contexte client, points d'attention pour le service Offres…"
                    data-testid="offre-commentaires-complementaires"
                  />
                </div>
                {missing.length > 0 && (
                  <div className="mt-5 rounded-md border border-rose-200 bg-rose-50 p-4">
                    <p className="font-semibold text-sm text-rose-800 flex items-center gap-2"><XCircle className="h-4 w-4" /> Champs obligatoires manquants ({missing.length})</p>
                    <ul className="mt-2 grid sm:grid-cols-2 gap-1 text-sm text-rose-700 list-disc list-inside">
                      {missing.map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                )}
              </Card>
              <Documents demande={demande} canEdit={canEdit} uploading={uploading} fileRef={fileRef} upload={uploadDocument} remove={deleteDocument} />
              <div className="flex flex-wrap justify-between gap-2">
                <div className="flex flex-wrap gap-2">
                  {["Brouillon", "Demande annulée"].includes(demande.statut) && (
                    <Button variant="ghost" className="text-rose-700" onClick={deleteDemande} disabled={actionBusy}>
                      <Trash2 className="h-4 w-4 mr-2" /> Supprimer
                    </Button>
                  )}
                  {!["Offre signée", "Demande annulée"].includes(demande.statut) && (
                    <Button variant="outline" className="border-rose-300 text-rose-800" onClick={() => setCancelOpen(true)} disabled={actionBusy}>
                      <XCircle className="h-4 w-4 mr-2" /> Annuler l&apos;offre
                    </Button>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={() => save()} disabled={saving}>
                    {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />} Enregistrer
                  </Button>
                  <Button onClick={validateAndSend} disabled={actionBusy || missing.length > 0} className="bg-[#002FA7] hover:bg-[#00248a]">
                    {actionBusy ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
                    {demande.statut === "Brouillon" ? "Valider et envoyer" : "Informations complétées – Renvoyer"}
                  </Button>
                </div>
              </div>
            </>
          )
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5 items-start">
            <div className="space-y-5">
              {!showFullForm ? (
                <>
                  <DemandeResumeCard demande={demande} schema={schema} />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" onClick={() => setShowFullForm(true)} className="gap-2">
                      <Pencil className="h-4 w-4" /> Voir le formulaire complet
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm text-muted-foreground">Formulaire complet (lecture seule)</p>
                    <Button variant="outline" size="sm" onClick={() => setShowFullForm(false)}>
                      Retour au résumé
                    </Button>
                  </div>
                  {isLegacy ? (
                    <ReadOnlyData data={demande} />
                  ) : (
                    <Card className="p-5">
                      <h2 className="font-display font-bold text-[#002FA7] mb-4">{demande.form_type_label || "Formulaire"}</h2>
                      <SchemaReadOnlySummary schema={schema} values={demande.form_payload || {}} />
                    </Card>
                  )}
                </>
              )}
              <CompanyResponsesPanel
                cards={reponsesCompagnies}
                canProcess={canProcess}
                busy={actionBusy}
                onAddOffer={openAddOffer}
                onAddDocs={openAddDocs}
                onMarkIncomplete={markCompanyIncomplete}
                onNotifyIncomplete={openIncompleteNotify}
                onDeleteDoc={deleteOfferDocument}
              />
              {variantes.length > 0 && !reponsesCompagnies.length && (
                <Card className="p-5">
                  <h2 className="font-display font-bold mb-3">Variantes sollicitées ({variantes.length})</h2>
                  <ul className="space-y-2">
                    {variantes.map((v) => (
                      <li key={`${v.index}-${v.compagnie}`} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                        <span className="font-medium">{v.index}. {v.compagnie}</span>
                        <Badge statut={v.statut} />
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
              {canProcess && (
                <Card className="p-5 space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="font-display font-bold flex items-center gap-2"><StickyNote className="h-5 w-5 text-[#002FA7]" /> Notes internes</h2>
                    <Button size="sm" variant="outline" onClick={() => setNoteOpen(true)}><Plus className="h-3.5 w-3.5 mr-1" /> Ajouter</Button>
                  </div>
                  <p className="text-xs text-muted-foreground">Visibles uniquement des gestionnaires, CEO et admin.</p>
                  {!notesInternes.length ? (
                    <p className="text-sm text-muted-foreground">Aucune note interne.</p>
                  ) : (
                    <ul className="space-y-3">
                      {[...notesInternes].reverse().map((n) => (
                        <li key={n.id} className="rounded-md border bg-slate-50 px-3 py-2 text-sm">
                          <p className="whitespace-pre-wrap">{n.note}</p>
                          <p className="text-xs text-muted-foreground mt-1">{formatDateFr(n.at)}{n.by_name ? ` · ${n.by_name}` : ""}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              )}
              {erreursAgent.length > 0 && (
                <Card className="p-5 space-y-3 border-rose-200">
                  <h2 className="font-display font-bold flex items-center gap-2 text-rose-800">
                    <AlertTriangle className="h-5 w-5" /> Erreurs signalées ({erreursAgent.length})
                  </h2>
                  <ul className="space-y-2">
                    {[...erreursAgent].reverse().map((err) => (
                      <li key={err.id || `${err.field}-${err.at}`} className="rounded-md border border-rose-100 bg-rose-50/60 px-3 py-2 text-sm">
                        <p className="font-medium text-rose-900">❌ {err.field_label || erreurChampLabel(err.field)}</p>
                        {err.comment && <p className="text-xs text-rose-800/80 mt-0.5">{err.comment}</p>}
                        <p className="text-xs text-muted-foreground mt-1">
                          {formatDateFr(err.at || err.date)}
                          {err.by_name ? ` · ${err.by_name}` : ""}
                        </p>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
              {demande.conclusion && (
                <Card className="p-5">
                  <h2 className="font-display font-bold mb-2">Conclusion</h2>
                  <p className="text-sm">{demande.conclusion.commentaire || "Dossier en conclusion"}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {formatDateFr(demande.conclusion.at)}
                    {demande.conclusion.by ? ` · ${demande.conclusion.by}` : ""}
                  </p>
                </Card>
              )}
              <Documents demande={demande} canEdit={canProcess} uploading={uploading} fileRef={fileRef} upload={uploadDocument} remove={deleteDocument} />
              <History entries={demande.historique || []} />
            </div>
            <ActionPanel
              demande={demande}
              canEdit={canEdit}
              canProcess={canProcess}
              canFollowSignature={canFollowSignature}
              busy={actionBusy}
              hasOffers={offresList.length > 0 || reponsesCompagnies.some((c) => c.has_offre)}
              hasIncompleteCompany={hasIncompleteCompany}
              onIncomplete={() => openIncompleteNotify(incompleteCompagnie || reponsesCompagnies.find((c) => String(c.statut || "").toLowerCase().includes("incompl"))?.compagnie || "")}
              onOffer={() => openAddOffer()}
              onOffresCompletes={markOffresCompletes}
              onErreurs={openErreursDialog}
              onNote={() => setNoteOpen(true)}
              onDoc={() => fileRef.current?.click()}
              onConclusion={markConclusion}
              onSendClient={() => runAction("envoyer-client", {}, "Offre envoyée au client")}
              onSignature={(signed) => { setSignatureMode(signed); setSignatureOpen(true); }}
              onCancel={() => setCancelOpen(true)}
              onRestore={restoreDemande}
              onDelete={deleteDemande}
            />
          </div>
        )}

        {editable && <History entries={demande.historique || []} />}
      </div>

      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Annuler cette offre / demande ?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            La demande passera au statut « Demande annulée ». Toutes les données sont conservées ;
            vous pourrez ensuite la restaurer en brouillon, ou la supprimer définitivement si besoin.
          </p>
          <Field label="Motif (optionnel)">
            <Textarea
              rows={3}
              value={cancelComment}
              onChange={(e) => setCancelComment(e.target.value)}
              placeholder="Ex. : client n'est plus intéressé, doublon, erreur de saisie…"
            />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)}>Retour</Button>
            <Button
              className="bg-rose-700 hover:bg-rose-800"
              onClick={confirmCancel}
              disabled={actionBusy}
            >
              Confirmer l&apos;annulation
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={incompleteOpen} onOpenChange={setIncompleteOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Notifier l&apos;offre incomplète</DialogTitle></DialogHeader>
          {incompleteCompagnie && (
            <p className="text-sm text-slate-600">Compagnie : <strong>{incompleteCompagnie}</strong></p>
          )}
          <Field label="Message au conseiller" required>
            <Textarea rows={4} value={incompleteComment} onChange={(e) => setIncompleteComment(e.target.value)} placeholder="Ex. : Il manque le questionnaire médical signé et le justificatif de domicile…" />
          </Field>
          <Field label="Types d'erreurs (catalogue)">
            <div className="space-y-2">
              {ERREURS_INCOMPLETE_CATALOG.map((err) => {
                const state = incompleteErreurs[err.code] || {};
                return (
                  <div key={err.code} className={`rounded-md border p-2.5 ${state.checked ? "border-[#002FA7]/40 bg-[#002FA7]/5" : "border-border"}`}>
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        className="accent-[#002FA7]"
                        checked={Boolean(state.checked)}
                        onChange={(e) => setIncompleteErreurs((prev) => ({
                          ...prev,
                          [err.code]: { ...prev[err.code], checked: e.target.checked, detail: prev[err.code]?.detail || "" },
                        }))}
                      />
                      <span className="font-medium">{err.label}</span>
                      <span className="text-[10px] text-muted-foreground font-mono">{err.code}</span>
                    </label>
                    {state.checked && (
                      <Input
                        className="mt-2 h-8 text-sm"
                        placeholder="Précision (optionnel)…"
                        value={state.detail || ""}
                        onChange={(e) => setIncompleteErreurs((prev) => ({
                          ...prev,
                          [err.code]: { ...prev[err.code], checked: true, detail: e.target.value },
                        }))}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </Field>
          <Field label="Documents manquants">
            <Textarea rows={2} value={incompleteDocs} onChange={(e) => setIncompleteDocs(e.target.value)} placeholder="Liste des documents à transmettre…" />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIncompleteOpen(false)}>Annuler</Button>
            <Button onClick={markIncomplete} disabled={actionBusy} className="bg-[#002FA7] hover:bg-[#00248a]">
              <Mail className="h-4 w-4 mr-2" /> Envoyer au conseiller
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Note interne</DialogTitle></DialogHeader>
          <Field label="Note (interne uniquement)" required>
            <Textarea rows={4} value={noteText} onChange={(e) => setNoteText(e.target.value)} placeholder="Commentaire visible uniquement par les gestionnaires…" />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNoteOpen(false)}>Annuler</Button>
            <Button onClick={addInternalNote} disabled={actionBusy}>Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={offresCompletesOpen} onOpenChange={setOffresCompletesOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Offres complètes</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Le statut passera à « Offres complètes » et l&apos;agent créateur recevra un e-mail avec un lien vers la demande.
          </p>
          <Field label="Note / message pour l'agent (optionnel)">
            <Textarea
              rows={4}
              value={offresCompletesNote}
              onChange={(e) => setOffresCompletesNote(e.target.value)}
              placeholder="Ex. : Les offres Zurich et Helvetia sont prêtes à présenter au client…"
              data-testid="offres-completes-note"
            />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOffresCompletesOpen(false)}>Annuler</Button>
            <Button
              className="bg-emerald-600 hover:bg-emerald-700"
              onClick={confirmOffresCompletes}
              disabled={actionBusy}
              data-testid="offres-completes-confirm"
            >
              <Mail className="h-4 w-4 mr-2" /> Confirmer et notifier
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={erreursOpen} onOpenChange={setErreursOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Signaler des erreurs</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Sélectionnez les champs concernés. Chaque erreur sera comptabilisée pour l&apos;agent qui a créé la demande.
          </p>
          <Field label="Champs en erreur">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto pr-1">
              {erreursChecklist.map((item) => {
                const checked = Boolean(erreursSelected[item.code]);
                return (
                  <label
                    key={item.code}
                    className={`flex items-center gap-2 rounded-md border p-2.5 text-sm cursor-pointer ${checked ? "border-rose-400 bg-rose-50" : "border-border"}`}
                  >
                    <input
                      type="checkbox"
                      className="accent-rose-700"
                      checked={checked}
                      onChange={(e) => setErreursSelected((prev) => ({
                        ...prev,
                        [item.code]: e.target.checked,
                      }))}
                    />
                    <span>{item.label}</span>
                  </label>
                );
              })}
            </div>
          </Field>
          <Field label="Commentaire (optionnel)">
            <Textarea
              rows={2}
              value={erreursComment}
              onChange={(e) => setErreursComment(e.target.value)}
              placeholder="Précision éventuelle…"
            />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setErreursOpen(false)}>Annuler</Button>
            <Button
              className="bg-rose-700 hover:bg-rose-800"
              onClick={confirmErreurs}
              disabled={actionBusy}
              data-testid="erreurs-confirm"
            >
              Enregistrer les erreurs
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={offerOpen} onOpenChange={setOfferOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {offer._mode === "add-docs" ? `Ajouter des documents — ${offer.compagnie || "offre"}` : "Enregistrer une offre compagnie"}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {offer._mode !== "add-docs" && (
              <>
                <Field label="Compagnie" required>
                  <Choice value={offer.compagnie} onChange={(v) => setOffer({ ...offer, compagnie: v })} options={meta.compagnies || COMPAGNIES_DEFAUT} />
                </Field>
                <Field label="Date de réception" required>
                  <Input type="date" value={offer.date_reception} onChange={(e) => setOffer({ ...offer, date_reception: e.target.value })} />
                </Field>
                <Field label="Référence"><Input value={offer.reference} onChange={(e) => setOffer({ ...offer, reference: e.target.value })} /></Field>
                <Field label="Montant (CHF)"><Input type="number" value={offer.montant_prime} onChange={(e) => setOffer({ ...offer, montant_prime: e.target.value })} /></Field>
                <Field label="Type de contrat"><Input value={offer.type_contrat} onChange={(e) => setOffer({ ...offer, type_contrat: e.target.value })} /></Field>
                <Field label="Durée"><Input value={offer.duree} onChange={(e) => setOffer({ ...offer, duree: e.target.value })} /></Field>
                <Field label="Garanties" className="sm:col-span-2"><Textarea value={offer.garanties} onChange={(e) => setOffer({ ...offer, garanties: e.target.value })} /></Field>
              </>
            )}
            <Field label="Documents de l'offre" className="sm:col-span-2">
              <Input
                type="file"
                multiple
                onChange={(e) => setOffer({ ...offer, files: Array.from(e.target.files || []) })}
              />
              {Array.isArray(offer.files) && offer.files.length > 0 && (
                <ul className="mt-2 text-xs text-slate-600 space-y-0.5">
                  {offer.files.map((f) => (
                    <li key={`${f.name}-${f.size}`}>{f.name}</li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] text-muted-foreground mt-1">
                Plusieurs fichiers possibles. Les documents déjà enregistrés ne sont jamais remplacés.
              </p>
            </Field>
            {offer._mode !== "add-docs" && (
              <Field label="Commentaires" className="sm:col-span-2">
                <Textarea value={offer.commentaires} onChange={(e) => setOffer({ ...offer, commentaires: e.target.value })} />
              </Field>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOfferOpen(false)}>Annuler</Button>
            <Button onClick={addOffer} disabled={actionBusy}>
              {offer._mode === "add-docs" ? "Ajouter les documents" : "Enregistrer l'offre reçue"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={signatureOpen} onOpenChange={setSignatureOpen}>
        <DialogContent><DialogHeader><DialogTitle>{signatureMode ? "Enregistrer l'offre signée" : "Enregistrer l'offre non signée"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Field label={signatureMode ? "Date de signature" : "Date de décision"}><Input type="date" value={signature.date_signature} onChange={(e) => setSignature({ ...signature, date_signature: e.target.value })} /></Field>
            {!signatureMode && <Field label="Date de relance"><Input type="date" value={signature.date_relance} onChange={(e) => setSignature({ ...signature, date_relance: e.target.value })} /></Field>}
            <Field label="Commentaire"><Textarea value={signature.commentaire} onChange={(e) => setSignature({ ...signature, commentaire: e.target.value })} /></Field>
            <Field label="Document signé"><Input type="file" onChange={(e) => setSignature({ ...signature, file: e.target.files?.[0] || null })} /></Field>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setSignatureOpen(false)}>Annuler</Button><Button onClick={recordSignature} disabled={actionBusy}>Enregistrer</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}

function companyStatusStyle(statut) {
  const s = String(statut || "").toLowerCase();
  if (s.includes("incompl")) return "bg-rose-100 text-rose-900 ring-1 ring-rose-300";
  if (s.includes("reçue") || s.includes("recue") || s.includes("complète") || s.includes("complete") || s.includes("retenue") || s.includes("choisie")) {
    return "bg-violet-100 text-violet-900 ring-1 ring-violet-300";
  }
  return "bg-amber-50 text-amber-900 ring-1 ring-amber-200";
}

function companyStatusLabel(statut) {
  const s = String(statut || "").trim();
  const low = s.toLowerCase();
  if (low.includes("incompl")) return s || "Incomplète";
  if (low.includes("retenue") || low.includes("choisie") || low.includes("reçue") || low.includes("recue") || low.includes("complète") || low.includes("complete")) {
    return "🟢 Offre reçue";
  }
  return s || "En attente";
}

function CompanyResponsesPanel({
  cards, canProcess, busy,
  onAddOffer, onAddDocs, onMarkIncomplete, onNotifyIncomplete, onDeleteDoc,
}) {
  return (
    <Card className="p-5" data-testid="reponses-compagnies">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h2 className="font-display font-bold flex items-center gap-2 tracking-wide">
          <Paperclip className="h-5 w-5 text-[#002FA7]" /> RÉPONSES DES COMPAGNIES
        </h2>
        <span className="text-xs text-muted-foreground">{cards.length} compagnie(s)</span>
      </div>
      {!cards.length ? (
        <p className="text-sm text-muted-foreground">Aucune compagnie sollicitée sur cette demande.</p>
      ) : (
        <div className="space-y-3">
          {cards.map((card) => {
            const incomplete = String(card.statut || "").toLowerCase().includes("incompl");
            const pending = !card.has_offre && !incomplete;
            const docs = card.documents || [];
            return (
              <div
                key={`${card.compagnie}-${card.offre_id || card.index}`}
                className="rounded-lg border p-4 border-border"
              >
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-semibold text-base">{card.compagnie || "Compagnie"}</p>
                      <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${companyStatusStyle(card.statut)}`}>
                        {companyStatusLabel(card.statut)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {card.date_reception
                        ? `Réception : ${formatDateFr(card.date_reception)}`
                        : "En attente de réponse"}
                      {card.reference ? ` · Réf. ${card.reference}` : ""}
                    </p>
                    {(card.montant_prime != null && card.montant_prime !== "") && (
                      <p className="text-sm mt-1.5">
                        {formatChf(card.montant_prime)}
                        {card.duree ? ` · ${card.duree}` : ""}
                        {card.type_contrat ? ` · ${card.type_contrat}` : ""}
                      </p>
                    )}
                    {card.garanties && (
                      <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{card.garanties}</p>
                    )}
                  </div>
                  {canProcess && (
                    <div className="flex flex-col gap-1.5 shrink-0">
                      {pending && (
                        <Button size="sm" className="bg-violet-700 hover:bg-violet-800" disabled={busy} onClick={() => onAddOffer(card.compagnie)}>
                          Offre reçue
                        </Button>
                      )}
                      {card.has_offre && card.offre_id && (
                        <Button size="sm" variant="outline" disabled={busy} onClick={() => onAddDocs(card)}>
                          <Plus className="h-3.5 w-3.5 mr-1" /> Document
                        </Button>
                      )}
                      {!incomplete && (
                        <Button size="sm" variant="outline" className="border-rose-300 text-rose-800" disabled={busy} onClick={() => onMarkIncomplete(card.compagnie)}>
                          Marquer incomplète
                        </Button>
                      )}
                      {incomplete && (
                        <Button size="sm" variant="outline" className="border-rose-300 text-rose-800" disabled={busy} onClick={() => onNotifyIncomplete(card.compagnie)}>
                          <Mail className="h-3.5 w-3.5 mr-1" /> Notifier l&apos;offre incomplète
                        </Button>
                      )}
                    </div>
                  )}
                </div>

                <div className="mt-3 border-t pt-3">
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground font-semibold mb-2">Documents</p>
                  {!docs.length ? (
                    <p className="text-xs text-muted-foreground">Aucun document pour cette compagnie.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {docs.map((doc) => (
                        <li key={doc.id || doc.original_filename} className="flex items-center gap-2 text-sm rounded-md border px-2.5 py-1.5 bg-white/80">
                          <FileText className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-medium">{doc.original_filename || "Document"}</p>
                            <p className="text-[10px] text-muted-foreground">
                              {doc.content_type || "fichier"}
                              {doc.created_at ? ` · ${formatDateTimeFr(doc.created_at)}` : ""}
                            </p>
                          </div>
                          {doc.id && (
                            <>
                              <Button size="icon" variant="ghost" title="Ouvrir" onClick={() => openAuthenticatedBlob(`/demandes-offres/documents/${doc.id}/download`)}>
                                <ExternalLink className="h-4 w-4" />
                              </Button>
                              <Button size="icon" variant="ghost" title="Télécharger" onClick={() => downloadAuthenticatedBlob(`/demandes-offres/documents/${doc.id}/download`, doc.original_filename)}>
                                <Download className="h-4 w-4" />
                              </Button>
                              {canProcess && card.offre_id && (
                                <Button size="icon" variant="ghost" title="Supprimer" className="text-rose-700" disabled={busy} onClick={() => onDeleteDoc(card.offre_id, doc)}>
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              )}
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function WizardProgress({ step, onStep }) {
  return <div className="overflow-x-auto"><div className="flex min-w-[780px]">
    {STEPS.map((name, index) => <button key={name} onClick={() => onStep(index)} className="flex-1 flex items-center group">
      <span className={`h-8 w-8 rounded-full shrink-0 flex items-center justify-center text-xs font-bold ${index <= step ? "bg-[#002FA7] text-white" : "bg-secondary text-muted-foreground"}`}>
        {index < step ? <Check className="h-4 w-4" /> : index + 1}
      </span>
      <span className={`ml-2 text-xs font-medium whitespace-nowrap ${index === step ? "text-[#002FA7]" : "text-muted-foreground"}`}>{name}</span>
      {index < STEPS.length - 1 && <span className={`mx-3 h-px flex-1 ${index < step ? "bg-[#002FA7]" : "bg-border"}`} />}
    </button>)}
  </div></div>;
}

function applyHubClientToOffreForm(client, setValue, form) {
  if (!client) {
    setValue("client_id", null);
    return;
  }
  setValue("client_id", client.id);
  setValue("type_client", "existant");
  setValue("civilite", client.civilite || client.sexe || form.civilite || "");
  setValue("prenom", client.prenom || "");
  setValue("nom", client.nom || "");
  setValue("sexe", client.sexe || form.sexe || "");
  setValue("date_naissance", toSwissDate(client.date_naissance) || "");
  setValue("nationalite", client.nationalite || form.nationalite || "");
  setValue("adresse", client.adresse || "");
  setValue("npa", client.npa || "");
  setValue("ville", client.ville || "");
  setValue("pays", client.pays_residence || client.pays || form.pays || "Suisse");
  if (client.etat_civil) setValue("situation", client.etat_civil);
  if (client.profession) setValue("profession", client.profession);
  if (client.employeur) setValue("employeur", client.employeur);
  if (client.email) setValue("email", client.email);
  if (client.telephone) setValue("telephone", client.telephone);
}

/** Liaison client hub + préremplissage adresse/identité dans le payload schéma. */
function SchemaClientLinker({ form, setValue, schema, formPayload, onPrefillPayload }) {
  const linked = Boolean(form.client_id);
  const searchTerm = [form.prenom, form.nom].map((s) => (s || "").trim()).filter(Boolean).join(" ");

  const pick = (client) => {
    if (!client) {
      setValue("client_id", null);
      return;
    }
    setValue("client_id", client.id);
    setValue("type_client", "existant");
    setValue("prenom", client.prenom || form.prenom || "");
    setValue("nom", client.nom || form.nom || "");
    setValue("adresse", client.adresse || "");
    setValue("npa", client.npa || "");
    setValue("ville", client.ville || "");
    setValue("pays", client.pays_residence || client.pays || "Suisse");
    const next = prefillSchemaPayloadFromClient(schema, formPayload, {
      ...client,
      date_naissance: toSwissDate(client.date_naissance) || client.date_naissance,
    }, { overwrite: false });
    onPrefillPayload(next);
  };

  return (
    <div className="space-y-3">
      <SectionTitle
        title="Client & adresse"
        subtitle="Liez un client LeoSoft pour préremplir l'adresse (modifiable dans le formulaire)."
      />
      {linked ? (
        <div className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-900">
          <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-emerald-700" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold">Client existant lié</p>
            <p className="text-emerald-800/90">
              {form.prenom} {form.nom}
              {form.adresse ? ` — ${[form.adresse, form.npa, form.ville].filter(Boolean).join(", ")}` : ""}
            </p>
          </div>
          <button type="button" onClick={() => pick(null)} className="shrink-0 inline-flex items-center gap-1 text-xs text-emerald-800 hover:underline">
            <X className="h-3.5 w-3.5" /> Dissocier
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Rechercher un client (prénom)">
            <ClientSuggestInput
              value={form.prenom || ""}
              onChange={(e) => setValue("prenom", e.target.value)}
              searchTerm={searchTerm}
              onSelectClient={pick}
              enabled={form.type_client !== "nouveau"}
              placeholder="Ex. Jean"
            />
          </Field>
          <Field label="Nom">
            <ClientSuggestInput
              value={form.nom || ""}
              onChange={(e) => setValue("nom", e.target.value)}
              searchTerm={searchTerm}
              onSelectClient={pick}
              enabled={form.type_client !== "nouveau"}
              placeholder="Ex. Dupont"
            />
          </Field>
        </div>
      )}
    </div>
  );
}

function TypeClientField({ value, onChange }) {
  return (
    <div className="space-y-2">
      <SectionTitle title="Type de client" subtitle="Indiquez si le preneur est déjà client ou nouveau." />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {TYPES_CLIENT.map((opt) => {
          const active = value === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => onChange(opt.id)}
              className={`rounded-md border px-3 py-2.5 text-sm text-left transition ${
                active
                  ? "border-[#002FA7] bg-[#002FA7]/5 text-[#002FA7] font-semibold ring-1 ring-[#002FA7]/30"
                  : "border-border hover:border-[#002FA7]/40"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ClientStep({ form, setValue, onPickClient, finmaWarning, canManageUsers }) {
  const linked = Boolean(form.client_id);
  const searchTerm = [form.prenom, form.nom].map((s) => (s || "").trim()).filter(Boolean).join(" ");
  const suppressSuggest = linked; // une fois lié, pas de liste tant qu'on ne dissocie pas

  const selectClient = (client) => {
    onPickClient(client);
  };

  const unlink = () => {
    onPickClient(null);
  };

  const onIdentityChange = (key, value) => {
    setValue(key, value);
    // Taper à nouveau après liaison → on libère le client_id pour permettre un autre choix
    if (form.client_id) {
      setValue("client_id", null);
    }
  };

  const onTypeClient = (v) => {
    setValue("type_client", v);
    if (v === "nouveau" && form.client_id) {
      setValue("client_id", null);
    }
  };

  return (
    <div className="space-y-6">
      <TypeClientField value={form.type_client || ""} onChange={onTypeClient} />

      <SectionTitle
        title="Preneur d'assurance"
        subtitle="Tapez un nom ou un prénom : suggestions en direct depuis la base Clients."
      />

      {linked && (
        <div
          className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-900"
          data-testid="offre-client-linked-banner"
        >
          <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-emerald-700" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold">Client existant lié</p>
            <p className="text-emerald-800/90">
              {form.prenom} {form.nom}
              {form.date_naissance ? ` — ${formatDateFr(form.date_naissance)}` : ""}
              {" · "}demande rattachée (pas de doublon).
            </p>
          </div>
          <button
            type="button"
            onClick={unlink}
            className="shrink-0 inline-flex items-center gap-1 text-xs text-emerald-800 hover:underline"
            title="Dissocier"
          >
            <X className="h-3.5 w-3.5" /> Dissocier
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Field label="Civilité" required>
          <Choice value={form.civilite} onChange={(v) => setValue("civilite", v)} options={CIVILITES} />
        </Field>
        <Field label="Prénom" required>
          <ClientSuggestInput
            value={form.prenom}
            onChange={(e) => onIdentityChange("prenom", e.target.value)}
            searchTerm={searchTerm}
            onSelectClient={selectClient}
            enabled={!suppressSuggest && form.type_client !== "nouveau"}
            data-testid="offre-prenom"
            placeholder="Ex. Jean"
          />
        </Field>
        <Field label="Nom" required>
          <ClientSuggestInput
            value={form.nom}
            onChange={(e) => onIdentityChange("nom", e.target.value)}
            searchTerm={searchTerm}
            onSelectClient={selectClient}
            enabled={!suppressSuggest && form.type_client !== "nouveau"}
            data-testid="offre-nom"
            placeholder="Ex. Dupont"
          />
        </Field>
        <Field label="Sexe">
          <Choice value={form.sexe} onChange={(v) => setValue("sexe", v)} options={SEXES} />
        </Field>
        <Field label="Date de naissance" required>
          <Input
            type="text"
            inputMode="numeric"
            placeholder="jj.mm.aaaa"
            value={form.date_naissance}
            onChange={(e) => setValue("date_naissance", e.target.value)}
            data-testid="offre-date-naissance"
          />
        </Field>
        <Field label="Nationalité">
          <Input value={form.nationalite} onChange={(e) => setValue("nationalite", e.target.value)} />
        </Field>
        <Field label="Permis">
          <Input value={form.permis} onChange={(e) => setValue("permis", e.target.value)} />
        </Field>
        <Field label="Adresse" required className="sm:col-span-2">
          <Input value={form.adresse} onChange={(e) => setValue("adresse", e.target.value)} />
        </Field>
        <Field label="NPA" required>
          <Input value={form.npa} onChange={(e) => setValue("npa", e.target.value)} />
        </Field>
        <Field label="Ville" required>
          <Input value={form.ville} onChange={(e) => setValue("ville", e.target.value)} />
        </Field>
        <Field label="Pays" required>
          <Input value={form.pays} onChange={(e) => setValue("pays", e.target.value)} />
        </Field>
      </div>

      <SectionTitle
        title="Agent"
        subtitle="Renseigné automatiquement depuis votre profil (non modifiable)."
      />
      {finmaWarning ? (
        <div
          className="rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-950"
          data-testid="offre-finma-missing-warning"
        >
          <p className="font-semibold text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" /> Numéro FINMA manquant
          </p>
          <p className="text-sm mt-1">{finmaWarning}</p>
          {canManageUsers ? (
            <p className="text-sm mt-2">
              <Link to="/utilisateurs" className="underline font-medium">
                Ouvrir Utilisateurs
              </Link>
              {" "}pour compléter le N° FINMA sur votre profil.
            </p>
          ) : (
            <p className="text-sm mt-2">
              Contactez un administrateur pour renseigner votre N° FINMA dans Utilisateurs.
            </p>
          )}
        </div>
      ) : null}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Prénom de l'agent" required>
          <Input
            value={form.agent_prenom}
            readOnly
            disabled
            className="bg-slate-50 text-slate-700"
            data-testid="offre-agent-prenom"
            data-agent-locked="true"
          />
        </Field>
        <Field label="Nom de l'agent" required>
          <Input
            value={form.agent_nom}
            readOnly
            disabled
            className="bg-slate-50 text-slate-700"
            data-testid="offre-agent-nom"
            data-agent-locked="true"
          />
        </Field>
        <Field label="E-mail de l'agent" required>
          <Input
            type="email"
            value={form.agent_email}
            readOnly
            disabled
            className="bg-slate-50 text-slate-700"
            data-testid="offre-agent-email"
            data-agent-locked="true"
          />
        </Field>
        <Field label="N° FINMA" required>
          <Input
            value={form.agent_finma}
            readOnly
            disabled
            className="bg-slate-50 text-slate-700"
            data-testid="offre-agent-finma"
            data-agent-locked="true"
          />
        </Field>
      </div>
    </div>
  );
}

function CompagniesStep({ form, toggle, meta }) {
  return (
    <div className="space-y-6">
      <SectionTitle title="Compagnies à consulter" subtitle="Sélectionnez les compagnies pour lesquelles une variante d'offre est sollicitée." />
      <Field label="Compagnies" required>
        <CheckGrid options={meta.compagnies || COMPAGNIES_DEFAUT} selected={form.compagnies || []} onToggle={toggle} />
      </Field>
      {!form.compagnies?.length && (
        <p className="text-sm text-rose-700">Au moins une compagnie est obligatoire.</p>
      )}
    </div>
  );
}

function SituationStep({ form, setValue, toggle, meta }) {
  return <div className="space-y-6">
    <SectionTitle title="Situation personnelle et professionnelle" subtitle="Informations nécessaires à l'analyse du risque." />
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <Field label="Statut professionnel" required><Choice value={form.statut_professionnel} onChange={(v) => setValue("statut_professionnel", v)} options={meta.statuts_professionnels || STATUTS_PRO} /></Field>
      <Field label="Profession"><Input value={form.profession} onChange={(e) => setValue("profession", e.target.value)} /></Field>
      <Field label="Situation familiale"><Choice value={form.situation} onChange={(v) => setValue("situation", v)} options={meta.situations || SITUATIONS} /></Field>
      <Field label="Travail de bureau à 80 %"><Choice value={form.travail_bureau_80} onChange={(v) => setValue("travail_bureau_80", v)} options={OUI_NON} /></Field>
      <Field label="Affilié(e) LPP"><Choice value={form.affilie_lpp} onChange={(v) => setValue("affilie_lpp", v)} options={OUI_NON} /></Field>
      <Field label="Fumeur / fumeuse"><Choice value={form.fumeur} onChange={(v) => setValue("fumeur", v)} options={OUI_NON} /></Field>
      <Field label="Diplôme"><Input value={form.diplome} onChange={(e) => setValue("diplome", e.target.value)} /></Field>
      <Field label="Taille (cm)"><Input type="number" value={form.taille} onChange={(e) => setValue("taille", e.target.value)} /></Field>
      <Field label="Poids (kg)"><Input type="number" value={form.poids} onChange={(e) => setValue("poids", e.target.value)} /></Field>
    </div>
    <label className="flex items-center gap-3 rounded-md border p-3 cursor-pointer">
      <input type="checkbox" checked={form.activites_risque} onChange={(e) => setValue("activites_risque", e.target.checked)} className="accent-[#002FA7]" />
      <span className="text-sm font-medium">Le client pratique une ou plusieurs activités à risque</span>
    </label>
    {form.activites_risque && <Field label="Activités pratiquées" required><CheckGrid options={meta.activites_risque || ACTIVITES_RISQUE} selected={form.activites_risque_liste || []} onToggle={toggle} /></Field>}
  </div>;
}

function PilierStep({ form, setValue, meta }) {
  return <div className="space-y-6">
    <SectionTitle title="Caractéristiques du 3e pilier" subtitle="Paramètres de l'offre à solliciter." />
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <Field label="Type de pilier" required><Choice value={form.type_pilier} onChange={(v) => setValue("type_pilier", v)} options={meta.types_pilier || TYPES_PILIER} /></Field>
      <Field label="Date de début"><Input type="date" value={form.date_debut} onChange={(e) => setValue("date_debut", e.target.value)} /></Field>
      <Field label="Périodicité" required><Choice value={form.periodicite_prime} onChange={(v) => setValue("periodicite_prime", v)} options={meta.periodicites || PERIODICITES} /></Field>
      <Field label="Montant de la prime (CHF)" required><Input type="number" min="0" value={form.montant_prime} onChange={(e) => setValue("montant_prime", e.target.value)} /></Field>
      <Field label="Déjà des piliers PAX"><Choice value={form.deja_piliers_pax} onChange={(v) => setValue("deja_piliers_pax", v)} options={OUI_NON} /></Field>
      <Field label="Type de paiement"><Choice value={form.type_paiement} onChange={(v) => setValue("type_paiement", v)} options={meta.types_paiement || TYPES_PAIEMENT} /></Field>
      <Field label="Durée du contrat"><Input value={form.duree_contrat} onChange={(e) => setValue("duree_contrat", e.target.value)} /></Field>
      <Field label="Âge au terme"><Input type="number" value={form.age_terme} onChange={(e) => setValue("age_terme", e.target.value)} /></Field>
      <Field label="Exonération des primes"><Choice value={form.exoneration_primes} onChange={(v) => setValue("exoneration_primes", v)} options={meta.exonerations || EXONERATIONS} /></Field>
      <Field label="Rente d'invalidité"><Input value={form.rente_invalidite} onChange={(e) => setValue("rente_invalidite", e.target.value)} /></Field>
      <Field label="Adaptation automatique des primes"><Choice value={form.adaptation_auto_primes} onChange={(v) => setValue("adaptation_auto_primes", v)} options={OUI_NON} /></Field>
      <Field label="Risque pur"><Choice value={form.risque_pur} onChange={(v) => setValue("risque_pur", v)} options={OUI_NON} /></Field>
      <Field label="Langue de l'offre" required><Choice value={form.langue_offre} onChange={(v) => setValue("langue_offre", v)} options={meta.langues || LANGUES} /></Field>
      <Field label="Prochain rendez-vous"><Input type="date" value={form.date_prochain_rdv} onChange={(e) => setValue("date_prochain_rdv", e.target.value)} /></Field>
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <label className="flex items-center gap-3 border rounded-md p-3"><input type="checkbox" checked={form.inclure_cga} onChange={(e) => setValue("inclure_cga", e.target.checked)} className="accent-[#002FA7]" /><span className="text-sm">Inclure les CGA</span></label>
      <label className="flex items-center gap-3 border rounded-md p-3"><input type="checkbox" checked={form.mandat_gestion} onChange={(e) => setValue("mandat_gestion", e.target.checked)} className="accent-[#002FA7]" /><span className="text-sm">Mandat de gestion</span></label>
    </div>
    <Field label="Renseignements complémentaires"><Textarea rows={3} value={form.renseignements_complementaires} onChange={(e) => setValue("renseignements_complementaires", e.target.value)} /></Field>
    <Field label="Commentaires"><Textarea rows={3} value={form.commentaires} onChange={(e) => setValue("commentaires", e.target.value)} /></Field>
  </div>;
}

function Documents({ demande, canEdit, uploading, fileRef, upload, remove }) {
  const docs = demande.documents || [];
  return <div className="space-y-4">
    <div className="flex items-start justify-between gap-3">
      <SectionTitle title="Documents" subtitle="Pièces jointes, mandats et offres liés à cette demande." />
      {canEdit && <><input ref={fileRef} type="file" className="hidden" onChange={upload} />
        <Button size="sm" onClick={() => fileRef.current?.click()} disabled={uploading} className="bg-[#002FA7] hover:bg-[#00248a]">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Plus className="h-4 w-4 mr-1" />} Ajouter
        </Button></>}
    </div>
    {!docs.length ? <p className="border border-dashed rounded-md p-8 text-center text-sm text-muted-foreground">Aucun document ajouté.</p> :
      <div className="space-y-2">{docs.map((doc) => <div key={doc.id} className="flex items-center justify-between gap-3 border rounded-md p-3">
        <div className="flex items-center gap-3 min-w-0"><FileText className="h-5 w-5 text-[#002FA7] shrink-0" /><div className="min-w-0">
          <p className="text-sm font-medium truncate">{doc.original_filename}</p><p className="text-xs text-muted-foreground">{doc.category} · {formatDateFr(doc.created_at)}</p>
        </div></div>
        <div className="flex gap-1 shrink-0">
          <Button size="icon" variant="ghost" title="Ouvrir" onClick={() => openAuthenticatedBlob(`/demandes-offres/documents/${doc.id}/download`)}><ExternalLink className="h-4 w-4" /></Button>
          <Button size="icon" variant="ghost" title="Télécharger" onClick={() => downloadAuthenticatedBlob(`/demandes-offres/documents/${doc.id}/download`, doc.original_filename)}><Download className="h-4 w-4" /></Button>
          {canEdit && <Button size="icon" variant="ghost" className="text-rose-600" title="Supprimer" onClick={() => remove(doc)}><Trash2 className="h-4 w-4" /></Button>}
        </div>
      </div>)}</div>}
  </div>;
}

function Verification({ form, missing, demande }) {
  const items = [
    ["Type client", typeClientLabel(form.type_client)],
    ["Client", `${form.civilite} ${form.prenom} ${form.nom}`.trim()],
    ["Naissance", formatDateFr(form.date_naissance)],
    ["Adresse", [form.adresse, form.npa, form.ville, form.pays].filter(Boolean).join(", ")],
    ["Situation", [form.statut_professionnel, form.profession].filter(Boolean).join(" · ")],
    ["3e pilier", `${form.type_pilier} · ${form.periodicite_prime}`],
    ["Prime", formatChf(form.montant_prime)],
    ["Compagnies", form.compagnies?.join(", ")],
    ["Agent", `${form.agent_prenom} ${form.agent_nom} · ${form.agent_email}`],
  ];
  return <div className="space-y-5">
    <SectionTitle title="Vérification" subtitle={`Contrôlez la demande ${demande.numero} avant envoi.`} />
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{items.map(([label, value]) =>
      <div key={label} className="rounded-md border p-3"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p><p className="text-sm font-medium mt-1">{value || "—"}</p></div>)}
    </div>
    {missing.length ? <div className="rounded-md border border-rose-200 bg-rose-50 p-4">
      <p className="font-semibold text-sm text-rose-800 flex items-center gap-2"><XCircle className="h-4 w-4" /> Éléments à compléter ({missing.length})</p>
      <ul className="mt-2 grid sm:grid-cols-2 gap-1 text-sm text-rose-700 list-disc list-inside">{missing.map((item) => <li key={item}>{item}</li>)}</ul>
    </div> : <div className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800 flex gap-2"><CheckCircle2 className="h-5 w-5" /> La demande est complète et prête à être envoyée.</div>}
  </div>;
}

function DemandeResumeCard({ demande, schema }) {
  const { rows, docs } = buildDemandeResume(demande, { schema });
  return (
    <Card className="p-5 sm:p-6 space-y-5" data-testid="demande-offre-resume">
      <div>
        <h2 className="font-display font-bold text-xl text-[#002FA7]">Résumé de la demande</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Informations renseignées et pertinentes pour l&apos;offre. Le formulaire complet reste accessible séparément.
        </p>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucune information renseignée.</p>
      ) : (
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
          {rows.map((r) => (
            <div key={r.label} className={r.label === "Commentaires / informations complémentaires" || r.label === "Note / commentaires" || r.label === "Options demandées" || r.label === "Adresse" || String(r.label || "").includes("— précision") ? "sm:col-span-2" : ""}>
              <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{r.label}</dt>
              <dd className="text-sm mt-1 whitespace-pre-wrap text-slate-900">{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {docs.length > 0 && (
        <div className="border-t pt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Documents transmis ({docs.length})
          </p>
          <ul className="space-y-1.5">
            {docs.map((d) => (
              <li key={d.id || d.name} className="text-sm flex items-center gap-2">
                <FileText className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span>{d.name}</span>
                {d.category ? <span className="text-xs text-muted-foreground">· {d.category}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function ReadOnlyData({ data }) {
  const sections = [
    ["Client", [["Type", typeClientLabel(data.type_client)], ["Identité", `${data.civilite} ${data.prenom} ${data.nom}`], ["Naissance", formatDateFr(data.date_naissance)], ["Adresse", [data.adresse, data.npa, data.ville, data.pays].filter(Boolean).join(", ")], ["Nationalité", data.nationalite]]],
    ["Situation", [["Statut", data.statut_professionnel], ["Profession", data.profession], ["Situation familiale", data.situation], ["Fumeur", data.fumeur], ["Activités à risque", data.activites_risque_liste?.join(", ")]]],
    ["3e pilier", [["Type", data.type_pilier], ["Prime", `${formatChf(data.montant_prime)} · ${data.periodicite_prime || "—"}`], ["Compagnies", data.compagnies?.join(", ")], ["Paiement", data.type_paiement], ["Langue", data.langue_offre]]],
    ["Agent", [["Conseiller", data.agent_label], ["E-mail", data.agent_email], ["FINMA", data.agent_finma], ["Commentaires", data.commentaires]]],
  ];
  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">{sections.map(([title, rows]) =>
    <Card key={title} className="p-5"><h2 className="font-display font-bold text-[#002FA7] mb-4">{title}</h2><dl className="space-y-3">{rows.map(([label, value]) =>
      <div key={label}><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="text-sm mt-0.5 whitespace-pre-wrap">{value || "—"}</dd></div>)}</dl></Card>)}</div>;
}

function ActionPanel({
  demande, canEdit, canProcess, canFollowSignature, busy, hasOffers, hasIncompleteCompany,
  onIncomplete, onOffer, onOffresCompletes, onErreurs, onNote, onDoc, onConclusion, onSendClient, onSignature, onCancel, onRestore, onDelete,
}) {
  const terminal = ["Offre signée", "Demande annulée", "Offre refusée"].includes(demande.statut);
  const canSendClient = hasOffers || demande.offre;
  const offresCompletes = ["Offres complètes", "Offre complète"].includes(demande.statut);
  const signatureReady = ["Offre envoyée au client", "Offre reçue", "Offres complètes", "Offre complète", "Offre choisie", "En conclusion", "Demande envoyée"].includes(demande.statut)
    || (hasOffers && !["Brouillon", "Demande annulée", "Offre refusée"].includes(demande.statut));
  const showProcess = Boolean(canProcess);
  const showConseillerFollowup = Boolean(canEdit) && !showProcess;
  const showSignature = Boolean(canFollowSignature) && signatureReady && demande.statut !== "Offre signée";
  const canCancel = (canEdit || canProcess) && !terminal && demande.statut !== "Offre signée";
  const canRestore = (canEdit || canProcess) && demande.statut === "Demande annulée";
  const canDeleteHard = (canEdit || canProcess) && ["Brouillon", "Demande annulée"].includes(demande.statut);
  if (!showProcess && !showConseillerFollowup && !canEdit && !showSignature) return null;
  return <Card className="p-5 space-y-3 sticky top-20">
    <h2 className="font-display font-bold flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-[#002FA7]" /> {showProcess ? "Traitement" : "Actions"}</h2>
    {canRestore && (
      <div className="rounded-md border border-amber-200 bg-amber-50/80 p-3 space-y-2">
        <p className="text-sm text-amber-950 font-medium">Demande annulée</p>
        <p className="text-xs text-amber-900/80">
          Toutes les données sont conservées. La restauration remet la demande en brouillon
          (même numéro) pour que vous puissiez la modifier avant de la renvoyer.
        </p>
        <Button className="w-full justify-start bg-[#002FA7] hover:bg-[#00248a]" onClick={onRestore} disabled={busy} data-testid="restore-demande-btn">
          <RotateCcw className="h-4 w-4 mr-2" /> Restaurer en brouillon
        </Button>
      </div>
    )}
    {showProcess && !terminal && <Button className="w-full justify-start bg-violet-700 hover:bg-violet-800" onClick={onOffer} disabled={busy}><Paperclip className="h-4 w-4 mr-2" /> Offre reçue</Button>}
    {showProcess && !terminal && (
      <Button
        className={`w-full justify-start ${offresCompletes ? "bg-emerald-800 ring-2 ring-emerald-300 ring-offset-1" : "bg-emerald-600 hover:bg-emerald-700"}`}
        onClick={onOffresCompletes}
        disabled={busy || offresCompletes}
        data-testid="offres-completes-btn"
      >
        <CheckCircle2 className="h-4 w-4 mr-2" />
        {offresCompletes ? "Offres complètes ✓" : "Offres complètes"}
      </Button>
    )}
    {showProcess && hasIncompleteCompany && !terminal && (
      <Button variant="outline" className="w-full justify-start border-rose-300 text-rose-800" onClick={onIncomplete} disabled={busy}>
        <AlertTriangle className="h-4 w-4 mr-2" /> Notifier l&apos;offre incomplète
      </Button>
    )}
    {showProcess && !terminal && <Button variant="outline" className="w-full justify-start" onClick={onDoc} disabled={busy}><FileText className="h-4 w-4 mr-2" /> Ajouter un document</Button>}
    {showProcess && !terminal && <Button variant="outline" className="w-full justify-start" onClick={onNote} disabled={busy}><StickyNote className="h-4 w-4 mr-2" /> Ajouter une note interne</Button>}
    {showProcess && !terminal && (
      <Button className="w-full justify-start bg-rose-700 hover:bg-rose-800" onClick={onErreurs} disabled={busy} data-testid="erreurs-btn">
        <AlertTriangle className="h-4 w-4 mr-2" /> Erreurs
      </Button>
    )}
    {showConseillerFollowup && !terminal && hasOffers && !["En conclusion", "Offre envoyée au client", "Offre signée", "Offre refusée"].includes(demande.statut) &&
      <Button variant="outline" className="w-full justify-start" onClick={onConclusion} disabled={busy}><FileText className="h-4 w-4 mr-2" /> Passer en conclusion</Button>}
    {showConseillerFollowup && canSendClient && !["Offre envoyée au client", "Offre signée", "Offre refusée", "Demande annulée"].includes(demande.statut) &&
      <Button className="w-full justify-start bg-[#002FA7] hover:bg-[#00248a]" onClick={onSendClient} disabled={busy}><Mail className="h-4 w-4 mr-2" /> Envoyer au client</Button>}
    {showSignature && <>
      <Button className="w-full justify-start bg-emerald-700 hover:bg-emerald-800" onClick={() => onSignature(true)} disabled={busy} data-testid="offre-signee-btn"><CheckCircle2 className="h-4 w-4 mr-2" /> Offre signée</Button>
      <Button variant="outline" className="w-full justify-start text-rose-700" onClick={() => onSignature(false)} disabled={busy} data-testid="offre-non-signee-btn"><XCircle className="h-4 w-4 mr-2" /> Offre non signée</Button>
    </>}
    {canCancel && (
      <Button variant="outline" className="w-full justify-start border-rose-300 text-rose-800" onClick={onCancel} disabled={busy}>
        <XCircle className="h-4 w-4 mr-2" /> Annuler l&apos;offre
      </Button>
    )}
    {canDeleteHard && (
      <Button variant="ghost" className="w-full justify-start text-rose-700" onClick={onDelete} disabled={busy}>
        <Trash2 className="h-4 w-4 mr-2" /> Supprimer définitivement
      </Button>
    )}
    {busy && <p className="text-xs text-muted-foreground text-center"><Loader2 className="inline h-3.5 w-3.5 animate-spin mr-1" /> Traitement…</p>}
  </Card>;
}

function History({ entries }) {
  return <Card className="p-5"><h2 className="font-display font-bold mb-4">Historique</h2>
    {!entries.length ? <p className="text-sm text-muted-foreground">Aucun événement.</p> :
      <ol className="space-y-0">{[...entries].reverse().map((entry, index) => <li key={entry.id || index} className="relative pl-6 pb-5 last:pb-0 border-l border-border last:border-transparent">
        <span className="absolute -left-1.5 top-1 h-3 w-3 rounded-full bg-[#002FA7] ring-4 ring-background" />
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium">{entry.action}</p>
          {entry.statut && (
            <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUT_STYLE[entry.statut] || "bg-secondary text-muted-foreground"}`}>
              {entry.statut}
            </span>
          )}
          {entry.meta?.compagnie && (
            <span className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium bg-slate-100 text-slate-700">
              {entry.meta.compagnie}
            </span>
          )}
        </div>
        {entry.detail && <p className="text-sm text-muted-foreground mt-0.5">{entry.detail}</p>}
        {(entry.document_id || entry.document_filename || entry.document) && (
          <p className="text-xs text-[#002FA7] mt-1 flex items-center gap-1">
            <FileText className="h-3 w-3" />
            {entry.document_filename || entry.document?.original_filename || entry.document || `Document ${entry.document_id}`}
          </p>
        )}
        <p className="text-xs text-muted-foreground mt-1">{formatDateFr(entry.at)}{entry.by_name ? ` · ${entry.by_name}` : ""}</p>
      </li>)}</ol>}
  </Card>;
}

function SectionTitle({ title, subtitle }) {
  return <div><h2 className="font-display font-bold text-lg text-[#002FA7]">{title}</h2>{subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}</div>;
}
