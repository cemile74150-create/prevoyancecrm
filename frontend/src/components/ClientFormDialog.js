import React, { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { STATUTS } from "@/lib/constants";
import { finmaByConseillerName, lookupConseillerFinma, normalizeConseillerKey, parseConseillerList } from "@/lib/conseillers";
import ConseillerCombobox from "@/components/ConseillerCombobox";
import ClientDuplicateDialog from "@/components/ClientDuplicateDialog";
import { parseClientDuplicateError } from "@/lib/clientDuplicate";
import api from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { toIsoDate, toSwissDate } from "@/lib/dates";

function Field({ label, k, type = "text", placeholder, form, setField, testId }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input
        data-testid={testId || `client-field-${k}`}
        type={type}
        value={form[k] ?? ""}
        placeholder={placeholder}
        onChange={(e) => setField(k, e.target.value)}
      />
    </div>
  );
}

const ETATS_CIVIL = ["Célibataire", "Marié(e)", "Divorcé(e)", "Veuf(ve)", "Partenariat enregistré", "Séparé(e)"];

const ACTIVITE_OPTIONS = [
  { id: "prevoyance", label: "Analyse de prévoyance", hint: "Apparaît dans Dossiers" },
  { id: "fiscalite", label: "Fiscalité / 3e pilier", hint: "Fiche Fiscalité liée" },
  { id: "offre", label: "Offre", hint: "Module Demandes d'offres" },
  { id: "autre", label: "Autre", hint: "Clients uniquement" },
];

const empty = {
  prenom: "", nom: "", date_naissance: "", sexe: "", nationalite: "Suisse", avs_number: "",
  email: "", telephone: "", adresse: "", npa: "", ville: "",
  pays_residence: "Suisse", frontalier: "",
  conseiller: "", conseiller_finma: "", agent_apporteur: "",
  etat_civil: "", nombre_enfants: 0, conjoint: "",
  employeur: "", profession: "", taux_activite: "", salaire_annuel: "",
  statut: "Nouveau", priorite: "normale",
};

const emptySpouse = {
  prenom: "", nom: "", date_naissance: "", sexe: "", avs_number: "",
};

function isMarriedEtat(etat) {
  const v = (etat || "").toLowerCase();
  return v.includes("mari") || v.includes("partenariat");
}

/**
 * @param {string[]} [defaultActivites] — ex. ["prevoyance"] depuis Kanban Dossiers
 */
export default function ClientFormDialog({ open, onOpenChange, client, onSaved, defaultActivites }) {
  const { user, isGlobal } = useAuth();
  const [form, setForm] = useState(empty);
  const [spouseForm, setSpouseForm] = useState(emptySpouse);
  const [createSpouseFiche, setCreateSpouseFiche] = useState(true);
  const [activites, setActivites] = useState([]);
  const [saving, setSaving] = useState(false);
  const [conseillerOptions, setConseillerOptions] = useState([]);
  const [finmaMap, setFinmaMap] = useState({});
  const [duplicateConflict, setDuplicateConflict] = useState(null);
  const isEdit = !!client;
  const showSpouseBlock = !isEdit && isMarriedEtat(form.etat_civil);

  useEffect(() => {
    if (client) {
      setForm({
        ...empty,
        ...client,
        date_naissance: toSwissDate(client.date_naissance) || "",
        salaire_annuel: client.salaire_annuel ?? "",
        conseiller_finma: client.conseiller_finma ?? "",
      });
      const fromClient = Array.isArray(client.activites) ? client.activites : [];
      if (fromClient.length) {
        setActivites(fromClient);
      } else {
        const inferred = [];
        if (client.in_dossiers !== false) inferred.push("prevoyance");
        const mods = client.source_modules || [];
        if (mods.includes("suivi_3p")) inferred.push("fiscalite");
        if (mods.includes("offres")) inferred.push("offre");
        setActivites(inferred);
      }
    } else {
      const defaultCons = user?.role === "conseiller"
        ? (user.conseiller || user.name || "")
        : "";
      const defaultFinma = user?.role === "conseiller"
        ? (user.finma_number || "")
        : "";
      setForm({
        ...empty,
        conseiller: defaultCons,
        conseiller_finma: defaultFinma,
      });
      setActivites(Array.isArray(defaultActivites) ? [...defaultActivites] : []);
    }
    setSpouseForm(emptySpouse);
    setCreateSpouseFiche(true);
    setDuplicateConflict(null);
  }, [client, open, user, defaultActivites]);

  useEffect(() => {
    if (!open) return;
    api.get("/users/conseillers").then((res) => {
      const rows = parseConseillerList(res.data);
      const names = rows.map((r) => r.name).filter(Boolean);
      // Garder la valeur actuelle si elle n'est plus dans la liste (legacy / inactif)
      const current = (client?.conseiller || form.conseiller || "").trim();
      if (current && !names.some((n) => normalizeConseillerKey(n) === normalizeConseillerKey(current))) {
        names.unshift(current);
      }
      setConseillerOptions(names);
      const map = finmaByConseillerName(rows);
      setFinmaMap(map);
      setForm((f) => {
        if (!f.conseiller) return f;
        const known = lookupConseillerFinma(map, f.conseiller);
        if (known) {
          return { ...f, conseiller_finma: known };
        }
        if (user?.role === "conseiller" && (user.finma_number || "") && !f.conseiller_finma) {
          return { ...f, conseiller_finma: user.finma_number || "" };
        }
        return f;
      });
    }).catch(() => {});
    // form.conseiller volontairement omis : on ne recharge pas à chaque frappe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user, client]);

  useEffect(() => {
    if (!showSpouseBlock) return;
    const parts = (form.conjoint || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length && !spouseForm.prenom && !spouseForm.nom) {
      setSpouseForm((s) => ({
        ...s,
        prenom: parts[0] || "",
        nom: parts.slice(1).join(" ") || form.nom || "",
      }));
    } else if (!spouseForm.nom && form.nom) {
      setSpouseForm((s) => ({ ...s, nom: s.nom || form.nom }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showSpouseBlock, form.conjoint, form.nom]);

  const setField = (k, v) => {
    setForm((f) => ({ ...f, [k]: v }));
  };

  const setConseiller = (name) => {
    const known = lookupConseillerFinma(finmaMap, name);
    setForm((f) => {
      const prevKnown = lookupConseillerFinma(finmaMap, f.conseiller);
      // Conseiller connu avec FINMA → préremplir
      if (known) {
        return { ...f, conseiller: name, conseiller_finma: known };
      }
      // On change de conseiller : si l'ancien FINMA venait du mapping, le vider
      if (f.conseiller_finma && prevKnown && f.conseiller_finma === prevKnown) {
        return { ...f, conseiller: name, conseiller_finma: "" };
      }
      // Sinon conserver la saisie manuelle (ne pas l'effacer à chaque frappe)
      return { ...f, conseiller: name };
    });
  };

  const onConseillerBlur = () => {
    const known = lookupConseillerFinma(finmaMap, form.conseiller);
    if (known && known !== form.conseiller_finma) {
      setField("conseiller_finma", known);
    }
  };

  const setSpouseField = (k, v) => {
    setSpouseForm((f) => ({ ...f, [k]: v }));
  };

  const toggleActivite = (id) => {
    setActivites((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const save = async () => {
    if (!form.prenom.trim() || !form.nom.trim()) {
      toast.error("Le prénom et le nom sont obligatoires");
      return;
    }
    if (showSpouseBlock && createSpouseFiche) {
      if (!spouseForm.prenom.trim() || !spouseForm.nom.trim()) {
        toast.error("Renseignez le prénom et le nom du conjoint");
        return;
      }
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        date_naissance: toIsoDate(form.date_naissance) || null,
        conseiller_finma: form.conseiller_finma ?? "",
        nombre_enfants: parseInt(form.nombre_enfants) || 0,
        salaire_annuel: form.salaire_annuel ? parseFloat(form.salaire_annuel) : null,
        conjoint: showSpouseBlock && createSpouseFiche
          ? `${spouseForm.prenom} ${spouseForm.nom}`.trim()
          : form.conjoint,
      };
      if (!isEdit) {
        payload.activites = activites;
      }
      // Ne pas renvoyer des champs UI / lecture seule
      delete payload.id;
      delete payload.user_id;
      delete payload.numero_dossier;
      delete payload.in_dossiers;
      delete payload.source_modules;
      delete payload.created_at;
      const res = isEdit
        ? await api.put(`/clients/${client.id}`, payload)
        : await api.post("/clients", payload);

      let spouse = null;
      if (!isEdit && showSpouseBlock && createSpouseFiche) {
        try {
          const spouseRes = await api.post(`/clients/${res.data.id}/create-spouse`, {
            prenom: spouseForm.prenom.trim(),
            nom: spouseForm.nom.trim(),
            date_naissance: toIsoDate(spouseForm.date_naissance) || null,
            sexe: spouseForm.sexe || null,
            avs_number: spouseForm.avs_number || null,
          });
          spouse = spouseRes.data;
          toast.success("Dossier familial créé (2 fiches)");
        } catch (err) {
          const spouseDup = parseClientDuplicateError(err);
          if (spouseDup.isDuplicate) {
            setDuplicateConflict(spouseDup);
            toast.error(spouseDup.message);
          } else {
            toast.error(spouseDup.message || "Client créé, mais fiche conjoint impossible");
          }
        }
      } else {
        toast.success(isEdit ? "Fiche mise à jour" : "Client créé");
      }

      onSaved?.(res.data, { spouse, isFamily: Boolean(spouse) || isMarriedEtat(res.data.etat_civil) });
      onOpenChange(false);
    } catch (e) {
      const dup = parseClientDuplicateError(e);
      if (dup.isDuplicate) {
        setDuplicateConflict(dup);
        toast.error(dup.message);
      } else {
        toast.error(dup.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const conseillerValue = isGlobal
    ? (form.conseiller || "")
    : (form.conseiller || user?.conseiller || user?.name || "");

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display tracking-tight">{isEdit ? "Modifier la fiche client" : "Nouveau client"}</DialogTitle>
          {!isEdit && (
            <DialogDescription>
              Une seule fiche Clients. Cochez les activités pour rattacher Prévoyance, Fiscalité, etc.
            </DialogDescription>
          )}
          {showSpouseBlock && (
            <DialogDescription>
              Deux fiches clients séparées seront créées (une par personne), rattachées au même dossier.
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="space-y-5 py-2">
          {!isEdit && (
            <div data-testid="client-activites-section">
              <p className="text-sm font-semibold text-[#002FA7] mb-1">Type de dossier / Activité</p>
              <p className="text-xs text-muted-foreground mb-3">
                Plusieurs cases possibles. Sans « Analyse de prévoyance », le client reste uniquement dans Clients.
              </p>
              <div className="grid sm:grid-cols-2 gap-2">
                {ACTIVITE_OPTIONS.map((opt) => {
                  const checked = activites.includes(opt.id);
                  return (
                    <label
                      key={opt.id}
                      className={`flex items-start gap-2.5 rounded-md border px-3 py-2.5 cursor-pointer transition-colors ${
                        checked ? "border-[#002FA7]/40 bg-[#002FA7]/5" : "border-border hover:bg-secondary/40"
                      }`}
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={() => toggleActivite(opt.id)}
                        data-testid={`client-activite-${opt.id}`}
                        className="mt-0.5"
                      />
                      <span className="min-w-0">
                        <span className="text-sm font-medium block">{opt.label}</span>
                        <span className="text-[11px] text-muted-foreground">{opt.hint}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-3">Informations générales</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Prénom *" k="prenom" form={form} setField={setField} />
              <Field label="Nom *" k="nom" form={form} setField={setField} />
              <Field label="Date de naissance" k="date_naissance" placeholder="jj.mm.aaaa" form={form} setField={setField} />
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Sexe</Label>
                <Select value={form.sexe || "unset"} onValueChange={(v) => setField("sexe", v === "unset" ? "" : v)}>
                  <SelectTrigger data-testid="client-field-sexe"><SelectValue placeholder="Sélectionner" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unset">Non renseigné</SelectItem>
                    <SelectItem value="Homme">Homme</SelectItem>
                    <SelectItem value="Femme">Femme</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Field label="Nationalité" k="nationalite" form={form} setField={setField} />
              <Field label="Pays de résidence" k="pays_residence" form={form} setField={setField} />
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Frontalier</Label>
                <Select
                  value={form.frontalier || "__none__"}
                  onValueChange={(v) => setField("frontalier", v === "__none__" ? "" : v)}
                >
                  <SelectTrigger data-testid="client-field-frontalier">
                    <SelectValue placeholder="Non renseigné" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">Non renseigné</SelectItem>
                    <SelectItem value="oui">Oui</SelectItem>
                    <SelectItem value="non">Non</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Field label="N° AVS" k="avs_number" placeholder="756.XXXX.XXXX.XX" form={form} setField={setField} />
              <Field label="Email" k="email" type="email" form={form} setField={setField} />
              <Field label="Téléphone" k="telephone" form={form} setField={setField} />
              <Field label="Adresse" k="adresse" form={form} setField={setField} />
              <Field label="NPA" k="npa" form={form} setField={setField} />
              <Field label="Ville" k="ville" form={form} setField={setField} />
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Responsable (collaborateur)</Label>
                {isGlobal ? (
                  <ConseillerCombobox
                    value={form.conseiller || ""}
                    onChange={setConseiller}
                    onBlur={onConseillerBlur}
                    options={conseillerOptions}
                    disabled={user?.role === "conseiller"}
                  />
                ) : (
                  <Input
                    data-testid="client-field-conseiller"
                    value={conseillerValue}
                    disabled
                    readOnly
                  />
                )}
                {isGlobal && (
                  <p className="text-[11px] text-muted-foreground">
                    Choisissez dans la liste ou tapez un nouveau nom.
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">N° FINMA</Label>
                <Input
                  data-testid="client-field-conseiller_finma"
                  value={form.conseiller_finma || ""}
                  placeholder="Ex. 123456"
                  onChange={(e) => setField("conseiller_finma", e.target.value)}
                  disabled={!String(conseillerValue || "").trim()}
                />
                <p className="text-[11px] text-muted-foreground">
                  Lié au conseiller : une fois enregistré, il se remplit tout seul sur les autres fiches.
                </p>
              </div>
              <Field label="Agent apporteur" k="agent_apporteur" form={form} setField={setField} />
            </div>
          </div>

          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-3">Situation familiale</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">État civil</Label>
                <Select value={form.etat_civil || ""} onValueChange={(v) => setField("etat_civil", v)}>
                  <SelectTrigger data-testid="client-field-etat_civil"><SelectValue placeholder="Sélectionner" /></SelectTrigger>
                  <SelectContent>
                    {ETATS_CIVIL.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Field label="Nombre d'enfants" k="nombre_enfants" type="number" form={form} setField={setField} />
              {!showSpouseBlock && (
                <Field label="Conjoint" k="conjoint" form={form} setField={setField} />
              )}
            </div>
          </div>

          {showSpouseBlock && (
            <div className="rounded-md border border-[#002FA7]/20 bg-[#002FA7]/5 p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7]">2ᵉ client (conjoint)</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Fiche indépendante (AVS, salaire, employeur…) + même dossier partagé.
                  </p>
                </div>
                <label className="flex items-center gap-2 text-xs shrink-0 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={createSpouseFiche}
                    onChange={(e) => setCreateSpouseFiche(e.target.checked)}
                    data-testid="create-spouse-toggle"
                  />
                  Créer maintenant
                </label>
              </div>
              {createSpouseFiche && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Prénom conjoint *" k="prenom" form={spouseForm} setField={setSpouseField} testId="spouse-field-prenom" />
                  <Field label="Nom conjoint *" k="nom" form={spouseForm} setField={setSpouseField} testId="spouse-field-nom" />
                  <Field label="Date de naissance" k="date_naissance" placeholder="jj.mm.aaaa" form={spouseForm} setField={setSpouseField} testId="spouse-field-date_naissance" />
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Sexe</Label>
                    <Select value={spouseForm.sexe || "unset"} onValueChange={(v) => setSpouseField("sexe", v === "unset" ? "" : v)}>
                      <SelectTrigger data-testid="spouse-field-sexe"><SelectValue placeholder="Sélectionner" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="unset">Non renseigné</SelectItem>
                        <SelectItem value="Homme">Homme</SelectItem>
                        <SelectItem value="Femme">Femme</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Field label="N° AVS conjoint" k="avs_number" placeholder="756.XXXX.XXXX.XX" form={spouseForm} setField={setSpouseField} testId="spouse-field-avs" />
                </div>
              )}
            </div>
          )}

          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-3">Situation professionnelle</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Employeur" k="employeur" form={form} setField={setField} />
              <Field label="Profession" k="profession" form={form} setField={setField} />
              <Field label="Taux d'activité" k="taux_activite" placeholder="ex: 80%" form={form} setField={setField} />
              <Field label="Salaire annuel (CHF)" k="salaire_annuel" type="number" form={form} setField={setField} />
            </div>
          </div>

          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-3">Dossier</p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Statut</Label>
                <Select value={form.statut} onValueChange={(v) => setField("statut", v)}>
                  <SelectTrigger data-testid="client-field-statut"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {STATUTS.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Priorité</Label>
                <Select value={form.priorite} onValueChange={(v) => setField("priorite", v)}>
                  <SelectTrigger data-testid="client-field-priorite"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normale">Normale</SelectItem>
                    <SelectItem value="urgent">Urgent</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="client-form-cancel">Annuler</Button>
          <Button onClick={save} disabled={saving} data-testid="client-form-save" className="bg-[#002FA7] hover:bg-[#00248a]">
            {saving ? "Enregistrement…" : isEdit ? "Enregistrer" : showSpouseBlock && createSpouseFiche ? "Créer le dossier familial" : "Créer le dossier"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    <ClientDuplicateDialog
      open={Boolean(duplicateConflict)}
      onOpenChange={(v) => { if (!v) setDuplicateConflict(null); }}
      conflict={duplicateConflict}
    />
    </>
  );
}
