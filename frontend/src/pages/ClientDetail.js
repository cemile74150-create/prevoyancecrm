import React, { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import ClientFormDialog from "@/components/ClientFormDialog";
import { STATUT_COLORS, STATUTS, DOC_CATEGORIES } from "@/lib/constants";
import { toast } from "sonner";
import {
  ArrowLeft, Pencil, Trash2, Mail, Phone, MapPin, Briefcase, Users2, AlertTriangle,
  FileText, Download, Upload, Plus, StickyNote, History, CalendarClock, User,
} from "lucide-react";

const Info = ({ label, value }) => (
  <div>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="text-sm font-medium mt-0.5">{value || "—"}</p>
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
  const [uploadCat, setUploadCat] = useState("Certificat LPP");
  const [apptDialog, setApptDialog] = useState(false);
  const [apptForm, setApptForm] = useState({ titre: "", date: "", type: "Rendez-vous", lieu: "" });
  const fileRef = useRef();

  const loadAll = async () => {
    const [c, n, d, a, h] = await Promise.all([
      api.get(`/clients/${id}`),
      api.get(`/clients/${id}/notes`),
      api.get(`/clients/${id}/documents`),
      api.get(`/appointments`, { params: { client_id: id } }),
      api.get(`/clients/${id}/actions`),
    ]);
    setClient(c.data); setNotes(n.data); setDocs(d.data); setAppts(a.data); setActions(h.data);
  };
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

  const uploadDoc = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("category", uploadCat);
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

  const deleteDoc = async (docId) => {
    await api.delete(`/documents/${docId}`);
    setDocs((prev) => prev.filter((x) => x.id !== docId));
    toast.success("Document supprimé");
  };

  const deleteClient = async () => {
    if (!window.confirm("Supprimer définitivement ce dossier ?")) return;
    await api.delete(`/clients/${id}`);
    toast.success("Dossier supprimé");
    navigate("/clients");
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

  if (!client) return <Layout><div className="animate-pulse text-muted-foreground">Chargement…</div></Layout>;

  const fmtDate = (s) => s ? new Date(s).toLocaleString("fr-CH", { dateStyle: "medium", timeStyle: "short" }) : "";
  const fmtSize = (b) => b > 1e6 ? `${(b / 1e6).toFixed(1)} Mo` : `${Math.round(b / 1024)} Ko`;

  return (
    <Layout>
      <button onClick={() => navigate("/clients")} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors" data-testid="back-btn">
        <ArrowLeft className="h-4 w-4" /> Retour aux clients
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
            <TabsList className="mb-4">
              <TabsTrigger value="infos" data-testid="tab-infos"><User className="h-4 w-4 mr-1.5" />Infos</TabsTrigger>
              <TabsTrigger value="rdv" data-testid="tab-rdv"><CalendarClock className="h-4 w-4 mr-1.5" />Rendez-vous</TabsTrigger>
              <TabsTrigger value="notes" data-testid="tab-notes"><StickyNote className="h-4 w-4 mr-1.5" />Notes</TabsTrigger>
              <TabsTrigger value="docs" data-testid="tab-docs"><FileText className="h-4 w-4 mr-1.5" />Documents</TabsTrigger>
              <TabsTrigger value="hist" data-testid="tab-hist"><History className="h-4 w-4 mr-1.5" />Historique</TabsTrigger>
            </TabsList>

            <TabsContent value="infos">
              <Card className="p-6 space-y-6">
                <div>
                  <p className="text-sm font-semibold text-[#002FA7] mb-3">Informations personnelles</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    <Info label="Date de naissance" value={client.date_naissance} />
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
              <Card className="p-6">
                <div className="flex items-center gap-2 mb-4 flex-wrap">
                  <Select value={uploadCat} onValueChange={setUploadCat}>
                    <SelectTrigger className="w-52" data-testid="doc-category-select"><SelectValue /></SelectTrigger>
                    <SelectContent>{DOC_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                  </Select>
                  <input ref={fileRef} type="file" className="hidden" onChange={uploadDoc} data-testid="doc-file-input" />
                  <Button onClick={() => fileRef.current?.click()} data-testid="upload-doc-btn" className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"><Upload className="h-4 w-4" />Téléverser</Button>
                </div>
                {docs.length === 0 ? <p className="text-sm text-muted-foreground py-8 text-center">Aucun document.</p> : (
                  <div className="space-y-2">
                    {docs.map((d) => (
                      <div key={d.id} data-testid={`doc-row-${d.id}`} className="flex items-center gap-3 p-3 rounded-md border border-border hover:bg-secondary transition-colors">
                        <div className="h-9 w-9 rounded bg-red-50 text-red-600 flex items-center justify-center"><FileText className="h-4.5 w-4.5" /></div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">{d.original_filename}</p>
                          <p className="text-xs text-muted-foreground">{d.category} · {fmtSize(d.size)}</p>
                        </div>
                        <a href={`${API}/documents/${d.id}/download`} target="_blank" rel="noreferrer" data-testid={`doc-download-${d.id}`}>
                          <Button size="icon" variant="ghost"><Download className="h-4 w-4" /></Button>
                        </a>
                        <Button size="icon" variant="ghost" onClick={() => deleteDoc(d.id)} className="text-destructive hover:text-destructive" data-testid={`doc-delete-${d.id}`}><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    ))}
                  </div>
                )}
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
    </Layout>
  );
}
