import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import LamalShell from "./LamalShell";

const FILTERS = [
  { id: "tous", label: "Tous" },
  { id: "preparer", label: "À préparer" },
  { id: "prets", label: "Prêts" },
  { id: "verifier", label: "À vérifier" },
  { id: "valides", label: "Validés" },
];

const MODELS = [
  ["PRAXIS", "Médecin de famille"],
  ["TEL_DIG", "Télémédecine"],
  ["FLEX", "Flexible"],
];

function campaignIdOf(current) {
  return current?.campaign?.id || current?.id || null;
}

function importedCampaign(items) {
  const scored = (items || []).map((item) => ({
    item,
    people: Number(item?.progress?.total || item?.progress?.selected || item?.recipient_ids?.length || 0),
  }));
  const withPeople = scored.filter((row) => row.people > 0);
  const pool = withPeople.length ? withPeople : scored;
  pool.sort((a, b) => b.people - a.people);
  return pool[0]?.item || null;
}

function lineFor(lignes, franchise, code) {
  return (lignes || []).find((row) => Number(row.franchise) === franchise && row.modele === code) || null;
}

export default function CampaignsPage() {
  const [items, setItems] = useState([]);
  const [current, setCurrent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("tous");
  const [sort, setSort] = useState("alpha");
  const [progress, setProgress] = useState(null);
  const [editing, setEditing] = useState(false);
  const [mailEditing, setMailEditing] = useState(false);
  const [form, setForm] = useState(null);
  const [mailForm, setMailForm] = useState(null);
  const [offers, setOffers] = useState(null);
  const fileRef = useRef(null);

  const load = useCallback(() => api.get("/lamal/campaigns").then((res) => {
    const rows = res.data.items || [];
    setItems(rows);
    return rows;
  }).catch(() => []), []);

  const openCampaign = useCallback((id) => {
    setSelectedId(null);
    setOffers(null);
    setEditing(false);
    setMailEditing(false);
    return api.get(`/lamal/campaigns/${id}`).then((res) => setCurrent(res.data));
  }, []);

  useEffect(() => {
    load().then((rows) => {
      const chosen = importedCampaign(rows);
      if (chosen?.id) openCampaign(chosen.id);
    });
  }, [load, openCampaign]);

  const prepare = async () => {
    setBusy(true);
    try {
      const res = await api.post("/lamal/campaigns", { year: 2027, client_ids: [] });
      toast.success("Campagne préparée, sans envoi");
      await openCampaign(res.data.id);
      load();
    } catch (error) {
      toast.error(typeof error?.response?.data?.detail === "string" ? error.response.data.detail : "Préparation impossible");
    } finally {
      setBusy(false);
    }
  };

  const importList = async (event) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", chosen);
      const res = await api.post("/lamal/campaigns/import", body);
      setSummary(res.data);
      toast.success(`${res.data.contacts_created} contacts, ${res.data.emails_prepared} brouillons`);
      setSelectedId(null);
      await openCampaign(res.data.id);
      load();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Import impossible");
    } finally {
      setBusy(false);
    }
  };

  const contacts = current?.contacts || [];
  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("fr");
    const rows = contacts.filter((item) => {
      if (filter !== "tous" && item.bucket !== filter) return false;
      if (!needle) return true;
      const haystack = [item.prenom, item.nom, item.email, item.npa, item.lieu].join(" ").toLocaleLowerCase("fr");
      return haystack.includes(needle);
    });
    rows.sort((a, b) => {
      if (sort === "age") return (a.age ?? 999) - (b.age ?? 999) || `${a.nom}`.localeCompare(`${b.nom}`, "fr");
      if (sort === "statut") return `${a.etat_comparatif} ${a.etat_email}`.localeCompare(`${b.etat_comparatif} ${b.etat_email}`, "fr") || `${a.nom}`.localeCompare(`${b.nom}`, "fr");
      return `${a.nom} ${a.prenom}`.localeCompare(`${b.nom} ${b.prenom}`, "fr");
    });
    return rows;
  }, [contacts, query, filter, sort]);

  const selectedIndex = visible.findIndex((item) => item.id === selectedId);
  const selected = selectedIndex >= 0 ? visible[selectedIndex] : null;
  const counts = current?.summary;

  useEffect(() => {
    if (!selected) {
      setForm(null);
      setMailForm(null);
      return;
    }
    setForm({
      prenom: selected.prenom || "",
      nom: selected.nom || "",
      naissance: selected.naissance || "",
      adresse: selected.adresse || "",
      npa: selected.npa || "",
      lieu: selected.lieu || "",
      email: selected.email || "",
    });
    setMailForm({
      subject: selected.email_apercu?.subject || "",
      intro: selected.email_apercu?.intro || "",
      closing: selected.email_apercu?.closing || "",
    });
    setEditing(false);
    setMailEditing(false);
    setOffers(null);
  }, [selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  const replaceContact = (payload) => {
    if (!payload?.contact) return;
    setCurrent((prev) => {
      if (!prev) return prev;
      const nextContacts = (prev.contacts || []).map((item) => (item.id === payload.contact.id ? payload.contact : item));
      const emails = (prev.emails || []).map((item) => (item.id === payload.email?.id ? payload.email : item));
      return { ...prev, contacts: nextContacts, emails, summary: recount(nextContacts, emails) };
    });
  };

  const saveIdentity = async () => {
    if (!selected || !form) return;
    setBusy(true);
    try {
      const res = await api.patch(`/lamal/campaigns/contacts/${selected.id}`, form);
      replaceContact(res.data);
      toast.success(res.data.contact?.etat_comparatif === "a_recalculer" ? "Enregistré. Le comparatif est à recalculer." : "Modifications enregistrées");
      setEditing(false);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Enregistrement impossible");
    } finally {
      setBusy(false);
    }
  };

  const recalculate = async (confirm = false) => {
    if (!selected) return;
    setBusy(true);
    try {
      const res = await api.post(`/lamal/campaigns/contacts/${selected.id}/recalculer`, { confirm });
      replaceContact(res.data);
      toast.success("Comparatif recalculé");
    } catch (error) {
      if (error?.response?.status === 409 && !confirm) {
        if (window.confirm("Ce brouillon a été modifié. Le régénérer à partir des primes officielles ?")) {
          setBusy(false);
          return recalculate(true);
        }
      } else {
        toast.error(error?.response?.data?.detail || "Recalcul impossible");
      }
    } finally {
      setBusy(false);
    }
  };

  const showOffers = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const res = await api.post(`/lamal/campaigns/contacts/${selected.id}/offres`);
      setOffers(res.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Offres indisponibles");
    } finally {
      setBusy(false);
    }
  };

  const saveDraft = async () => {
    if (!selected || !mailForm) return;
    setBusy(true);
    try {
      const res = await api.patch(`/lamal/campaigns/contacts/${selected.id}/brouillon`, mailForm);
      replaceContact(res.data);
      toast.success("Brouillon enregistré");
      setMailEditing(false);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Brouillon non enregistré");
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async (confirm = false) => {
    if (!selected) return;
    if (!confirm && selected.email_apercu?.manual_edit && !window.confirm("Régénérer l'e-mail efface les modifications manuelles du texte. Continuer ?")) return;
    setBusy(true);
    try {
      const res = await api.post(`/lamal/campaigns/contacts/${selected.id}/regenerer`, { confirm: true });
      replaceContact(res.data);
      toast.success("E-mail régénéré");
      setMailEditing(false);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Régénération impossible");
    } finally {
      setBusy(false);
    }
  };

  const validate = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const res = await api.post(`/lamal/campaigns/contacts/${selected.id}/valider`);
      replaceContact(res.data);
      toast.success("Brouillon validé. Aucun e-mail n'est envoyé.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Validation impossible");
    } finally {
      setBusy(false);
    }
  };

  const prepareAll = async () => {
    const id = campaignIdOf(current);
    if (!id) return;
    setBusy(true);
    setProgress({ done: 0, total: contacts.length || 1 });
    try {
      let offset = 0;
      let total = contacts.length || 1;
      let guard = 0;
      while (offset < total && guard < 50) {
        const res = await api.post(`/lamal/campaigns/${id}/preparer`, { offset, limit: 40 });
        total = res.data.total;
        offset = res.data.next_offset;
        setProgress(res.data);
        guard += 1;
        if (res.data.done) break;
      }
      await openCampaign(id);
      toast.success("Comparatifs et brouillons préparés. Aucun envoi.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Préparation impossible");
    } finally {
      setBusy(false);
    }
  };

  const step = (direction) => {
    if (!visible.length) return;
    const next = selectedIndex < 0 ? 0 : (selectedIndex + direction + visible.length) % visible.length;
    setSelectedId(visible[next].id);
  };

  const body = selected?.email_apercu?.body || "";
  const htmlMail = body.trim().startsWith("<");

  return (
    <LamalShell wide title="Campagne 1" subtitle="Mode préparation — Aucun e-mail envoyé">
      <div className="flex flex-wrap items-center gap-2">
        <Button className="bg-[#002FA7] hover:bg-[#163A5F]" onClick={prepare} disabled={busy}>Préparer la campagne 2027</Button>
        <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}>Importer une liste Excel</Button>
        <Button className="bg-[#1A8A9C] hover:bg-[#163A5F] text-white" onClick={prepareAll} disabled={busy || !contacts.length}>Préparer tous les comparatifs et brouillons</Button>
        <input ref={fileRef} type="file" accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="hidden" onChange={importList} />
      </div>
      <p className="text-sm font-medium text-[#163A5F]">Mode préparation — Aucun e-mail envoyé</p>
      {(counts || summary) && (
        <p className="text-sm text-[#5C6B76]">
          {(counts?.contacts ?? summary?.contacts_created ?? 0)} contacts
          {" · "}{(counts?.comparatifs_disponibles ?? summary?.with_premiums ?? 0)} comparatifs disponibles
          {" · "}{(counts?.a_verifier ?? 0)} à vérifier
          {" · "}{(counts?.brouillons_valides ?? 0)} brouillons validés
          {" · "}0 envoyé
          {counts ? ` · ${counts.avec_primes} avec prime · ${counts.sans_primes} sans prime` : ""}
        </p>
      )}
      {progress && busy && <p className="text-sm text-[#163A5F]">Préparation {progress.next_offset || progress.done || 0} / {progress.total}</p>}
      <div className="grid gap-4 lg:grid-cols-[32%_1fr] lg:items-start">
        <Card className="p-0 overflow-hidden lg:sticky lg:top-4 lg:max-h-[calc(100vh-7rem)] lg:flex lg:flex-col">
          <div className="p-3 space-y-2 border-b bg-white">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium text-[#163A5F]">Campagne 1 · {visible.length} personne{visible.length > 1 ? "s" : ""}</p>
              <div className="flex gap-1">
                <Button type="button" variant="outline" className="h-8 px-2" onClick={() => step(-1)} disabled={!visible.length}>Précédent</Button>
                <Button type="button" variant="outline" className="h-8 px-2" onClick={() => step(1)} disabled={!visible.length}>Suivant</Button>
              </div>
            </div>
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Prénom, nom, e-mail, NPA, localité" />
            <div className="flex flex-wrap gap-1">
              {FILTERS.map((item) => (
                <button key={item.id} type="button" className={`text-xs px-2 py-1 rounded-md border ${filter === item.id ? "bg-[#163A5F] text-white border-[#163A5F]" : "bg-white text-[#5C6B76]"}`} onClick={() => setFilter(item.id)}>{item.label}</button>
              ))}
            </div>
            <select className="w-full h-9 rounded-md border bg-white px-2 text-sm" value={sort} onChange={(event) => setSort(event.target.value)}>
              <option value="alpha">Tri alphabétique</option>
              <option value="age">Tri par âge</option>
              <option value="statut">Tri par statut</option>
            </select>
          </div>
          <div className="overflow-auto lg:flex-1">
            {!current && <p className="p-4 text-sm text-[#5C6B76]">Importez un Excel pour afficher les personnes. Aucune fiche n’est masquée.</p>}
            {current && !contacts.length && <p className="p-4 text-sm text-[#5C6B76]">Cette campagne n’a pas encore de contacts. Importez le fichier Excel.</p>}
            {visible.map((item) => (
              <button key={item.id} type="button" className={`block w-full text-left px-3 py-3 border-b ${item.id === selectedId ? "bg-[#E7F4F6] border-l-4 border-l-[#1A8A9C]" : "bg-white hover:bg-[#F4F7F8]"}`} onClick={() => setSelectedId(item.id)}>
                <span className="flex justify-between gap-3">
                  <span className="font-medium text-[#163A5F]">{item.prenom} {item.nom}</span>
                  <span className="text-xs text-[#5C6B76] shrink-0">{item.age != null ? `${item.age} ans` : (item.naissance || "")}</span>
                </span>
                <span className="block text-xs text-[#5C6B76] mt-1">{item.npa} {item.lieu}</span>
                <span className="block text-xs text-[#333333] truncate">{item.email || "E-mail manquant"}</span>
                <span className="block text-xs mt-1 text-[#163A5F]">{item.etat_comparatif_label} · {item.etat_email_label}</span>
              </button>
            ))}
          </div>
        </Card>
        <div className="space-y-4 min-w-0">
          {!selected && <Card className="p-5 text-sm text-[#5C6B76]">Choisissez un nom dans la liste. S’il n’y a personne, importez l’Excel : les fiches sans prime restent visibles.</Card>}
          {selected && form && (
            <>
              <Card className="p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-semibold text-[#163A5F]">Informations personnelles</h2>
                  <Button type="button" variant="outline" onClick={() => setEditing((value) => !value)}>{editing ? "Fermer l’édition" : "Modifier"}</Button>
                </div>
                {editing ? (
                  <div className="grid sm:grid-cols-2 gap-3">
                    {[["prenom", "Prénom"], ["nom", "Nom"], ["naissance", "Naissance"], ["adresse", "Adresse"], ["npa", "NPA"], ["lieu", "Localité"], ["email", "E-mail"]].map(([key, label]) => (
                      <label key={key} className="text-sm text-[#5C6B76]">{label}
                        <Input className="mt-1 text-[#163A5F]" value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
                      </label>
                    ))}
                    <div className="sm:col-span-2">
                      <Button className="bg-[#002FA7] hover:bg-[#163A5F]" onClick={saveIdentity} disabled={busy}>Enregistrer les modifications</Button>
                    </div>
                  </div>
                ) : (
                  <dl className="grid sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
                    <Info label="Prénom" value={selected.prenom} />
                    <Info label="Nom" value={selected.nom} />
                    <Info label="Naissance" value={selected.naissance} />
                    <Info label="Âge en 2027" value={selected.age == null ? "" : String(selected.age)} />
                    <Info label="Catégorie" value={selected.categorie} />
                    <Info label="Adresse" value={selected.adresse} />
                    <Info label="Complément" value={selected.complement} />
                    <Info label="NPA" value={selected.npa} />
                    <Info label="Localité" value={selected.lieu} />
                    <Info label="Canton" value={selected.canton} />
                    <Info label="E-mail" value={selected.email} />
                    <Info label="Téléphone" value={selected.telephone} />
                    <Info label="Fichier source" value={selected.fichier} />
                    <Info label="Importé le" value={formatWhen(selected.importe_le)} />
                    <Info label="N° de ligne" value={selected.ligne == null ? "" : String(selected.ligne)} />
                    <Info label="Campagne" value="Campagne 1" />
                    <Info label="Comparatif" value={selected.etat_comparatif_label} />
                    <Info label="E-mail" value={selected.etat_email_label} />
                    <Info label="Calculé le" value={formatWhen(selected.calcule_le)} />
                    <Info label="Modifié le" value={formatWhen(selected.modifie_le)} />
                  </dl>
                )}
                {Object.keys(selected.extras || {}).length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-[#163A5F] mb-2">Autres informations importées</h3>
                    <dl className="grid sm:grid-cols-2 gap-2 text-sm">
                      {Object.entries(selected.extras).map(([key, value]) => <Info key={key} label={key} value={String(value)} />)}
                    </dl>
                  </div>
                )}
              </Card>
              <Card className="p-5 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-semibold text-[#163A5F]">Comparatif LAMal 2027</h2>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" onClick={() => recalculate(false)} disabled={busy}>Recalculer le comparatif</Button>
                    <Button type="button" variant="outline" onClick={showOffers} disabled={busy}>Voir toutes les offres</Button>
                  </div>
                </div>
                <p className="text-sm text-[#5C6B76]">OFSP 2027, avec accidents. Âge tarifaire calculé depuis la date de naissance.</p>
                {selected.comparatif?.afficher ? (
                  <>
                    <OfferTable title="01 / Franchise de 300 CHF" franchise={300} lignes={selected.comparatif.lignes} />
                    <OfferTable title="02 / Franchise de 2’500 CHF" franchise={2500} lignes={selected.comparatif.lignes} note={(selected.comparatif.franchise_notes || []).find((item) => Number(item.franchise) === 2500)?.texte} />
                  </>
                ) : (
                  <div className="rounded-md bg-[#F4F7F8] border border-[#D5E3E8] p-4 text-sm text-[#163A5F] space-y-2">
                    <p>{selected.comparatif?.message}</p>
                    {(selected.comparatif?.motifs || []).filter((item) => selected.etat_comparatif === "calcule" ? false : item !== "franchise incompatible" || selected.etat_comparatif !== "calcule").map((item) => (
                      <p key={item}>{item}</p>
                    ))}
                    {(selected.comparatif?.franchise_notes || []).map((item) => <p key={item.franchise}>{item.texte}</p>)}
                  </div>
                )}
                {offers && (
                  <div className="border-t pt-3 space-y-2">
                    <p className="text-sm font-medium text-[#163A5F]">Autres offres du même profil</p>
                    {offers.message && <p className="text-sm">{offers.message}</p>}
                    <div className="max-h-64 overflow-auto text-sm">
                      {(offers.lignes || []).map((row, index) => (
                        <p key={`${row.franchise}-${row.modele}-${row.label}-${index}`} className="py-1 border-b border-[#F4F7F8]">
                          Franchise {row.franchise} · {labelOf(row.modele)} · {row.label} · {row.premium} CHF
                        </p>
                      ))}
                      {!offers.lignes?.length && <p className="text-[#5C6B76]">Aucune offre officielle pour ce profil.</p>}
                    </div>
                  </div>
                )}
              </Card>
              <Card className="p-5 space-y-3">
                <h2 className="text-lg font-semibold text-[#163A5F]">Aperçu de l’e-mail personnalisé</h2>
                <dl className="grid sm:grid-cols-2 gap-2 text-sm">
                  <Info label="Destinataire" value={selected.email_apercu?.to} />
                  <Info label="Statut" value={selected.email_apercu?.statut_label} />
                  <div className="sm:col-span-2"><Info label="Objet" value={selected.email_apercu?.subject} /></div>
                </dl>
                {mailEditing && mailForm && (
                  <div className="space-y-2">
                    <label className="text-sm text-[#5C6B76] block">Objet
                      <Input className="mt-1" value={mailForm.subject} onChange={(event) => setMailForm({ ...mailForm, subject: event.target.value })} />
                    </label>
                    <label className="text-sm text-[#5C6B76] block">Introduction
                      <textarea className="mt-1 w-full min-h-24 border rounded-md p-2 text-sm" value={mailForm.intro} onChange={(event) => setMailForm({ ...mailForm, intro: event.target.value })} />
                    </label>
                    <label className="text-sm text-[#5C6B76] block">Signature
                      <textarea className="mt-1 w-full min-h-24 border rounded-md p-2 text-sm" value={mailForm.closing} onChange={(event) => setMailForm({ ...mailForm, closing: event.target.value })} />
                    </label>
                    <p className="text-xs text-[#5C6B76]">Le texte se modifie ici. Les primes du tableau restent celles du tarif OFSP.</p>
                  </div>
                )}
                {htmlMail ? (
                  <iframe title="Mail LAMal" sandbox="" srcDoc={body} className="w-full h-[720px] border rounded-md bg-white" />
                ) : (
                  <pre className="whitespace-pre-wrap text-xs bg-[#F4F7F8] p-3 rounded-md">{body || "Mail pas encore préparé."}</pre>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" onClick={() => setMailEditing((value) => !value)}>Modifier l’e-mail</Button>
                  <Button type="button" variant="outline" onClick={saveDraft} disabled={busy || !mailEditing}>Enregistrer le brouillon</Button>
                  <Button type="button" variant="outline" onClick={() => regenerate(false)} disabled={busy}>Régénérer l’e-mail</Button>
                  <Button type="button" className="bg-[#002FA7] hover:bg-[#163A5F]" onClick={validate} disabled={busy}>Valider le brouillon</Button>
                  <Button type="button" variant="outline" onClick={() => step(1)} disabled={!visible.length}>Contact suivant</Button>
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
    </LamalShell>
  );
}

function recount(contacts, emails) {
  const sent = (emails || []).filter((item) => item?.status === "envoye").length;
  return {
    contacts: contacts.length,
    avec_primes: contacts.filter((item) => (item.premiums_found || 0) > 0).length,
    sans_primes: contacts.filter((item) => !(item.premiums_found || 0)).length,
    comparatifs_disponibles: contacts.filter((item) => item.etat_comparatif === "calcule").length,
    a_verifier: contacts.filter((item) => item.bucket === "verifier").length,
    brouillons_valides: contacts.filter((item) => item.etat_email === "valide").length,
    envoyes: sent,
  };
}

function Info({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-xs text-[#5C6B76]">{label}</dt>
      <dd className="text-[#163A5F]">{value}</dd>
    </div>
  );
}

function OfferTable({ title, franchise, lignes, note }) {
  return (
    <div>
      <p className="font-medium text-[#163A5F]">{title}</p>
      {note && <p className="text-sm text-[#5C6B76] mb-2">{note}</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-[#163A5F] text-white">
            <th className="text-left font-medium px-3 py-2">Compagnie</th>
            <th className="text-left font-medium px-3 py-2">Modèle de soins</th>
            <th className="text-right font-medium px-3 py-2">Prime / mois</th>
          </tr>
        </thead>
        <tbody>
          {MODELS.map(([code, label], index) => {
            const row = lineFor(lignes, franchise, code);
            const empty = note ? "—" : "non disponible";
            return (
              <tr key={code} className={index % 2 ? "bg-[#F7F8F9]" : "bg-white"}>
                <td className="px-3 py-2">{row?.label || empty}</td>
                <td className="px-3 py-2">{label}</td>
                <td className="px-3 py-2 text-right font-semibold text-[#1B4F72]">{row?.premium ? `${row.premium} CHF` : empty}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function labelOf(code) {
  return MODELS.find((item) => item[0] === code)?.[1] || code;
}

function formatWhen(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("fr-CH", { dateStyle: "short", timeStyle: "short" }).format(date);
}
