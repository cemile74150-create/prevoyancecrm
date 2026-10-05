import React, { useEffect, useState, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import api, { openAuthenticatedBlob, downloadAuthenticatedBlob } from "@/lib/api";
import { documentDisplayName, hasWordDownload, openClientDocument, wordDownloadFilename, wordDownloadPath } from "@/lib/documents";
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
import ClientDuplicateDialog from "@/components/ClientDuplicateDialog";
import { parseClientDuplicateError } from "@/lib/clientDuplicate";
import { STATUTS, normalizeStatut, DOCUMENT_TYPES_3P, NO_EXPIRY_DOC_TYPES_3P } from "@/lib/constants";
import { finmaByConseillerName, lookupConseillerFinma } from "@/lib/conseillers";
import { useAuth } from "@/context/AuthContext";
import { getInitialDocumentChecklistState, getNextDocumentStatus, getDemandesChecklistItems, getChecklistDisplayLabel, isStandardChecklistItem, omitChecklistItem } from "@/lib/documentChecklist";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { toast } from "sonner";
import {
  RAPPEL_STATUT_LABEL,
  RAPPEL_STATUT_STYLE,
  formatRappelAttributionLine,
  formatRappelDateFr,
  rappelStatutEffectif,
  rappelStoredStatut,
} from "@/lib/rappels";
import { STATUT_STYLE as OFFRE_STATUT_STYLE, formatDateFr } from "@/lib/demandesOffres";
import {
  ArrowLeft, Pencil, Trash2, Mail, Phone, MapPin, Briefcase, Users2, AlertTriangle,
  FileText, Upload, Plus, StickyNote, CalendarClock, User, Sparkles, Loader2,
  Send, ClipboardList, Shield, Eye, Download, BarChart3, Bell, FileSpreadsheet,
  Paperclip, ExternalLink,
} from "lucide-react";

const ANALYSE_PREVOYANCE_CATEGORY = "Analyse de prévoyance";
const CLIENT_DETAIL_TABS = new Set([
  "infos",
  "rdv",
  "notes",
  "demandes",
  "docs",
  "demande-lpp",
  "demande-avs",
  "echeance3p",
  "analyse-prevoyance",
  "offres",
]);
const OFFRE_CATEGORY = "Offre";
const RACHAT_3P_DOC_CATEGORY = "Confirmation rachat 3P";

const fundNameKey = (fundOrName) => {
  if (typeof fundOrName === "string") return fundOrName.trim().toLowerCase();
  return String(fundOrName?.name || fundOrName?.nom || "").trim().toLowerCase();
};

const fundPersonKey = (fundOrName) =>
  String(fundOrName?.person || "").trim().toLowerCase();

const fundTrackKey = (fundOrName) =>
  `${fundPersonKey(fundOrName)}|${fundNameKey(fundOrName)}`;

function rappelStatutOf(d) {
  return rappelStoredStatut(d);
}

const formatLppDate = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("fr-CH");
  } catch {
    return String(iso).slice(0, 10);
  }
};

const personBadgeLabel = (person) => {
  const p = String(person || "").trim();
  if (p === "Madame") return "Madame";
  if (p === "Monsieur") return "Monsieur";
  return p || "";
};

const getCaisseReplyBadge = (caisse) => {
  if (caisse?.sent && caisse?.received) {
    return {
      label: "Réponse reçue",
      className: "border-transparent bg-emerald-100 text-emerald-800 hover:bg-emerald-100",
    };
  }
  if (caisse?.sent && !caisse?.received) {
    return {
      label: "En attente de réponse",
      className: "border-transparent bg-amber-100 text-amber-900 hover:bg-amber-100",
    };
  }
  return {
    label: "À envoyer",
    className: "border-transparent bg-slate-100 text-slate-600 hover:bg-slate-100",
  };
};

const buildTrackingFromFunds = (funds, existing = []) => {
  const previous = new Map(
    (existing || [])
      .filter((item) => item?.name)
      .map((item) => [fundTrackKey(item), item])
  );
  const tracking = [];
  const seen = new Set();
  for (const fund of funds || []) {
    const name = String(fund?.name || fund?.nom || "").trim();
    if (!name) continue;
    const person = String(fund?.person || "").trim();
    const key = fundTrackKey({ name, person });
    const prior = previous.get(key) || {};
    tracking.push({
      id: prior.id || crypto.randomUUID?.() || `${key}-${Date.now()}`,
      name,
      person: person || prior.person || "",
      address: fund?.address || fund?.adresse || prior.address || "",
      reference: fund?.reference || fund?.ref || prior.reference || "",
      source_doc_id: fund?.source_doc_id || prior.source_doc_id,
      sent: Boolean(prior.sent),
      received: Boolean(prior.received),
      sent_at: prior.sent_at || null,
      received_at: prior.received_at || null,
    });
    seen.add(key);
  }
  for (const item of existing || []) {
    const key = fundTrackKey(item);
    if (!key || key === "|" || seen.has(key)) continue;
    tracking.push({
      id: item.id || crypto.randomUUID?.() || `${key}-${Date.now()}`,
      name: item.name,
      person: item.person || "",
      address: item.address || "",
      reference: item.reference || "",
      source_doc_id: item.source_doc_id,
      sent: Boolean(item.sent),
      received: Boolean(item.received),
      sent_at: item.sent_at || null,
      received_at: item.received_at || null,
    });
    seen.add(key);
  }
  return tracking;
};

const mergeLppFundsLists = (...lists) => {
  const map = new Map();
  const order = [];
  for (const list of lists) {
    for (const fund of list || []) {
      if (!fund) continue;
      const name = String(fund.name || fund.nom || "").trim();
      if (!name) continue;
      const person = String(fund.person || "").trim();
      const key = fundTrackKey({ name, person });
      if (map.has(key)) {
        map.set(key, { ...map.get(key), ...fund, name, person: person || map.get(key).person || "" });
      } else {
        map.set(key, { ...fund, name, person });
        order.push(key);
      }
    }
  }
  return order.map((k) => map.get(k));
};

const Info = ({ label, value }) => (
  <div>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="text-sm font-medium mt-0.5">{value || "—"}</p>
  </div>
);

/** Âge en années révolues à partir d'une date de naissance (ISO ou JJ.MM.AAAA). */
const calcAgeFromBirthDate = (dateNaissance) => {
  if (!dateNaissance) return null;
  const raw = String(dateNaissance).trim();
  let d = new Date(raw);
  if (Number.isNaN(d.getTime())) {
    const m = raw.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})$/);
    if (!m) return null;
    d = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  }
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - d.getFullYear();
  const monthDiff = now.getMonth() - d.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < d.getDate())) age -= 1;
  return age >= 0 && age < 150 ? age : null;
};

const matchesChecklistItem = (doc, documentName) => {
  if (documentName === "Demande LPP") {
    return ["Demande LPP", "Procuration", "Formulaire Recherche LPP"].includes(doc.checklist_item)
      || ["Demande LPP", "Procuration", "Formulaire de recherche LPP"].includes(doc.category);
  }
  return doc.checklist_item === documentName || doc.category === documentName;
};

const FileChip = ({ doc, onDelete }) => {
  const label = documentDisplayName(doc);
  const tip = doc.title && doc.original_filename && doc.title !== doc.original_filename
    ? `${doc.original_filename} (${doc.title})`
    : (doc.original_filename || label);
  const openDoc = async (e) => {
    e.preventDefault();
    try {
      await openClientDocument(doc, openAuthenticatedBlob);
    } catch {
      /* 401 redirect handled by api interceptor */
    }
  };
  const word = hasWordDownload(doc);
  return (
  <div className="inline-flex items-center gap-0.5 max-w-[240px]">
    <button
      type="button"
      onClick={openDoc}
      data-testid={`doc-chip-${doc.id}`}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-border bg-secondary/50 text-xs hover:border-[#002FA7] hover:text-[#002FA7] transition-colors min-w-0 text-left"
      title={tip}
    >
      <FileText className="h-3 w-3 flex-shrink-0" />
      <span className="truncate">{label}</span>
    </button>
    <Button
      size="icon"
      variant="ghost"
      title={word ? "Télécharger en Word" : "Télécharger"}
      onClick={() =>
        downloadAuthenticatedBlob(
          word ? wordDownloadPath(doc) : `/documents/${doc.id}/download`,
          word ? wordDownloadFilename(doc) : (doc.original_filename || "document.pdf")
        )
      }
      className="h-6 w-6 text-muted-foreground hover:text-[#002FA7] shrink-0"
      data-testid={`doc-download-${doc.id}`}
    >
      <Download className="h-3 w-3" />
    </Button>
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
};

export default function ClientDetail() {
  const { hasPerm } = useAuth();
  const canEditClient = hasPerm("clients.edit");
  const canDeleteClient = hasPerm("clients.delete");
  const canAddDocs = hasPerm("documents.add");
  const canDeleteDocs = hasPerm("documents.delete");
  const canEditOffres = hasPerm("demandes_offres.edit");
  const canViewOffres = hasPerm("demandes_offres.view");
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [client, setClient] = useState(null);
  const [modulesActivity, setModulesActivity] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);
  const tabFromUrl = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState(
    CLIENT_DETAIL_TABS.has(tabFromUrl) ? tabFromUrl : "infos"
  );
  const [addOffreOpen, setAddOffreOpen] = useState(false);
  const [offreFormMenu, setOffreFormMenu] = useState(null);
  const [creatingOffreKey, setCreatingOffreKey] = useState(null);
  const [notes, setNotes] = useState([]);
  const [demandes, setDemandes] = useState([]);
  const [demandeForm, setDemandeForm] = useState({
    titre: "",
    description: "",
    date: "",
    heure: "",
    priorite: "normale",
    send_email: true,
    notify_crm: true,
  });
  const [savingDemande, setSavingDemande] = useState(false);
  const [docs, setDocs] = useState([]);
  const [appts, setAppts] = useState([]);
  const [actions, setActions] = useState([]);
  const [editDialog, setEditDialog] = useState(false);
  const [duplicateConflict, setDuplicateConflict] = useState(null);
  const [noteText, setNoteText] = useState("");
  const [documentChecklist, setDocumentChecklist] = useState({});
  const [echeances3p, setEcheances3p] = useState([]);
  const [savingEcheance3p, setSavingEcheance3p] = useState(false);
  const [echeance3pDraftById, setEcheance3pDraftById] = useState({});
  const [editingEcheance3pLineId, setEditingEcheance3pLineId] = useState(null);
  const [uploadingRachatLineId, setUploadingRachatLineId] = useState(null);
  const rachat3pFileRef = useRef();
  const rachat3pLineIdRef = useRef(null);
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
  const [generatingMandat, setGeneratingMandat] = useState(false);
  const checklistFileRef = useRef();
  const uploadTargetRef = useRef(null);
  const lppResponseRef = useRef();
  const otherFileRef = useRef();
  const analyseFileRef = useRef();
  const offreFileRef = useRef();
  const offreBackfillDoneRef = useRef(false);
  const [uploadingAnalyse, setUploadingAnalyse] = useState(false);
  const [uploadingOffre, setUploadingOffre] = useState(false);
  const [extractingOffres, setExtractingOffres] = useState(false);
  const [titleDialogOpen, setTitleDialogOpen] = useState(false);
  const [pendingUploadFiles, setPendingUploadFiles] = useState([]);
  const [docTitle, setDocTitle] = useState("");
  const [savingTitleUpload, setSavingTitleUpload] = useState(false);
  const [dragOverChecklist, setDragOverChecklist] = useState(null);
  const [dragOverZone, setDragOverZone] = useState(null);

  const loadAll = async ({ quiet = false } = {}) => {
    if (!quiet) {
      setLoading(true);
      setLoadError(null);
    }
    try {
      const c = await api.get(`/clients/${id}`);
      const [n, d, a, h, lib, dem, mods] = await Promise.all([
        api.get(`/clients/${id}/notes`).catch(() => ({ data: [] })),
        api.get(`/clients/${id}/documents`).catch(() => ({ data: [] })),
        api.get(`/appointments`, { params: { client_id: id } }).catch(() => ({ data: [] })),
        api.get(`/clients/${id}/actions`).catch(() => ({ data: [] })),
        api.get("/form-library").catch(() => ({ data: [] })),
        api.get(`/clients/${id}/demandes`).catch(() => ({ data: [] })),
        api.get(`/clients/${id}/modules`).catch(() => ({ data: null })),
      ]);
      setClient(c.data);
      setModulesActivity(mods.data?.found ? mods.data : null);
      // Filet de sécurité : si le backend n'a pas encore renvoyé le FINMA, le résoudre via la liste conseillers
      const consName = (c.data?.conseiller || "").trim();
      if (consName && !(c.data?.conseiller_finma || "").trim()) {
        api.get("/users/conseillers").then((res) => {
          const finma = lookupConseillerFinma(finmaByConseillerName(res.data), consName);
          if (finma) {
            setClient((prev) => (prev && prev.id === c.data.id ? { ...prev, conseiller_finma: finma } : prev));
          }
        }).catch(() => {});
      }
      setNotes(n.data); setDocs(d.data); setAppts(a.data); setActions(h.data);
      const sortRappelsByDate = (list) => {
        const toTs = (r) => {
          const day = (r.date || "").slice(0, 10);
          const t = r.heure ? String(r.heure).slice(0, 5) : "00:00";
          if (!day) return Number.POSITIVE_INFINITY;
          const dt = new Date(`${day}T${t}:00`);
          return Number.isFinite(dt.getTime()) ? dt.getTime() : Number.POSITIVE_INFINITY;
        };
        return [...list].sort((a, b) => {
          if (!!a.done !== !!b.done) return a.done ? 1 : -1;
          const diff = toTs(a) - toTs(b);
          if (diff !== 0) return diff;
          return String(a.id).localeCompare(String(b.id));
        });
      };
      setDemandes(sortRappelsByDate(Array.isArray(dem.data) ? dem.data : []));
      setLibraryForms(lib.data || []);
      const savedChecklist = c.data?.document_checklist || {};
      const migratedLpp = savedChecklist["Demande LPP"] || savedChecklist.Procuration || savedChecklist["Formulaire Recherche LPP"];
      const demandeItems = getDemandesChecklistItems(savedChecklist, d.data || []);
      const nextChecklist = getInitialDocumentChecklistState(
        [...demandeItems, "Autre formulaire"],
        {
          ...savedChecklist,
          ...(migratedLpp ? { "Demande LPP": migratedLpp } : {}),
        }
      );
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
      const forms = lib.data || [];
      setSelectedLibraryForm((prev) => {
        if (prev && forms.some((f) => f.id === prev)) return prev;
        return forms[0]?.id || "";
      });

      // Restaurer caisses LPP déjà détectées (tous les PDF réponse M./Mme fusionnés)
      const docsList = Array.isArray(d.data) ? d.data : [];
      const ownDocIds = new Set(
        docsList
          .filter((doc) => !doc.client_id || doc.client_id === id)
          .map((doc) => doc.id)
          .filter(Boolean)
      );
      const responseDocs = docsList.filter(
        (doc) =>
          (doc.category === "Réponse recherche LPP" ||
            doc.checklist_item === "Formulaire Recherche LPP")
          && (!doc.client_id || doc.client_id === id)
      );
      const fundsFromDocs = mergeLppFundsLists(
        ...responseDocs.map((doc) =>
          (Array.isArray(doc.detected_funds) ? doc.detected_funds : []).map((f) => ({
            ...f,
            person: f.person || doc.lpp_person || "",
            source_doc_id: f.source_doc_id || doc.id,
          }))
        )
      );
      const restored = mergeLppFundsLists(fundsFromDocs, c.data?.lpp_detected_funds || []).filter(
        (fund) => !fund?.source_doc_id || ownDocIds.has(fund.source_doc_id)
      );
      const savedTracking = c.data?.lpp_caisse_tracking || [];
      if (Array.isArray(restored) && restored.length > 0) {
        setLppFunds(restored);
        setSelectedFunds(restored.map((_, i) => i));
        const withFunds = responseDocs.find((doc) => Array.isArray(doc.detected_funds) && doc.detected_funds.length > 0);
        if (withFunds) setLppResponseDoc(withFunds);
        else if (c.data?.lpp_response_doc_id) {
          const match = docsList.find((doc) => doc.id === c.data.lpp_response_doc_id);
          if (match) setLppResponseDoc(match);
        }
        const synced = buildTrackingFromFunds(restored, savedTracking);
        setLppCaisseTracking(synced);
        const needsPersist =
          synced.length !== savedTracking.length ||
          synced.some((entry) => {
            const prior = savedTracking.find((p) => p.id === entry.id || fundTrackKey(p) === fundTrackKey(entry));
            return !prior || (entry.person && !prior.person);
          });
        if (needsPersist) {
          api.patch(`/clients/${id}/lpp-caisse-tracking`, { lpp_caisse_tracking: synced }).catch(() => {});
        }
      } else {
        setLppCaisseTracking(savedTracking);
      }
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : status === 404
            ? "Client introuvable"
            : status === 403
              ? "Accès non autorisé à ce dossier"
              : status === 401
                ? "Session expirée — reconnectez-vous"
                : "Impossible de charger cette fiche client";
      if (!quiet) {
        setClient(null);
        setLoadError(message);
      }
      toast.error(message);
    } finally {
      if (!quiet) setLoading(false);
    }
  };
  useEffect(() => {
    offreBackfillDoneRef.current = false;
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when client id changes
  }, [id]);

  useEffect(() => {
    const t = searchParams.get("tab");
    setActiveTab(CLIENT_DETAIL_TABS.has(t) ? t : "infos");
  }, [id, searchParams]);

  useEffect(() => {
    if (activeTab !== "offres" || !id || loading || offreBackfillDoneRef.current) return;

    const offreList = (docs || []).filter(
      (d) => d?.category === OFFRE_CATEGORY || d?.checklist_item === OFFRE_CATEGORY
    );
    const missing = offreList.filter(
      (d) =>
        d?.offre_extract == null &&
        d?.compagnie == null &&
        d?.rente_mensuelle_garantie == null &&
        d?.montant_investi == null &&
        d?.duree == null
    );
    if (missing.length === 0) {
      offreBackfillDoneRef.current = true;
      return;
    }

    let cancelled = false;
    (async () => {
      setExtractingOffres(true);
      try {
        const res = await api.post(`/clients/${id}/offres/extract-missing`);
        if (cancelled) return;
        const updated = res.data?.updated || [];
        if (updated.length > 0) {
          const byId = Object.fromEntries(updated.map((d) => [d.id, d]));
          setDocs((prev) => prev.map((d) => (byId[d.id] ? { ...d, ...byId[d.id] } : d)));
        }
      } catch {
        // Ne pas bloquer l'onglet si l'analyse rétroactive échoue
      } finally {
        if (!cancelled) {
          offreBackfillDoneRef.current = true;
          setExtractingOffres(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeTab, id, loading, docs]);

  const openAddOffreDialog = async () => {
    if (!canEditOffres) {
      toast.error("Vous n'avez pas le droit de créer une demande d'offre");
      return;
    }
    setAddOffreOpen(true);
    if (!offreFormMenu) {
      try {
        const res = await api.get("/demandes-offres/meta");
        const menu = res.data?.form_menu;
        if (menu?.families?.length) {
          setOffreFormMenu(menu);
        } else {
          setOffreFormMenu({
            families: [
              {
                id: "particulier",
                label: "Assurances particulier",
                sections: [
                  {
                    id: "pilier3",
                    label: "Formulaires 3ème pilier",
                    items: [
                      { label: "3ème pilier", form_type: "pilier3" },
                      { label: "RC-Ménage", form_type: "menage_rc" },
                      { label: "LAA employée de maison", form_type: "laa_employee_maison" },
                    ],
                  },
                ],
              },
            ],
          });
        }
      } catch {
        setOffreFormMenu({
          families: [
            {
              id: "particulier",
              label: "Assurances particulier",
              sections: [
                {
                  id: "pilier3",
                  label: "Formulaires",
                  items: [{ label: "3ème pilier", form_type: "pilier3" }],
                },
              ],
            },
          ],
        });
      }
    }
  };

  const createOffreForClient = async (item, sectionId) => {
    if (!canEditOffres || !client) return;
    if (item.coming_soon || !item.form_type) {
      toast.message("Formulaire bientôt disponible", { description: item.label });
      return;
    }
    const key = `${sectionId}-${item.label}`;
    setCreatingOffreKey(key);
    try {
      const res = await api.post("/demandes-offres", {
        form_type: item.form_type,
        form_type_label: item.label,
        client_id: client.id,
      });
      setAddOffreOpen(false);
      toast.success("Demande d'offre créée");
      navigate(`/demandes-offres/${res.data.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Création impossible");
    } finally {
      setCreatingOffreKey(null);
    }
  };

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

  const [editingNoteId, setEditingNoteId] = useState(null);
  const [editingNoteText, setEditingNoteText] = useState("");

  const startEditNote = (n) => {
    setEditingNoteId(n.id);
    setEditingNoteText(n.content);
  };

  const cancelEditNote = () => {
    setEditingNoteId(null);
    setEditingNoteText("");
  };

  const saveEditNote = async (noteId) => {
    if (!editingNoteText.trim()) return;
    try {
      const res = await api.patch(`/clients/${id}/notes/${noteId}`, { content: editingNoteText.trim() });
      setNotes((prev) => prev.map((n) => n.id === noteId ? { ...n, ...res.data } : n));
      setEditingNoteId(null);
      setEditingNoteText("");
      toast.success("Note modifiée");
    } catch {
      toast.error("Modification impossible");
    }
  };

  const reloadDemandes = async () => {
    const res = await api.get(`/clients/${id}/demandes`);
    setDemandes(Array.isArray(res.data) ? res.data : []);
  };

  const addDemande = async () => {
    if (!demandeForm.titre.trim()) {
      toast.error("Le titre est obligatoire");
      return;
    }
    if (!demandeForm.date) {
      toast.error("La date est obligatoire");
      return;
    }
    if (!demandeForm.send_email && !demandeForm.notify_crm) {
      toast.error("Activez au moins l'e-mail ou la notification CRM");
      return;
    }
    setSavingDemande(true);
    try {
      await api.post(`/clients/${id}/rappels`, {
        titre: demandeForm.titre.trim(),
        description: demandeForm.description.trim() || null,
        date: demandeForm.date,
        heure: demandeForm.heure || null,
        priorite: demandeForm.priorite || "normale",
        send_email: !!demandeForm.send_email,
        notify_crm: !!demandeForm.notify_crm,
      });
      setDemandeForm({
        titre: "",
        description: "",
        date: "",
        heure: "",
        priorite: "normale",
        send_email: true,
        notify_crm: true,
      });
      await reloadDemandes();
      toast.success("Rappel ajouté");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible d'ajouter le rappel");
    } finally {
      setSavingDemande(false);
    }
  };

  const toggleDemandeDone = async (demande) => {
    const nextDone = !demande.done;
    await setDemandeStatut(demande, nextDone ? "termine" : "a_faire");
  };

  const setDemandeStatut = async (demande, statut) => {
    try {
      if (statut === "termine") {
        await api.post(`/rappels/${demande.id}/effectuer`);
      } else {
        await api.patch(`/rappels/${demande.id}`, { statut, done: false });
      }
      await reloadDemandes();
      toast.success(
        statut === "en_attente"
          ? "Rappel mis en attente"
          : statut === "termine"
            ? "Rappel effectué"
            : "Rappel à faire",
      );
    } catch {
      toast.error("Impossible de mettre à jour le rappel");
    }
  };

  const postponeDemande = async (demande) => {
    try {
      const res = await api.post(`/rappels/${demande.id}/reporter`, { days: 14 });
      const nextDate = formatRappelDateFr(res.data?.date);
      toast.success(
        nextDate
          ? `Rappel reporté de 14 jours — nouvelle échéance le ${nextDate}`
          : "Rappel reporté de 14 jours",
      );
      await reloadDemandes();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Report impossible");
    }
  };

  const deleteDemande = async (demandeId) => {
    if (!window.confirm("Supprimer définitivement ce rappel ?")) return;
    try {
      await api.delete(`/rappels/${demandeId}`);
      await reloadDemandes();
      toast.success("Rappel supprimé");
    } catch {
      toast.error("Impossible de supprimer le rappel");
    }
  };

  const postDocumentsBatch = async (files, { category, checklistItem, title } = {}) => {
    const list = Array.from(files || []).filter(Boolean);
    if (list.length === 0) return { uploaded_count: 0, documents: [], errors: [] };
    const fd = new FormData();
    list.forEach((file) => fd.append("files", file));
    fd.append("category", category || "Autre");
    if (checklistItem) fd.append("checklist_item", checklistItem);
    if (title) fd.append("title", title);
    const res = await api.post(`/clients/${id}/documents/batch`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data || { uploaded_count: 0, documents: [], errors: [] };
  };

  const refreshDocsAfterUpload = async () => {
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
    return { docs: d.data, client: cl.data };
  };

  const uploadChecklistFiles = async (files, documentName) => {
    const list = Array.from(files || []).filter(Boolean);
    if (!list.length || !documentName) return;
    try {
      const result = await postDocumentsBatch(list, {
        category: documentName,
        checklistItem: documentName,
      });
      const n = result.uploaded_count || 0;
      const errN = result.error_count || (result.errors || []).length;
      const detected = (result.documents || []).find((d) => d.echeance_3p_detected && d.echeance_3p);
      if (detected) {
        const date = detected.echeance_3p;
        const dtype = detected?.document_type ? ` (${detected.document_type})` : "";
        toast.success(`Échéance 3e pilier détectée${dtype} : ${new Date(`${date}T00:00:00`).toLocaleDateString("fr-CH")}`);
      } else if (n > 0 && errN === 0) {
        toast.success(n > 1 ? `${n} documents téléversés` : "Document téléversé");
      } else if (n > 0) {
        toast.warning(`${n} fichier(s) ajouté(s), ${errN} échec(s)`);
      } else {
        toast.error("Échec du téléversement");
      }
      await refreshDocsAfterUpload();
    } catch (err) {
      toast.error("Échec du téléversement");
    }
  };

  const uploadChecklistDoc = async (e) => {
    const files = Array.from(e.target.files || []);
    const documentName = uploadTargetRef.current;
    e.target.value = "";
    uploadTargetRef.current = null;
    await uploadChecklistFiles(files, documentName);
  };

  const uploadOtherDoc = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    const base = (files[0].name || "").replace(/\.[^.]+$/, "") || "Document";
    setPendingUploadFiles(files);
    setDocTitle(base);
    setTitleDialogOpen(true);
  };

  const confirmTitledUpload = async () => {
    if (!pendingUploadFiles.length) return;
    const title = docTitle.trim();
    if (!title) {
      toast.error("Indiquez un intitulé pour le document");
      return;
    }
    if (title === "Autre formulaire" || title === "Autre") {
      toast.error("Choisissez un intitulé plus précis");
      return;
    }
    setSavingTitleUpload(true);
    try {
      const nextChecklist = {
        ...documentChecklist,
        [title]: documentChecklist[title] || { sent: false, received: false },
      };
      await api.patch(`/clients/${id}/document-checklist`, {
        document_checklist: nextChecklist,
      });
      setDocumentChecklist(nextChecklist);

      const result = await postDocumentsBatch(pendingUploadFiles, {
        category: title,
        checklistItem: title,
        // Pas de title forcé sur chaque fichier : on conserve le nom d'origine à l'affichage
      });
      const n = result.uploaded_count || 0;
      const errN = result.error_count || (result.errors || []).length;
      if (n > 0 && errN === 0) {
        toast.success(
          isStandardChecklistItem(title)
            ? (n > 1 ? `${n} fichiers ajoutés à « ${title} »` : `Fichier ajouté à « ${title} »`)
            : (n > 1 ? `Type « ${title} » créé — ${n} fichiers ajoutés` : `Type « ${title} » créé et fichier ajouté`)
        );
      } else if (n > 0) {
        toast.warning(`${n} fichier(s) ajouté(s), ${errN} échec(s)`);
      } else {
        toast.error("Échec de l'enregistrement");
      }

      const refreshed = await refreshDocsAfterUpload();
      const saved = refreshed.client?.document_checklist || nextChecklist;
      const demandeItems = getDemandesChecklistItems(saved, refreshed.docs || []);
      setDocumentChecklist(
        getInitialDocumentChecklistState([...demandeItems, "Autre formulaire"], saved)
      );
      setTitleDialogOpen(false);
      setPendingUploadFiles([]);
      setDocTitle("");
    } catch (err) {
      toast.error("Échec de l'enregistrement");
    } finally {
      setSavingTitleUpload(false);
    }
  };

  const uploadCategorizedDocs = async (e, category, setUploading, successSingular, successPlural) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (files.length === 0) return;
    setUploading(true);
    try {
      const result = await postDocumentsBatch(files, { category, checklistItem: category });
      const ok = result.uploaded_count || 0;
      const errN = result.error_count || (result.errors || []).length;
      if (ok > 0 && errN === 0) {
        toast.success(ok > 1 ? successPlural.replace("{n}", String(ok)) : successSingular);
      } else if (ok > 0) {
        toast.warning(`${ok} fichier(s) ajouté(s), ${errN} échec(s)`);
      } else {
        toast.error("Échec du téléversement");
      }
      const [d, h] = await Promise.all([api.get(`/clients/${id}/documents`), api.get(`/clients/${id}/actions`)]);
      setDocs(d.data);
      setActions(h.data);
    } catch (err) {
      toast.error("Échec du téléversement");
    } finally {
      setUploading(false);
    }
  };

  const uploadFilesToCategory = async (files, category, setUploading, successSingular, successPlural) => {
    const list = Array.from(files || []).filter(Boolean);
    if (!list.length) return;
    setUploading(true);
    try {
      const result = await postDocumentsBatch(list, { category, checklistItem: category });
      const ok = result.uploaded_count || 0;
      const errN = result.error_count || (result.errors || []).length;
      if (ok > 0 && errN === 0) {
        toast.success(ok > 1 ? successPlural.replace("{n}", String(ok)) : successSingular);
      } else if (ok > 0) {
        toast.warning(`${ok} fichier(s) ajouté(s), ${errN} échec(s)`);
      } else {
        toast.error("Échec du téléversement");
      }
      const [d, h] = await Promise.all([api.get(`/clients/${id}/documents`), api.get(`/clients/${id}/actions`)]);
      setDocs(d.data);
      setActions(h.data);
    } catch {
      toast.error("Échec du téléversement");
    } finally {
      setUploading(false);
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

  const onDropChecklist = async (e, documentName) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverChecklist(null);
    const files = Array.from(e.dataTransfer?.files || []);
    await uploadChecklistFiles(files, documentName);
  };

  const onDropZone = async (e, category, setUploading, successSingular, successPlural) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOverZone(null);
    const files = Array.from(e.dataTransfer?.files || []);
    await uploadFilesToCategory(files, category, setUploading, successSingular, successPlural);
  };

  const deleteDoc = async (docId) => {
    const doc = docs.find((x) => x.id === docId);
    await api.delete(`/documents/${docId}`);
    const remaining = docs.filter((x) => x.id !== docId);
    setDocs(remaining);

    const itemName = doc?.checklist_item || doc?.category;
    if (
      itemName &&
      !isStandardChecklistItem(itemName) &&
      itemName !== "Autre formulaire" &&
      itemName !== "Autre"
    ) {
      const stillHas = remaining.some((d) => matchesChecklistItem(d, itemName) && !d.generated);
      if (!stillHas) {
        const nextChecklist = omitChecklistItem(documentChecklist, itemName);
        setDocumentChecklist(nextChecklist);
        try {
          await api.patch(`/clients/${id}/document-checklist`, {
            document_checklist: nextChecklist,
          });
        } catch {
          /* la ligne disparaît déjà côté UI (plus de fichier) */
        }
      }
    }

    toast.success("Document supprimé");
    await loadAll({ quiet: true });
  };

  const removeCustomChecklistRow = async (documentName) => {
    if (isStandardChecklistItem(documentName) || documentName === "Autre formulaire") return;
    const linked = docs.filter((d) => matchesChecklistItem(d, documentName) && !d.generated);
    const msg = linked.length > 0
      ? `Supprimer la ligne « ${documentName} » et ses ${linked.length} fichier(s) ?`
      : `Supprimer la ligne « ${documentName} » ?`;
    if (!window.confirm(msg)) return;
    try {
      for (const d of linked) {
        await api.delete(`/documents/${d.id}`);
      }
      const nextChecklist = omitChecklistItem(documentChecklist, documentName);
      await api.patch(`/clients/${id}/document-checklist`, {
        document_checklist: nextChecklist,
      });
      setDocumentChecklist(nextChecklist);
      setDocs((prev) => prev.filter((d) => !matchesChecklistItem(d, documentName) || d.generated));
      toast.success(`Ligne « ${documentName} » supprimée`);
      await loadAll({ quiet: true });
    } catch {
      toast.error("Impossible de supprimer la ligne");
      await loadAll({ quiet: true });
    }
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
      if (res.data?.document_checklist) {
        setDocumentChecklist(
          getInitialDocumentChecklistState(
            getDemandesChecklistItems(res.data.document_checklist, docs),
            res.data.document_checklist,
          ),
        );
      }
    } catch (err) {
      toast.error("Impossible d'enregistrer le statut du document");
      await loadAll({ quiet: true });
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
      available.sort((a, b) => {
        if (a.id === "mandat_de_gestion") return -1;
        if (b.id === "mandat_de_gestion") return 1;
        return 0;
      });
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

  const generateMandatDeGestion = async () => {
    setGeneratingMandat(true);
    try {
      const res = await api.post(`/clients/${id}/generate-document`, {
        template_id: "mandat_de_gestion",
        checklist_item: "Mandat de gestion",
      });
      toast.success("Mandat MG + LSA généré (nouveau modèle)");
      const [d, h] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
      ]);
      setDocs(d.data);
      setActions(h.data);
      const docId = res?.data?.id;
      if (docId) {
        try {
          await openAuthenticatedBlob(`/documents/${docId}/download`);
        } catch (_) {
          /* liste déjà rafraîchie */
        }
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Génération du mandat impossible");
    } finally {
      setGeneratingMandat(false);
    }
  };

  const generateLibraryForm = async () => {
    if (!selectedLibraryForm) {
      toast.error("Choisissez un formulaire dans la bibliothèque");
      return;
    }
    setGeneratingLibrary(true);
    try {
      const res = await api.post(`/clients/${id}/generate-library-form`, {
        library_form_id: selectedLibraryForm,
      });
      const [d, h] = await Promise.all([
        api.get(`/clients/${id}/documents`),
        api.get(`/clients/${id}/actions`),
      ]);
      setDocs(d.data);
      setActions(h.data);
      toast.success("Formulaire prérempli enregistré dans le dossier");
      const docId = res?.data?.id;
      if (docId) {
        try {
          await openAuthenticatedBlob(`/documents/${docId}/download`);
        } catch (_) {
          /* liste déjà rafraîchie */
        }
      }
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
      const dup = parseClientDuplicateError(err);
      if (dup.isDuplicate) {
        setDuplicateConflict(dup);
        toast.error(dup.message);
      } else {
        toast.error(dup.message || "Impossible de créer la fiche conjoint");
      }
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
      setLppCaisseTracking(buildTrackingFromFunds(list, res.data?.lpp_caisse_tracking || []));
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
        const person = res.data?.lpp_person;
        toast.success(
          person
            ? `${list.length} caisse(s) au total (${person} pris en compte, sans écraser l'autre personne)`
            : `${list.length} caisse(s) détectée(s)`
        );
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de l'analyse du PDF (timeout possible — rechargez la page)");
      // Recharger : les caisses ont pu être persistées côté serveur malgré un timeout client
      try {
        await loadAll({ quiet: true });
      } catch (_) { /* ignore */ }
    } finally {
      setParsingLpp(false);
      e.target.value = "";
    }
  };

  const reparseLatestLppResponse = async () => {
    const responseDocs = docs.filter((d) => d.category === "Réponse recherche LPP");
    if (!responseDocs.length && !lppResponseDoc?.id) {
      toast.error("Aucune réponse LPP à réanalyser");
      return;
    }
    setParsingLpp(true);
    toast.message("Réanalyse OCR de toutes les réponses LPP…");
    try {
      const res = await api.post(`/clients/${id}/reparse-all-lpp-responses`, null, { timeout: 180000 });
      const funds = res.data?.funds ?? [];
      setLppFunds(funds);
      setLppCaisseTracking(buildTrackingFromFunds(funds, res.data?.lpp_caisse_tracking || []));
      setSelectedFunds(funds.map((_, i) => i));
      toast.success(`${funds.length} caisse(s) détectée(s) (Monsieur + Madame fusionnés)`);
      await loadAll({ quiet: true });
    } catch (err) {
      // Fallback : une seule réponse si l'endpoint multi n'est pas dispo
      const target = lppResponseDoc || responseDocs[0];
      if (!target?.id) {
        toast.error(err?.response?.data?.detail || "Réanalyse impossible");
        return;
      }
      try {
        const res = await api.post(`/clients/${id}/reparse-lpp-response/${target.id}`, null, { timeout: 120000 });
        const funds = res.data?.funds ?? [];
        setLppFunds(funds);
        setLppCaisseTracking(buildTrackingFromFunds(funds, res.data?.lpp_caisse_tracking || []));
        setSelectedFunds(funds.map((_, i) => i));
        if (res.data?.document) setLppResponseDoc(res.data.document);
        toast.success(`${funds.length} caisse(s) détectée(s)`);
        await loadAll({ quiet: true });
      } catch (err2) {
        toast.error(err2?.response?.data?.detail || "Réanalyse impossible");
      }
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
    const previous = lppCaisseTracking;
    const next = previous.map((entry) =>
      entry.id === trackingId ? { ...entry, [key]: !entry[key] } : entry
    );
    setLppCaisseTracking(next);
    try {
      const res = await api.patch(`/clients/${id}/lpp-caisse-tracking`, { lpp_caisse_tracking: next });
      setLppCaisseTracking(res.data?.lpp_caisse_tracking || next);
      // Recharger rappels si Envoyé/Reçu a changé
      if (key === "sent" || key === "received") {
        try {
          const dem = await api.get(`/clients/${id}/demandes`);
          setDemandes(Array.isArray(dem.data) ? dem.data : []);
        } catch {
          /* ignore */
        }
      }
    } catch {
      toast.error("Impossible d'enregistrer le suivi de la caisse");
      setLppCaisseTracking(previous);
    }
  };

  const trackingForFund = (fund) =>
    lppCaisseTracking.find((entry) => fundTrackKey(entry) === fundTrackKey(fund))
    || lppCaisseTracking.find((entry) => !fundPersonKey(fund) && fundNameKey(entry) === fundNameKey(fund));

  const decompteDocsForFund = (fund) => {
    const nameKey = fundNameKey(fund);
    const person = fundPersonKey(fund);
    return docs.filter((d) => {
      const isDecompte =
        d.template_id === "lettre_decompte_lpp" || d.category === "Demande de décompte LPP";
      if (!isDecompte) return false;
      if (fundNameKey(d.caisse_name || "") !== nameKey) return false;
      if (person && d.lpp_person && String(d.lpp_person).trim().toLowerCase() !== person) return false;
      return true;
    });
  };

  const generateForSelectedFunds = async () => {
    if (selectedFunds.length === 0) {
      toast.error("Sélectionnez au moins une caisse");
      return;
    }
    const funds = selectedFunds.map((i) => {
      const fund = lppFunds[i];
      if (!fund) return null;
      const tracking = trackingForFund(fund);
      const person = fund.person || tracking?.person || "";
      return {
        ...fund,
        // Personne détectée sur LE PDF de cette caisse — jamais le titulaire global du dossier.
        person,
        tracking_id: tracking?.id,
        id: tracking?.id || fund.id,
      };
    }).filter(Boolean);
    const missingPerson = funds.filter((f) => !String(f.person || "").trim());
    if (missingPerson.length > 0) {
      toast.error(
        "Certaines caisses n'ont pas de personne (Madame/Monsieur). Relancez l'analyse LPP avant de générer."
      );
      return;
    }
    setGeneratingDemand("decompte_lpp");
    try {
      const res = await api.post(`/clients/${id}/generate-decompte-letters`, { funds });
      const documents = res.data?.documents ?? [];
      const byPerson = documents.reduce((acc, d) => {
        const p = d.lpp_person || "?";
        acc[p] = (acc[p] || 0) + 1;
        return acc;
      }, {});
      const detail = Object.entries(byPerson)
        .map(([p, n]) => `${n}× ${p}`)
        .join(", ");
      toast.success(
        detail
          ? `${documents.length} demande(s) de décompte générée(s) (${detail})`
          : `${documents.length} demande(s) de décompte générée(s)`
      );
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

  const applyEcheancesFromClient = (clientData) => {
    const rawLines = Array.isArray(clientData?.echeances_3p) ? clientData.echeances_3p : null;
    if (rawLines && rawLines.length > 0) {
      setEcheances3p(
        rawLines.map((l) => ({
          ...l,
          echeance_3p: l?.echeance_3p ? String(l.echeance_3p).split("T")[0] : null,
        }))
      );
    } else {
      const legacy = clientData?.echeance_3p ? String(clientData.echeance_3p).split("T")[0] : null;
      setEcheances3p(
        legacy ? [{ id: "legacy-3p", company: null, policy_number: null, echeance_3p: legacy, detected: true }] : []
      );
    }
  };

  const saveEcheance3pLine = async (lineId) => {
    const line = echeances3p.find((l) => l?.id === lineId) || {};
    const draft = echeance3pDraftById[lineId] || {};

    const nextCompany = (draft.company !== undefined ? draft.company : line.company) || "";
    const nextPolicy = (draft.policy_number !== undefined ? draft.policy_number : line.policy_number) || "";
    const nextDate = (draft.date !== undefined ? draft.date : line.echeance_3p) || "";
    const nextType = (draft.document_type !== undefined ? draft.document_type : line.document_type) || "Autre document";
    const clearDate = NO_EXPIRY_DOC_TYPES_3P.has(nextType);

    const payload = {
      company: nextCompany.trim() ? nextCompany.trim() : null,
      policy_number: nextPolicy.trim() ? nextPolicy.trim() : null,
      echeance_3p: clearDate ? null : (nextDate ? nextDate : null),
      document_type: nextType,
    };

    setSavingEcheance3p(true);
    try {
      const res = await api.patch(`/clients/${id}/echeances-3p/${lineId}`, payload);
      const updated = res.data;
      setClient(updated);
      applyEcheancesFromClient(updated);
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
        document_type: line?.document_type || "Autre document",
      },
    });
    setEditingEcheance3pLineId(line.id);
  };

  const toggleRachat3pEffectue = async (line) => {
    if (!line?.id || line.id === "legacy-3p") {
      toast.error("Enregistre d’abord cette ligne 3e pilier.");
      return;
    }
    const next = !line.rachat_effectue;
    setEcheances3p((rows) =>
      rows.map((l) => (l.id === line.id ? { ...l, rachat_effectue: next } : l))
    );
    try {
      const res = await api.patch(`/clients/${id}/echeances-3p/${line.id}`, {
        rachat_effectue: next,
      });
      setClient(res.data);
      applyEcheancesFromClient(res.data);
    } catch {
      setEcheances3p((rows) =>
        rows.map((l) => (l.id === line.id ? { ...l, rachat_effectue: line.rachat_effectue } : l))
      );
      toast.error("Impossible d'enregistrer le rachat");
    }
  };

  const triggerRachat3pUpload = (line) => {
    if (!line?.id || line.id === "legacy-3p") {
      toast.error("Enregistre d’abord cette ligne 3e pilier.");
      return;
    }
    rachat3pLineIdRef.current = line.id;
    rachat3pFileRef.current?.click();
  };

  const onRachat3pFileSelected = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    const lineId = rachat3pLineIdRef.current;
    rachat3pLineIdRef.current = null;
    if (!file || !lineId) return;
    const line = echeances3p.find((l) => l.id === lineId) || {};
    setUploadingRachatLineId(lineId);
    try {
      const result = await postDocumentsBatch([file], {
        category: RACHAT_3P_DOC_CATEGORY,
        checklistItem: RACHAT_3P_DOC_CATEGORY,
        title: line.company
          ? `Confirmation rachat 3P — ${line.company}`
          : "Confirmation rachat 3P",
      });
      const uploaded = result.documents?.[0];
      if (!uploaded?.id) {
        toast.error(result.errors?.[0]?.error || "Échec du téléversement");
        return;
      }
      const res = await api.patch(`/clients/${id}/echeances-3p/${lineId}`, {
        rachat_doc_id: uploaded.id,
        rachat_doc_filename: uploaded.original_filename || file.name,
      });
      setClient(res.data);
      applyEcheancesFromClient(res.data);
      await refreshDocsAfterUpload();
      toast.success("Confirmation de rachat ajoutée au dossier");
    } catch {
      toast.error("Impossible de joindre le document");
    } finally {
      setUploadingRachatLineId(null);
    }
  };

  const addEcheance3pLine = async () => {
    setSavingEcheance3p(true);
    try {
      const res = await api.post(`/clients/${id}/echeances-3p`, {
        company: null,
        policy_number: null,
        echeance_3p: null,
        document_type: "Police 3a",
      });
      const updated = res.data;
      setClient(updated);
      applyEcheancesFromClient(updated);
      const lines = Array.isArray(updated?.echeances_3p) ? updated.echeances_3p : [];
      const created = lines[lines.length - 1];
      if (created?.id) {
        startEditEcheance3pLine({
          id: created.id,
          company: created.company || "",
          policy_number: created.policy_number || "",
          echeance_3p: created.echeance_3p ? String(created.echeance_3p).split("T")[0] : "",
          document_type: created.document_type || "Police 3a",
        });
      }
      toast.success("Ligne 3e pilier ajoutée — complète les informations");
    } catch (err) {
      toast.error("Impossible d'ajouter une ligne");
    } finally {
      setSavingEcheance3p(false);
    }
  };

  const deleteEcheance3pLine = async (lineId) => {
    if (!window.confirm("Supprimer ce contrat 3e pilier ? Si une police PDF est liée, elle sera aussi retirée des Documents.")) return;
    setSavingEcheance3p(true);
    try {
      const res = await api.delete(`/clients/${id}/echeances-3p/${lineId}`);
      const updated = res.data;
      setClient(updated);
      applyEcheancesFromClient(updated);
      if (editingEcheance3pLineId === lineId) setEditingEcheance3pLineId(null);
      toast.success("Contrat 3e pilier supprimé");
      await loadAll({ quiet: true });
    } catch (err) {
      toast.error("Impossible de supprimer la ligne");
    } finally {
      setSavingEcheance3p(false);
    }
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
    docs.filter((d) => {
      if (!matchesChecklistItem(d, documentName)) return false;
      // Les PDF générés depuis la bibliothèque doivent rester visibles
      if (documentName === "Autre formulaire" || documentName === "Mandat de gestion") return true;
      return !d.generated;
    });

  const getDocsForTemplates = (templateIds) =>
    docs.filter((d) => templateIds.includes(d.template_id) || templateIds.includes(d?.meta?.template_id));

  const LPP_DEMAND_TEMPLATES = ["recherche_avoirs_lpp", "procuration_avs_lpp", "lettre_lpp"];
  const AVS_DEMAND_TEMPLATES = ["calcul_rente_future", "lettre_avs"];
  const LPP_CHECKLIST = ["Demande LPP"];
  const AVS_CHECKLIST = ["Formulaire AVS"];

  const getDecompteDocs = () =>
    docs.filter((d) => d.template_id === "lettre_decompte_lpp" || d.category === "Demande de décompte LPP");

  const getUnattachedDecompteDocs = () => {
    const attached = new Set();
    const rows = lppFunds.length > 0 ? lppFunds : lppCaisseTracking;
    for (const fund of rows) {
      for (const d of decompteDocsForFund(fund)) attached.add(d.id);
    }
    return getDecompteDocs().filter((d) => !attached.has(d.id));
  };

  const getLppResponseDocs = () =>
    docs.filter((d) =>
      (d.category === "Réponse recherche LPP" || (lppResponseDoc && d.id === lppResponseDoc.id))
      && (!d.client_id || d.client_id === id)
    );

  const renderDocList = (list) =>
    list.length === 0 ? (
      <p className="text-sm text-muted-foreground">Aucun document.</p>
    ) : (
      <div className="flex flex-wrap gap-2">
        {list.map((d) => (
          <FileChip key={d.id} doc={d} onDelete={canDeleteDocs ? deleteDoc : undefined} />
        ))}
      </div>
    );

  const renderChecklistRows = (items) =>
    items.map((documentName) => {
      const status = documentChecklist[documentName] || { sent: false, received: false };
      const linkedDocs = getDocsForChecklistItem(documentName);
      const isCustom = !isStandardChecklistItem(documentName) && documentName !== "Autre formulaire";
      const isDragOver = dragOverChecklist === documentName;
      return (
        <div
          key={documentName}
          data-testid={`doc-checklist-${documentName}`}
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setDragOverChecklist(documentName);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            if (e.currentTarget.contains(e.relatedTarget)) return;
            setDragOverChecklist((cur) => (cur === documentName ? null : cur));
          }}
          onDrop={(e) => onDropChecklist(e, documentName)}
          className={`flex flex-col gap-2 rounded-md border px-3 py-2 lg:flex-row lg:items-center lg:justify-between transition-colors ${
            isDragOver ? "border-[#002FA7] bg-[#002FA7]/5" : "border-border bg-background"
          }`}
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4 min-w-0 flex-1">
            <div className="flex items-center gap-1.5 shrink-0 min-w-0">
              <span className="text-sm font-medium truncate">{getChecklistDisplayLabel(documentName)}</span>
              {isCustom && (
                <Button
                  size="icon"
                  variant="ghost"
                  title="Supprimer la ligne"
                  data-testid={`doc-checklist-remove-${documentName}`}
                  onClick={() => removeCustomChecklistRow(documentName)}
                  className="h-7 w-7 text-destructive hover:text-destructive shrink-0"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
            <div className="flex flex-wrap gap-3 text-sm">
              {documentName === "Demande LPP" && (
                <label
                  className={`inline-flex items-center gap-2 cursor-pointer rounded-md border px-2 py-1 ${
                    status.effectue
                      ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                      : "border-amber-300 bg-amber-50 text-amber-900"
                  }`}
                  title={status.effectue ? "Effectué — cliquer pour marquer À effectuer" : "À effectuer — cliquer pour marquer Effectué"}
                >
                  <Checkbox
                    data-testid={`doc-check-${documentName}-effectue`}
                    checked={Boolean(status.effectue)}
                    onCheckedChange={() => toggleDocumentStatus(documentName, "effectue")}
                  />
                  <span className="text-xs font-medium whitespace-nowrap">
                    {status.effectue ? "Effectué" : "À effectuer"}
                  </span>
                </label>
              )}
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
              {status.sent && status.sent_at && !status.received && (
                <span className="text-xs text-muted-foreground self-center">
                  Envoyé le {new Date(status.sent_at).toLocaleDateString("fr-CH")}
                </span>
              )}
            </div>
            <Button
              size="sm"
              variant="ghost"
              data-testid={`doc-upload-${documentName}`}
              onClick={() => triggerChecklistUpload(documentName)}
              title="Ajouter un ou plusieurs fichiers (ou glisser-déposer)"
              className="h-7 px-2 gap-1 text-xs text-muted-foreground hover:text-[#002FA7] shrink-0"
            >
              <Upload className="h-3.5 w-3.5" />
            </Button>
            {documentName === "Mandat de gestion" && (
              <Button
                size="sm"
                data-testid="generate-mandat-gestion"
                onClick={generateMandatDeGestion}
                disabled={generatingMandat}
                className="h-8 px-3 gap-1.5 text-xs bg-[#002FA7] hover:bg-[#00248a] text-white shrink-0"
              >
                {generatingMandat ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                Générer le mandat
              </Button>
            )}
          </div>
          {linkedDocs.length > 0 && (
            <div className="flex flex-wrap gap-1.5 justify-end lg:max-w-[55%]">
              {linkedDocs.map((d) => (
                <FileChip key={d.id} doc={d} onDelete={canDeleteDocs ? deleteDoc : undefined} />
              ))}
            </div>
          )}
        </div>
      );
    });

  if (loading) {
    return (
      <Layout>
        <div className="animate-pulse text-muted-foreground">Chargement…</div>
      </Layout>
    );
  }

  if (loadError || !client) {
    return (
      <Layout>
        <Card className="p-8 max-w-lg">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <h1 className="font-display font-bold text-xl tracking-tight mb-1">Fiche inaccessible</h1>
              <p className="text-sm text-muted-foreground mb-4">
                {loadError || "Client introuvable"}
              </p>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => navigate(-1)} className="gap-1.5">
                  <ArrowLeft className="h-4 w-4" /> Retour
                </Button>
                <Button onClick={() => loadAll()} className="bg-[#002FA7] hover:bg-[#00248a]">
                  Réessayer
                </Button>
              </div>
            </div>
          </div>
        </Card>
      </Layout>
    );
  }

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
  const demandesChecklistItems = getDemandesChecklistItems(
    documentChecklist,
    docs
  );
  const checklistNameSet = new Set([...demandesChecklistItems, "Autre formulaire"]);
  const isAutreFormulaireDoc = (d) =>
    d?.checklist_item === "Autre formulaire" || d?.category === "Autre formulaire";
  // Fichiers hors checklist + PDF générés « Autre formulaire » (bibliothèque)
  const otherDocs = docs.filter(
    (d) =>
      !isAnalysePrevoyanceDoc(d) &&
      !isOffreDoc(d) &&
      (isAutreFormulaireDoc(d) ||
        (!d.generated &&
          !checklistNameSet.has(d.checklist_item) &&
          !checklistNameSet.has(d.category)))
  );

  const formatOffreMetaLine = (d) => {
    const extract = d?.offre_extract || {};
    const hasAny =
      d?.offre_extract
      || d?.compagnie != null
      || d?.rente_mensuelle_garantie != null
      || d?.montant_investi != null
      || d?.duree != null;
    if (!hasAny) return null;
    return {
      compagnie: extract.compagnie_label || d?.compagnie || "Non indiqué",
      renteLabel: extract.rente_mensuelle_garantie_label || "Non indiqué",
      montantLabel: extract.montant_investi_label || "Non indiqué",
      dureeLabel: extract.duree_label || (d?.duree != null ? `${d.duree} ans` : "Non indiqué"),
    };
  };

  const renderSpecialDocList = (list, { emptyLabel, testIdPrefix, onDelete, showLatestBadge = false, showOffreMeta = false }) => {
    if (list.length === 0) {
      return <p className="text-sm text-muted-foreground py-4">{emptyLabel}</p>;
    }
    return (
      <div className="space-y-3">
        {list.map((d, index) => {
          const offreMeta = showOffreMeta ? formatOffreMetaLine(d) : null;
          return (
          <div key={d.id} className="flex items-start justify-between gap-3 border-b border-border pb-3 last:border-0 last:pb-0">
            <div className="min-w-0">
              <p className="text-sm font-medium truncate" title={d.original_filename}>
                {documentDisplayName(d)}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {fmtDate(d.created_at)}
                {d.author ? ` · ${d.author}` : ""}
                {showLatestBadge && index === 0 ? " · Version la plus récente" : ""}
              </p>
              {offreMeta && (
                <div className="mt-1.5 space-y-0.5" data-testid={`${testIdPrefix}-meta-${d.id}`}>
                  <p className="text-[11px] font-medium text-foreground/80">{offreMeta.compagnie}</p>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Rente mensuelle garantie : <span className="font-medium text-foreground/75">{offreMeta.renteLabel}</span>
                    {" · "}
                    Montant investi : <span className="font-medium text-foreground/75">{offreMeta.montantLabel}</span>
                    {" · "}
                    Durée : <span className="font-medium text-foreground/75">{offreMeta.dureeLabel}</span>
                  </p>
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                title="Ouvrir"
                data-testid={`${testIdPrefix}-open-${d.id}`}
                onClick={() => openClientDocument(d, openAuthenticatedBlob)}
              >
                <Eye className="h-4 w-4" />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                title={hasWordDownload(d) ? "Télécharger en Word" : "Télécharger"}
                data-testid={`${testIdPrefix}-download-${d.id}`}
                onClick={() =>
                  downloadAuthenticatedBlob(
                    hasWordDownload(d) ? wordDownloadPath(d) : `/documents/${d.id}/download`,
                    hasWordDownload(d)
                      ? wordDownloadFilename(d)
                      : (d.original_filename || "document.pdf")
                  )
                }
              >
                <Download className="h-4 w-4" />
              </Button>
              {onDelete && (
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
              )}
            </div>
          </div>
          );
        })}
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
                {canEditClient && (
                <Button size="icon" variant="ghost" onClick={() => setEditDialog(true)} data-testid="edit-client-btn"><Pencil className="h-4 w-4" /></Button>
                )}
                {canDeleteClient && (
                <Button size="icon" variant="ghost" onClick={deleteClient} data-testid="delete-client-btn" className="text-destructive hover:text-destructive"><Trash2 className="h-4 w-4" /></Button>
                )}
              </div>
            </div>
            <h1 className="font-display font-black text-2xl tracking-tight mt-4 flex items-center gap-2">
              {client.prenom} {client.nom}
              {client.priorite === "urgent" && <AlertTriangle className="h-5 w-5 text-red-600" />}
            </h1>
            {(() => {
              const age = calcAgeFromBirthDate(client.date_naissance);
              return age != null ? (
                <p className="text-sm text-muted-foreground mt-0.5" data-testid="client-age">
                  {age} ans
                </p>
              ) : null;
            })()}
            <p className="text-sm text-muted-foreground font-mono">{client.numero_dossier}</p>

            <div className="mt-3 flex flex-wrap gap-2">
              {analyseDocs.length > 0 && (
                <Button
                  size="sm"
                  data-testid="open-analyse-prevoyance-btn"
                  onClick={() => {
                    const dossierKey = client.dossier_id || client.id;
                    navigate(`/dossiers/${dossierKey}`);
                  }}
                  className="gap-1.5 bg-[#002FA7] hover:bg-[#00248a] text-white shadow-sm"
                >
                  <BarChart3 className="h-4 w-4" />
                  Analyse de prévoyance
                </Button>
              )}
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
              <Select value={normalizeStatut(client.statut)} onValueChange={changeStatut}>
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

          {modulesActivity && (
            <Card className="p-5 space-y-3" data-testid="client-modules-activity">
              <p className="text-sm font-semibold text-[#002FA7]">Activité CRM</p>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" className="border-[#002FA7]/30 text-[#002FA7]">
                  Prévoyance · {modulesActivity.prevoyance?.statut || "—"}
                </Badge>
                {(modulesActivity.offres?.count || 0) > 0 && (
                  <Badge variant="outline" className="border-violet-300 text-violet-800">
                    Offres · {modulesActivity.offres.count}
                  </Badge>
                )}
                {(modulesActivity.suivi_3p?.count || 0) > 0 && (
                  <Badge variant="outline" className="border-emerald-300 text-emerald-800">
                    Fiscalité 3P · {modulesActivity.suivi_3p.count}
                  </Badge>
                )}
                {(modulesActivity.mandats?.count || 0) > 0 && (
                  <Badge variant="outline" className="border-amber-300 text-amber-900">
                    Mandat · {modulesActivity.mandats.count}
                  </Badge>
                )}
              </div>
              {(modulesActivity.offres?.items || []).slice(0, 5).map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className="block w-full text-left text-sm text-[#002FA7] hover:underline"
                  onClick={() => navigate(`/demandes-offres/${o.id}`)}
                >
                  Offre {o.numero || o.id}{o.statut ? ` · ${o.statut}` : ""}
                </button>
              ))}
              {(modulesActivity.suivi_3p?.items || []).slice(0, 5).map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="block w-full text-left text-sm text-[#002FA7] hover:underline"
                  onClick={() => navigate(`/suivi-3p/${s.id}`)}
                >
                  Suivi 3P{s.statut_suivi ? ` · ${s.statut_suivi}` : ""}
                </button>
              ))}
              {(modulesActivity.mandats?.items || []).slice(0, 3).map((m) => (
                <p key={m.id} className="text-xs text-muted-foreground truncate">
                  Mandat · {m.original_filename || m.id}
                </p>
              ))}
            </Card>
          )}
        </div>

        {/* Right tabs */}
        <div className="lg:col-span-8">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="mb-4 flex flex-wrap h-auto gap-1">
              <TabsTrigger value="infos" data-testid="tab-infos"><User className="h-4 w-4 mr-1.5" />Infos</TabsTrigger>
              <TabsTrigger value="rdv" data-testid="tab-rdv"><CalendarClock className="h-4 w-4 mr-1.5" />Rendez-vous</TabsTrigger>
              <TabsTrigger value="notes" data-testid="tab-notes"><StickyNote className="h-4 w-4 mr-1.5" />Notes</TabsTrigger>
              <TabsTrigger value="demandes" data-testid="tab-rappels"><Bell className="h-4 w-4 mr-1.5" />Rappels</TabsTrigger>
              <TabsTrigger value="docs" data-testid="tab-docs"><FileText className="h-4 w-4 mr-1.5" />Documents</TabsTrigger>
              <TabsTrigger value="demande-lpp" data-testid="tab-demande-lpp"><ClipboardList className="h-4 w-4 mr-1.5" />Demande LPP</TabsTrigger>
              <TabsTrigger value="demande-avs" data-testid="tab-demande-avs"><Send className="h-4 w-4 mr-1.5" />Demande AVS</TabsTrigger>
              <TabsTrigger value="echeance3p" data-testid="tab-echeance3p"><Shield className="h-4 w-4 mr-1.5" />Échéance 3P</TabsTrigger>
              <TabsTrigger value="analyse-prevoyance" data-testid="tab-analyse-prevoyance"><BarChart3 className="h-4 w-4 mr-1.5" />Analyse de prévoyance</TabsTrigger>
              <TabsTrigger value="offres" data-testid="tab-offres"><FileSpreadsheet className="h-4 w-4 mr-1.5" />Offres</TabsTrigger>
            </TabsList>

            <TabsContent value="infos">
              <Card className="p-6 space-y-6">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-3">Informations personnelles</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    <Info label="Nom" value={client.nom} />
                    <Info label="Prénom" value={client.prenom} />
                    <Info label="Date de naissance" value={client.date_naissance ? formatDateFr(client.date_naissance) : null} />
                    <Info label="Adresse" value={[client.adresse, client.npa, client.ville].filter(Boolean).join(", ")} />
                    <Info label="Téléphone" value={client.telephone} />
                    <Info label="Email" value={client.email} />
                    <Info label="Sexe" value={client.sexe} />
                    <Info label="Nationalité" value={client.nationalite} />
                    <Info label="Pays de résidence" value={client.pays_residence} />
                    <Info
                      label="Frontalier"
                      value={
                        client.frontalier === "oui"
                          ? "Oui"
                          : client.frontalier === "non"
                            ? "Non"
                            : null
                      }
                    />
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
                    <Info label="N° FINMA" value={client.conseiller_finma} />
                    <Info label="Agent apporteur" value={client.agent_apporteur} />
                    <Info label="N° dossier" value={client.numero_dossier} />
                    <Info label="Statut" value={normalizeStatut(client.statut)} />
                    <Info label="Priorité" value={client.priorite} />
                  </div>
                </div>

                {(canViewOffres || canEditOffres) && (
                  <div className="border-t border-border pt-6" data-testid="client-infos-offres">
                    <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
                      <p className="text-sm font-semibold text-[#002FA7]">Offres</p>
                      {canEditOffres && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-8 gap-1.5 border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7]/5"
                          onClick={openAddOffreDialog}
                          data-testid="client-add-offre-btn"
                        >
                          <Plus className="h-4 w-4" /> Ajouter une offre
                        </Button>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mb-3">
                      Demandes d&apos;offres liées à ce client (module Demandes d&apos;offres).
                    </p>
                    {(modulesActivity?.offres?.items || []).length === 0 ? (
                      <p className="text-sm text-muted-foreground py-4 text-center border border-dashed rounded-md">
                        Aucune demande d&apos;offre liée pour l&apos;instant.
                      </p>
                    ) : (
                      <div className="rounded-md border border-border overflow-hidden">
                        <table className="w-full text-sm">
                          <thead className="bg-secondary/50 text-xs text-muted-foreground">
                            <tr>
                              <th className="text-left font-medium px-3 py-2">Offre</th>
                              <th className="text-left font-medium px-3 py-2">Statut</th>
                              <th className="w-10" />
                            </tr>
                          </thead>
                          <tbody>
                            {(modulesActivity.offres.items || []).map((o) => (
                              <tr
                                key={o.id}
                                className="border-t border-border hover:bg-secondary/30 cursor-pointer"
                                onClick={() => navigate(`/demandes-offres/${o.id}`)}
                              >
                                <td className="px-3 py-2.5 font-medium">
                                  {o.form_type_label || o.numero || "Demande d'offre"}
                                  {o.numero ? (
                                    <span className="block text-xs text-muted-foreground font-normal">{o.numero}</span>
                                  ) : null}
                                </td>
                                <td className="px-3 py-2.5">
                                  <span className={`inline-flex text-xs px-2 py-0.5 rounded-full ${OFFRE_STATUT_STYLE[o.statut] || "bg-slate-100 text-slate-700"}`}>
                                    {o.statut || "—"}
                                  </span>
                                </td>
                                <td className="px-2 py-2.5 text-muted-foreground">
                                  <ExternalLink className="h-3.5 w-3.5" />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
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
                    {notes.map((n) => {
                      const isEditing = editingNoteId === n.id;
                      return (
                        <div key={n.id} className="p-3 rounded-md border border-border bg-secondary/40">
                          {isEditing ? (
                            <>
                              <Textarea
                                value={editingNoteText}
                                onChange={(e) => setEditingNoteText(e.target.value)}
                                className="resize-none text-sm mb-2"
                                rows={Math.max(3, editingNoteText.split("\n").length + 1)}
                                autoFocus
                              />
                              <div className="flex gap-2 justify-end">
                                <Button size="sm" variant="outline" onClick={cancelEditNote}>Annuler</Button>
                                <Button size="sm" className="bg-[#002FA7] hover:bg-[#00248a]" onClick={() => saveEditNote(n.id)}>Enregistrer</Button>
                              </div>
                            </>
                          ) : (
                            <p className="text-sm whitespace-pre-wrap">{n.content}</p>
                          )}
                          <div className="flex items-center justify-between mt-2">
                            <p className="text-xs text-muted-foreground">
                              {n.author} · {fmtDate(n.created_at)}
                              {n.updated_at && n.updated_at !== n.created_at && (
                                <span className="ml-1 italic">(modifié le {fmtDate(n.updated_at)})</span>
                              )}
                            </p>
                            {canEditClient && !isEditing && (
                              <button
                                type="button"
                                onClick={() => startEditNote(n)}
                                className="text-xs text-muted-foreground hover:text-[#002FA7] flex items-center gap-1 transition-colors"
                                title="Modifier la note"
                              >
                                <Pencil className="h-3 w-3" /> Modifier
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="demandes">
              <Card className="p-6 space-y-5">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7]">Rappels</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Rappels liés à ce client. Ils apparaissent aussi dans le menu Rappels et l&apos;ordre du jour.
                  </p>
                </div>

                <div className="space-y-3 p-4 rounded-md border border-border bg-secondary/30">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Titre</Label>
                    <Input
                      data-testid="demande-titre-input"
                      value={demandeForm.titre}
                      onChange={(e) => setDemandeForm((f) => ({ ...f, titre: e.target.value }))}
                      placeholder="Ex. Rappeler pour l'offre 3e pilier"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Description (optionnel)</Label>
                    <Textarea
                      data-testid="demande-description-input"
                      value={demandeForm.description}
                      onChange={(e) => setDemandeForm((f) => ({ ...f, description: e.target.value }))}
                      placeholder="Détails utiles…"
                      rows={2}
                      className="resize-none"
                    />
                  </div>
                  <div className="flex flex-wrap items-end gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Date</Label>
                      <Input
                        type="date"
                        data-testid="rappel-date-input"
                        value={demandeForm.date}
                        onChange={(e) => setDemandeForm((f) => ({ ...f, date: e.target.value }))}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Heure</Label>
                      <Input
                        type="time"
                        data-testid="rappel-heure-input"
                        value={demandeForm.heure}
                        onChange={(e) => setDemandeForm((f) => ({ ...f, heure: e.target.value }))}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs text-muted-foreground">Priorité</Label>
                      <Select
                        value={demandeForm.priorite}
                        onValueChange={(v) => setDemandeForm((f) => ({ ...f, priorite: v }))}
                      >
                        <SelectTrigger data-testid="demande-priorite-select" className="w-[140px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="faible">Faible</SelectItem>
                          <SelectItem value="normale">Normale</SelectItem>
                          <SelectItem value="haute">Haute</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <Button
                      onClick={addDemande}
                      disabled={savingDemande}
                      data-testid="add-demande-btn"
                      className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
                    >
                      <Plus className="h-4 w-4" />
                      {savingDemande ? "…" : "Ajouter le rappel"}
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-5 pt-1">
                    <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                      <Checkbox
                        checked={!!demandeForm.send_email}
                        onCheckedChange={(v) =>
                          setDemandeForm((f) => ({ ...f, send_email: v === true }))
                        }
                        data-testid="rappel-send-email"
                      />
                      <span>Envoyer un e-mail</span>
                    </label>
                    <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
                      <Checkbox
                        checked={!!demandeForm.notify_crm}
                        onCheckedChange={(v) =>
                          setDemandeForm((f) => ({ ...f, notify_crm: v === true }))
                        }
                        data-testid="rappel-notify-crm"
                      />
                      <span>Afficher une notification dans le CRM</span>
                    </label>
                  </div>
                </div>

                {demandes.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-6 text-center">Aucun rappel pour ce dossier.</p>
                ) : (
                  <div className="space-y-4">
                    {["ouvertes", "attente", "traitees"].map((section) => {
                      const items = demandes.filter((d) => {
                        const st = rappelStatutOf(d);
                        if (section === "ouvertes") return st === "a_faire";
                        if (section === "attente") return st === "en_attente";
                        return st === "termine";
                      });
                      if (items.length === 0) return null;
                      const titles = {
                        ouvertes: `À faire (${items.length})`,
                        attente: `En attente (${items.length})`,
                        traitees: `Terminés (${items.length})`,
                      };
                      return (
                        <div key={section}>
                          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                            {titles[section]}
                          </p>
                          <div className="space-y-2">
                            {items.map((d) => {
                              const stored = rappelStatutOf(d);
                              const effectif = rappelStatutEffectif(d);
                              return (
                              <div
                                key={d.id}
                                data-testid={`demande-${d.id}`}
                                className={`flex items-start gap-3 p-3 rounded-md border border-border ${
                                  effectif === "termine"
                                    ? "bg-secondary/20 opacity-80"
                                    : effectif === "en_attente"
                                      ? "bg-amber-50/70 border-amber-200"
                                      : effectif === "echeance_passee"
                                        ? "bg-red-50/70 border-red-200"
                                        : "bg-card"
                                }`}
                              >
                                <div className="flex items-center gap-2 pt-0.5">
                                  <Checkbox
                                    checked={!!d.done}
                                    onCheckedChange={() => toggleDemandeDone(d)}
                                    data-testid={`demande-check-${d.id}`}
                                  />
                                  <span className="text-xs text-muted-foreground hidden sm:inline">Terminé</span>
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-start justify-between gap-2 flex-wrap">
                                    <p className={`text-sm font-medium ${effectif === "termine" ? "line-through text-muted-foreground" : ""}`}>
                                      {d.titre}
                                    </p>
                                    <Select value={stored} onValueChange={(v) => setDemandeStatut(d, v)}>
                                      <SelectTrigger className={`h-8 w-[9.5rem] text-xs ${RAPPEL_STATUT_STYLE[effectif] || ""}`} data-testid={`demande-statut-${d.id}`}>
                                        <SelectValue>{RAPPEL_STATUT_LABEL[effectif]}</SelectValue>
                                      </SelectTrigger>
                                      <SelectContent>
                                        <SelectItem value="a_faire">À faire</SelectItem>
                                        <SelectItem value="en_attente">En attente</SelectItem>
                                        <SelectItem value="termine">Terminé</SelectItem>
                                      </SelectContent>
                                    </Select>
                                  </div>
                                  {d.description ? (
                                    <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{d.description}</p>
                                  ) : null}
                                  <div className="flex items-center gap-2 mt-2 flex-wrap text-xs text-muted-foreground">
                                    {(d.date || d.heure) && (
                                      <span>
                                        {d.date ? new Date(`${d.date}T12:00:00`).toLocaleDateString("fr-CH") : ""}
                                        {d.heure ? ` · ${d.heure}` : ""}
                                      </span>
                                    )}
                                    {d.priorite === "haute" && !d.done && (
                                      <span className="inline-flex items-center gap-1 font-medium text-red-700 bg-red-50 border border-red-100 px-1.5 py-0.5 rounded">
                                        <AlertTriangle className="h-3 w-3" /> Haute
                                      </span>
                                    )}
                                    {d.priorite === "faible" && !d.done && (
                                      <span className="inline-flex font-medium text-emerald-700 bg-emerald-50 border border-emerald-100 px-1.5 py-0.5 rounded">
                                        Faible
                                      </span>
                                    )}
                                    {effectif === "echeance_passee" && (
                                      <span className="inline-flex font-semibold text-red-800 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">
                                        Échéance passée
                                      </span>
                                    )}
                                    {d.send_email !== false && (
                                      <span className="inline-flex font-medium text-sky-800 bg-sky-50 border border-sky-100 px-1.5 py-0.5 rounded">
                                        {d.email_sent ? "E-mail envoyé" : "E-mail prévu"}
                                      </span>
                                    )}
                                    {d.notify_crm === false && (
                                      <span className="inline-flex font-medium text-slate-600 bg-slate-50 border border-slate-200 px-1.5 py-0.5 rounded">
                                        Hors ordre du jour
                                      </span>
                                    )}
                                  </div>
                                  <p className="text-xs text-muted-foreground mt-1.5" data-testid={`demande-attribution-${d.id}`}>
                                    {formatRappelAttributionLine(d)}
                                    {d.done && d.done_at ? (
                                      <span> · Terminé le {fmtDate(d.done_at)}</span>
                                    ) : null}
                                  </p>
                                </div>
                                <div className="flex flex-col gap-1 shrink-0">
                                  {stored !== "termine" && (
                                    <>
                                      {stored !== "en_attente" && (
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          className="h-8 text-xs"
                                          onClick={() => setDemandeStatut(d, "en_attente")}
                                        >
                                          En attente
                                        </Button>
                                      )}
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-8 text-xs"
                                        onClick={() => toggleDemandeDone(d)}
                                      >
                                        Effectué
                                      </Button>
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        className="h-8 text-xs"
                                        onClick={() => postponeDemande(d)}
                                      >
                                        Reporter
                                      </Button>
                                    </>
                                  )}
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    onClick={() => deleteDemande(d.id)}
                                    className="h-8 w-8 text-destructive hover:text-destructive"
                                    data-testid={`demande-delete-${d.id}`}
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </div>
                              </div>
                            );
                            })}
                          </div>
                        </div>
                      );
                    })}
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
                <input ref={checklistFileRef} type="file" multiple className="hidden" onChange={uploadChecklistDoc} data-testid="checklist-file-input" />
                <input ref={otherFileRef} type="file" multiple className="hidden" onChange={uploadOtherDoc} data-testid="other-file-input" />
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-3">Demandes</p>
                  <p className="text-xs text-muted-foreground mb-3">
                    Suivi Envoyé / Reçu. Sélectionnez ou glissez-déposez plusieurs fichiers sur une ligne.
                    « Ajouter un fichier » crée une nouvelle ligne (ex. Compte de libre passage).
                    Les lignes ajoutées peuvent être supprimées (icône poubelle) ; elles disparaissent aussi si tous leurs fichiers sont retirés.
                  </p>
                  <div className="space-y-3">{renderChecklistRows(demandesChecklistItems)}</div>
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
                          disabled={generatingLibrary || !selectedLibraryForm || !canAddDocs}
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
                    <p className="text-sm text-muted-foreground py-2">Aucun autre fichier hors suivi.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {otherDocs.map((d) => (
                        <div key={d.id} className="flex items-center gap-1">
                          <FileChip doc={d} />
                          {canDeleteDocs && (
                          <Button size="icon" variant="ghost" onClick={() => deleteDoc(d.id)} className="h-6 w-6 text-destructive hover:text-destructive" data-testid={`doc-delete-${d.id}`}>
                            <Trash2 className="h-3 w-3" />
                          </Button>
                          )}
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
                  {renderDocList(getDocsForTemplates(LPP_DEMAND_TEMPLATES).filter((d) => !d.client_id || d.client_id === id))}
                </div>

                <div className="border-t border-border pt-4">
                  <p className="text-sm font-semibold mb-3">Suivi</p>
                  <p className="text-xs text-muted-foreground mb-3">Statuts Envoyé / Reçu de cette personne uniquement. Le conjoint a son propre suivi LPP.</p>
                  <div className="space-y-3">{renderChecklistRows(LPP_CHECKLIST)}</div>
                </div>

                <div className="border-t border-border pt-4 space-y-4">
                  <p className="text-sm font-semibold text-[#002FA7]">Réponse LPP / Caisses</p>
                  <p className="text-xs text-muted-foreground">Téléversez chaque réponse de la Centrale du 2ème pilier (ex. Recherche LPP Mme.pdf et Recherche LPP Mr.pdf). Le CRM détecte les caisses pour Monsieur et Madame séparément, puis génère une lettre de décompte par caisse. Cochez Envoyé / Reçu pour suivre chaque caisse.</p>
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
                      Relancer l&apos;analyse (tous les PDF)
                    </Button>
                  )}
                  </div>

                  {(getLppResponseDocs().length > 0 || lppResponseDoc) && (
                    <div>
                      <p className="text-sm font-medium mb-2">Réponse LPP</p>
                      {renderDocList(getLppResponseDocs().length ? getLppResponseDocs() : (lppResponseDoc ? [lppResponseDoc] : []))}
                    </div>
                  )}

                  {(lppFunds.length > 0 || lppCaisseTracking.length > 0) && (
                    <div className="space-y-3 rounded-md border border-border p-4 bg-secondary/30">
                      <p className="text-sm font-medium">Caisses détectées</p>
                      <div className="space-y-3">
                        {(lppFunds.length > 0 ? lppFunds : lppCaisseTracking).map((fund, index) => {
                          const label = fund?.name ?? fund?.nom ?? `Caisse ${index + 1}`;
                          const person = fund?.person || trackingForFund(fund)?.person || "";
                          const block = fund?.recipient_block || fund?.raw || fund?.address || fund?.adresse || "";
                          const ref = fund?.reference || fund?.ref || "";
                          const tracking =
                            trackingForFund(fund) ||
                            (lppFunds.length === 0 ? fund : null) ||
                            {
                              id: null,
                              name: label,
                              person,
                              sent: false,
                              received: false,
                            };
                          const badge = getCaisseReplyBadge(tracking);
                          const canSelectForGeneration = lppFunds.length > 0;
                          const canToggleStatus = Boolean(tracking?.id);
                          const letters = decompteDocsForFund({ ...fund, person: person || fund?.person });
                          return (
                            <div
                              key={tracking?.id || fundTrackKey(fund) || `fund-${index}`}
                              className="rounded-md border border-border bg-background px-3 py-3 space-y-2"
                              data-testid={`lpp-caisse-row-${index}`}
                            >
                              <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                                <div className="flex items-start gap-2 text-sm min-w-0 flex-1">
                                  {canSelectForGeneration && (
                                    <Checkbox
                                      checked={selectedFunds.includes(index)}
                                      onCheckedChange={() => toggleFund(index)}
                                      data-testid={`lpp-fund-${index}`}
                                      className="mt-0.5"
                                    />
                                  )}
                                  <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                      {personBadgeLabel(person) && (
                                        <Badge
                                          variant="outline"
                                          className="border-[#002FA7]/40 text-[#002FA7]"
                                          data-testid={`lpp-caisse-person-${index}`}
                                        >
                                          {person === "Madame" ? "Madame" : person === "Monsieur" ? "Monsieur" : personBadgeLabel(person)}
                                        </Badge>
                                      )}
                                      <span className="font-medium">{label}</span>
                                      <Badge className={badge.className} data-testid={`lpp-caisse-badge-${index}`}>
                                        {badge.label}
                                      </Badge>
                                    </div>
                                    {block && <p className="text-xs text-muted-foreground whitespace-pre-line mt-0.5">{block}</p>}
                                    {ref && <p className="text-xs text-muted-foreground">Réf. {ref}</p>}
                                  </div>
                                </div>
                                <div className="flex flex-col gap-2 shrink-0 lg:items-end lg:pl-2">
                                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                                    {[
                                      { key: "sent", label: "Envoyé", atKey: "sent_at" },
                                      { key: "received", label: "Reçu", atKey: "received_at" },
                                    ].map((option) => (
                                      <label key={option.key} className={`flex items-center gap-2 ${canToggleStatus ? "cursor-pointer" : "opacity-60"}`}>
                                        <Checkbox
                                          checked={Boolean(tracking[option.key])}
                                          disabled={!canToggleStatus}
                                          onCheckedChange={() => canToggleStatus && updateCaisseTracking(tracking.id, option.key)}
                                          data-testid={`lpp-caisse-${option.key}-${index}`}
                                        />
                                        <span>
                                          {option.label}
                                          {tracking[option.key] && tracking[option.atKey]
                                            ? ` — ${formatLppDate(tracking[option.atKey])}`
                                            : ""}
                                        </span>
                                      </label>
                                    ))}
                                  </div>
                                  {letters.length > 0 && (
                                    <div className="flex flex-wrap gap-1.5 justify-end" data-testid={`lpp-caisse-letters-${index}`}>
                                      {letters.map((doc) => (
                                        <FileChip key={doc.id} doc={doc} onDelete={canDeleteDocs ? deleteDoc : undefined} />
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {lppFunds.length > 0 && (
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
                      )}
                    </div>
                  )}

                  {getUnattachedDecompteDocs().length > 0 && (
                    <div>
                      <p className="text-sm font-medium mb-2">Demandes générées (non rattachées)</p>
                      {renderDocList(getUnattachedDecompteDocs())}
                    </div>
                  )}
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="demande-avs">
              <Card className="p-6 space-y-6">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-1">Demande AVS</p>
                  <p className="text-xs text-muted-foreground mb-4">Génère le formulaire rente future et la lettre d&apos;accompagnement — préremplis et enregistrés dans le CRM. Cliquez pour prévisualiser (même viewer PDF) ; téléchargez la lettre en Word au besoin.</p>
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
                  {renderDocList(getDocsForTemplates(AVS_DEMAND_TEMPLATES))}
                </div>
                <div className="border-t border-border pt-4">
                  <p className="text-sm font-semibold mb-3">Suivi</p>
                  <div className="space-y-3">{renderChecklistRows(AVS_CHECKLIST)}</div>
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="echeance3p">
              <Card className="p-6 space-y-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <p className="text-sm font-semibold text-[#002FA7]">Échéance 3e pilier</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Une ligne par PDF (Documents → Police 3e pilier). Le type de document est détecté automatiquement ; l’échéance n’est extraite que si elle est pertinente.
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={addEcheance3pLine}
                    disabled={savingEcheance3p}
                    data-testid="add-echeance-3p-btn"
                    className="h-8 gap-1.5 bg-[#002FA7] hover:bg-[#00248a]"
                  >
                    <Plus className="h-4 w-4" />
                    Ajouter un 3e pilier
                  </Button>
                </div>

                {echeances3p.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Aucun contrat 3e pilier pour l’instant. Ajoute une police dans Documents, ou clique sur « Ajouter un 3e pilier ».
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left">
                          <th className="pb-2 pr-3 font-medium text-muted-foreground whitespace-nowrap">Type</th>
                          <th className="pb-2 pr-3 font-medium text-muted-foreground whitespace-nowrap">Compagnie</th>
                          <th className="pb-2 pr-3 font-medium text-muted-foreground whitespace-nowrap">N° de police</th>
                          <th className="pb-2 pr-3 font-medium text-muted-foreground whitespace-nowrap">Date d&apos;échéance</th>
                          <th className="pb-2 font-medium text-muted-foreground whitespace-nowrap">Statut</th>
                          <th className="pb-2 font-medium text-muted-foreground whitespace-nowrap text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {echeances3p.map((line) => {
                          const draft = echeance3pDraftById[line.id] || {};
                          const iso = line?.echeance_3p;

                          const effectiveIso = draft.date !== undefined ? draft.date : iso;
                          const effectiveCompany = draft.company !== undefined ? draft.company : (line?.company || "");
                          const effectivePolicy = draft.policy_number !== undefined ? draft.policy_number : (line?.policy_number || "");
                          const effectiveType = draft.document_type !== undefined
                            ? draft.document_type
                            : (line?.document_type || "Autre document");
                          const isEditing = editingEcheance3pLineId === line.id;
                          const noExpiryType = NO_EXPIRY_DOC_TYPES_3P.has(effectiveType);

                          const dueDate = effectiveIso ? new Date(`${effectiveIso}T00:00:00`) : null;
                          const now = new Date();
                          now.setHours(0, 0, 0, 0);
                          const daysLeft = dueDate ? Math.floor((dueDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)) : null;

                          let statusLabel = "—";
                          let statusOk = false;
                          if (effectiveType === "Libre passage") {
                            statusLabel = "Compte libre passage (pas une échéance 3a)";
                            statusOk = true;
                          } else if (effectiveType === "Résiliation") {
                            statusLabel = "Résiliation — pas d’échéance créée";
                            statusOk = true;
                          } else if (effectiveType === "Rachat") {
                            statusLabel = "Rachat — pas d’échéance créée";
                            statusOk = true;
                          } else if (!effectiveIso) {
                            statusLabel = "⚠ Date d’échéance à compléter";
                          } else if (typeof daysLeft === "number" && daysLeft < 0) {
                            statusLabel = "⚠ Échéance passée";
                          } else if (typeof daysLeft === "number" && 0 <= daysLeft && daysLeft <= 365) {
                            statusLabel = "⚠ Échéance dans moins d’un an";
                          } else {
                            statusLabel = "✅ À jour";
                            statusOk = true;
                          }

                          return (
                            <tr key={line.id} className="border-t border-border">
                              <td className="py-3 pr-3 whitespace-nowrap">
                                {isEditing ? (
                                  <select
                                    className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                                    data-testid={`echeance-3p-line-type-${line.id}`}
                                    value={effectiveType}
                                    onChange={(e) => {
                                      const value = e.target.value;
                                      setEcheance3pDraftById((m) => ({
                                        ...m,
                                        [line.id]: { ...(m[line.id] || {}), document_type: value },
                                      }));
                                    }}
                                  >
                                    {DOCUMENT_TYPES_3P.map((t) => (
                                      <option key={t} value={t}>{t}</option>
                                    ))}
                                  </select>
                                ) : (
                                  <span className="inline-flex items-center rounded-md bg-secondary px-2 py-0.5 text-xs font-medium">
                                    {effectiveType}
                                  </span>
                                )}
                              </td>
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
                                  noExpiryType ? (
                                    <span className="text-muted-foreground text-xs">Non applicable</span>
                                  ) : (
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
                                  )
                                ) : (
                                  <span>
                                    {noExpiryType
                                      ? "—"
                                      : (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("fr-CH") : "—")}
                                  </span>
                                )}
                              </td>
                              <td className="py-3 whitespace-nowrap">
                                <span className={statusOk ? "text-emerald-700" : "text-amber-700"}>
                                  {statusLabel}
                                </span>
                              </td>
                              <td className="py-3 whitespace-nowrap text-right">
                                <div className="inline-flex items-center gap-1 justify-end">
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
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => deleteEcheance3pLine(line.id)}
                                    disabled={savingEcheance3p}
                                    className="text-destructive hover:text-destructive"
                                    data-testid={`echeance-3p-line-delete-${line.id}`}
                                  >
                                    🗑 Supprimer
                                  </Button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card className="p-6 space-y-4 mt-4">
                <input
                  ref={rachat3pFileRef}
                  type="file"
                  className="hidden"
                  onChange={onRachat3pFileSelected}
                  data-testid="rachat-3p-file-input"
                />
                <div>
                  <p className="text-sm font-semibold text-[#002FA7]">Rachats 3e pilier</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Suivi simple des rachats effectués, avec copie de la confirmation de la compagnie.
                  </p>
                </div>
                {echeances3p.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Aucun contrat 3e pilier à suivre pour le moment.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {echeances3p.map((line) => {
                      const company = line?.company || "—";
                      const rachatDoc =
                        docs.find((d) => d.id === line.rachat_doc_id && !d.is_deleted) ||
                        (line.rachat_doc_id
                          ? {
                              id: line.rachat_doc_id,
                              original_filename: line.rachat_doc_filename || "Confirmation",
                              title: "Confirmation",
                            }
                          : null);
                      return (
                        <div
                          key={line.id}
                          className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-border bg-secondary/30 px-3 py-2 text-sm"
                          data-testid={`rachat-3p-row-${line.id}`}
                        >
                          <span className="font-medium text-[#002FA7]">Rachat 3P</span>
                          <span className="text-muted-foreground">|</span>
                          <span>{company}</span>
                          <span className="text-muted-foreground">|</span>
                          <label className="inline-flex items-center gap-2 cursor-pointer">
                            <Checkbox
                              data-testid={`rachat-3p-check-${line.id}`}
                              checked={Boolean(line.rachat_effectue)}
                              onCheckedChange={() => toggleRachat3pEffectue(line)}
                            />
                            <span>
                              {line.rachat_effectue ? "✅ Rachat effectué" : "Rachat effectué"}
                            </span>
                          </label>
                          <span className="text-muted-foreground">|</span>
                          {rachatDoc ? (
                            <span className="inline-flex items-center gap-1 min-w-0">
                              <button
                                type="button"
                                className="inline-flex items-center gap-1.5 text-[#002FA7] hover:underline min-w-0"
                                title={rachatDoc.original_filename || "Confirmation"}
                                onClick={() =>
                                  openAuthenticatedBlob(`/documents/${rachatDoc.id}/download`)
                                }
                                data-testid={`rachat-3p-open-${line.id}`}
                              >
                                <Paperclip className="h-3.5 w-3.5 shrink-0" />
                                <span className="truncate">Confirmation</span>
                              </button>
                              <Button
                                size="icon"
                                variant="ghost"
                                title="Télécharger"
                                className="h-6 w-6 text-muted-foreground hover:text-[#002FA7]"
                                onClick={() =>
                                  downloadAuthenticatedBlob(
                                    `/documents/${rachatDoc.id}/download`,
                                    rachatDoc.original_filename || "confirmation-rachat.pdf"
                                  )
                                }
                                data-testid={`rachat-3p-download-${line.id}`}
                              >
                                <Download className="h-3 w-3" />
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-xs text-muted-foreground hover:text-[#002FA7]"
                                disabled={uploadingRachatLineId === line.id}
                                onClick={() => triggerRachat3pUpload(line)}
                              >
                                Remplacer
                              </Button>
                            </span>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2 gap-1.5 text-xs text-muted-foreground hover:text-[#002FA7]"
                              disabled={uploadingRachatLineId === line.id}
                              onClick={() => triggerRachat3pUpload(line)}
                              data-testid={`rachat-3p-upload-${line.id}`}
                            >
                              {uploadingRachatLineId === line.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Paperclip className="h-3.5 w-3.5" />
                              )}
                              Ajouter un document
                            </Button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="analyse-prevoyance">
              <Card
                className={`p-6 space-y-4 transition-colors ${dragOverZone === "analyse" ? "border-[#002FA7] bg-[#002FA7]/5" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOverZone("analyse");
                }}
                onDragLeave={(e) => {
                  if (e.currentTarget.contains(e.relatedTarget)) return;
                  setDragOverZone((z) => (z === "analyse" ? null : z));
                }}
                onDrop={(e) =>
                  onDropZone(
                    e,
                    ANALYSE_PREVOYANCE_CATEGORY,
                    setUploadingAnalyse,
                    "Analyse ajoutée",
                    "{n} analyses ajoutées"
                  )
                }
              >
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <p className="text-sm font-semibold text-[#002FA7]">Analyse de prévoyance</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      PDF d’analyse (sélection multiple ou glisser-déposer). Les nouvelles versions sont conservées dans l’historique.
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
                  onDelete: canDeleteDocs ? deleteAnalyseDoc : undefined,
                  showLatestBadge: true,
                })}
              </Card>
            </TabsContent>

            <TabsContent value="offres">
              {(canViewOffres || canEditOffres) && (
                <Card className="p-6 space-y-3 mb-4" data-testid="client-tab-offres-demandes">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                      <p className="text-sm font-semibold text-[#002FA7]">Demandes d&apos;offres</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Liées automatiquement via le client (module Demandes d&apos;offres).
                      </p>
                    </div>
                    {canEditOffres && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 gap-1.5 border-[#002FA7] text-[#002FA7] hover:bg-[#002FA7]/5"
                        onClick={openAddOffreDialog}
                      >
                        <Plus className="h-4 w-4" /> Ajouter une offre
                      </Button>
                    )}
                  </div>
                  {(modulesActivity?.offres?.items || []).length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4 text-center">Aucune demande liée.</p>
                  ) : (
                    <div className="space-y-1.5">
                      {(modulesActivity.offres.items || []).map((o) => (
                        <button
                          key={o.id}
                          type="button"
                          className="w-full flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-left hover:bg-secondary/40"
                          onClick={() => navigate(`/demandes-offres/${o.id}`)}
                        >
                          <span className="text-sm font-medium">{o.form_type_label || o.numero || "Offre"}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${OFFRE_STATUT_STYLE[o.statut] || "bg-slate-100 text-slate-700"}`}>
                            {o.statut || "—"}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </Card>
              )}
              <Card
                className={`p-6 space-y-4 transition-colors ${dragOverZone === "offre" ? "border-[#002FA7] bg-[#002FA7]/5" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOverZone("offre");
                }}
                onDragLeave={(e) => {
                  if (e.currentTarget.contains(e.relatedTarget)) return;
                  setDragOverZone((z) => (z === "offre" ? null : z));
                }}
                onDrop={(e) =>
                  onDropZone(e, OFFRE_CATEGORY, setUploadingOffre, "Offre ajoutée", "{n} offres ajoutées")
                }
              >
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <p className="text-sm font-semibold text-[#002FA7]">Documents d&apos;offres</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      PDF remis au client (sélection multiple ou glisser-déposer).
                      {extractingOffres ? " Analyse des offres existantes…" : ""}
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
                    Ajouter un PDF
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
                  onDelete: canDeleteDocs ? deleteOffreDoc : undefined,
                  showOffreMeta: true,
                })}
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <ClientFormDialog open={editDialog} onOpenChange={setEditDialog} client={client} onSaved={(c) => setClient(c)} />
      <ClientDuplicateDialog
        open={Boolean(duplicateConflict)}
        onOpenChange={(v) => { if (!v) setDuplicateConflict(null); }}
        conflict={duplicateConflict}
      />

      <Dialog open={addOffreOpen} onOpenChange={setAddOffreOpen}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">Ajouter une offre</DialogTitle>
            <DialogDescription>
              Nouvelle demande d&apos;offre pour {client?.prenom} {client?.nom} (client déjà sélectionné).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            {!offreFormMenu?.families?.length ? (
              <p className="text-sm text-muted-foreground py-6 text-center">
                {creatingOffreKey ? "Création…" : "Chargement du catalogue…"}
              </p>
            ) : (
              (offreFormMenu.families || []).map((family) => (
                <div key={family.id} className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{family.label}</p>
                  {(family.sections || []).map((section) => (
                    <div key={section.id} className="space-y-1.5">
                      <p className="text-sm font-medium text-[#002FA7]">{section.label}</p>
                      <div className="grid gap-1.5">
                        {(section.items || []).map((item) => {
                          const key = `${section.id}-${item.label}`;
                          const unavailable = Boolean(item.coming_soon || !item.form_type);
                          return (
                            <button
                              key={key}
                              type="button"
                              disabled={unavailable || Boolean(creatingOffreKey)}
                              onClick={() => createOffreForClient(item, section.id)}
                              className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-secondary disabled:opacity-50"
                              data-testid={`client-offre-type-${item.form_type || "soon"}`}
                            >
                              <span>
                                <span className="font-medium">{item.label}</span>
                                {item.subtitle ? (
                                  <span className="block text-xs text-muted-foreground">{item.subtitle}</span>
                                ) : null}
                              </span>
                              {creatingOffreKey === key ? (
                                <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                              ) : (
                                <Plus className="h-4 w-4 shrink-0 text-[#002FA7]" />
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOffreOpen(false)}>Annuler</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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

      <Dialog
        open={titleDialogOpen}
        onOpenChange={(open) => {
          setTitleDialogOpen(open);
          if (!open) {
            setPendingUploadFiles([]);
            setDocTitle("");
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-display">Nouveau type de document</DialogTitle>
            <DialogDescription>
              L&apos;intitulé crée une ligne dans Demandes (Envoyé / Reçu), comme Police 3e pilier.
              {pendingUploadFiles.length === 1
                ? ` Fichier : ${pendingUploadFiles[0].name}`
                : pendingUploadFiles.length > 1
                  ? ` ${pendingUploadFiles.length} fichiers sélectionnés`
                  : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-2">
            <Label className="text-xs text-muted-foreground">Intitulé du document</Label>
            <Input
              data-testid="doc-title-input"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              placeholder="Ex. Compte de libre passage"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  confirmTitledUpload();
                }
              }}
            />
            {pendingUploadFiles.length > 1 && (
              <ul className="text-xs text-muted-foreground mt-2 max-h-24 overflow-auto space-y-0.5">
                {pendingUploadFiles.map((f) => (
                  <li key={`${f.name}-${f.size}`}>{f.name}</li>
                ))}
              </ul>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setTitleDialogOpen(false);
                setPendingUploadFiles([]);
                setDocTitle("");
              }}
            >
              Annuler
            </Button>
            <Button
              onClick={confirmTitledUpload}
              disabled={savingTitleUpload || !docTitle.trim()}
              data-testid="doc-title-save"
              className="bg-[#002FA7] hover:bg-[#00248a]"
            >
              {savingTitleUpload ? <Loader2 className="h-4 w-4 animate-spin" /> : "Créer la ligne"}
            </Button>
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
