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
  formatDateFr,
  formatChf,
  toIsoDate,
  toSwissDate,
  valuesEqual,
} from "@/lib/demandesOffres";
import {
  ArrowLeft, FileUp, Loader2, Pencil, Send, ShieldCheck,
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
    <div className={`space-y-1.5 ${className}`}>
      <div className="flex items-center gap-2">
        <Label className="text-xs text-muted-foreground">{label}</Label>
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

function ChangedInput({ changed, className = "", ...props }) {
  return (
    <Input
      {...props}
      className={`${className} ${changed ? "border-rose-400 bg-rose-50/60 focus-visible:ring-rose-300" : ""}`}
    />
  );
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
  const { hasPerm } = useAuth();
  const canEdit = hasPerm("demandes_offres.edit");
  const pdfRef = useRef(null);

  const [formMenu, setFormMenu] = useState(null);
  const [phase, setPhase] = useState("catalog"); // catalog | workspace
  const [selectedType, setSelectedType] = useState(null); // { form_type, label }

  const [demande, setDemande] = useState(null);
  const [numeroInput, setNumeroInput] = useState("");
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
    setNumeroInput("");
    setSnapshot(null);
    setForm(emptyForm());
    setFormPayload({});
    setPayloadSnapshot({});
    setSchema(null);
    setNote("");
    setExtracted(null);
    setPdfReady(false);
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
    if (data.demande) {
      setDemande(data.demande);
      setNumeroInput(data.demande.numero || data.numero || "");
    } else if (data.numero || data.numero_detecte) {
      setNumeroInput(data.numero || data.numero_detecte || "");
    }
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

      let data;
      if (demande?.id) {
        const res = await api.post(`/demandes-offres/${demande.id}/modifier/extract-pdf`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        data = res.data;
        // Conserver le lien demande + email_subject
        if (!data.demande && demande) {
          data.demande = {
            id: demande.id,
            numero: demande.numero || data.numero,
            email_subject: data.email_subject || demande.email_subject || "",
            statut: demande.statut,
          };
        }
      } else {
        const res = await api.post("/demandes-offres/modifier/analyse-pdf", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        data = res.data;
      }
      applyPrefill(data);
      const nFilled = Object.keys(data.fields || {}).length + Object.keys(data.form_payload || {}).length;
      toast.success(
        nFilled
          ? `PDF analysé — ${nFilled} champ(s) prérempli(s)`
          : "PDF importé — peu de champs détectés, vérifiez manuellement",
      );
    } catch (e) {
      toast.error(errorMessage(e, "Extraction PDF impossible"));
    } finally {
      setUploading(false);
      if (pdfRef.current) pdfRef.current.value = "";
    }
  };

  const resolveDemandeByNumero = async (numero) => {
    const q = (numero || "").trim();
    if (!q) return null;
    const res = await api.get("/demandes-offres", { params: { q, limit: 10 } });
    const rows = Array.isArray(res.data) ? res.data : [];
    const exact = rows.find((r) => String(r.numero || "").toUpperCase() === q.toUpperCase());
    return exact || rows[0] || null;
  };

  const setValue = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const changes = useMemo(() => {
    const base = buildModificationChanges(snapshot || {}, form);
    if (!isLegacyType(selectedType?.form_type)) {
      const oldFp = payloadSnapshot || {};
      const newFp = formPayload || {};
      for (const k of new Set([...Object.keys(oldFp), ...Object.keys(newFp)])) {
        if (valuesEqual(oldFp[k], newFp[k])) continue;
        base.push({
          field: `form_payload.${k}`,
          label: k,
          old: oldFp[k] ?? null,
          new: newFp[k] ?? null,
        });
      }
    }
    return base;
  }, [snapshot, form, payloadSnapshot, formPayload, selectedType]);

  const isChanged = useCallback(
    (key) => {
      if (!snapshot) return false;
      return !valuesEqual(snapshot[key], form[key]);
    },
    [snapshot, form],
  );

  const changedPayloadKeys = useMemo(() => {
    const keys = [];
    const oldFp = payloadSnapshot || {};
    const newFp = formPayload || {};
    for (const k of new Set([...Object.keys(oldFp), ...Object.keys(newFp)])) {
      if (!valuesEqual(oldFp[k], newFp[k])) keys.push(k);
    }
    return keys;
  }, [payloadSnapshot, formPayload]);

  const envoyer = async () => {
    if (!selectedType) return;
    if (!pdfReady) {
      return toast.error("Importez d'abord la police / l'offre PDF pour préremplir le formulaire");
    }
    if (!changes.length && !note.trim()) {
      return toast.error("Indiquez au moins une modification ou une note au service Offre");
    }

    setBusy(true);
    try {
      let target = demande;
      if (!target?.id) {
        const found = await resolveDemandeByNumero(numeroInput);
        if (!found?.id) {
          toast.error("Saisissez le n° d'offre existant (OFF-AAAA-NNNN) pour conserver le numéro et l'objet e-mail");
          setBusy(false);
          return;
        }
        target = found;
        setDemande(found);
        setNumeroInput(found.numero || numeroInput);
      }

      // Snapshot serveur (numéro + email_subject inchangés)
      if (!target.snapshot_original) {
        await api.post(`/demandes-offres/${target.id}/modifier/start`);
      }

      // Stocker aussi le PDF sur la demande si analyse sans id préalable
      if (pdfRef.current?.files?.[0] && !demande?.id) {
        // déjà analysé ; le document sera lié à l'envoi via les champs
      }

      const fields = { ...form };
      if (fields.montant_prime === "") fields.montant_prime = null;
      if (fields.date_naissance) fields.date_naissance = toIsoDate(fields.date_naissance) || fields.date_naissance;
      if (fields.date_debut) fields.date_debut = toIsoDate(fields.date_debut) || fields.date_debut;

      const body = {
        fields,
        note_service_offre: note.trim() || null,
        changes,
      };
      if (!isLegacyType(selectedType.form_type)) {
        body.form_payload = formPayload;
      }

      const res = await api.post(`/demandes-offres/${target.id}/modifier/envoyer`, body);
      toast.success("Modification envoyée au service Offre — numéro et objet e-mail conservés");
      if (res.data?.email_sent === false && res.data?.email_error) {
        toast.warning("Statut enregistré, mais e-mail non envoyé", {
          description: String(res.data.email_error).slice(0, 200),
        });
      }
      navigate(`/demandes-offres/${target.id}`);
    } catch (e) {
      toast.error(errorMessage(e, "Envoi de la modification impossible"));
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
              ? "Choisissez le type de formulaire, importez la police PDF — le CRM préremplit automatiquement tous les champs."
              : "Importez le PDF, vérifiez le formulaire prérempli, modifiez uniquement le nécessaire, puis envoyez."}
          </p>
        </div>

        {phase === "catalog" && (
          <div className="space-y-6" data-testid="modifier-offre-catalog">
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
                  {(demande?.numero || numeroInput) && (
                    <p className="font-mono text-sm font-semibold text-slate-800 mt-2">
                      {demande?.numero || numeroInput}
                      {demande?.email_subject ? (
                        <span className="block font-sans font-medium text-slate-600 mt-0.5">
                          {demande.email_subject}
                        </span>
                      ) : null}
                    </p>
                  )}
                  {demande?.statut && (
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

              <div className="grid sm:grid-cols-2 gap-3">
                <Field label="N° d'offre existant (conservé à l'envoi)">
                  <Input
                    value={numeroInput}
                    onChange={(e) => setNumeroInput(e.target.value)}
                    placeholder="OFF-2026-0042"
                    className="font-mono"
                    data-testid="modifier-offre-numero"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Détecté automatiquement dans le PDF si présent. L&apos;objet e-mail associé est conservé.
                  </p>
                </Field>
                <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 flex gap-2 items-start">
                  <ShieldCheck className="h-4 w-4 text-[#002FA7] shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-slate-900">Flux recommandé</p>
                    <ol className="mt-1 text-xs space-y-0.5 list-decimal list-inside text-muted-foreground">
                      <li>Importer le PDF de la police / offre</li>
                      <li>Vérifier le formulaire 100 % prérempli</li>
                      <li>Modifier uniquement les champs nécessaires (marqués en rouge)</li>
                      <li>Ajouter une note → Envoyer au service Offre</li>
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

            {pdfReady && (
              <Card className="p-5 space-y-5">
                <div>
                  <h2 className="font-display font-bold text-[#002FA7]">Formulaire prérempli</h2>
                  <p className="text-xs text-muted-foreground mt-1">
                    Toutes les informations détectées dans le PDF sont déjà saisies. Les champs que vous
                    changez sont marqués en rouge « Modifié ».
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
                              className={changed ? "border-rose-400 bg-rose-50/60" : ""}
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
                        className={isChanged("compagnies") ? "border-rose-400 bg-rose-50/60" : ""}
                        placeholder="Vaudoise, Swiss Life…"
                      />
                    </Field>
                  </div>
                ) : schema ? (
                  <OffreSchemaForm
                    schema={schema}
                    values={formPayload}
                    onChange={setFormPayload}
                    changedKeys={changedPayloadKeys}
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
                              onChange={(e) =>
                                setFormPayload((prev) => ({ ...prev, [key]: e.target.value }))
                              }
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
                    Envoyer
                  </Button>
                </div>
              </Card>
            )}

            {!pdfReady && (
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
