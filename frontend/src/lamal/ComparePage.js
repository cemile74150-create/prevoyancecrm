import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import LamalShell, { formatChf } from "./LamalShell";

const EMPTY = "À compléter";

export default function ComparePage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState("");
  const [clients, setClients] = useState([]);
  const [client, setClient] = useState(null);
  const [form, setForm] = useState({ year: 2027, with_accident: "", franchise_chf: "", model_type: "BASE", insurer_id: "" });
  const [result, setResult] = useState(null);
  const [email, setEmail] = useState(null);
  const [insurerFilter, setInsurerFilter] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const id = params.get("client");
    if (!id) return;
    api.get(`/lamal/clients/${id}`).then((res) => {
      setClient(res.data.client);
      const profile = res.data.profile || {};
      setForm((prev) => ({
        ...prev,
        insurer_id: profile.insurer_id || "",
        franchise_chf: profile.franchise_chf ?? "",
        with_accident: profile.with_accident == null ? "" : profile.with_accident ? "oui" : "non",
        model_type: profile.model_type || "BASE",
        commune: profile.commune || res.data.client.commune || "",
        plz: profile.plz || res.data.client.npa || "",
        canton: profile.canton || res.data.client.canton || "",
        birth_year: profile.birth_year || "",
      }));
    }).catch(() => toast.error("Client introuvable"));
  }, [params]);

  useEffect(() => {
    if (query.trim().length < 2) { setClients([]); return; }
    const timer = setTimeout(() => {
      api.get("/lamal/clients", { params: { q: query } }).then((res) => setClients(res.data.items || [])).catch(() => setClients([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const rows = useMemo(() => {
    const source = result?.offers || result?.comparison_a || [];
    return source.filter((row) => {
      if (insurerFilter && row.insurer_id !== insurerFilter) return false;
      if (modelFilter && row.model_type !== modelFilter) return false;
      return true;
    });
  }, [result, insurerFilter, modelFilter]);

  const compare = async () => {
    setBusy(true);
    try {
      const payload = {
        client_id: client?.id,
        year: Number(form.year) || 2027,
        plz: form.plz || null,
        commune: form.commune || null,
        canton: form.canton || null,
        birth_year: form.birth_year ? Number(form.birth_year) : null,
        franchise_chf: form.franchise_chf === "" ? null : Number(form.franchise_chf),
        with_accident: form.with_accident === "" ? null : form.with_accident === "oui",
        model_type: form.model_type || null,
        insurer_id: form.insurer_id || null,
        save: Boolean(client?.id),
      };
      const res = await api.post("/lamal/comparisons", payload);
      setResult(res.data);
      setEmail(null);
      if (!res.data.ok) toast.error(res.data.messages?.[0] || "Informations incomplètes");
      else toast.success("Comparaison calculée à partir des primes OFSP");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Comparaison impossible");
    } finally {
      setBusy(false);
    }
  };

  const prepareEmail = async () => {
    if (!result?.comparison_id) {
      toast.error("Enregistrez d'abord une comparaison liée à un client");
      return;
    }
    try {
      const preview = await api.post("/lamal/emails/preview", { comparison_id: result.comparison_id });
      setEmail(preview.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Aperçu impossible");
    }
  };

  const field = (label, value) => (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm mt-1">{value || EMPTY}</p>
    </div>
  );

  return (
    <LamalShell title="Comparaison individuelle" subtitle="Les paramètres manquants restent vides. Aucune franchise ni aucune prime n'est supposée.">
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5 space-y-4">
          <div>
            <Label>Client LeoSoft</Label>
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Nom, prénom, commune ou identifiant" className="mt-1" />
            {clients.length > 0 && (
              <div className="mt-2 border rounded-md divide-y">
                {clients.slice(0, 6).map((item) => (
                  <button key={item.id} type="button" className="block w-full text-left px-3 py-2 text-sm hover:bg-secondary" onClick={() => { setClient(item); setQuery(`${item.prenom || ""} ${item.nom || ""}`); setClients([]); }}>
                    {item.prenom} {item.nom} · {item.commune || EMPTY}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {field("Commune", form.commune || client?.commune)}
            {field("Canton", form.canton || client?.canton)}
            {field("Année", form.year)}
            {field("Caisse actuelle", form.insurer_id ? `OFSP n° ${form.insurer_id}` : client?.insurer)}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>NPA</Label><Input value={form.plz || ""} onChange={(e) => setForm({ ...form, plz: e.target.value })} /></div>
            <div><Label>Commune</Label><Input value={form.commune || ""} onChange={(e) => setForm({ ...form, commune: e.target.value })} /></div>
            <div><Label>Année de naissance</Label><Input value={form.birth_year || ""} onChange={(e) => setForm({ ...form, birth_year: e.target.value })} /></div>
            <div><Label>Franchise CHF</Label><Input value={form.franchise_chf} onChange={(e) => setForm({ ...form, franchise_chf: e.target.value })} placeholder={EMPTY} /></div>
            <div>
              <Label>Accidents</Label>
              <select className="mt-1 w-full h-10 rounded-md border px-3 text-sm bg-white" value={form.with_accident} onChange={(e) => setForm({ ...form, with_accident: e.target.value })}>
                <option value="">À compléter</option>
                <option value="oui">Avec accidents</option>
                <option value="non">Sans accidents</option>
              </select>
            </div>
            <div>
              <Label>Modèle</Label>
              <select className="mt-1 w-full h-10 rounded-md border px-3 text-sm bg-white" value={form.model_type} onChange={(e) => setForm({ ...form, model_type: e.target.value })}>
                <option value="">À compléter</option>
                <option value="BASE">Standard</option>
                <option value="PRAXIS">Médecin de famille</option>
                <option value="TEL_DIG">Télémédecine</option>
                <option value="FLEX">Flexible</option>
              </select>
            </div>
            <div className="col-span-2"><Label>N° OFSP de la caisse actuelle</Label><Input value={form.insurer_id} onChange={(e) => setForm({ ...form, insurer_id: e.target.value })} placeholder="Laisser vide si inconnu" /></div>
          </div>
          <Button className="bg-[#002FA7] hover:bg-[#00248a]" onClick={compare} disabled={busy}>{busy ? "Calcul…" : "Comparer les primes"}</Button>
        </Card>
        <Card className="p-5 space-y-4">
          {!result && <p className="text-sm text-muted-foreground">Les résultats s'afficheront ici après le calcul.</p>}
          {result && (
            <>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {field("Région tarifaire", result.region)}
                {field("Catégorie d'âge", result.age_label)}
                {field("Prime de référence 2027", result.reference ? `${formatChf(result.reference.premium_month)} CHF` : EMPTY)}
                {field("Économie annuelle fiable", result.best_equivalent_alternative ? `${formatChf(result.best_equivalent_alternative.year)} CHF` : "—")}
              </div>
              {result.known_premium_ignored && <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-md p-3">{result.known_premium_ignored}</p>}
              <p className="text-xs text-muted-foreground">Top 3 à paramètres équivalents. Ce classement n'est pas un conseil médical.</p>
              <ul className="space-y-2">
                {(result.top3 || []).map((row) => (
                  <li key={`${row.insurer_id}-${row.tarif_id}`} className="flex justify-between text-sm border rounded-md px-3 py-2">
                    <span>{row.insurer_name} · {row.product_name}</span>
                    <span>{formatChf(row.premium_month)} CHF</span>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <select className="h-9 rounded-md border px-2 text-sm" value={insurerFilter} onChange={(e) => setInsurerFilter(e.target.value)}>
                  <option value="">Tous les assureurs</option>
                  {[...new Set((result.offers || []).map((row) => row.insurer_id))].map((id) => <option key={id} value={id}>OFSP {id}</option>)}
                </select>
                <select className="h-9 rounded-md border px-2 text-sm" value={modelFilter} onChange={(e) => setModelFilter(e.target.value)}>
                  <option value="">Tous les modèles affichés</option>
                  <option value="BASE">Standard</option>
                  <option value="PRAXIS">Médecin de famille</option>
                  <option value="TEL_DIG">Télémédecine</option>
                  <option value="FLEX">Flexible</option>
                </select>
              </div>
              <div className="overflow-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      {["Assurance", "Modèle", "Franchise", "Prime mensuelle", "Prime annuelle", ""].map((label) => <th key={label} className="py-2 pr-3 font-medium">{label}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={`${row.insurer_id}-${row.tarif_id}-${row.franchise_chf}-${row.model_type}`} className="border-t">
                        <td className="py-2 pr-3">{row.insurer_name}</td>
                        <td className="py-2 pr-3">{row.equivalent ? row.product_name : `${row.product_name} (non équivalent)`}</td>
                        <td className="py-2 pr-3">{row.franchise_chf}</td>
                        <td className="py-2 pr-3">{formatChf(row.premium_month)}</td>
                        <td className="py-2">{formatChf(row.premium_year)}</td>
                        <td className="py-2">
                          {result.comparison_id && (
                            <button type="button" className="text-[#002FA7]" onClick={() => api.post(`/lamal/comparisons/${result.comparison_id}/recommendation`, { insurer_id: row.insurer_id, tarif_id: row.tarif_id }).then(() => toast.success("Offre retenue pour le suivi"))}>Retenir</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Button variant="outline" onClick={prepareEmail}>Préparer l'e-mail</Button>
              {(result.comparison_b || []).length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Autres franchises et modèles</p>
                  <p className="text-xs text-muted-foreground">Ces lignes ne sont pas une comparaison strictement équivalente. Le plafond de participation rappelle le risque de frais, sans juger l'intérêt médical.</p>
                  {(result.comparison_b || []).slice(0, 6).map((row) => (
                    <p key={`${row.insurer_id}-${row.tarif_id}-${row.franchise_chf}`} className="text-xs text-muted-foreground">
                      {row.insurer_name} · {row.model_label} · franchise {row.franchise_chf} · {formatChf(row.premium_month)} CHF. {row.participation_note}
                    </p>
                  ))}
                </div>
              )}
            </>
          )}
        </Card>
      </div>
      {email && (
        <Card className="p-5 space-y-3">
          <h2 className="font-display font-bold">Aperçu avant validation</h2>
          <Input value={email.subject} onChange={(e) => setEmail({ ...email, subject: e.target.value })} />
          <textarea className="w-full min-h-64 border rounded-md p-3 text-sm" value={email.body} onChange={(e) => setEmail({ ...email, body: e.target.value })} />
          <p className="text-xs text-muted-foreground">Aucun envoi réel n'est possible tant que le module n'a pas été autorisé. L'aperçu reste modifiable.</p>
        </Card>
      )}
    </LamalShell>
  );
}
