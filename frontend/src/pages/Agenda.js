import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import Layout from "@/components/Layout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { CalendarClock, ListTodo, Plus, Trash2, MapPin, AlertTriangle } from "lucide-react";

export default function Agenda() {
  const [appts, setAppts] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [clients, setClients] = useState([]);
  const [echeances3p, setEcheances3p] = useState([]);
  const [apptDialog, setApptDialog] = useState(false);
  const [taskDialog, setTaskDialog] = useState(false);
  const [apptForm, setApptForm] = useState({ titre: "", date: "", type: "Rendez-vous", lieu: "", client_id: "none" });
  const [taskForm, setTaskForm] = useState({ titre: "", echeance: "", priorite: "normale", client_id: "none" });
  const navigate = useNavigate();

  const load = async () => {
    const [a, t, c, e] = await Promise.all([
      api.get("/appointments"),
      api.get("/tasks"),
      api.get("/clients"),
      api.get("/echeances-3p").catch(() => ({ data: [] })),
    ]);
    setAppts(a.data); setTasks(t.data); setClients(c.data); setEcheances3p(e.data || []);
  };
  useEffect(() => { load(); }, []);

  const createAppt = async () => {
    if (!apptForm.titre || !apptForm.date) { toast.error("Titre et date requis"); return; }
    const payload = { ...apptForm, client_id: apptForm.client_id === "none" ? null : apptForm.client_id };
    await api.post("/appointments", payload);
    setApptDialog(false);
    setApptForm({ titre: "", date: "", type: "Rendez-vous", lieu: "", client_id: "none" });
    load(); toast.success("Rendez-vous ajouté");
  };

  const createTask = async () => {
    if (!taskForm.titre) { toast.error("Titre requis"); return; }
    const payload = { ...taskForm, client_id: taskForm.client_id === "none" ? null : taskForm.client_id };
    await api.post("/tasks", payload);
    setTaskDialog(false);
    setTaskForm({ titre: "", echeance: "", priorite: "normale", client_id: "none" });
    load(); toast.success("Tâche ajoutée");
  };

  const toggleTask = async (t) => { await api.patch(`/tasks/${t.id}`); load(); };
  const delTask = async (id) => { await api.delete(`/tasks/${id}`); load(); };
  const delAppt = async (id) => { await api.delete(`/appointments/${id}`); load(); };

  const fmtDate = (s) => s ? new Date(s).toLocaleString("fr-CH", { dateStyle: "medium", timeStyle: "short" }) : "";
  const grouped = {};
  appts.forEach((a) => {
    const day = a.date ? new Date(a.date).toLocaleDateString("fr-CH", { weekday: "long", day: "numeric", month: "long" }) : "Sans date";
    (grouped[day] = grouped[day] || []).push(a);
  });

  return (
    <Layout>
      <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
        <div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Ordre du jour</h1>
          <p className="text-muted-foreground mt-1">Rendez-vous, rappels et tâches à effectuer</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setTaskDialog(true)} data-testid="add-task-btn" className="gap-1.5"><Plus className="h-4 w-4" />Tâche</Button>
          <Button onClick={() => setApptDialog(true)} data-testid="agenda-add-appt-btn" className="bg-[#002FA7] hover:bg-[#00248a] gap-1.5"><Plus className="h-4 w-4" />Rendez-vous</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {echeances3p.length > 0 && (
          <div className="lg:col-span-3">
            <Card className="p-4 border-amber-200 bg-amber-50/50">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                <h2 className="font-display font-bold text-lg tracking-tight">Échéances 3e pilier (&lt; 1 an)</h2>
              </div>
              <div className="flex flex-wrap gap-2">
                {echeances3p.map((e) => (
                  <button
                    key={e.client_id || e.id}
                    data-testid={`echeance-3p-${e.client_id || e.id}`}
                    onClick={() => navigate(`/clients/${e.client_id || e.id}`)}
                    className="text-sm px-3 py-1.5 rounded-md border border-amber-200 bg-white hover:border-[#002FA7] hover:text-[#002FA7] transition-colors"
                  >
                    {e.prenom} {e.nom}
                    {e.echeance_3p && (
                      <span className="text-muted-foreground ml-1.5">
                        — {new Date(e.echeance_3p).toLocaleDateString("fr-CH")}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </Card>
          </div>
        )}

        <div className="lg:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <CalendarClock className="h-5 w-5 text-[#002FA7]" />
            <h2 className="font-display font-bold text-lg tracking-tight">Rendez-vous</h2>
          </div>
          {appts.length === 0 ? (
            <Card className="p-10 text-center text-sm text-muted-foreground">Aucun rendez-vous planifié.</Card>
          ) : (
            <div className="space-y-6">
              {Object.entries(grouped).map(([day, items]) => (
                <div key={day}>
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2 capitalize">{day}</p>
                  <div className="space-y-2">
                    {items.map((a) => (
                      <Card key={a.id} data-testid={`agenda-appt-${a.id}`} className="p-4 flex items-center gap-4 hover:border-[#002FA7] transition-colors">
                        <div className="text-sm font-bold text-[#002FA7] w-16">{a.date ? new Date(a.date).toLocaleTimeString("fr-CH", { hour: "2-digit", minute: "2-digit" }) : "—"}</div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium">{a.titre}</p>
                          <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                            {a.client_name && <button onClick={() => a.client_id && navigate(`/clients/${a.client_id}`)} className="hover:text-[#002FA7]">{a.client_name}</button>}
                            {a.lieu && <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{a.lieu}</span>}
                          </div>
                        </div>
                        <span className="text-xs px-2 py-1 rounded bg-secondary">{a.type}</span>
                        <Button size="icon" variant="ghost" onClick={() => delAppt(a.id)} className="text-destructive hover:text-destructive"><Trash2 className="h-4 w-4" /></Button>
                      </Card>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center gap-2 mb-4">
            <ListTodo className="h-5 w-5 text-[#002FA7]" />
            <h2 className="font-display font-bold text-lg tracking-tight">Tâches & rappels</h2>
          </div>
          <Card className="p-4">
            {tasks.length === 0 ? <p className="text-sm text-muted-foreground py-8 text-center">Aucune tâche.</p> : (
              <div className="space-y-1">
                {tasks.map((t) => (
                  <div key={t.id} data-testid={`task-${t.id}`} className="flex items-start gap-3 p-2.5 rounded-md hover:bg-secondary transition-colors group">
                    <Checkbox checked={t.done} onCheckedChange={() => toggleTask(t)} data-testid={`task-check-${t.id}`} className="mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm ${t.done ? "line-through text-muted-foreground" : "font-medium"}`}>{t.titre}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        {t.echeance && <span className="text-xs text-muted-foreground">{new Date(t.echeance).toLocaleDateString("fr-CH")}</span>}
                        {t.priorite === "urgent" && <span className="text-[11px] text-red-700 bg-red-100 rounded px-1.5">Urgent</span>}
                      </div>
                    </div>
                    <button onClick={() => delTask(t.id)} className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"><Trash2 className="h-4 w-4" /></button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Appt dialog */}
      <Dialog open={apptDialog} onOpenChange={setApptDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display">Nouveau rendez-vous</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Titre</Label><Input data-testid="agenda-appt-titre" value={apptForm.titre} onChange={(e) => setApptForm({ ...apptForm, titre: e.target.value })} /></div>
            <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Date et heure</Label><Input data-testid="agenda-appt-date" type="datetime-local" value={apptForm.date} onChange={(e) => setApptForm({ ...apptForm, date: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Type</Label>
                <Select value={apptForm.type} onValueChange={(v) => setApptForm({ ...apptForm, type: v })}><SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{["Rendez-vous", "Appel", "Visio", "Présentation"].map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select>
              </div>
              <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Client</Label>
                <Select value={apptForm.client_id} onValueChange={(v) => setApptForm({ ...apptForm, client_id: v })}><SelectTrigger data-testid="agenda-appt-client"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="none">Aucun</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.prenom} {c.nom}</SelectItem>)}</SelectContent></Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Lieu</Label><Input value={apptForm.lieu} onChange={(e) => setApptForm({ ...apptForm, lieu: e.target.value })} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setApptDialog(false)}>Annuler</Button><Button onClick={createAppt} data-testid="agenda-appt-save" className="bg-[#002FA7] hover:bg-[#00248a]">Enregistrer</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Task dialog */}
      <Dialog open={taskDialog} onOpenChange={setTaskDialog}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display">Nouvelle tâche</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Titre</Label><Input data-testid="task-titre" value={taskForm.titre} onChange={(e) => setTaskForm({ ...taskForm, titre: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Échéance</Label><Input data-testid="task-echeance" type="date" value={taskForm.echeance} onChange={(e) => setTaskForm({ ...taskForm, echeance: e.target.value })} /></div>
              <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Priorité</Label>
                <Select value={taskForm.priorite} onValueChange={(v) => setTaskForm({ ...taskForm, priorite: v })}><SelectTrigger data-testid="task-priorite"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="normale">Normale</SelectItem><SelectItem value="urgent">Urgent</SelectItem></SelectContent></Select>
              </div>
            </div>
            <div className="space-y-1.5"><Label className="text-xs text-muted-foreground">Client (optionnel)</Label>
              <Select value={taskForm.client_id} onValueChange={(v) => setTaskForm({ ...taskForm, client_id: v })}><SelectTrigger data-testid="task-client"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="none">Aucun</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.prenom} {c.nom}</SelectItem>)}</SelectContent></Select>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setTaskDialog(false)}>Annuler</Button><Button onClick={createTask} data-testid="task-save" className="bg-[#002FA7] hover:bg-[#00248a]">Enregistrer</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
