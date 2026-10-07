import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import OffreSchemaForm from "@/components/OffreSchemaForm";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  MODIFICATION_COMPARE_FIELDS,
  OFFRES_FORM_MENU_FALLBACK,
  STATUT_STYLE,
  buildModificationChanges,
  emptyForm,
  fieldCommentKey,
  formatDateFr,
  formatChf,
  toIsoDate,
  toSwissDate,
  valuesEqual,
} from "@/lib/demandesOffres";
import { agentIdentityFromUser } from "@/lib/offreAgentIdentity";
import {
  ArrowLeft, FileUp, Loader2, Pencil, Search, Send, ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";

const ACCENT = "#002FA7";

function errorMessage(e, fallback) {
  const detail = e?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((x) => x.msg).filter(Boolean).join(" · ") || fallback;
  return fallback;
}

function Field({ label, children, changed, className = "" }) {
  return (
    <div className={`space-y-1.5 rounded-md ${changed ? "border border-rose-600 bg-rose-50/80 px-2.5 py-2" : ""} ${className}`}>
      <div className="flex items-center gap-2">
        <Label className={`text-xs ${changed ? "text-rose-700 font-semibold" : "text-muted-foreground"}`}>{label}</Label>
        {changed && (
          <span className="inline-flex rounded-full bg-rose-500/15 text-rose-800 ring-1 ring-inset ring-rose-500/30 px-1.5 py-0.5 text-[10px] font-semibold">
            Modifié
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

const CHANGED_CONTROL =
  "border-rose-600 bg-rose-50 text-rose-700 placeholder:text-rose-400 focus-visible:ring-rose-400";

function ChangedInput({ changed, className = "", ...props }) {
  return (
    <Input
      {...props}
      className={`${className} ${changed ? CHANGED_CONTROL : ""}`}
    />
  );
}

function modificationsComment(note, changes) {
  const parts = [];
  const cleaned = (note || "").trim();
  if (cleaned) parts.push(cleaned);
  if (changes?.length) {
    if (parts.length) parts.push("");
    parts.push("Modifications :");
    for (const change of changes) {
      const label = change.label || change.field || "Champ";
      parts.push(`- ${label} : ${formatChangeVal(change.old)} → ${formatChangeVal(change.new)}`);
    }
  }
  return parts.join("\n");
}

function formatChangeVal(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.join(", ") || "—";
  return String(v);
}

function isLegacyType(formType) {
  return !formType || formType === "pilier3_legacy";
}

export default function ModifierOffre() {
  const navigate = useNavigate();
  const { hasPerm, user, isAdmin } = useAuth();
  const canEdit = hasPerm("demandes_offres.edit");
  const pdfRef = useRef(null);
  const userTouchedRef = useRef(false);
  const agentIdentity = useMemo(() => agentIdentityFromUser(user), [user]);

  const [formMenu, setFormMenu] = useState(null);
  const [phase, setPhase] = useState("catalog"); // catalog | workspace
  const [selectedType, setSelectedType] = useState(null); // { form_type, label }

  const [demande, setDemande] = useState(null);
  const [source, setSource] = useState(null); // null | "pdf" | "leosoft" | "off" | "refus"
  const [formOrigin, setFormOrigin] = useState(null); // null | "stored" | "pdf"
  const [draftId, setDraftId] = useState(null);
  const [numeroInput, setNumeroInput] = useState("");
  const [openingNumero, setOpeningNumero] = useState(false);
  const [nameQuery, setNameQuery] = useState("");
  const [searchHits, setSearchHits] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchDone, setSearchDone] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [form, setForm] = useState(() => emptyForm());
  const [formPayload, setFormPayload] = useState({});
  const [payloadSnapshot, setPayloadSnapshot] = useState({});
  const [schema, setSchema] = useState(null);
  const [note, setNote] = useState("");
  const [extracted, setExtracted] = useState(null);
  const [pdfReady, setPdfReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [manualKeys, setManualKeys] = useState(() => new Set());
  const [prefilledCount, setPrefilledCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get("/demandes-offres/meta");
        if (!cancelled) setFormMenu(res.data?.form_menu || null);
      } catch {
        if (!cancelled) setFormMenu(null);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const families = formMenu?.families?.length
    ? formMenu.families
    : OFFRES_FORM_MENU_FALLBACK.families;

  const resetWorkspace = () => {
    setDemande(null);
    setSource(null);
    setFormOrigin(null);
    setDraftId(null);
    setSnapshot(null);
    setForm(emptyForm());
    setFormPayload({});
    setPayloadSnapshot({});
    setSchema(null);
    setNote("");
    setExtracted(null);
    setPdfReady(false);
    setManualKeys(new Set());
    setPrefilledCount(0);
    userTouchedRef.current = false;
  };

  const openFormType = async (item) => {
    const formType = item.form_type || "pilier3_legacy";
    setSelectedType({ form_type: formType, label: item.label || formType });
    resetWorkspace();
    setPhase("workspace");
    if (!isLegacyType(formType)) {
      try {
        const res = await api.get(`/demandes-offres/form-types/${formType}`);
        setSchema(res.data?.schema || res.data || null);
      } catch {
        setSchema(null);
        toast.message("Schéma du formulaire indisponible — saisie libre des champs PDF");
      }
    }
  };

  const backToCatalog = () => {
    setPhase("catalog");
    setSelectedType(null);
    resetWorkspace();
  };

  const applyPrefill = (data) => {
    const fields = data.fields || {};
    const payload = data.form_payload || {};
    const nextForm = { ...emptyForm(), ...fields };
    if (fields.date_naissance) nextForm.date_naissance = toSwissDate(fields.date_naissance) || "";
    if (fields.date_debut) nextForm.date_debut = toSwissDate(fields.date_debut) || String(fields.date_debut).slice(0, 10);
    if (fields.montant_prime != null && fields.montant_prime !== "") {
      nextForm.montant_prime = fields.montant_prime;
    }
    if (Array.isArray(fields.compagnies)) nextForm.compagnies = fields.compagnies;
    setForm(nextForm);
    setFormPayload(payload);
    // Snapshot = valeurs PDF → seuls les changements manuels sont marqués « Modifié »
    setSnapshot({ ...nextForm, compagnies: [...(nextForm.compagnies || [])] });
    setPayloadSnapshot({ ...payload });
    setExtracted(data.extracted || null);
    setPdfReady(true);
    setFormOrigin("pdf");
    userTouchedRef.current = false;
    setManualKeys(new Set());
    setPrefilledCount(Array.isArray(data.filled_keys) ? data.filled_keys.length : 0);
    const action = data.action || (data.demande?.id ? "rattacher" : "creer");
    if (action === "rattacher" && data.demande?.id) {
      const keptNumero = data.demande.numero || data.numero || "";
      setDemande({
        id: data.demande.id,
        numero: keptNumero,
        email_subject: data.demande.email_subject || data.email_subject || "",
        statut: data.demande.statut,
        prenom: data.demande.prenom || "",
        nom: data.demande.nom || "",
      });
      if (keptNumero) setNumeroInput(keptNumero);
      setSource("off");
      setDraftId(null);
      return;
    }
    if (action === "rattacher" || action === "refus") {
      setDemande(null);
      setSource("refus");
      setDraftId(null);
      const shown = data.numero || data.numero_detecte || "";
      if (shown) setNumeroInput(shown);
      return;
    }
    // PDF sans numéro OFF : préremplissage, nouvelle demande à l'envoi.
    setDemande(null);
    setSource("pdf");
    setDraftId(null);
  };

  const uploadPdf = async (event) => {
    const file = event.target.files?.[0];
    if (!file || !selectedType) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("form_type", selectedType.form_type);
      if (numeroInput.trim()) fd.append("numero", numeroInput.trim());

      const res = await api.post("/demandes-offres/modifier/analyse-pdf", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const data = res.data;
      const action = data.action || (data.demande?.id ? "rattacher" : "creer");
      if (action === "creer" && source === "leosoft") {
        toast.message("PDF hors LeoSoft : une nouvelle demande sera créée. L'offre déjà enregistrée n'est pas modifiée.");
      }
      applyPrefill(data);
      const nFilled = Array.isArray(data.filled_keys)
        ? data.filled_keys.length
        : Object.keys(data.fields || {}).filter((k) => data.fields[k] != null && data.fields[k] !== "").length;
      if (action === "rattacher") {
        const kept = data.demande?.numero || data.numero || "la demande existante";
        toast.success(`PDF rattaché à ${kept} — numéro OFF et objet e-mail conservés`);
      } else if (action === "refus") {
        toast.error("Ce n° OFF ne correspond à aucune demande. Aucune nouvelle demande n'a été créée.");
      } else {
        toast.success(
          nFilled
            ? `PDF analysé — ${nFilled} champ(s) prérempli(s)`
            : "PDF importé — peu de champs détectés, vérifiez manuellement",
        );
      }
    } catch (e) {
      toast.error(errorMessage(e, "Extraction PDF impossible"));
    } finally {
      setUploading(false);
      if (pdfRef.current) pdfRef.current.value = "";
    }
  };

  const rechercherClient = async () => {
    const q = nameQuery.trim();
    if (q.length < 2) {
      toast.error("Saisissez au moins 2 caractères du nom du client");
      return;
    }
    setSearching(true);
    setSearchDone(false);
    try {
      const res = await api.get("/demandes-offres/modifier/recherche", { params: { q, limit: 30 } });
      setSearchHits(Array.isArray(res.data) ? res.data : []);
      setSearchDone(true);
    } catch (e) {
      toast.error(errorMessage(e, "Recherche impossible"));
    } finally {
      setSearching(false);
    }
  };

  const selectExisting = async (hit, mode) => {
    if (!hit?.id) return;
    setBusy(true);
    try {
      const res = await api.get(`/demandes-offres/${hit.id}`);
      const data = res.data || {};
      const formType = data.form_type || hit.form_type || "pilier3_legacy";
      const label = data.form_type_label || hit.form_type_label || formType;
      const keptNumero = data.numero || hit.numero || "";
      setSelectedType({ form_type: formType, label });
      setSource(mode === "off" ? "off" : "leosoft");
      setFormOrigin("stored");
      setDraftId(null);
      setDemande({
        id: data.id,
        numero: keptNumero,
        email_subject: data.email_subject || hit.email_subject || "",
        statut: data.statut,
        prenom: data.prenom || hit.prenom || "",
        nom: data.nom || hit.nom || "",
      });
      if (mode === "off" && keptNumero) setNumeroInput(keptNumero);
      setPdfReady(false);
      setExtracted(null);
      setNote("");
      userTouchedRef.current = false;
      setManualKeys(new Set());
      const payload = data.form_payload && typeof data.form_payload === "object" ? data.form_payload : {};
      setFormPayload(payload);
      setPayloadSnapshot({ ...payload });
      const nextForm = { ...emptyForm() };
      for (const key of Object.keys(nextForm)) {
        if (data[key] !== undefined && data[key] !== null) nextForm[key] = data[key];
      }
      if (data.date_naissance) nextForm.date_naissance = toSwissDate(data.date_naissance) || data.date_naissance || "";
      setForm(nextForm);
      setSnapshot({ ...nextForm, compagnies: [...(nextForm.compagnies || [])] });
      const filled = Object.keys(payload).filter((key) => {
        const value = payload[key];
        if (value == null || value === "") return false;
        if (Array.isArray(value) && value.length === 0) return false;
        return true;
      });
      setPrefilledCount(filled.length);
      if (!isLegacyType(formType)) {
        try {
          const schemaRes = await api.get(`/demandes-offres/form-types/${formType}`);
          setSchema(schemaRes.data?.schema || schemaRes.data || null);
        } catch {
          setSchema(null);
          toast.message("Schéma du formulaire indisponible");
        }
      } else {
        setSchema(null);
      }
      setPhase("workspace");
      const who = mode === "off"
        ? (keptNumero || "cette offre")
        : ([hit.prenom, hit.nom].filter(Boolean).join(" ") || hit.client_label || "ce client");
      toast.success(
        mode === "off"
          ? `Offre ${who} ouverte — numéro et objet e-mail conservés`
          : `Formulaire d'origine prérempli — ${who}`,
      );
    } catch (e) {
      toast.error(errorMessage(e, "Impossible de charger cette offre"));
    } finally {
      setBusy(false);
    }
  };

  const selectLeosoft = (hit) => selectExisting(hit, "leosoft");

  const ouvrirParNumero = async () => {
    const q = numeroInput.trim();
    if (!q) {
      toast.error("Saisissez un n° d'offre existant (OFF-AAAA-NNNN)");
      return;
    }
    setOpeningNumero(true);
    try {
      const res = await api.get("/demandes-offres/modifier/recherche-numero", { params: { numero: q } });
      if (!res.data?.id) {
        toast.error("Aucune demande pour ce n° OFF. Aucune nouvelle demande n'a été créée.");
        return;
      }
      await selectExisting(res.data, "off");
    } catch (e) {
      toast.error(errorMessage(e, "Aucune demande pour ce n° OFF"));
    } finally {
      setOpeningNumero(false);
    }
  };

  const setValue = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const labelForPayloadKey = useCallback((key) => {
    const fields = schema?.fields || [];
    const field = fields.find((f) => {
      const name = f.name || f.id;
      return name === key || fieldCommentKey(name) === key;
    });
    if (!field) return key;
    const name = field.name || field.id;
    if (fieldCommentKey(name) === key) return `${field.label || name} — précision`;
    return field.label || key;
  }, [schema]);

  const onManualEdit = useCallback((name) => {
    userTouchedRef.current = true;
    setManualKeys((prev) => {
      if (prev.has(name)) return prev;
      const next = new Set(prev);
      next.add(name);
      return next;
    });
  }, []);

  const onSchemaChange = useCallback((next) => {
    setFormPayload(next);
    if (!userTouchedRef.current) {
      setPayloadSnapshot(next);
    }
  }, []);

  const changes = useMemo(() => {
    if (!isLegacyType(selectedType?.form_type)) {
      const oldFp = payloadSnapshot || {};
      const newFp = formPayload || {};
      const rows = [];
      for (const k of manualKeys) {
        if (valuesEqual(oldFp[k], newFp[k])) continue;
        rows.push({
          field: `form_payload.${k}`,
          label: labelForPayloadKey(k),
          old: oldFp[k] ?? null,
          new: newFp[k] ?? null,
        });
      }
      return rows;
    }
    return buildModificationChanges(snapshot || {}, form);
  }, [snapshot, form, payloadSnapshot, formPayload, selectedType, manualKeys, labelForPayloadKey]);

  const isChanged = useCallback(
    (key) => {
      if (!snapshot) return false;
      return !valuesEqual(snapshot[key], form[key]);
    },
    [snapshot, form],
  );

  const changedPayloadKeys = useMemo(() => {
    const oldFp = payloadSnapshot || {};
    const newFp = formPayload || {};
    return [...manualKeys].filter((k) => !valuesEqual(oldFp[k], newFp[k]));
  }, [payloadSnapshot, formPayload, manualKeys]);

  const legacyFields = () => {
    const fields = { ...form };
    if (fields.montant_prime === "") fields.montant_prime = null;
    if (fields.date_naissance) fields.date_naissance = toIsoDate(fields.date_naissance) || fields.date_naissance;
    if (fields.date_debut) fields.date_debut = toIsoDate(fields.date_debut) || fields.date_debut;
    delete fields.numero;
    delete fields.id;
    return fields;
  };

  const warnEmail = (res) => {
    if (res?.data?.email_sent === false && res.data?.email_error) {
      toast.warning("Statut enregistré, mais e-mail non envoyé", {
        description: String(res.data.email_error).slice(0, 200),
      });
    }
  };

  const envoyer = async () => {
    if (!selectedType) return;
    const attached = (source === "leosoft" || source === "off") && Boolean(demande?.id);
    if (source === "refus") {
      return toast.error("Ce n° OFF ne correspond à aucune demande. Corrigez-le ou effacez-le pour une offre hors LeoSoft.");
    }
    if (!attached && source !== "pdf") {
      return toast.error("Ouvrez une offre par n° OFF ou par nom, ou importez un PDF sans numéro OFF");
    }
    if (source === "pdf" && !pdfReady) {
      return toast.error("Importez d'abord la police / l'offre PDF pour préremplir le formulaire");
    }
    if (attached && formOrigin === "stored" && !changes.length && !note.trim()) {
      return toast.error("Modifiez au moins un champ ou ajoutez une note avant l'envoi");
    }
    if ((source === "pdf" || (attached && formOrigin === "pdf")) && !changes.length && !note.trim() && prefilledCount <= 0) {
      return toast.error("Le PDF n'a rempli aucun champ. Modifiez le formulaire ou ajoutez une note avant l'envoi.");
    }
    if (source === "pdf" && numeroInput.trim()) {
      return toast.error("Un n° OFF est saisi : ouvrez la demande existante. Aucune deuxième demande n'est créée.");
    }

    setBusy(true);
    try {
      if (attached) {
        if (!demande.snapshot_original) {
          await api.post(`/demandes-offres/${demande.id}/modifier/start`);
        }
        const body = {
          note_service_offre: note.trim() || null,
          changes,
        };
        if (isLegacyType(selectedType.form_type)) {
          body.fields = legacyFields();
        } else {
          body.form_payload = formPayload;
          body.form_type = selectedType.form_type;
          body.form_type_label = selectedType.label;
        }
        const res = await api.post(`/demandes-offres/${demande.id}/modifier/envoyer`, body);
        toast.success("Modification envoyée — numéro OFF et objet e-mail conservés");
        warnEmail(res);
        navigate(`/demandes-offres/${demande.id}`);
        return;
      }

      const comment = modificationsComment(note, changes);
      let id = draftId;
      if (!id) {
        const created = await api.post("/demandes-offres", {
          form_type: selectedType.form_type,
          form_type_label: selectedType.label,
        });
        id = created.data?.id;
        if (!id) throw new Error("Création de la demande impossible");
        setDraftId(id);
      }
      if (isLegacyType(selectedType.form_type)) {
        const fields = legacyFields();
        if (comment) {
          fields.commentaires = comment;
          fields.note_service_offre = comment;
        }
        await api.put(`/demandes-offres/${id}`, fields);
      } else {
        await api.put(`/demandes-offres/${id}`, {
          form_type: selectedType.form_type,
          form_payload: formPayload,
          commentaires: comment,
          note_service_offre: comment || null,
        });
      }
      await api.post(`/demandes-offres/${id}/validate`);
      const res = await api.post(`/demandes-offres/${id}/envoyer`);
      toast.success("Nouvelle demande envoyée au service Offre");
      warnEmail(res);
      navigate(`/demandes-offres/${id}`);
    } catch (e) {
      toast.error(errorMessage(e, "Envoi au service Offre impossible"));
    } finally {
      setBusy(false);
    }
  };

  if (!canEdit) {
    return (
      <Layout>
        <Card className="p-6 border-rose-200 bg-rose-50 max-w-xl">
          <h1 className="text-lg font-semibold text-rose-900">Accès restreint</h1>
          <p className="text-sm text-rose-700 mt-1">
            La modification d&apos;offre nécessite la permission d&apos;édition des demandes.
          </p>
        </Card>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="animate-fade-up max-w-5xl space-y-5 pb-10" data-testid="modifier-offre-page">
        <button
          type="button"
          onClick={() => (phase === "workspace" ? backToCatalog() : navigate("/demandes-offres"))}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-[#002FA7]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {phase === "workspace" ? "Tous les types d'offres" : "Demandes d'offres"}
        </button>

        <div>
          <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
            <Pencil className="h-7 w-7" style={{ color: ACCENT }} />
            Modifier une offre
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {phase === "catalog"
              ? "Offre déjà dans LeoSoft : par n° OFF ou par nom et prénom. Sans numéro OFF : choisissez le type et importez le PDF."
              : source === "leosoft" || source === "off"
                ? "La demande existante est ouverte. Le numéro OFF et l'objet e-mail restent ceux du fil. Les champs modifiés passent en rouge."
                : source === "refus"
                  ? "Ce n° OFF ne correspond à aucune demande. Aucune nouvelle demande n'est créée."
                  : "PDF sans numéro OFF : le formulaire est prérempli et l'envoi crée une nouvelle demande. Les champs modifiés passent en rouge."}
          </p>
        </div>

        <Card className="p-5 space-y-3 border-[#002FA7]/20" data-testid="modifier-offre-recherche">
          <div>
            <h2 className="font-display font-bold text-lg text-[#002FA7]">Offre déjà dans LeoSoft</h2>
            <p className="text-xs text-muted-foreground mt-1">
              Recherchez par le nom et le prénom du client. S&apos;il y a plusieurs personnes ou plusieurs offres, choisissez la bonne dans la liste.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <Input
              value={nameQuery}
              onChange={(e) => setNameQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  rechercherClient();
                }
              }}
              placeholder="Nom ou prénom du client"
              data-testid="modifier-offre-nom-client"
            />
            <Button
              type="button"
              disabled={searching || busy}
              onClick={rechercherClient}
              className="gap-2 bg-[#002FA7] hover:bg-[#00248a] shrink-0"
              data-testid="modifier-offre-rechercher"
            >
              {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Rechercher
            </Button>
          </div>
          {searchDone && searchHits.length === 0 && (
            <p className="text-sm text-muted-foreground" data-testid="modifier-offre-recherche-vide">
              Aucune offre pour ce nom. Pour une police hors LeoSoft, choisissez le type puis importez le PDF.
            </p>
          )}
          {searchHits.length > 0 && (
            <ul className="divide-y rounded-md border border-border" data-testid="modifier-offre-recherche-liste">
              {searchHits.map((hit) => {
                const who = [hit.prenom, hit.nom].filter(Boolean).join(" ") || hit.client_label || "Client";
                const selected = (source === "leosoft" || source === "off") && demande?.id === hit.id;
                return (
                  <li key={hit.id}>
                    <button
                      type="button"
                      onClick={() => selectLeosoft(hit)}
                      disabled={busy}
                      className={`w-full text-left px-3 py-2.5 hover:bg-[#002FA7]/5 ${selected ? "bg-[#002FA7]/10" : ""}`}
                      data-testid={`modifier-offre-hit-${hit.id}`}
                    >
                      <span className="block text-sm font-semibold text-slate-900">{who}</span>
                      <span className="block text-xs text-muted-foreground mt-0.5">
                        {[hit.numero, hit.form_type_label || hit.form_type, hit.date ? formatDateFr(hit.date) : null, hit.statut]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="pt-3 border-t border-border space-y-2">
            <Label className="text-xs text-muted-foreground">{"N° d'offre existant"}</Label>
            <div className="flex flex-col sm:flex-row gap-2">
              <Input
                value={numeroInput}
                onChange={(e) => setNumeroInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    ouvrirParNumero();
                  }
                }}
                placeholder="OFF-2026-0042"
                className="font-mono"
                data-testid="modifier-offre-numero"
              />
              <Button
                type="button"
                disabled={openingNumero || busy}
                onClick={ouvrirParNumero}
                className="gap-2 bg-[#002FA7] hover:bg-[#00248a] shrink-0"
                data-testid="modifier-offre-ouvrir-numero"
              >
                {openingNumero ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                Ouvrir
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Détecté automatiquement dans le PDF si présent. S&apos;il correspond à une demande, le numéro OFF et l&apos;objet e-mail sont conservés.
            </p>
          </div>
        </Card>

        {phase === "catalog" && (
          <div className="space-y-6" data-testid="modifier-offre-catalog">
            <p className="text-sm text-muted-foreground">
              Offre hors LeoSoft : choisissez le type, puis importez le PDF. Les champs absents du PDF restent vides.
            </p>
            {families.map((family) => (
              <Card key={family.id || family.label} className="p-5 space-y-4 border-[#002FA7]/15">
                <h2 className="font-display font-bold text-lg text-[#002FA7]">{family.label}</h2>
                {(family.sections || []).map((section) => (
                  <div key={section.id || section.label} className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {section.label}
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                      {(section.items || []).map((item) => (
                        <button
                          key={`${item.form_type}-${item.label}`}
                          type="button"
                          onClick={() => openFormType(item)}
                          className="text-left rounded-lg border border-border px-3.5 py-3 hover:border-[#002FA7]/50 hover:bg-[#002FA7]/5 transition group"
                          data-testid={`modifier-offre-type-${item.form_type}`}
                        >
                          <span className="block text-sm font-semibold text-slate-900 group-hover:text-[#002FA7]">
                            {item.label}
                          </span>
                          {item.subtitle ? (
                            <span className="block text-[11px] text-muted-foreground mt-0.5 leading-snug">
                              {item.subtitle}
                            </span>
                          ) : null}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </Card>
            ))}
          </div>
        )}

        {phase === "workspace" && selectedType && (
          <>
            <Card className="p-5 space-y-4 border-[#002FA7]/20">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Type d&apos;offre
                  </p>
                  <h2 className="font-display font-bold text-xl text-[#002FA7] mt-0.5">
                    {selectedType.label}
                  </h2>
                  {(source === "leosoft" || source === "off") && (demande?.prenom || demande?.nom) && (
                    <p className="text-sm font-medium text-slate-800 mt-2">
                      {[demande.prenom, demande.nom].filter(Boolean).join(" ")}
                    </p>
                  )}
                  {(source === "leosoft" || source === "off") && (demande?.numero || numeroInput) && (
                    <p className="font-mono text-sm font-semibold text-slate-800 mt-2">
                      {demande?.numero || numeroInput}
                      {demande?.email_subject ? (
                        <span className="block font-sans font-medium text-slate-600 mt-0.5">
                          {demande.email_subject}
                        </span>
                      ) : null}
                    </p>
                  )}
                  {source === "pdf" && (
                    <p className="text-sm text-slate-700 mt-2">
                      Nouvelle demande — le PDF n&apos;a pas de numéro OFF
                    </p>
                  )}
                  {source === "refus" && (
                    <p className="text-sm text-rose-700 mt-2">
                      N° OFF inconnu — aucune demande créée
                    </p>
                  )}
                  {demande?.statut && (source === "leosoft" || source === "off") && (
                    <span className={`mt-2 inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${STATUT_STYLE[demande.statut] || ""}`}>
                      {demande.statut}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <input
                    ref={pdfRef}
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    onChange={uploadPdf}
                  />
                  <Button
                    type="button"
                    disabled={uploading || busy}
                    onClick={() => pdfRef.current?.click()}
                    className="gap-2 bg-[#002FA7] hover:bg-[#00248a]"
                    data-testid="modifier-offre-import-pdf"
                  >
                    {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                    Importer la police PDF
                  </Button>
                </div>
              </div>

              <div className="grid sm:grid-cols-1 gap-3">
                <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 flex gap-2 items-start">
                  <ShieldCheck className="h-4 w-4 text-[#002FA7] shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-slate-900">Flux recommandé</p>
                    <ol className="mt-1 text-xs space-y-0.5 list-decimal list-inside text-muted-foreground">
                      <li>Par n° OFF ou par nom et prénom si l&apos;offre est dans LeoSoft ; sinon importez le PDF sans OFF</li>
                      <li>Vérifier le formulaire prérempli (champs introuvables laissés vides)</li>
                      <li>Modifier uniquement le nécessaire — ces champs passent en rouge</li>
                      <li>Envoyer au service Offre le formulaire complet et les modifications</li>
                    </ol>
                  </div>
                </div>
              </div>

              {extracted && Object.keys(extracted).length > 0 && (
                <div className="rounded-md border border-emerald-200 bg-emerald-50/80 p-3 text-sm">
                  <p className="font-semibold text-xs uppercase tracking-wide text-emerald-900 mb-2">
                    Extrait automatiquement du PDF
                  </p>
                  <dl className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1">
                    {Object.entries(extracted).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2 min-w-0">
                        <dt className="text-muted-foreground truncate">{k}</dt>
                        <dd className="font-medium text-right truncate">{String(v)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
            </Card>

            {(source === "leosoft" || source === "off" || pdfReady) && (
              <Card className="p-5 space-y-5">
                <div>
                  <h2 className="font-display font-bold text-[#002FA7]">Formulaire prérempli</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    {formOrigin === "stored"
                      ? "Même formulaire que celui enregistré pour cette demande. Seuls les champs que vous changez s'affichent en rouge. Le numéro OFF et l'objet e-mail sont conservés."
                      : "Champs remplis depuis le PDF. Ceux que vous changez s'affichent en rouge. Les autres restent tels quels."}
                  </p>
                </div>

                {isLegacyType(selectedType.form_type) ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {MODIFICATION_COMPARE_FIELDS.map(({ key, label }) => {
                      const changed = isChanged(key);
                      const isDate = key === "date_naissance" || key === "date_debut";
                      const isNum = key === "montant_prime";
                      const isArea = key === "commentaires" || key === "adresse";
                      return (
                        <Field
                          key={key}
                          label={label}
                          changed={changed}
                          className={isArea ? "sm:col-span-2" : ""}
                        >
                          {isArea ? (
                            <Textarea
                              rows={key === "commentaires" ? 3 : 2}
                              value={form[key] ?? ""}
                              onChange={(e) => setValue(key, e.target.value)}
                              className={changed ? CHANGED_CONTROL : ""}
                            />
                          ) : (
                            <ChangedInput
                              type={isNum ? "number" : "text"}
                              inputMode={isDate ? "numeric" : undefined}
                              placeholder={isDate ? "jj.mm.aaaa" : undefined}
                              value={form[key] ?? ""}
                              onChange={(e) => setValue(key, e.target.value)}
                              changed={changed}
                            />
                          )}
                          {changed && snapshot && (
                            <p className="text-[11px] text-muted-foreground">
                              Avant :{" "}
                              {key === "montant_prime"
                                ? formatChf(snapshot[key])
                                : isDate
                                  ? formatDateFr(snapshot[key])
                                  : (snapshot[key] ?? "—") || "—"}
                            </p>
                          )}
                        </Field>
                      );
                    })}
                    <Field label="Compagnies" changed={isChanged("compagnies")} className="sm:col-span-2">
                      <Input
                        value={(form.compagnies || []).join(", ")}
                        onChange={(e) =>
                          setValue(
                            "compagnies",
                            e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                          )
                        }
                        className={isChanged("compagnies") ? CHANGED_CONTROL : ""}
                        placeholder="Vaudoise, Swiss Life…"
                      />
                    </Field>
                  </div>
                ) : schema ? (
                  <OffreSchemaForm
                    schema={schema}
                    values={formPayload}
                    onChange={onSchemaChange}
                    onManualEdit={onManualEdit}
                    changedKeys={changedPayloadKeys}
                    agentIdentity={formOrigin === "stored" ? null : agentIdentity}
                    lockAgent={formOrigin === "stored" ? false : !isAdmin}
                    skipDefaults
                  />
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {Object.keys({ ...payloadSnapshot, ...formPayload }).length === 0 ? (
                      <p className="text-sm text-muted-foreground col-span-full">
                        Aucun champ extrait. Vous pouvez tout de même saisir une note et le n° d&apos;offre.
                      </p>
                    ) : (
                      Object.keys({ ...payloadSnapshot, ...formPayload }).map((key) => {
                        const changed = !valuesEqual(payloadSnapshot[key], formPayload[key]);
                        return (
                          <Field key={key} label={key} changed={changed}>
                            <ChangedInput
                              value={formPayload[key] ?? ""}
                              onChange={(e) => {
                                onManualEdit(key);
                                setFormPayload((prev) => ({ ...prev, [key]: e.target.value }));
                              }}
                              changed={changed}
                            />
                          </Field>
                        );
                      })
                    )}
                  </div>
                )}

                <Field label="Note au service Offre" className="pt-2">
                  <Textarea
                    rows={4}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="Expliquez les modifications demandées au service Offre…"
                    data-testid="modifier-offre-note"
                  />
                </Field>

                {changes.length > 0 && (
                  <div className="rounded-md border bg-slate-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-600 mb-2">
                      Récapitulatif ({changes.length} champ{changes.length > 1 ? "s" : ""} modifié
                      {changes.length > 1 ? "s" : ""})
                    </p>
                    <ul className="space-y-1 text-sm">
                      {changes.map((c) => (
                        <li key={c.field} className="flex flex-wrap gap-1">
                          <span className="font-medium">{c.label}</span>
                          <span className="text-muted-foreground">:</span>
                          <span className="line-through text-slate-400">{formatChangeVal(c.old)}</span>
                          <span>→</span>
                          <span className="text-rose-800 font-medium">{formatChangeVal(c.new)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={backToCatalog}>
                    Annuler
                  </Button>
                  <Button
                    onClick={envoyer}
                    disabled={busy}
                    className="gap-2 bg-[#002FA7] hover:bg-[#00248a]"
                    data-testid="modifier-offre-envoyer"
                  >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    Envoyer au service Offre
                  </Button>
                </div>
              </Card>
            )}

            {source !== "leosoft" && source !== "off" && !pdfReady && (
              <Card className="p-8 text-center border-dashed">
                <FileUp className="h-10 w-10 mx-auto text-[#002FA7]/70" />
                <p className="mt-3 font-medium text-slate-800">
                  Importez la police ou l&apos;offre PDF pour préremplir le formulaire « {selectedType.label} »
                </p>
                <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
                  Nom, prénom, dates, adresse, compagnie, n° de police, montants et primes seront
                  extraits automatiquement.
                </p>
                <Button
                  type="button"
                  className="mt-4 gap-2 bg-[#002FA7] hover:bg-[#00248a]"
                  disabled={uploading}
                  onClick={() => pdfRef.current?.click()}
                >
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
                  Importer la police PDF
                </Button>
              </Card>
            )}
          </>
        )}
      </div>
    </Layout>
  );
}
