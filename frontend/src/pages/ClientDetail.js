import React, { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { apiBaseUrl } from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUTS } from "@/lib/constants";
import { DOCUMENT_CHECKLIST_ITEMS, getInitialDocumentChecklistState, getNextDocumentStatus } from "@/lib/documentChecklist";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import {
  ArrowLeft, Pencil, Trash2, Mail, Phone, MapPin, Briefcase, Users2, AlertTriangle,
  FileText, Upload, Plus, StickyNote, History, CalendarClock, User, Sparkles, Loader2,
  Send, ClipboardList, Shield, Eye, Download, BarChart3,
} from "lucide-react";

const ANALYSE_PREVOYANCE_CATEGORY = "Analyse de prévoyance";
const OFFRE_CATEGORY = "Offre";

const Info = ({ label, value }) => (
  <div>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="text-sm font-medium mt-0.5">{value || "—"}</p>
  </div>
);

const matchesChecklistItem = (doc, documentName) => {
  if (documentName === "Demande LPP") {
    return ["Demande LPP", "Procuration", "Formulaire Recherche LPP"].includes(doc.checklist_item)
      || ["Demande LPP", "Procuration", "Formulaire de recherche LPP"].includes(doc.category);
  }
  return doc.checklist_item === documentName || doc.category === documentName;
};

const FileChip = ({ doc, onDelete }) => (
  <div className="inline-flex items-center gap-0.5 max-w-[240px]">
    <a
      href={`${apiBaseUrl}/documents/${doc.id}/download`}
      target="_blank"
      rel="noreferrer"
      data-testid={`doc-chip-${doc.id}`}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-border bg-secondary/50 text-xs hover:border-[#002FA7] hover:text-[#002FA7] transition-colors min-w-0"
      title={doc.original_filename}
    >
      <FileText className="h-3 w-3 flex-shrink-0" />
      <span className="truncate">{doc.original_filename}</span>
    </a>
    {onDelete && (
      <Button
        size="icon"
        variant="ghost"
        onClick={() => onDelete(doc.id)}
        className="h-6 w-6 text-destructive hover:text-destructive"
        data-testid={`doc-delete-${doc.id}`}
      >
        <Trash2 className="h-3 w-3" />
      </Button>
    )}
  </div>
);

export default function ClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [notes, setNotes] = useState([]);
  const [docs, setDocs] = useState([]);
  const [appts, setAppts] = useState([]);
  const [actions, setActions] = useState([]);
  const [editDialog, setEditDialog] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [documentChecklist, setDocumentChecklist] = useState({});
  const [echeances3p, setEcheances3p] = useState([]);
  const [savingEcheance3p, setSavingEcheance3p] = useState(false);
  const [echeance3pDraftById, setEcheance3pDraftById] = useState({});
  const [editingEcheance3pLineId, setEditingEcheance3pLineId] = useState(null);
  const [generatingDemand, setGeneratingDemand] = useState(null);
  const [lppFunds, setLppFunds] = useState([]);
  const [lppCaisseTracking, setLppCaisseTracking] = useState([]);
  const [selectedFunds, setSelectedFunds] = useState([]);
  const [lppResponseDoc, setLppResponseDoc] = useState(null);
  const [parsingLpp, setParsingLpp] = useState(false);
  const [apptDialog, setApptDialog] = useState(false);
  const [apptForm, setApptForm] = useState({ titre: "", date: "", type: "Rendez-vous", lieu: "" });
  const [generateDialog, setGenerateDialog] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [generating, setGenerating] = useState(false);
  const [libraryForms, setLibraryForms] = useState([]);
  const [selectedLibraryForm, setSelectedLibraryForm] = useState("");
  const [generatingLibrary, setGeneratingLibrary] = useState(false);
  const checklistFileRef = useRef();
  const uploadTargetRef = useRef(null);
  const lppResponseRef = useRef();
  const otherFileRef = useRef();
  const analyseFileRef = useRef();
  const offreFileRef = useRef();
  const [uploadingAnalyse, setUploadingAnalyse] = useState(false);
  const [uploadingOffre, setUploadingOffre] = useState(false);

  const loadAll = async () => {
    const [c, n, d, a, h, lib] = await Promise.all([
      api.get(`/clients/${id}`),
      api.get(`/clients/${id}/notes`),
      api.get(`/clients/${id}/documents`),
      api.get(`/appointments`, { params: { client_id: id } }),
      api.get(`/clients/${id}/actions`),
      api.get("/form-library").catch(() => ({ data: [] })),
    ]);
    setClient(c.data); setNotes(n.data); setDocs(d.data); setAppts(a.data); setActions(h.data);
    setLibraryForms(lib.data || []);
    const savedChecklist = c.data?.document_checklist || {};
    const migratedLpp = savedChecklist["Demande LPP"] || savedChecklist.Procuration || savedChecklist["Formulaire Recherche LPP"];
    const nextChecklist = getInitialDocumentChecklistState(DOCUMENT_CHECKLIST_ITEMS, {
      ...savedChecklist,
      ...(migratedLpp ? { "Demande LPP": migratedLpp } : {}),
    });
    setDocumentChecklist(nextChecklist);
    if (migratedLpp && !savedChecklist["Demande LPP"]) {
      api.patch(`/clients/${id}/document-checklist`, { document_checklist: nextChecklist }).catch(() => {});
    }
    // Multi-contrats 3P : on affiche les lignes si présentes, sinon compat champ unique.
    const rawLines = Array.isArray(c.data?.echeances_3p) ? c.data.echeances_3p : null;
    if (rawLines && rawLines.length > 0) {
      setEcheances3p(
        rawLines.map((l) => ({
          ...l,
          echeance_3p: l?.echeance_3p ? String(l.echeance_3p).split("T")[0] : null,
        }))
      );
    } else {
      const legacy = c.data?.echeance_3p ? String(c.data.echeance_3p).split("T")[0] : null;
      setEcheances3p(
        legacy
          ? [{ id: "legacy-3p", company: null, policy_number: null, echeance_3p: legacy, detected: true }]
          : []
      );
    }
    setLppCaisseTracking(c.data?.lpp_caisse_tracking || []);
    const forms = lib.data || [];
    setSelectedLibraryForm((prev) => {
      if (prev && forms.some((f) => f.id === prev)) return prev;
      return forms[0]?.id || "";
    });

    // Restaurer caisses LPP déjà détectées (document ou fiche client)
    const docsList = Array.isArray(d.data) ? d.data : [];
    const withFunds = docsList.find(
      (doc) =>
        (doc.category === "Réponse recherche LPP" || doc.checklist_item === "Formulaire Recherche LPP") &&
        Array.isArray(doc.detected_funds) &&
        doc.detected_funds.length > 0
    );
    const restored = withFunds?.detected_funds || c.data?.lpp_detected_funds || [];
    if (Array.isArray(restored) && restored.length > 0) {
      setLppFunds(restored);
      setSelectedFunds(restored.map((_, i) => i));
      if (withFunds) setLppResponseDoc(withFunds);
      else if (c.data?.lpp_response_doc_id) {
        const match = docsList.find((doc) => doc.id === c.data.lpp_response_doc_id);
        if (match) setLppResponseDoc(match);
      }
    }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAll(); }, [id]);

  const changeStatut = async (statut) => {
    setClient((c) => ({ ...c, statut }));
    await api.patch(`/clients/${id}/statut`, { statut });
    toast.success("Statut mis à jour");
    const h = await api.get(`/clients/${id}/actions`); setActions(h.data);
  };

  const addNote = async () => {
    if (!noteText.trim()) return;
    await api.post(`/clients/${id}/notes`, { content: noteText });
    setNoteText("");
    const [n, h] = await Promise.all([api.get(`/clients/${id}/notes`), api.get(`/clients/${id}/actions`)]);
    setNotes(n.data); setActions(h.data);
    toast.success("Note ajoutée");
  };

  const uploadChecklistDoc = async (e) => {
    const file = e.target.files?.[0];
    const documentName = uploadTargetRef.current;
    if (!file || !documentName) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("checklist_item", documentName);
    fd.append("category", documentName);
    try {
      const res = await api.post(`/clients/${id}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      if (res.data?.echeance_3p_detected && res.data?.echeance_3p) {
        const date = res.data.echeance_3p;
        toast.success(`Échéance 3e pilier détectée : ${new Date(`${date}T00:00:00`).toLocaleDateString("fr-CH")}`);
      } else {
        toast.success("Document téléversé");
      }
      const [d, h, cl] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
        api.get(`/clients/${id}`),
      ]);
      setDocs(d.data);
      setActions(h.data);
      setClient(cl.data);

      const rawLines = Array.isArray(cl.data?.echeances_3p) ? cl.data.echeances_3p : null;
      if (rawLines && rawLines.length > 0) {
        setEcheances3p(
          rawLines.map((l) => ({
            ...l,
            echeance_3p: l?.echeance_3p ? String(l.echeance_3p).split("T")[0] : null,
          }))
        );
      } else {
        const legacy = cl.data?.echeance_3p ? String(cl.data.echeance_3p).split("T")[0] : null;
        setEcheances3p(
          legacy
            ? [{ id: "legacy-3p", company: null, policy_number: null, echeance_3p: legacy, detected: true }]
            : []
        );
      }
    } catch (err) {
      toast.error("Échec du téléversement");
    }
    e.target.value = "";
    uploadTargetRef.current = null;
  };

  const uploadOtherDoc = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("category", "Autre");
    try {
      await api.post(`/clients/${id}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Document téléversé");
      const [d, h] = await Promise.all([api.get(`/clients/${id}/documents`), api.get(`/clients/${id}/actions`)]);
      setDocs(d.data); setActions(h.data);
    } catch (err) {
      toast.error("Échec du téléversement");
    }
    e.target.value = "";
  };

  const uploadCategorizedDocs = async (e, category, setUploading, successSingular, successPlural) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setUploading(true);
    let ok = 0;
    try {
      for (const file of files) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("category", category);
        fd.append("checklist_item", category);
        await api.post(`/clients/${id}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        ok += 1;
      }
      toast.success(ok > 1 ? successPlural.replace("{n}", String(ok)) : successSingular);
      const [d, h] = await Promise.all([api.get(`/clients/${id}/documents`), api.get(`/clients/${id}/actions`)]);
      setDocs(d.data);
      setActions(h.data);
    } catch (err) {
      toast.error(ok > 0 ? `${ok} fichier(s) ajouté(s), puis échec` : "Échec du téléversement");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const uploadAnalyseDocs = (e) =>
    uploadCategorizedDocs(e, ANALYSE_PREVOYANCE_CATEGORY, setUploadingAnalyse, "Analyse ajoutée", "{n} analyses ajoutées");

  const uploadOffreDocs = (e) =>
    uploadCategorizedDocs(e, OFFRE_CATEGORY, setUploadingOffre, "Offre ajoutée", "{n} offres ajoutées");

  const triggerChecklistUpload = (documentName) => {
    uploadTargetRef.current = documentName;
    checklistFileRef.current?.click();
  };

  const deleteDoc = async (docId) => {
    await api.delete(`/documents/${docId}`);
    setDocs((prev) => prev.filter((x) => x.id !== docId));
    toast.success("Document supprimé");
    await loadAll();
  };

  const deleteAnalyseDoc = async (docId) => {
    if (!window.confirm("Supprimer cette analyse de prévoyance ?")) return;
    await deleteDoc(docId);
  };

  const deleteOffreDoc = async (docId) => {
    if (!window.confirm("Supprimer cette offre ?")) return;
    await deleteDoc(docId);
  };

  const deleteClient = async () => {
    if (!window.confirm("Supprimer définitivement ce dossier ?")) return;
    await api.delete(`/clients/${id}`);
    toast.success("Dossier supprimé");
    navigate("/clients");
  };

  const toggleDocumentStatus = async (documentName, statusKey) => {
    const nextChecklist = {
      ...documentChecklist,
      [documentName]: getNextDocumentStatus(documentChecklist[documentName], statusKey),
    };
    setDocumentChecklist(nextChecklist);
    try {
      const res = await api.patch(`/clients/${id}/document-checklist`, {
        document_checklist: nextChecklist,
      });
      setClient(res.data);
    } catch (err) {
      toast.error("Impossible d'enregistrer le statut du document");
      await loadAll();
    }
  };

  const createAppt = async () => {
    if (!apptForm.titre || !apptForm.date) { toast.error("Titre et date requis"); return; }
    await api.post("/appointments", { ...apptForm, client_id: id });
    setApptDialog(false);
    setApptForm({ titre: "", date: "", type: "Rendez-vous", lieu: "" });
    const [a, h] = await Promise.all([api.get(`/appointments`, { params: { client_id: id } }), api.get(`/clients/${id}/actions`)]);
    setAppts(a.data); setActions(h.data);
    toast.success("Rendez-vous ajouté");
  };

  const openGenerateDialog = async () => {
    try {
      const res = await api.get("/document-templates");
      const available = (res.data || []).filter((t) => t.available !== false);
      setTemplates(available);
      setSelectedTemplate(available[0]?.id || "");
      setGenerateDialog(true);
    } catch (err) {
      toast.error("Impossible de charger les modèles de documents");
    }
  };

  const generateDocument = async () => {
    if (!selectedTemplate) {
      toast.error("Choisissez un formulaire");
      return;
    }
    setGenerating(true);
    try {
      await api.post(`/clients/${id}/generate-document`, { template_id: selectedTemplate });
      toast.success("Document généré et enregistré");
      setGenerateDialog(false);
      const [d, h] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
      ]);
      setDocs(d.data);
      setActions(h.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de la génération");
    } finally {
      setGenerating(false);
    }
  };

  const generateLibraryForm = async () => {
    if (!selectedLibraryForm) {
      toast.error("Choisissez un formulaire dans la bibliothèque");
      return;
    }
    setGeneratingLibrary(true);
    try {
      await api.post(`/clients/${id}/generate-library-form`, {
        library_form_id: selectedLibraryForm,
      });
      toast.success("Formulaire prérempli généré — cliquez pour télécharger");
      const [d, h] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
      ]);
      setDocs(d.data);
      setActions(h.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de la génération");
    } finally {
      setGeneratingLibrary(false);
    }
  };

  const createSpouse = async () => {
    try {
      let payload = {};
      if (!(client.conjoint || "").trim()) {
        const prenom = window.prompt("Prénom du conjoint ?");
        if (!prenom?.trim()) return;
        const nom = window.prompt("Nom du conjoint ?", client.nom || "") || client.nom;
        if (!nom?.trim()) return;
        payload = { prenom: prenom.trim(), nom: nom.trim() };
      }
      await api.post(`/clients/${id}/create-spouse`, payload);
      toast.success("Fiche conjoint créée");
      navigate(`/dossiers/${client.dossier_id || client.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Impossible de créer la fiche conjoint");
    }
  };

  const generateDemand = async (packId) => {
    setGeneratingDemand(packId);
    try {
      const res = await api.post(`/clients/${id}/generate-demand`, { pack_id: packId });
      const documents = res.data?.documents ?? (Array.isArray(res.data) ? res.data : res.data ? [res.data] : []);
      toast.success(`${documents.length || ""} document(s) généré(s) — cliquez pour télécharger`.trim());
      const [d, h] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
      ]);
      setDocs(d.data);
      setActions(h.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de la génération");
    } finally {
      setGeneratingDemand(null);
    }
  };

  const parseLppResponse = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setParsingLpp(true);
    toast.message("Analyse OCR en cours… (20–40 s)");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await api.post(`/clients/${id}/parse-lpp-response`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
      });
      const funds = res.data?.funds ?? [];
      const list = Array.isArray(funds) ? funds : [];
      setLppFunds(list);
      setLppCaisseTracking(res.data?.lpp_caisse_tracking || []);
      setSelectedFunds(list.map((_, i) => i));
      if (res.data?.document) setLppResponseDoc(res.data.document);
      const [d, h, c] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
        api.get(`/clients/${id}`),
      ]);
      setDocs(d.data);
      setActions(h.data);
      setClient(c.data);
      if (list.length === 0) {
        toast.error(res.data?.error || "Aucune caisse détectée — réessayez ou utilisez « Relancer l'analyse »");
      } else {
        toast.success(`${list.length} caisse(s) détectée(s)`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de l'analyse du PDF (timeout possible — rechargez la page)");
      // Recharger : les caisses ont pu être persistées côté serveur malgré un timeout client
      try {
        await loadAll();
      } catch (_) { /* ignore */ }
    } finally {
      setParsingLpp(false);
      e.target.value = "";
    }
  };

  const reparseLatestLppResponse = async () => {
    const responseDocs = docs.filter((d) => d.category === "Réponse recherche LPP");
    const target = lppResponseDoc || responseDocs[0];
    if (!target?.id) {
      toast.error("Aucune réponse LPP à réanalyser");
      return;
    }
    setParsingLpp(true);
    toast.message("Réanalyse OCR…");
    try {
      const res = await api.post(`/clients/${id}/reparse-lpp-response/${target.id}`, null, { timeout: 120000 });
      const funds = res.data?.funds ?? [];
      setLppFunds(funds);
      setLppCaisseTracking(res.data?.lpp_caisse_tracking || []);
      setSelectedFunds(funds.map((_, i) => i));
      if (res.data?.document) setLppResponseDoc(res.data.document);
      toast.success(`${funds.length} caisse(s) détectée(s)`);
      await loadAll();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Réanalyse impossible");
    } finally {
      setParsingLpp(false);
    }
  };

  const toggleFund = (index) => {
    setSelectedFunds((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
    );
  };

  const updateCaisseTracking = async (trackingId, key) => {
    const next = lppCaisseTracking.map((entry) =>
      entry.id === trackingId ? { ...entry, [key]: !entry[key] } : entry
    );
    setLppCaisseTracking(next);
    try {
      const res = await api.patch(`/clients/${id}/lpp-caisse-tracking`, { lpp_caisse_tracking: next });
      setLppCaisseTracking(res.data?.lpp_caisse_tracking || next);
    } catch {
      toast.error("Impossible d'enregistrer le suivi de la caisse");
      setLppCaisseTracking(lppCaisseTracking);
    }
  };

  const generateForSelectedFunds = async () => {
    if (selectedFunds.length === 0) {
      toast.error("Sélectionnez au moins une caisse");
      return;
    }
    const funds = selectedFunds.map((i) => lppFunds[i]).filter(Boolean);
    setGeneratingDemand("decompte_lpp");
    try {
      const res = await api.post(`/clients/${id}/generate-decompte-letters`, { funds });
      const documents = res.data?.documents ?? [];
      toast.success(`${documents.length} demande(s) de décompte générée(s)`);
      const [d, h] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
      ]);
      setDocs(d.data);
      setActions(h.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de la génération");
    } finally {
      setGeneratingDemand(null);
    }
  };

  const saveEcheance3pLine = async (lineId) => {
    const line = echeances3p.find((l) => l?.id === lineId) || {};
    const draft = echeance3pDraftById[lineId] || {};

    const nextCompany = (draft.company !== undefined ? draft.company : line.company) || "";
    const nextPolicy = (draft.policy_number !== undefined ? draft.policy_number : line.policy_number) || "";
    const nextDate = (draft.date !== undefined ? draft.date : line.echeance_3p) || "";

    const payload = {
      company: nextCompany.trim() ? nextCompany.trim() : null,
      policy_number: nextPolicy.trim() ? nextPolicy.trim() : null,
      echeance_3p: nextDate ? nextDate : null,
    };

    setSavingEcheance3p(true);
    try {
      const res = await api.patch(`/clients/${id}/echeances-3p/${lineId}`, payload);
      const updated = res.data;
      setClient(updated);

      const rawLines = Array.isArray(updated?.echeances_3p) ? updated.echeances_3p : null;
      if (rawLines && rawLines.length > 0) {
        setEcheances3p(
          rawLines.map((l) => ({
            ...l,
            echeance_3p: l?.echeance_3p ? String(l.echeance_3p).split("T")[0] : null,
          }))
        );
      } else {
        const legacy = updated?.echeance_3p ? String(updated.echeance_3p).split("T")[0] : null;
        setEcheances3p(
          legacy ? [{ id: "legacy-3p", company: null, policy_number: null, echeance_3p: legacy, detected: true }] : []
        );
      }

      setEcheance3pDraftById((m) => ({ ...m, [lineId]: {} }));
      setEditingEcheance3pLineId(null);
      toast.success("Échéance 3e pilier enregistrée");
    } catch (err) {
      toast.error("Impossible d'enregistrer la ligne");
    } finally {
      setSavingEcheance3p(false);
    }
  };

  const startEditEcheance3pLine = (line) => {
    if (!line?.id) return;
    setEcheance3pDraftById({
      [line.id]: {
        company: line?.company || "",
        policy_number: line?.policy_number || "",
        date: line?.echeance_3p || "",
      },
    });
    setEditingEcheance3pLineId(line.id);
  };

  const isWithinOneYear = (dateStr) => {
    if (!dateStr) return false;
    const d = new Date(dateStr);
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const oneYear = new Date();
    oneYear.setFullYear(oneYear.getFullYear() + 1);
    return d >= now && d <= oneYear;
  };

  const getDocsForChecklistItem = (documentName) =>
    docs.filter((d) => matchesChecklistItem(d, documentName));

  const getDocsForTemplates = (templateIds) =>
    docs.filter((d) => templateIds.includes(d.template_id) || templateIds.includes(d?.meta?.template_id));

  const LPP_DEMAND_TEMPLATES = ["recherche_avoirs_lpp", "procuration_avs_lpp", "lettre_lpp"];
  const AVS_DEMAND_TEMPLATES = ["calcul_rente_future", "lettre_avs"];
  const LPP_CHECKLIST = ["Demande LPP"];
  const AVS_CHECKLIST = ["Formulaire AVS"];

  const getDecompteDocs = () =>
    docs.filter((d) => d.template_id === "lettre_decompte_lpp" || d.category === "Demande de décompte LPP");

  const getLppResponseDocs = () =>
    docs.filter((d) => d.category === "Réponse recherche LPP" || (lppResponseDoc && d.id === lppResponseDoc.id));

  const renderDocList = (list) =>
    list.length === 0 ? (
      <p className="text-sm text-muted-foreground">Aucun document.</p>
    ) : (
      <div className="flex flex-wrap gap-2">
        {list.map((d) => (
          <FileChip key={d.id} doc={d} onDelete={deleteDoc} />
        ))}
      </div>
    );

  const renderChecklistRows = (items) =>
    items.map((documentName) => {
      const status = documentChecklist[documentName] || { sent: false, received: false };
      const linkedDocs = getDocsForChecklistItem(documentName);
      return (
        <div key={documentName} data-testid={`doc-checklist-${documentName}`} className="flex flex-col gap-2 rounded-md border border-border bg-background px-3 py-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4 min-w-0 flex-1">
            <span className="text-sm font-medium shrink-0">{documentName}</span>
            <div className="flex flex-wrap gap-3 text-sm">
              {[
                { key: "sent", label: "Envoyé" },
                { key: "received", label: "Reçu" },
              ].map((option) => (
                <label key={option.key} className="flex items-center gap-2 cursor-pointer">
                  <Checkbox
                    data-testid={`doc-check-${documentName}-${option.key}`}
                    checked={status[option.key]}
                    onCheckedChange={() => toggleDocumentStatus(documentName, option.key)}
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
            <Button
              size="sm"
              variant="ghost"
              data-testid={`doc-upload-${documentName}`}
              onClick={() => triggerChecklistUpload(documentName)}
              className="h-7 px-2 gap-1 text-xs text-muted-foreground hover:text-[#002FA7] shrink-0"
            >
              <Upload className="h-3.5 w-3.5" />
            </Button>
          </div>
          {linkedDocs.length > 0 && (
            <div className="flex flex-wrap gap-1.5 justify-end lg:max-w-[55%]">
              {linkedDocs.map((d) => (
                <FileChip key={d.id} doc={d} onDelete={deleteDoc} />
              ))}
            </div>
          )}
        </div>
      );
    });

  if (!client) return <Layout><div className="animate-pulse text-muted-foreground">Chargement…</div></Layout>;

  const isMarried = ((client.etat_civil || "").toLowerCase().includes("mari") || (client.etat_civil || "").toLowerCase().includes("partenariat"));
  const fmtDate = (s) => s ? new Date(s).toLocaleString("fr-CH", { dateStyle: "medium", timeStyle: "short" }) : "";

  const isAnalysePrevoyanceDoc = (d) =>
    d?.category === ANALYSE_PREVOYANCE_CATEGORY || d?.checklist_item === ANALYSE_PREVOYANCE_CATEGORY;

  const isOffreDoc = (d) =>
    d?.category === OFFRE_CATEGORY || d?.checklist_item === OFFRE_CATEGORY;

  const sortDocsByDateDesc = (list) =>
    list.slice().sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));

  const analyseDocs = sortDocsByDateDesc(docs.filter(isAnalysePrevoyanceDoc));
  const offreDocs = sortDocsByDateDesc(docs.filter(isOffreDoc));
  const otherDocs = docs.filter((d) => !isAnalysePrevoyanceDoc(d) && !isOffreDoc(d));

  const renderSpecialDocList = (list, { emptyLabel, testIdPrefix, onDelete, showLatestBadge = false }) => {
    if (list.length === 0) {
      return <p className="text-sm text-muted-foreground py-4">{emptyLabel}</p>;
    }
    return (
      <div className="space-y-3">
        {list.map((d, index) => (
          <div key={d.id} className="flex items-start justify-between gap-3 border-b border-border pb-3 last:border-0 last:pb-0">
            <div className="min-w-0">
              <p className="text-sm font-medium truncate" title={d.original_filename}>
                {d.original_filename || "Document"}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {fmtDate(d.created_at)}
                {d.author ? ` · ${d.author}` : ""}
                {showLatestBadge && index === 0 ? " · Version la plus récente" : ""}
              </p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <Button size="icon" variant="ghost" asChild className="h-8 w-8" title="Ouvrir">
                <a
                  href={`${apiBaseUrl}/documents/${d.id}/download`}
                  target="_blank"
                  rel="noreferrer"
                  data-testid={`${testIdPrefix}-open-${d.id}`}
                >
                  <Eye className="h-4 w-4" />
                </a>
              </Button>
              <Button size="icon" variant="ghost" asChild className="h-8 w-8" title="Télécharger">
                <a
                  href={`${apiBaseUrl}/documents/${d.id}/download`}
                  download={d.original_filename || "document.pdf"}
                  data-testid={`${testIdPrefix}-download-${d.id}`}
                >
                  <Download className="h-4 w-4" />
                </a>
              </Button>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => onDelete(d.id)}
                className="h-8 w-8 text-destructive hover:text-destructive"
                title="Supprimer"
                data-testid={`${testIdPrefix}-delete-${d.id}`}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <Layout>
      <button
        onClick={() => navigate(
          isMarried && client.dossier_id && client.linked_spouse_id
            ? `/dossiers/${client.dossier_id}`
            : "/clients"
        )}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors"
        data-testid="back-btn"
      >
        <ArrowLeft className="h-4 w-4" /> {
          isMarried && client.dossier_id && client.linked_spouse_id
            ? "Retour au dossier"
            : "Retour aux clients"
        }
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left summary */}
        <div className="lg:col-span-4 space-y-4">
          <Card className="p-6">
            <div className="flex items-start justify-between">
              <div className="h-16 w-16 rounded-full bg-[#002FA7]/10 text-[#002FA7] flex items-center justify-center font-display font-black text-xl">
                {client.prenom?.[0]}{client.nom?.[0]}
              </div>
              <div className="flex gap-1">
                <Button size="icon" variant="ghost" onClick={() => setEditDialog(true)} data-testid="edit-client-btn"><Pencil className="h-4 w-4" /></Button>
                <Button size="icon" variant="ghost" onClick={deleteClient} data-testid="delete-client-btn" className="text-destructive hover:text-destructive"><Trash2 className="h-4 w-4" /></Button>
              </div>
            </div>
            <h1 className="font-display font-black text-2xl tracking-tight mt-4 flex items-center gap-2">
              {client.prenom} {client.nom}
              {client.priorite === "urgent" && <AlertTriangle className="h-5 w-5 text-red-600" />}
            </h1>
            <p className="text-sm text-muted-foreground font-mono">{client.numero_dossier}</p>

            <div className="mt-3 flex flex-wrap gap-2">
              {isMarried && client.dossier_id && client.linked_spouse_id && (
                <Button
                  size="sm"
                  variant="outline"
                  data-testid="view-dossier-btn"
                  onClick={() => navigate(`/dossiers/${client.dossier_id}`)}
                  className="gap-1.5 border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7]/5"
                >
                  <Users2 className="h-4 w-4" />Voir le dossier
                </Button>
              )}
              {isMarried && client.linked_spouse_id && (
                <Button
                  size="sm"
                  variant="outline"
                  data-testid="view-spouse-btn"
                  onClick={() => navigate(`/clients/${client.linked_spouse_id}`)}
                  className="gap-1.5"
                >
                  Voir conjoint
                </Button>
              )}
              {isMarried && !client.linked_spouse_id && (
                <Button
                  size="sm"
                  variant="outline"
                  data-testid="create-spouse-btn"
                  onClick={createSpouse}
                  className="gap-1.5 border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7]/5"
                >
                  <Plus className="h-4 w-4" />Créer fiche conjoint
                </Button>
              )}
            </div>

            <div className="mt-4">
              <Label className="text-xs text-muted-foreground">Statut du dossier</Label>
              <Select value={client.statut} onValueChange={changeStatut}>
                <SelectTrigger data-testid="detail-statut-select" className="mt-1.5"><SelectValue /></SelectTrigger>
                <SelectContent>{STATUTS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>

            <div className="mt-5 space-y-3 border-t border-border pt-5">
              {client.email && <p className="text-sm flex items-center gap-2.5"><Mail className="h-4 w-4 text-muted-foreground" />{client.email}</p>}
              {client.telephone && <p className="text-sm flex items-center gap-2.5"><Phone className="h-4 w-4 text-muted-foreground" />{client.telephone}</p>}
              {(client.adresse || client.ville) && <p className="text-sm flex items-center gap-2.5"><MapPin className="h-4 w-4 text-muted-foreground" />{[client.adresse, client.npa, client.ville].filter(Boolean).join(", ")}</p>}
              {client.profession && <p className="text-sm flex items-center gap-2.5"><Briefcase className="h-4 w-4 text-muted-foreground" />{client.profession}</p>}
              {client.etat_civil && <p className="text-sm flex items-center gap-2.5"><Users2 className="h-4 w-4 text-muted-foreground" />{client.etat_civil}{client.nombre_enfants ? ` · ${client.nombre_enfants} enfant(s)` : ""}</p>}
            </div>
          </Card>
        </div>

        {/* Right tabs */}
        <div className="lg:col-span-8">
          <Tabs defaultValue="infos">
            <TabsList className="mb-4 flex flex-wrap h-auto gap-1">
              <TabsTrigger value="infos" data-testid="tab-infos"><User className="h-4 w-4 mr-1.5" />Infos</TabsTrigger>
              <TabsTrigger value="rdv" data-testid="tab-rdv"><CalendarClock className="h-4 w-4 mr-1.5" />Rendez-vous</TabsTrigger>
              <TabsTrigger value="notes" data-testid="tab-notes"><StickyNote className="h-4 w-4 mr-1.5" />Notes</TabsTrigger>
              <TabsTrigger value="docs" data-testid="tab-docs"><FileText className="h-4 w-4 mr-1.5" />Documents</TabsTrigger>
              <TabsTrigger value="demande-lpp" data-testid="tab-demande-lpp"><ClipboardList className="h-4 w-4 mr-1.5" />Demande LPP</TabsTrigger>
              <TabsTrigger value="demande-avs" data-testid="tab-demande-avs"><Send className="h-4 w-4 mr-1.5" />Demande AVS</TabsTrigger>
              <TabsTrigger value="echeance3p" data-testid="tab-echeance3p"><Shield className="h-4 w-4 mr-1.5" />Échéance 3P</TabsTrigger>
              <TabsTrigger value="analyse-prevoyance" data-testid="tab-analyse-prevoyance"><BarChart3 className="h-4 w-4 mr-1.5" />Analyse de prévoyance</TabsTrigger>
              <TabsTrigger value="hist" data-testid="tab-hist"><History className="h-4 w-4 mr-1.5" />Historique</TabsTrigger>
            </TabsList>

            <TabsContent value="infos">
              <Card className="p-6 space-y-6">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-3">Informations personnelles</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    <Info label="Nom" value={client.nom} />
                    <Info label="Prénom" value={client.prenom} />
                    <Info label="Date de naissance" value={client.date_naissance} />
                    <Info label="Adresse" value={[client.adresse, client.npa, client.ville].filter(Boolean).join(", ")} />
                    <Info label="Téléphone" value={client.telephone} />
                    <Info label="Email" value={client.email} />
                    <Info label="Sexe" value={client.sexe} />
                    <Info label="Nationalité" value={client.nationalite} />
                    <Info label="N° AVS" value={client.avs_number} />
                  </div>
                </div>
                <div className="border-t border-border pt-6">
                  <p className="text-sm font-semibold text-[#002FA7] mb-3">Situation familiale</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    <Info label="État civil" value={client.etat_civil} />
                    <Info label="Enfants" value={client.nombre_enfants} />
                    <Info label="Conjoint" value={client.conjoint} />
                  </div>
                </div>
                <div className="border-t border-border pt-6">
                  <p className="text-sm font-semibold text-[#002FA7] mb-3">Situation professionnelle</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    <Info label="Employeur" value={client.employeur} />
                    <Info label="Profession" value={client.profession} />
                    <Info label="Taux d'activité" value={client.taux_activite} />
                    <Info label="Salaire annuel" value={client.salaire_annuel ? `CHF ${Number(client.salaire_annuel).toLocaleString("fr-CH")}` : null} />
                    <Info label="Conseiller" value={client.conseiller} />
                    <Info label="Agent apporteur" value={client.agent_apporteur} />
                    <Info label="N° dossier" value={client.numero_dossier} />
                    <Info label="Statut" value={client.statut} />
                    <Info label="Priorité" value={client.priorite} />
                  </div>
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="rdv">
              <Card className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <p className="text-sm font-semibold">Historique des rendez-vous</p>
                  <Button size="sm" onClick={() => setApptDialog(true)} data-testid="add-appt-btn" className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"><Plus className="h-4 w-4" />Ajouter</Button>
                </div>
                {appts.length === 0 ? <p className="text-sm text-muted-foreground py-8 text-center">Aucun rendez-vous.</p> : (
                  <div className="space-y-2">
                    {appts.map((a) => (
                      <div key={a.id} className="flex items-center gap-4 p-3 rounded-md border border-border">
                        <div className="text-xs font-medium text-[#002FA7] w-32">{fmtDate(a.date)}</div>
                        <div className="flex-1"><p className="text-sm font-medium">{a.titre}</p>{a.lieu && <p className="text-xs text-muted-foreground">{a.lieu}</p>}</div>
                        <span className="text-xs px-2 py-1 rounded bg-secondary">{a.type}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="notes">
              <Card className="p-6">
                <div className="flex gap-2 mb-4">
                  <Textarea data-testid="note-input" value={noteText} onChange={(e) => setNoteText(e.target.value)} placeholder="Ajouter une note interne…" className="resize-none" rows={2} />
                  <Button onClick={addNote} data-testid="add-note-btn" className="bg-[#002FA7] hover:bg-[#00248a] self-end">Ajouter</Button>
                </div>
                {notes.length === 0 ? <p className="text-sm text-muted-foreground py-8 text-center">Aucune note.</p> : (
                  <div className="space-y-3">
                    {notes.map((n) => (
                      <div key={n.id} className="p-3 rounded-md border border-border bg-secondary/40">
                        <p className="text-sm whitespace-pre-wrap">{n.content}</p>
                        <p className="text-xs text-muted-foreground mt-2">{n.author} · {fmtDate(n.created_at)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="docs">
              <Card className="p-6 space-y-6">
                <div className="flex items-center justify-end gap-2 flex-wrap">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => otherFileRef.current?.click()}
                    data-testid="upload-other-doc-btn"
                    className="h-8 gap-1.5"
                  >
                    <Upload className="h-4 w-4" />Ajouter un fichier
                  </Button>
                  <Button onClick={openGenerateDialog} data-testid="generate-doc-btn" variant="outline" className="gap-1.5 border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7]/5">
                    <Sparkles className="h-4 w-4" />Générer un document
                  </Button>
                </div>
                <input ref={checklistFileRef} type="file" className="hidden" onChange={uploadChecklistDoc} data-testid="checklist-file-input" />
                <input ref={otherFileRef} type="file" className="hidden" onChange={uploadOtherDoc} data-testid="other-file-input" />
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-3">Demandes</p>
                  <p className="text-xs text-muted-foreground mb-3">Suivi Envoyé / Reçu des pièces demandées.</p>
                  <div className="space-y-3">{renderChecklistRows(DOCUMENT_CHECKLIST_ITEMS.filter((item) => item !== "Autre formulaire"))}</div>
                </div>

                <div className="border-t border-border pt-4 space-y-4">
                  <div>
                    <p className="text-sm font-semibold text-[#002FA7] mb-1">Autre formulaire</p>
                    <p className="text-xs text-muted-foreground mb-3">
                      Sélectionnez un PDF de la bibliothèque : il sera prérempli avec les données du client, puis enregistré dans le dossier.
                    </p>
                    {libraryForms.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        Aucun formulaire en bibliothèque. Ajoutez-en via le menu{" "}
                        <button type="button" className="text-[#002FA7] underline" onClick={() => navigate("/formulaires")}>
                          Formulaires
                        </button>
                        .
                      </p>
                    ) : (
                      <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                        <div className="space-y-1.5 flex-1 min-w-0">
                          <Label className="text-xs text-muted-foreground">Formulaire</Label>
                          <Select value={selectedLibraryForm} onValueChange={setSelectedLibraryForm}>
                            <SelectTrigger data-testid="library-form-select">
                              <SelectValue placeholder="Choisir…" />
                            </SelectTrigger>
                            <SelectContent>
                              {libraryForms.map((f) => (
                                <SelectItem key={f.id} value={f.id}>{f.name}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <Button
                          onClick={generateLibraryForm}
                          disabled={generatingLibrary || !selectedLibraryForm}
                          data-testid="generate-library-form-btn"
                          className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5 shrink-0"
                        >
                          {generatingLibrary ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                          Générer le PDF
                        </Button>
                      </div>
                    )}
                  </div>
                  <div className="space-y-3">{renderChecklistRows(["Autre formulaire"])}</div>
                </div>

                <div className="border-t border-border pt-4">
                  <p className="text-sm font-semibold mb-3">Fichiers du dossier</p>
                  {otherDocs.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-2">Aucun document pour le moment.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {otherDocs.map((d) => (
                        <div key={d.id} className="flex items-center gap-1">
                          <FileChip doc={d} />
                          <Button size="icon" variant="ghost" onClick={() => deleteDoc(d.id)} className="h-6 w-6 text-destructive hover:text-destructive" data-testid={`doc-delete-${d.id}`}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="demande-lpp">
              <Card className="p-6 space-y-6">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-1">Demande LPP</p>
                  <p className="text-xs text-muted-foreground mb-4">Génère automatiquement le formulaire de recherche (case « pour moi-même »), la procuration et la lettre — préremplis et enregistrés dans le dossier.</p>
                  <Button
                    data-testid="demande-recherche-lpp"
                    onClick={() => generateDemand("recherche_lpp")}
                    disabled={generatingDemand === "recherche_lpp"}
                    className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
                  >
                    {generatingDemand === "recherche_lpp" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardList className="h-4 w-4" />}
                    Générer lettre LPP + formulaire + procuration
                  </Button>
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">Documents générés</p>
                  {renderDocList(getDocsForTemplates(LPP_DEMAND_TEMPLATES))}
                </div>

                <div className="border-t border-border pt-4">
                  <p className="text-sm font-semibold mb-3">Suivi</p>
                  <p className="text-xs text-muted-foreground mb-3">Statuts Envoyé / Reçu uniquement. Ouvrir, télécharger ou supprimer les fichiers ci-dessous.</p>
                  <div className="space-y-3">{renderChecklistRows(LPP_CHECKLIST)}</div>
                  {lppCaisseTracking.length > 0 && (
                    <div className="mt-3 space-y-2">
                      {lppCaisseTracking.map((caisse) => (
                        <div key={caisse.id} className="flex flex-col gap-2 rounded-md border border-border bg-background px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <p className="text-sm font-medium">Demande {caisse.name}</p>
                            {(caisse.address || caisse.reference) && <p className="text-xs text-muted-foreground whitespace-pre-line">{caisse.address}{caisse.reference ? ` · Réf. ${caisse.reference}` : ""}</p>}
                          </div>
                          <div className="flex gap-4 text-sm">
                            {[
                              { key: "sent", label: "Envoyé" },
                              { key: "received", label: "Reçu" },
                            ].map((option) => (
                              <label key={option.key} className="flex items-center gap-2 cursor-pointer">
                                <Checkbox checked={Boolean(caisse[option.key])} onCheckedChange={() => updateCaisseTracking(caisse.id, option.key)} />
                                <span>{option.label}</span>
                              </label>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="border-t border-border pt-4 space-y-4">
                  <p className="text-sm font-semibold text-[#002FA7]">Réponse LPP / Caisses</p>
                  <p className="text-xs text-muted-foreground">Téléversez la réponse de la Centrale du 2ème pilier. Le CRM détecte les caisses (OCR) puis génère une lettre de décompte par caisse.</p>
                  <input ref={lppResponseRef} type="file" accept=".pdf" className="hidden" onChange={parseLppResponse} data-testid="lpp-response-input" />
                  <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    onClick={() => lppResponseRef.current?.click()}
                    disabled={parsingLpp}
                    data-testid="upload-lpp-response-btn"
                    className="gap-1.5"
                  >
                    {parsingLpp ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                    {parsingLpp ? "Analyse OCR en cours…" : "Téléverser réponse LPP (PDF)"}
                  </Button>
                  {(lppResponseDoc || docs.some((d) => d.category === "Réponse recherche LPP")) && (
                    <Button
                      variant="secondary"
                      onClick={reparseLatestLppResponse}
                      disabled={parsingLpp}
                      data-testid="reparse-lpp-btn"
                      className="gap-1.5"
                    >
                      {parsingLpp ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                      Relancer l&apos;analyse
                    </Button>
                  )}
                  </div>

                  {(getLppResponseDocs().length > 0 || lppResponseDoc) && (
                    <div>
                      <p className="text-sm font-medium mb-2">Réponse LPP</p>
                      {renderDocList(getLppResponseDocs().length ? getLppResponseDocs() : (lppResponseDoc ? [lppResponseDoc] : []))}
                    </div>
                  )}

                  {lppFunds.length > 0 && (
                    <div className="space-y-3 rounded-md border border-border p-4 bg-secondary/30">
                      <p className="text-sm font-medium">Caisses détectées</p>
                      <div className="space-y-2">
                        {lppFunds.map((fund, index) => {
                          const label = fund?.name ?? fund?.nom ?? `Caisse ${index + 1}`;
                          const block = fund?.recipient_block || fund?.raw || fund?.address || fund?.adresse || "";
                          const ref = fund?.reference || fund?.ref || "";
                          return (
                            <label key={index} className="flex items-start gap-2 cursor-pointer text-sm">
                              <Checkbox
                                checked={selectedFunds.includes(index)}
                                onCheckedChange={() => toggleFund(index)}
                                data-testid={`lpp-fund-${index}`}
                                className="mt-0.5"
                              />
                              <span>
                                <span className="font-medium">{label}</span>
                                {block && <span className="block text-xs text-muted-foreground whitespace-pre-line mt-0.5">{block}</span>}
                                {ref && <span className="block text-xs text-muted-foreground">Réf. {ref}</span>}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                      <Button
                        onClick={generateForSelectedFunds}
                        disabled={selectedFunds.length === 0 || generatingDemand === "decompte_lpp"}
                        data-testid="generate-lpp-funds-btn"
                        className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
                      >
                        {generatingDemand === "decompte_lpp" ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Sparkles className="h-4 w-4" />
                        )}
                        Générer les demandes de décompte
                      </Button>
                    </div>
                  )}

                  {getDecompteDocs().length > 0 && (
                    <div>
                      <p className="text-sm font-medium mb-2">Demandes générées</p>
                      {renderDocList(getDecompteDocs())}
                    </div>
                  )}
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="demande-avs">
              <Card className="p-6 space-y-6">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-1">Demande AVS</p>
                  <p className="text-xs text-muted-foreground mb-4">Génère le formulaire rente future et la lettre d&apos;accompagnement — préremplis et enregistrés dans le CRM (téléchargement au clic).</p>
                  <Button
                    data-testid="demande-avs"
                    onClick={() => generateDemand("demande_avs")}
                    disabled={generatingDemand === "demande_avs"}
                    className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
                  >
                    {generatingDemand === "demande_avs" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    Générer formulaire rente future + lettre AVS
                  </Button>
                </div>
                <div>
                  <p className="text-sm font-medium mb-2">Documents générés</p>
                  {getDocsForTemplates(AVS_DEMAND_TEMPLATES).length === 0 ? (
                    <p className="text-sm text-muted-foreground">Aucun document AVS généré pour ce client.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {getDocsForTemplates(AVS_DEMAND_TEMPLATES).map((d) => (
                        <FileChip key={d.id} doc={d} />
                      ))}
                    </div>
                  )}
                </div>
                <div className="border-t border-border pt-4">
                  <p className="text-sm font-semibold mb-3">Suivi</p>
                  <div className="space-y-3">{renderChecklistRows(AVS_CHECKLIST)}</div>
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="echeance3p">
              <Card className="p-6 space-y-4">
                <p className="text-sm font-semibold text-[#002FA7]">Échéance 3e pilier</p>

                {echeances3p.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Aucun contrat 3e pilier détecté pour l’instant. Ajoute une « Police 3e pilier » dans Documents.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left">
                          <th className="pb-2 pr-3 font-medium text-muted-foreground whitespace-nowrap">Compagnie</th>
                          <th className="pb-2 pr-3 font-medium text-muted-foreground whitespace-nowrap">N° de police</th>
                          <th className="pb-2 pr-3 font-medium text-muted-foreground whitespace-nowrap">Date d&apos;échéance</th>
                          <th className="pb-2 font-medium text-muted-foreground whitespace-nowrap">Statut</th>
                          <th className="pb-2 font-medium text-muted-foreground whitespace-nowrap">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {echeances3p.map((line) => {
                          const draft = echeance3pDraftById[line.id] || {};
                          const iso = line?.echeance_3p;

                          const effectiveIso = draft.date !== undefined ? draft.date : iso;
                          const effectiveCompany = draft.company !== undefined ? draft.company : (line?.company || "");
                          const effectivePolicy = draft.policy_number !== undefined ? draft.policy_number : (line?.policy_number || "");
                          const isEditing = editingEcheance3pLineId === line.id;

                          const dueDate = effectiveIso ? new Date(`${effectiveIso}T00:00:00`) : null;
                          const now = new Date();
                          now.setHours(0, 0, 0, 0);
                          const daysLeft = dueDate ? Math.floor((dueDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)) : null;

                          let statusLabel = "—";
                          if (!effectiveIso) {
                            statusLabel = "⚠ Date d’échéance non détectée";
                          } else if (typeof daysLeft === "number" && daysLeft < 0) {
                            statusLabel = "⚠ Échéance passée";
                          } else if (typeof daysLeft === "number" && 0 <= daysLeft && daysLeft <= 365) {
                            statusLabel = "⚠ Échéance dans moins d’un an";
                          } else {
                            statusLabel = "✅ À jour";
                          }

                          return (
                            <tr key={line.id} className="border-t border-border">
                              <td className="py-3 pr-3 whitespace-nowrap">
                                {isEditing ? (
                                  <Input
                                    data-testid={`echeance-3p-line-company-${line.id}`}
                                    value={effectiveCompany}
                                    onChange={(e) => {
                                      const value = e.target.value;
                                      setEcheance3pDraftById((m) => ({
                                        ...m,
                                        [line.id]: { ...(m[line.id] || {}), company: value },
                                      }));
                                    }}
                                  />
                                ) : (
                                  <span>{effectiveCompany || "Compagnie non détectée"}</span>
                                )}
                              </td>
                              <td className="py-3 pr-3 whitespace-nowrap">
                                {isEditing ? (
                                  <Input
                                    data-testid={`echeance-3p-line-policy-${line.id}`}
                                    value={effectivePolicy}
                                    onChange={(e) => {
                                      const value = e.target.value;
                                      setEcheance3pDraftById((m) => ({
                                        ...m,
                                        [line.id]: { ...(m[line.id] || {}), policy_number: value },
                                      }));
                                    }}
                                  />
                                ) : (
                                  <span>{effectivePolicy || "—"}</span>
                                )}
                              </td>
                              <td className="py-3 pr-3 whitespace-nowrap">
                                {isEditing ? (
                                  <Input
                                    type="date"
                                    data-testid={`echeance-3p-line-date-${line.id}`}
                                    value={effectiveIso || ""}
                                    onChange={(e) => {
                                      const value = e.target.value;
                                      setEcheance3pDraftById((m) => ({
                                        ...m,
                                        [line.id]: { ...(m[line.id] || {}), date: value },
                                      }));
                                    }}
                                  />
                                ) : (
                                  <span>
                                    {iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("fr-CH") : "—"}
                                  </span>
                                )}
                              </td>
                              <td className="py-3 whitespace-nowrap">
                                <span className={statusLabel.startsWith("✅") ? "text-emerald-700" : "text-amber-700"}>
                                  {statusLabel}
                                </span>
                              </td>
                              <td className="py-3 whitespace-nowrap text-right">
                                {isEditing ? (
                                  <Button
                                    size="sm"
                                    onClick={() => saveEcheance3pLine(line.id)}
                                    disabled={savingEcheance3p}
                                    data-testid={`echeance-3p-line-save-${line.id}`}
                                    className="bg-[#002FA7] hover:bg-[#00248a]"
                                  >
                                    {savingEcheance3p ? "…" : "✔ Enregistrer"}
                                  </Button>
                                ) : (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => startEditEcheance3pLine(line)}
                                    disabled={savingEcheance3p}
                                    data-testid={`echeance-3p-line-edit-${line.id}`}
                                  >
                                    ✏️ Modifier
                                  </Button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="analyse-prevoyance">
              <Card className="p-6 space-y-8">
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                      <p className="text-sm font-semibold text-[#002FA7]">Analyse de prévoyance</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        PDF d’analyse. Les nouvelles versions sont conservées dans l’historique.
                      </p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => analyseFileRef.current?.click()}
                      disabled={uploadingAnalyse}
                      data-testid="upload-analyse-prevoyance-btn"
                      className="h-8 gap-1.5 bg-[#002FA7] hover:bg-[#00248a]"
                    >
                      {uploadingAnalyse ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                      Ajouter une analyse
                    </Button>
                    <input
                      ref={analyseFileRef}
                      type="file"
                      accept=".pdf,application/pdf"
                      multiple
                      className="hidden"
                      onChange={uploadAnalyseDocs}
                      data-testid="analyse-prevoyance-file-input"
                    />
                  </div>
                  {renderSpecialDocList(analyseDocs, {
                    emptyLabel: "Aucune analyse enregistrée pour l’instant.",
                    testIdPrefix: "analyse",
                    onDelete: deleteAnalyseDoc,
                    showLatestBadge: true,
                  })}
                </div>

                <div className="border-t border-border pt-6 space-y-4">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                      <p className="text-sm font-semibold text-[#002FA7]">Offres</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Offres remises au client (rente, 3e pilier, LPP, hypothèque, etc.).
                      </p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => offreFileRef.current?.click()}
                      disabled={uploadingOffre}
                      data-testid="upload-offre-btn"
                      className="h-8 gap-1.5 bg-[#002FA7] hover:bg-[#00248a]"
                    >
                      {uploadingOffre ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                      Ajouter une offre
                    </Button>
                    <input
                      ref={offreFileRef}
                      type="file"
                      accept=".pdf,application/pdf"
                      multiple
                      className="hidden"
                      onChange={uploadOffreDocs}
                      data-testid="offre-file-input"
                    />
                  </div>
                  {renderSpecialDocList(offreDocs, {
                    emptyLabel: "Aucune offre enregistrée pour l’instant.",
                    testIdPrefix: "offre",
                    onDelete: deleteOffreDoc,
                  })}
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="hist">
              <Card className="p-6">
                <p className="text-sm font-semibold mb-4">Historique des actions</p>
                {actions.length === 0 ? <p className="text-sm text-muted-foreground py-8 text-center">Aucune action.</p> : (
                  <div className="relative pl-5 space-y-4 before:absolute before:left-1.5 before:top-1 before:bottom-1 before:w-px before:bg-border">
                    {actions.map((a) => (
                      <div key={a.id} className="relative">
                        <span className="absolute -left-[15px] top-1 h-2.5 w-2.5 rounded-full bg-[#002FA7] ring-2 ring-white" />
                        <p className="text-sm">{a.description}</p>
                        <p className="text-xs text-muted-foreground">{fmtDate(a.created_at)}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <ClientFormDialog open={editDialog} onOpenChange={setEditDialog} client={client} onSaved={(c) => setClient(c)} />

      <Dialog open={apptDialog} onOpenChange={setApptDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display">Nouveau rendez-vous</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Titre</Label><Input data-testid="appt-titre" value={apptForm.titre} onChange={(e) => setApptForm({ ...apptForm, titre: e.target.value })} placeholder="Ex: Entretien conseil retraite" /></div>
            <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Date et heure</Label><Input data-testid="appt-date" type="datetime-local" value={apptForm.date} onChange={(e) => setApptForm({ ...apptForm, date: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Type</Label>
                <Select value={apptForm.type} onValueChange={(v) => setApptForm({ ...apptForm, type: v })}><SelectTrigger data-testid="appt-type"><SelectValue /></SelectTrigger>
                  <SelectContent>{["Rendez-vous", "Appel", "Visio", "Présentation"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Lieu</Label><Input value={apptForm.lieu} onChange={(e) => setApptForm({ ...apptForm, lieu: e.target.value })} /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApptDialog(false)}>Annuler</Button>
            <Button onClick={createAppt} data-testid="appt-save" className="bg-[#002FA7] hover:bg-[#00248a]">Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={generateDialog} onOpenChange={setGenerateDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="font-display">Générer un document</DialogTitle>
            <DialogDescription>
              Les informations du dossier ({client.prenom} {client.nom}) seront préremplies automatiquement.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <Label className="text-xs text-muted-foreground">Formulaire à générer</Label>
            <div className="space-y-2">
              {templates.map((t) => (
                <label
                  key={t.id}
                  data-testid={`template-option-${t.id}`}
                  className={`flex items-start gap-3 rounded-md border p-3 cursor-pointer transition-colors ${
                    selectedTemplate === t.id ? "border-[#002FA7] bg-[#002FA7]/5" : "border-border hover:bg-secondary/50"
                  }`}
                >
                  <input
                    type="radio"
                    name="doc-template"
                    className="mt-1"
                    checked={selectedTemplate === t.id}
                    onChange={() => setSelectedTemplate(t.id)}
                  />
                  <span>
                    <span className="block text-sm font-medium">{t.label}</span>
                    <span className="block text-xs text-muted-foreground mt-0.5">{t.description}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGenerateDialog(false)} disabled={generating}>Annuler</Button>
            <Button
              onClick={generateDocument}
              disabled={generating || !selectedTemplate}
              data-testid="generate-doc-confirm"
              className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
            >
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {generating ? "Génération…" : "Générer le PDF"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
