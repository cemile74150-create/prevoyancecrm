import React, { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { STATUTS } from "@/lib/constants";
import api from "@/lib/api";
import { toast } from "sonner";

function Field({ label, k, type = "text", placeholder, form, setField }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input
        data-testid={`client-field-${k}`}
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

export default function ClientFormDialog({ open, onOpenChange, client, onSaved }) {
  const [form, setForm] = useState(empty);
  const [saving, setSaving] = useState(false);
  const isEdit = !!client;

  useEffect(() => {
    if (client) setForm({ ...empty, ...client, salaire_annuel: client.salaire_annuel ?? "" });
    else setForm(empty);
  }, [client, open]);

  const setField = (k, v) => {
    setForm((f) => ({ ...f, [k]: v }));
  };

  const save = async () => {
    if (!form.prenom.trim() || !form.nom.trim()) {
      toast.error("Le prénom et le nom sont obligatoires");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        nombre_enfants: parseInt(form.nombre_enfants) || 0,
        salaire_annuel: form.salaire_annuel ? parseFloat(form.salaire_annuel) : null,
      };
      const res = isEdit
        ? await api.put(`/clients/${client.id}`, payload)
        : await api.post("/clients", payload);
      toast.success(isEdit ? "Fiche mise à jour" : "Dossier créé");
      onSaved(res.data);
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
              <Field label="Conseiller" k="conseiller" form={form} setField={setField} />
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
              <Field label="Conjoint" k="conjoint" form={form} setField={setField} />
            </div>
          </div>

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
            {saving ? "Enregistrement…" : isEdit ? "Enregistrer" : "Créer le dossier"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
