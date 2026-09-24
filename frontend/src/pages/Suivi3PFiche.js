import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api, { downloadAuthenticatedPost, downloadAuthenticatedBlob, openAuthenticatedBlob, blobErrorMessage } from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ConseillerCombobox from "@/components/ConseillerCombobox";
import { conseillerNames } from "@/lib/conseillers";
import { useAuth } from "@/context/AuthContext";
import {
  SUIVI_3P_STATUTS,
  SUIVI_3P_STATUT_STYLE,
  formatChf,
  formatDateFr,
} from "@/lib/suivi3p";
import { ArrowLeft, Check, CheckCircle2, Download, ExternalLink, FileText, Loader2, Mail, Pencil, Plus, Save, Shield, Trash2, X } from "lucide-react";
import { toast } from "sonner";

function sexeDisplay(sexe) {
  if (sexe === "Homme") return "Homme (Monsieur)";
  if (sexe === "Femme") return "Femme (Madame)";
  return "";
}

function InlineField({
  label,
  display,
  isEditing,
  onEdit,
  onConfirm,
  onCancel,
  canEdit,
  testid,
  className = "",
  children,
}) {
  const empty = display === null || display === undefined || String(display).trim() === "";
  return (
    <div className={`space-y-1 ${className}`}>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {isEditing ? (
        <div className="flex items-start gap-1.5 animate-in fade-in duration-150">
          <div className="flex-1 min-w-0">{children}</div>
          <div className="flex items-center gap-0.5 pt-0.5 shrink-0">
            <button
              type="button"
              onClick={onConfirm}
              title="Valider"
              className="h-8 w-8 inline-flex items-center justify-center rounded-md text-emerald-700 hover:bg-emerald-50 transition-colors"
            >
              <Check className="h-4 w-4" strokeWidth={2.4} />
            </button>
            <button
              type="button"
              onClick={onCancel}
              title="Annuler"
              className="h-8 w-8 inline-flex items-center justify-center rounded-md text-muted-foreground hover:bg-secondary transition-colors"
            >
              <X className="h-4 w-4" strokeWidth={2.2} />
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          disabled={!canEdit}
          onClick={onEdit}
          data-testid={testid}
          className="group w-full text-left flex items-start justify-between gap-3 rounded-md px-1.5 -mx-1.5 py-1.5 min-h-[2.25rem] transition-colors hover:bg-[#002FA7]/[0.04] disabled:hover:bg-transparent disabled:cursor-default"
        >
          <span
            className={`text-sm leading-relaxed whitespace-pre-wrap break-words ${
              empty ? "text-muted-foreground/55" : "font-medium text-foreground"
            }`}
          >
            {empty ? "—" : display}
          </span>
          {canEdit && (
            <Pencil className="h-3.5 w-3.5 mt-0.5 text-muted-foreground/30 group-hover:text-[#002FA7] transition-colors shrink-0" />
          )}
        </button>
      )}
    </div>
  );
}

export default function Suivi3PFiche() {
  const { clientId } = useParams();
  const navigate = useNavigate();
  const { isGlobal, hasPerm } = useAuth();
  const canEditSuivi = hasPerm("suivi_3p.edit");
  const fileRef = useRef(null);
  const saveFlashTimer = useRef(null);
  const [fiche, setFiche] = useState(null);
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveFlash, setSaveFlash] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [generatingCourrier, setGeneratingCourrier] = useState(false);
  const [conseillerOptions, setConseillerOptions] = useState([]);
  const [editingKey, setEditingKey] = useState(null);
  const [editDraft, setEditDraft] = useState(null);
  const [form, setForm] = useState({
    prenom: "",
    nom: "",
    statut: "À analyser",
    gain_fiscal_estime: "",
    date_derniere_analyse: "",
    conseiller: "",
    client_contacte: false,
    rdv_pris: false,
    date_rdv: "",
    sexe: "",
    adresse: "",
    adresse_complement: "",
    npa: "",
    ville: "",
    pays: "",
    conjoint_prenom: "",
    conjoint_nom: "",
    notes: "",
  });

  const load = async () => {
    setLoading(true);
    try {
      const [ficheRes, docsRes] = await Promise.all([
        api.get(`/suivi-3p/${clientId}`),
        api.get(`/suivi-3p/${clientId}/documents`),
      ]);
      const data = ficheRes.data;
      setDocs(docsRes.data || []);
      applyFicheToForm(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Fiche introuvable");
      setFiche(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  useEffect(() => {
    if (!isGlobal) return;
    let cancelled = false;
    (async () => {
      try {
        const [suiviCons, usersCons] = await Promise.all([
          api.get("/suivi-3p/conseillers").catch(() => ({ data: [] })),
          api.get("/users/conseillers").catch(() => ({ data: [] })),
        ]);
        if (cancelled) return;
        const names = [
          ...(Array.isArray(suiviCons.data) ? suiviCons.data.map((c) => c.conseiller) : []),
          ...conseillerNames(usersCons.data),
        ].filter(Boolean);
        setConseillerOptions([...new Set(names)]);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isGlobal]);

  const mergedConseillerOptions = React.useMemo(() => {
    const names = [fiche?.conseiller, ...conseillerOptions].filter(Boolean);
    return [...new Set(names)];
  }, [conseillerOptions, fiche?.conseiller]);

  const applyFicheToForm = (data) => {
    setFiche(data);
    setForm({
      prenom: data.prenom || "",
      nom: data.nom || "",
      statut: data.statut_suivi || "À analyser",
      gain_fiscal_estime:
        data.gain_fiscal_estime === null || data.gain_fiscal_estime === undefined
          ? ""
          : String(data.gain_fiscal_estime),
      date_derniere_analyse: data.date_derniere_analyse || "",
      conseiller: data.conseiller || "",
      client_contacte: Boolean(data.client_contacte),
      rdv_pris: Boolean(data.rdv_pris),
      date_rdv: data.date_rdv || "",
      sexe: data.sexe || "",
      adresse: data.adresse || "",
      adresse_complement: data.adresse_complement || "",
      npa: data.npa || "",
      ville: data.ville || "",
      pays: data.pays || "",
      conjoint_prenom: data.conjoint_prenom || "",
      conjoint_nom: data.conjoint_nom || "",
      notes: data.notes || "",
    });
  };

  const saveErrorMessage = (e, fallback) => {
    const detail = e?.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length) {
      return detail.map((item) => item?.msg || item?.message || "").filter(Boolean).join(" · ") || fallback;
    }
    return fallback;
  };

  const startEdit = (key) => {
    if (!canEditSuivi) return;
    setEditingKey(key);
    setEditDraft(form[key]);
  };

  const cancelEdit = () => {
    setEditingKey(null);
    setEditDraft(null);
  };

  const confirmEdit = async (key, value = editDraft) => {
    await saveOneField(key, value);
    setEditingKey(null);
    setEditDraft(null);
  };

  const fieldKeyDown = (e, key) => {
    if (e.key === "Escape") {
      e.preventDefault();
      cancelEdit();
    }
    if (e.key === "Enter" && !e.shiftKey && e.target.tagName !== "TEXTAREA") {
      e.preventDefault();
      confirmEdit(key);
    }
  };

  const saveOneField = async (key, raw) => {
    if (!canEditSuivi) return;
    const payload = {};
    if (key === "sexe") {
      payload.sexe = raw && raw !== "unset" ? raw : null;
    } else if (key === "statut") {
      payload.statut = raw;
    } else if (key === "gain_fiscal_estime") {
      const n = Number(String(raw ?? "").trim().replace(/\s/g, "").replace(",", "."));
      payload.gain_fiscal_estime = String(raw ?? "").trim() && Number.isFinite(n) ? n : null;
    } else if (key === "date_derniere_analyse") {
      payload.date_derniere_analyse = raw || null;
    } else if (key === "conseiller") {
      payload.conseiller = String(raw || "").trim() || null;
    } else if (key === "client_contacte") {
      payload.client_contacte = Boolean(raw);
    } else if (key === "rdv_pris") {
      payload.rdv_pris = Boolean(raw);
      if (!payload.rdv_pris) payload.date_rdv = null;
    } else if (key === "date_rdv") {
      payload.date_rdv = raw || null;
      if (payload.date_rdv) payload.rdv_pris = true;
    } else if (key === "prenom" || key === "nom") {
      const val = String(raw ?? "").trim();
      if (!val) {
        toast.error(key === "prenom" ? "Le prénom ne peut pas être vide" : "Le nom ne peut pas être vide");
        return;
      }
      payload[key] = val;
    } else {
      payload[key] = String(raw ?? "").trim() || null;
    }
    setSaving(true);
    try {
      const res = await api.put(`/suivi-3p/${clientId}`, payload);
      applyFicheToForm(res.data);
      toast.success("Informations enregistrées");
      setSaveFlash(true);
      if (saveFlashTimer.current) clearTimeout(saveFlashTimer.current);
      saveFlashTimer.current = setTimeout(() => setSaveFlash(false), 3500);
    } catch (e) {
      toast.error(saveErrorMessage(e, "Enregistrement impossible"));
    } finally {
      setSaving(false);
    }
  };

  const save = async () => {
    cancelEdit();
    setSaving(true);
    try {
      const rawGain = String(form.gain_fiscal_estime ?? "").trim();
      let gain = null;
      if (rawGain) {
        const n = Number(rawGain.replace(/\s/g, "").replace(",", "."));
        gain = Number.isFinite(n) ? n : null;
      }
      const payload = {
        statut: form.statut,
        gain_fiscal_estime: gain,
        date_derniere_analyse: form.date_derniere_analyse || null,
        client_contacte: Boolean(form.client_contacte),
        rdv_pris: Boolean(form.rdv_pris),
        date_rdv: form.rdv_pris ? (form.date_rdv || null) : null,
        sexe: form.sexe || null,
        adresse: form.adresse || null,
        adresse_complement: form.adresse_complement || null,
        npa: form.npa || null,
        ville: form.ville || null,
        pays: form.pays || null,
        conjoint_prenom: form.conjoint_prenom || null,
        conjoint_nom: form.conjoint_nom || null,
        notes: form.notes || null,
      };
      if (isGlobal) {
        payload.conseiller = form.conseiller.trim() || null;
      }
      const res = await api.put(`/suivi-3p/${clientId}`, payload);
      applyFicheToForm(res.data);
      toast.success("Fiche enregistrée");
      setSaveFlash(true);
      if (saveFlashTimer.current) clearTimeout(saveFlashTimer.current);
      saveFlashTimer.current = setTimeout(() => setSaveFlash(false), 3500);
    } catch (e) {
      toast.error(saveErrorMessage(e, "Enregistrement impossible"));
    } finally {
      setSaving(false);
    }
  };

  const generateCourrier = async () => {
    setGeneratingCourrier(true);
    try {
      const name = await downloadAuthenticatedPost(
        `/suivi-3p/${clientId}/courrier`,
        {},
        `Courrier_${fiche.nom || ""}_${fiche.prenom || ""}.docx`,
      );
      toast.success(`Courrier généré : ${name}`);
      try {
        const docsRes = await api.get(`/suivi-3p/${clientId}/documents`);
        setDocs(docsRes.data || []);
      } catch {
        /* la génération a réussi ; la liste sera à jour au prochain chargement */
      }
    } catch (e) {
      toast.error(await blobErrorMessage(e, "Génération du courrier impossible"));
    } finally {
      setGeneratingCourrier(false);
    }
  };

  const uploadDoc = async (e) => {
    const files = e.target.files;
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        await api.post(`/suivi-3p/${clientId}/documents`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
      }
      toast.success("Document Analyse 3e Pilier ajouté");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload impossible");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const openDoc = async (doc) => {
    try {
      await openAuthenticatedBlob(
        `/suivi-3p/documents/${doc.id}/download`,
        doc.original_filename || "document.pdf"
      );
    } catch (err) {
      const detail = err?.response?.data?.detail;
      let msg = "Ouverture impossible";
      if (typeof detail === "string") msg = detail;
      else if (err?.message) msg = err.message;
      toast.error(await blobErrorMessage(err, msg));
    }
  };

  const deleteDoc = async (doc) => {
    if (!window.confirm(`Supprimer « ${doc.original_filename} » ?`)) return;
    try {
      await api.delete(`/suivi-3p/documents/${doc.id}`);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
      toast.success("Document supprimé");
    } catch {
      toast.error("Suppression impossible");
    }
  };

  if (loading) {
    return (
      <Layout>
        <p className="text-muted-foreground animate-pulse">Chargement de la fiche…</p>
      </Layout>
    );
  }

  if (!fiche) {
    return (
      <Layout>
        <div className="max-w-lg">
          <p className="text-muted-foreground mb-4">Client Suivi 3P introuvable.</p>
          <Button variant="outline" onClick={() => navigate("/suivi-3p")}>Retour au suivi</Button>
        </div>
      </Layout>
    );
  }

  const gainNum = Number(fiche.gain_fiscal_estime);
  const eligibleForCourrier = Number.isFinite(gainNum) && gainNum > 250;
  const isCourrierDoc = (doc) =>
    doc.kind === "courrier_optimisation_fiscale"
    || String(doc.display_label || "").toLowerCase().includes("courrier");
  const courrierDocs = eligibleForCourrier ? docs.filter(isCourrierDoc) : [];
  const analyseDocs = docs.filter((d) => !isCourrierDoc(d));

  return (
    <Layout>
      <div className="animate-fade-up max-w-3xl space-y-6" data-testid="suivi-3p-fiche">
        <button
          type="button"
          onClick={() => navigate("/suivi-3p")}
          className="text-xs text-muted-foreground hover:text-[#002FA7] flex items-center gap-1"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Fiscalité, 3e pilier & Fortune 2026
        </button>

        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="font-display font-black text-3xl tracking-tight flex items-center gap-2">
              <Shield className="h-7 w-7 text-[#002FA7]" />
              {fiche.prenom} {fiche.nom}
            </h1>
            <p className="text-muted-foreground mt-1">
              {fiche.conseiller ? `Conseiller : ${fiche.conseiller}` : null}
              {fiche.conseiller && fiche.conjoint ? " · " : null}
              {fiche.conjoint ? `Conjoint : ${fiche.conjoint}` : null}
              {!fiche.conseiller && !fiche.conjoint && fiche.etat_civil ? fiche.etat_civil : null}
              {(fiche.conseiller || fiche.conjoint) && fiche.etat_civil ? ` · ${fiche.etat_civil}` : null}
            </p>
            {(fiche.adresse || fiche.npa || fiche.ville) && (
              <p className="text-sm text-muted-foreground mt-1">
                {[fiche.adresse, [fiche.npa, fiche.ville].filter(Boolean).join(" ")].filter(Boolean).join(", ")}
              </p>
            )}
            <span className={`inline-flex mt-2 text-xs px-2 py-0.5 rounded-md border ${SUIVI_3P_STATUT_STYLE[fiche.statut_suivi] || ""}`}>
              {fiche.statut_suivi}
            </span>
          </div>
          {eligibleForCourrier && (
            <Button
              variant="outline"
              className="gap-1.5"
              onClick={generateCourrier}
              disabled={generatingCourrier || !canEditSuivi}
              data-testid="suivi-3p-generate-courrier"
            >
              {generatingCourrier ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
              {generatingCourrier ? "Génération…" : "Générer le courrier Word"}
            </Button>
          )}
        </div>

        {eligibleForCourrier && (
          <Card className="p-5 border-[#002FA7]/30 bg-[#002FA7]/5" data-testid="suivi-3p-courrier-card">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <p className="text-sm font-semibold text-[#002FA7]">Courrier optimisation fiscale</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Gain fiscal {formatChf(fiche.gain_fiscal_estime)} — le courrier est enregistré dans ce dossier.
                </p>
              </div>
            </div>
            {courrierDocs.length === 0 ? (
              <p className="text-sm text-muted-foreground mt-3">
                Pas encore de courrier. Utilisez « GÉNÉRER TOUS LES COURRIERS » ou le bouton ci-dessus.
              </p>
            ) : (
              <div className="mt-3 space-y-2">
                {courrierDocs.map((doc) => (
                  <div key={doc.id} className="flex items-center justify-between gap-3 p-3 rounded-md border border-[#002FA7]/20 bg-white">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {doc.display_label || "Courrier optimisation fiscale"}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">{doc.original_filename}</p>
                    </div>
                    <Button
                      size="sm"
                      className="shrink-0 bg-[#002FA7] hover:bg-[#00248a] gap-1.5"
                      onClick={() => downloadAuthenticatedBlob(
                        `/suivi-3p/documents/${doc.id}/download`,
                        doc.original_filename || "courrier.docx",
                      )}
                    >
                      <Download className="h-4 w-4" />
                      Télécharger
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        <Card className="p-6 space-y-5">
          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-1">Identité</p>
            <p className="text-xs text-muted-foreground">Corrigez le prénom ou le nom en cas de faute de frappe, sans recréer la fiche.</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <InlineField
              label="Prénom"
              display={form.prenom}
              isEditing={editingKey === "prenom"}
              onEdit={() => startEdit("prenom")}
              onConfirm={() => confirmEdit("prenom")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-prenom"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "prenom")}
                placeholder="Prénom"
                autoFocus
                data-testid="suivi-3p-prenom-edit"
              />
            </InlineField>
            <InlineField
              label="Nom"
              display={form.nom}
              isEditing={editingKey === "nom"}
              onEdit={() => startEdit("nom")}
              onConfirm={() => confirmEdit("nom")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-nom"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "nom")}
                placeholder="Nom"
                autoFocus
                data-testid="suivi-3p-nom-edit"
              />
            </InlineField>
          </div>
        </Card>

        <Card className="p-6 space-y-5">
          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-1">Adresse</p>
            <p className="text-xs text-muted-foreground">Coordonnées postales du client (import Excel possible depuis la liste).</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <InlineField
              label="Civilité / sexe"
              display={sexeDisplay(form.sexe)}
              isEditing={editingKey === "sexe"}
              onEdit={() => startEdit("sexe")}
              onConfirm={() => confirmEdit("sexe")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-sexe"
            >
              <Select
                value={editDraft || "unset"}
                onValueChange={(v) => setEditDraft(v === "unset" ? "" : v)}
                disabled={saving}
              >
                <SelectTrigger data-testid="suivi-3p-sexe-edit"><SelectValue placeholder="Non renseigné" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="unset">Non renseigné</SelectItem>
                  <SelectItem value="Homme">Homme (Monsieur)</SelectItem>
                  <SelectItem value="Femme">Femme (Madame)</SelectItem>
                </SelectContent>
              </Select>
            </InlineField>
            <InlineField
              label="Prénom du conjoint"
              display={form.conjoint_prenom}
              isEditing={editingKey === "conjoint_prenom"}
              onEdit={() => startEdit("conjoint_prenom")}
              onConfirm={() => confirmEdit("conjoint_prenom")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-conjoint-prenom"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "conjoint_prenom")}
                placeholder="Si couple"
                autoFocus
                data-testid="suivi-3p-conjoint-prenom-edit"
              />
            </InlineField>
            <InlineField
              label="Nom du conjoint"
              display={form.conjoint_nom}
              isEditing={editingKey === "conjoint_nom"}
              onEdit={() => startEdit("conjoint_nom")}
              onConfirm={() => confirmEdit("conjoint_nom")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-conjoint-nom"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "conjoint_nom")}
                placeholder="Si couple"
                autoFocus
                data-testid="suivi-3p-conjoint-nom-edit"
              />
            </InlineField>
            <InlineField
              label="Rue / adresse"
              display={form.adresse}
              isEditing={editingKey === "adresse"}
              onEdit={() => startEdit("adresse")}
              onConfirm={() => confirmEdit("adresse")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-adresse"
              className="sm:col-span-3"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "adresse")}
                placeholder="Ex. Route de Genève 12"
                autoFocus
                data-testid="suivi-3p-adresse-edit"
              />
            </InlineField>
            <InlineField
              label="Complément d'adresse (optionnel)"
              display={form.adresse_complement}
              isEditing={editingKey === "adresse_complement"}
              onEdit={() => startEdit("adresse_complement")}
              onConfirm={() => confirmEdit("adresse_complement")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-adresse-complement"
              className="sm:col-span-3"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "adresse_complement")}
                placeholder="Ex. C/O, bât. B, 2e étage"
                autoFocus
                data-testid="suivi-3p-adresse-complement-edit"
              />
            </InlineField>
            <InlineField
              label="NPA"
              display={form.npa}
              isEditing={editingKey === "npa"}
              onEdit={() => startEdit("npa")}
              onConfirm={() => confirmEdit("npa")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-npa"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "npa")}
                placeholder="1200"
                autoFocus
                data-testid="suivi-3p-npa-edit"
              />
            </InlineField>
            <InlineField
              label="Ville"
              display={form.ville}
              isEditing={editingKey === "ville"}
              onEdit={() => startEdit("ville")}
              onConfirm={() => confirmEdit("ville")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-ville"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "ville")}
                placeholder="Genève"
                autoFocus
                data-testid="suivi-3p-ville-edit"
              />
            </InlineField>
            <InlineField
              label="Pays"
              display={form.pays}
              isEditing={editingKey === "pays"}
              onEdit={() => startEdit("pays")}
              onConfirm={() => confirmEdit("pays")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-pays"
            >
              <Input
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "pays")}
                placeholder="Suisse"
                autoFocus
                data-testid="suivi-3p-pays-edit"
              />
            </InlineField>
          </div>
        </Card>

        <Card className="p-6 space-y-5">
          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-1">Analyse &amp; gain fiscal</p>
            <p className="text-xs text-muted-foreground">
              Gain : <strong>{formatChf(fiche.gain_fiscal_estime)}</strong>
              {" · "}Dernière analyse : <strong>{formatDateFr(fiche.date_derniere_analyse)}</strong>
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <InlineField
              label="Statut"
              display={form.statut}
              isEditing={editingKey === "statut"}
              onEdit={() => startEdit("statut")}
              onConfirm={() => confirmEdit("statut")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-statut"
            >
              <Select value={editDraft || form.statut} onValueChange={setEditDraft}>
                <SelectTrigger data-testid="suivi-3p-statut-edit"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SUIVI_3P_STATUTS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </InlineField>
            <InlineField
              label="Date de la dernière analyse"
              display={form.date_derniere_analyse ? formatDateFr(form.date_derniere_analyse) : ""}
              isEditing={editingKey === "date_derniere_analyse"}
              onEdit={() => startEdit("date_derniere_analyse")}
              onConfirm={() => confirmEdit("date_derniere_analyse")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
            >
              <Input
                type="date"
                value={editDraft || ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "date_derniere_analyse")}
                autoFocus
              />
            </InlineField>
            <InlineField
              label="Gain fiscal estimé (CHF)"
              display={form.gain_fiscal_estime === "" || form.gain_fiscal_estime == null ? "" : formatChf(form.gain_fiscal_estime)}
              isEditing={editingKey === "gain_fiscal_estime"}
              onEdit={() => startEdit("gain_fiscal_estime")}
              onConfirm={() => confirmEdit("gain_fiscal_estime")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              className="sm:col-span-2"
            >
              <Input
                type="number"
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => fieldKeyDown(e, "gain_fiscal_estime")}
                placeholder="Ex. 2400"
                autoFocus
              />
            </InlineField>
          </div>
        </Card>

        <Card className="p-6 space-y-5">
          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-1">Suivi commercial</p>
            <p className="text-xs text-muted-foreground">
              Contact et rendez-vous — suivi simple, sans CRM complexe.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            <InlineField
              label="Conseiller"
              display={form.conseiller}
              isEditing={editingKey === "conseiller"}
              onEdit={() => isGlobal && startEdit("conseiller")}
              onConfirm={() => confirmEdit("conseiller")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi && isGlobal}
              testid="suivi-3p-commercial-conseiller"
            >
              <ConseillerCombobox
                value={editDraft ?? ""}
                onChange={setEditDraft}
                options={mergedConseillerOptions}
                placeholder="Choisir ou saisir un nom…"
                data-testid="suivi-3p-commercial-conseiller-edit"
              />
            </InlineField>
            <InlineField
              label="Client contacté"
              display={form.client_contacte ? "Oui" : "Non"}
              isEditing={editingKey === "client_contacte"}
              onEdit={() => startEdit("client_contacte")}
              onConfirm={() => confirmEdit("client_contacte")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-contacte"
            >
              <Select
                value={editDraft ? "oui" : "non"}
                onValueChange={(v) => setEditDraft(v === "oui")}
              >
                <SelectTrigger data-testid="suivi-3p-contacte-edit"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="non">Non</SelectItem>
                  <SelectItem value="oui">Oui</SelectItem>
                </SelectContent>
              </Select>
            </InlineField>
            <InlineField
              label="Rendez-vous pris"
              display={form.rdv_pris ? "Oui" : "Non"}
              isEditing={editingKey === "rdv_pris"}
              onEdit={() => startEdit("rdv_pris")}
              onConfirm={() => confirmEdit("rdv_pris")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-rdv-pris"
            >
              <Select
                value={editDraft ? "oui" : "non"}
                onValueChange={(v) => setEditDraft(v === "oui")}
              >
                <SelectTrigger data-testid="suivi-3p-rdv-pris-edit"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="non">Non</SelectItem>
                  <SelectItem value="oui">Oui</SelectItem>
                </SelectContent>
              </Select>
            </InlineField>
            {(form.rdv_pris || editingKey === "date_rdv") && (
              <InlineField
                label="Date du rendez-vous"
                display={form.date_rdv ? formatDateFr(form.date_rdv) : ""}
                isEditing={editingKey === "date_rdv"}
                onEdit={() => startEdit("date_rdv")}
                onConfirm={() => confirmEdit("date_rdv")}
                onCancel={cancelEdit}
                canEdit={canEditSuivi}
                testid="suivi-3p-date-rdv"
                className="sm:col-span-2"
              >
                <Input
                  type="date"
                  value={editDraft || ""}
                  onChange={(e) => setEditDraft(e.target.value)}
                  onKeyDown={(e) => fieldKeyDown(e, "date_rdv")}
                  autoFocus
                  data-testid="suivi-3p-date-rdv-edit"
                />
              </InlineField>
            )}
            <InlineField
              label="Notes"
              display={form.notes}
              isEditing={editingKey === "notes"}
              onEdit={() => startEdit("notes")}
              onConfirm={() => confirmEdit("notes")}
              onCancel={cancelEdit}
              canEdit={canEditSuivi}
              testid="suivi-3p-notes"
              className="sm:col-span-2 lg:col-span-3"
            >
              <Textarea
                rows={4}
                value={editDraft ?? ""}
                onChange={(e) => setEditDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") cancelEdit();
                }}
                autoFocus
              />
            </InlineField>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3">
            {saveFlash && (
              <div
                className="inline-flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm font-medium text-emerald-800 animate-in fade-in slide-in-from-bottom-1 duration-300"
                data-testid="suivi-3p-save-flash"
                role="status"
              >
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                Informations enregistrées
              </div>
            )}
            <Button type="button" onClick={save} disabled={saving || !canEditSuivi} className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5" data-testid="suivi-3p-save">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Enregistrer
            </Button>
          </div>
        </Card>

        <Card className="p-6 space-y-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-semibold text-[#002FA7]">Documents</p>
              <p className="text-xs text-muted-foreground mt-1">
                Analyses PDF et courrier Word d&apos;optimisation fiscale.
              </p>
            </div>
            <Button
              size="sm"
              onClick={() => fileRef.current?.click()}
              disabled={uploading || !canEditSuivi}
              className="h-8 gap-1.5 bg-[#002FA7] hover:bg-[#00248a]"
              data-testid="suivi-3p-upload-analyse"
            >
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Ajouter le document
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,image/*"
              className="hidden"
              onChange={uploadDoc}
            />
          </div>

          {analyseDocs.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center border border-dashed rounded-md">
              Aucun document pour l&apos;instant.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="suivi-3p-analyse-docs">
              {analyseDocs.map((doc) => {
                const label =
                  doc.display_label ||
                  (String(doc.source_folder || "").toLowerCase().includes("fortune")
                    ? "Analyse optimisation fiscale"
                    : "Analyse 3e Pilier");
                const dateLabel = formatDateFr((doc.generated_at || doc.created_at || "").slice(0, 10));
                return (
                  <div
                    key={doc.id}
                    className="flex items-center justify-between gap-3 p-3 rounded-md border border-border bg-secondary/20"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="h-4 w-4 text-[#002FA7] shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate" title={doc.original_filename}>
                          {label}
                        </p>
                        <p className="text-xs text-muted-foreground truncate" title={doc.original_filename}>
                          {doc.original_filename}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {dateLabel}
                          {doc.size ? ` · ${Math.max(1, Math.round(doc.size / 1024))} Ko` : ""}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-8 px-2 text-xs"
                        title="Télécharger"
                        onClick={() => downloadAuthenticatedBlob(
                          `/suivi-3p/documents/${doc.id}/download`,
                          doc.original_filename || "document.pdf",
                        )}
                      >
                        <Download className="h-4 w-4 mr-1" />
                        Télécharger
                      </Button>
                      <Button size="icon" variant="ghost" className="h-8 w-8" title="Ouvrir" onClick={() => openDoc(doc)}>
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="ghost" className="h-8 w-8 text-rose-600" title="Supprimer" onClick={() => deleteDoc(doc)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </Layout>
  );
}
