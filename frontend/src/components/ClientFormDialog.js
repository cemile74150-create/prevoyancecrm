import React, { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { STATUTS, CONSEILLERS } from "@/lib/constants";
import api from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

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

const empty = {
  prenom: "", nom: "", date_naissance: "", sexe: "", nationalite: "Suisse", avs_number: "",
  email: "", telephone: "", adresse: "", npa: "", ville: "",
  conseiller: "", agent_apporteur: "",
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

export default function ClientFormDialog({ open, onOpenChange, client, onSaved }) {
  const { user, isGlobal } = useAuth();
  const [form, setForm] = useState(empty);
  const [spouseForm, setSpouseForm] = useState(emptySpouse);
  const [createSpouseFiche, setCreateSpouseFiche] = useState(true);
  const [saving, setSaving] = useState(false);
  const [conseillerOptions, setConseillerOptions] = useState(CONSEILLERS);
  const isEdit = !!client;
  const showSpouseBlock = !isEdit && isMarriedEtat(form.etat_civil);

  useEffect(() => {
    if (client) setForm({ ...empty, ...client, salaire_annuel: client.salaire_annuel ?? "" });
    else {
      const defaultCons = user?.role === "conseiller"
        ? (user.conseiller || user.name || "")
        : "";
      setForm({ ...empty, conseiller: defaultCons });
    }
    setSpouseForm(emptySpouse);
    setCreateSpouseFiche(true);
  }, [client, open, user]);

  useEffect(() => {
    if (!open) return;
    api.get("/users/conseillers").then((res) => {
      const names = Array.isArray(res.data) ? res.data : [];
      setConseillerOptions(Array.from(new Set([...CONSEILLERS, ...names])));
    }).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (!showSpouseBlock) return;
    // Préremplir depuis le champ conjoint si saisi (Prénom Nom)
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

  const setSpouseField = (k, v) => {
    setSpouseForm((f) => ({ ...f, [k]: v }));
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
        nombre_enfants: parseInt(form.nombre_enfants) || 0,
        salaire_annuel: form.salaire_annuel ? parseFloat(form.salaire_annuel) : null,
        conjoint: showSpouseBlock && createSpouseFiche
          ? `${spouseForm.prenom} ${spouseForm.nom}`.trim()
          : form.conjoint,
      };
      const res = isEdit
        ? await api.put(`/clients/${client.id}`, payload)
        : await api.post("/clients", payload);

      let spouse = null;
      if (!isEdit && showSpouseBlock && createSpouseFiche) {
        try {
          const spouseRes = await api.post(`/clients/${res.data.id}/create-spouse`, {
            prenom: spouseForm.prenom.trim(),
            nom: spouseForm.nom.trim(),
            date_naissance: spouseForm.date_naissance || null,
            sexe: spouseForm.sexe || null,
            avs_number: spouseForm.avs_number || null,
          });
          spouse = spouseRes.data;
          toast.success("Dossier familial créé (2 fiches)");
        } catch (err) {
          toast.error(err?.response?.data?.detail || "Client créé, mais fiche conjoint impossible");
        }
      } else {
        toast.success(isEdit ? "Fiche mise à jour" : "Dossier créé");
      }

      onSaved?.(res.data, { spouse, isFamily: Boolean(spouse) || isMarriedEtat(res.data.etat_civil) });
      onOpenChange(false);
    } catch (e) {
      toast.error("Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-display tracking-tight">{isEdit ? "Modifier la fiche client" : "Nouveau dossier client"}</DialogTitle>
          {showSpouseBlock && (
            <DialogDescription>
              Deux fiches clients séparées seront créées (une par personne), rattachées au même dossier.
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="space-y-5 py-2">
          <div>
            <p className="text-sm font-semibold text-[#002FA7] mb-3">Informations générales</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Prénom *" k="prenom" form={form} setField={setField} />
              <Field label="Nom *" k="nom" form={form} setField={setField} />
              <Field label="Date de naissance" k="date_naissance" type="date" form={form} setField={setField} />
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Sexe</Label>
                <Select value={form.sexe || ""} onValueChange={(v) => setField("sexe", v)}>
                  <SelectTrigger data-testid="client-field-sexe"><SelectValue placeholder="Sélectionner" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Homme">Homme</SelectItem>
                    <SelectItem value="Femme">Femme</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Field label="Nationalité" k="nationalite" form={form} setField={setField} />
              <Field label="N° AVS" k="avs_number" placeholder="756.XXXX.XXXX.XX" form={form} setField={setField} />
              <Field label="Email" k="email" type="email" form={form} setField={setField} />
              <Field label="Téléphone" k="telephone" form={form} setField={setField} />
              <Field label="Adresse" k="adresse" form={form} setField={setField} />
              <Field label="NPA" k="npa" form={form} setField={setField} />
              <Field label="Ville" k="ville" form={form} setField={setField} />
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">Conseiller</Label>
                {isGlobal ? (
                  <Select
                    value={form.conseiller || ""}
                    onValueChange={(v) => setField("conseiller", v)}
                    disabled={user?.role === "conseiller"}
                  >
                    <SelectTrigger data-testid="client-field-conseiller">
                      <SelectValue placeholder="Sélectionner" />
                    </SelectTrigger>
                    <SelectContent>
                      {conseillerOptions.map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    data-testid="client-field-conseiller"
                    value={form.conseiller || user?.conseiller || user?.name || ""}
                    disabled
                    readOnly
                  />
                )}
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
                  <Field label="Date de naissance" k="date_naissance" type="date" form={spouseForm} setField={setSpouseField} testId="spouse-field-date_naissance" />
                  <div className="space-y-1.5">
                    <Label className="text-xs text-muted-foreground">Sexe</Label>
                    <Select value={spouseForm.sexe || ""} onValueChange={(v) => setSpouseField("sexe", v)}>
                      <SelectTrigger data-testid="spouse-field-sexe"><SelectValue placeholder="Sélectionner" /></SelectTrigger>
                      <SelectContent>
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
  );
}
