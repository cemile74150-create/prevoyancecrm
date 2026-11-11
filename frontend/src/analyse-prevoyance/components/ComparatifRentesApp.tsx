// @ts-nocheck
"use client";

import { useEffect, useState } from "react";
import { FileDown, Loader2, Plus, Trash2 } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CommuneSearch } from "@/analyse-prevoyance/components/CommuneSearch";
import { PersonIdentityFields } from "@/analyse-prevoyance/components/PersonIdentityFields";
import { ConfirmDeleteButton } from "@/analyse-prevoyance/components/ConfirmDeleteButton";
import { Alert, AlertDescription, AlertTitle } from "@/analyse-prevoyance/ui/alert";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/analyse-prevoyance/ui/select";
import { withSingleRecommander } from "@/analyse-prevoyance/lib/analyseWizard";
import { compagnieEstPax, NOTE_PAX_DIFFERE } from "@/analyse-prevoyance/lib/compagniePax";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";
import {
  emptyPerson,
  type AnalyseInput,
  type EtatCivil,
  type RenteHypothesisInput,
  type TaxLocation,
} from "@/analyse-prevoyance/lib/types";

function emptyOffer(): RenteHypothesisInput {
  return {
    id: `offre-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    type: "certaine",
    compagnie: "",
    capitalPlace: 0,
    dureeAnnees: 20,
    renteGarantieAnnuelle: 0,
    participationExcedentsAnnuelle: 0,
    recommander: false,
  };
}

function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return formatChf(value);
}

function errorText(err: unknown): string {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  return "Calcul impossible";
}

export function ComparatifRentesApp({
  initialRecord,
  onSaved,
}: {
  initialRecord: {
    id: string;
    clientId?: string | null;
    input: AnalyseInput;
    results?: unknown;
  };
  onSaved?: () => void;
}) {
  const [input, setInput] = useState<AnalyseInput>(initialRecord.input);
  const [results, setResults] = useState(initialRecord.results || null);
  const [error, setError] = useState<string | null>(null);
  const [folderNote, setFolderNote] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [conseillerOptions, setConseillerOptions] = useState<string[]>([]);
  const { user, isAdmin } = useAuth() || {};
  const isMarried = input.etatCivil === "Marié(e)";

  useEffect(() => {
    const name = (user?.name || "").trim();
    if (!name) return;
    setInput((prev) => {
      if ((prev.conseillerNom || "").trim()) return prev;
      return { ...prev, conseillerNom: name };
    });
  }, [user]);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    api.get("/users/conseillers")
      .then((res) => {
        if (cancelled) return;
        const names = (Array.isArray(res.data) ? res.data : [])
          .map((row) => (row?.name || "").trim())
          .filter(Boolean);
        setConseillerOptions(names);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [isAdmin]);

  function patchInput(partial: Partial<AnalyseInput>) {
    setInput((prev) => ({ ...prev, ...partial }));
    setResults(null);
    setFolderNote(null);
  }

  /** Affichage / PDF seulement : ne force pas un nouveau calcul. */
  function setInclureImpotFortune(checked: boolean) {
    setInput((prev) => ({ ...prev, inclureImpotFortune: checked }));
    setResults((prev) => (prev ? { ...prev, inclureImpotFortune: checked } : prev));
    setFolderNote(null);
  }

  function onEtatCivil(v: EtatCivil) {
    if (v === "Marié(e)") {
      patchInput({
        etatCivil: v,
        conjoint: input.conjoint ?? emptyPerson(input.client1.civilite === "Madame" ? "Monsieur" : "Madame"),
      });
    } else {
      patchInput({ etatCivil: v, conjoint: null, salaireConjoint: 0 });
    }
  }

  function onCommune(ville: string, loc: TaxLocation | null) {
    patchInput({
      villeRecherche: ville,
      taxLocationId: loc?.TaxLocationID ?? null,
      taxGroupId: loc?.TaxLocationID ?? null,
    });
  }

  const rows = input.renteHypotheses || [];

  function updateOffer(id: string, partial: Partial<RenteHypothesisInput>) {
    patchInput({
      renteHypotheses: rows.map((row) => (row.id === id ? { ...row, ...partial } : row)),
    });
  }

  async function saveDraft() {
    setPending(true);
    setError(null);
    try {
      const res = await api.put(`/comparatifs-rentes/${initialRecord.id}`, { input });
      setInput(res.data.input);
      setResults(null);
      onSaved?.();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setPending(false);
    }
  }

  /** Persiste la case fortune sans effacer le tableau calculé. */
  async function persistDisplayOptions() {
    const res = await api.put(`/comparatifs-rentes/${initialRecord.id}`, {
      input,
      autosave: true,
    });
    setInput(res.data.input);
    if (res.data.results) setResults(res.data.results);
    onSaved?.();
  }

  async function downloadPdf() {
    setPending(true);
    setError(null);
    try {
      await persistDisplayOptions();
      const res = await api.get(`/comparatifs-rentes/${initialRecord.id}/pdf`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "Comparatif_offres_rentes.pdf";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setPending(false);
    }
  }

  async function integrateFolder() {
    if (!initialRecord.clientId) {
      setError("Choisissez un client avant d'intégrer le comparatif au dossier.");
      return;
    }
    if (!columns.length) {
      setError("Calculez le tableau avant de l'intégrer au dossier.");
      return;
    }
    setPending(true);
    setError(null);
    setFolderNote(null);
    try {
      await persistDisplayOptions();
      await api.post(`/comparatifs-rentes/${initialRecord.id}/enregistrer-dossier`);
      setFolderNote("Le PDF est dans le dossier du client, rubrique Analyse de prévoyance.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setPending(false);
    }
  }

  async function calculate() {
    setPending(true);
    setError(null);
    setFolderNote(null);
    try {
      const res = await api.post(`/comparatifs-rentes/${initialRecord.id}/calculer`, { input });
      setInput(res.data.input);
      setResults(res.data.results);
      onSaved?.();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setPending(false);
    }
  }

  const columns = results?.columns || [];
  const yearCount = results?.anneesAffichees || 0;
  const inclureImpotFortune = input.inclureImpotFortune !== false;
  const fortuneDurations = columns
    .map((col) => col.dureeFortune)
    .filter((value) => value != null);
  const uniqueDurations = [...new Set(fortuneDurations)];
  const totalLabel = uniqueDurations.length === 1
    ? `Total impôt fortune sur ${uniqueDurations[0]} ans`
    : uniqueDurations.length === 0
      ? "Total impôt fortune"
      : "Total impôt fortune sur la durée";

  return (
    <div className="mx-auto max-w-[1680px] px-4 pt-3 pb-10 sm:px-6 lg:px-8">
      <header className="mb-6 space-y-2">
        <p className="text-sm font-medium tracking-[0.12em] text-[#002FA7] uppercase">
          LeoSoft · Comparatif des rentes
        </p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight">
          Tableau comparatif de rentes
        </h1>
        <p className="max-w-3xl text-muted-foreground">
          Même fiche client que la planification. Cet onglet ne calcule que les offres de rente.
          L&apos;impôt de la rente est annuel. Le bouton + ajoute une AVS, une rente LPP ou un autre revenu dans cet impôt. Les deux impôts sur la fortune n&apos;apparaissent que si la rente a une durée.
        </p>
      </header>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="space-y-6">
        <section className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-7">
          <div>
            <h2 className="font-heading text-lg font-semibold">Fiche client</h2>
            <p className="text-sm text-muted-foreground">
              Identité, commune fiscale et état civil du foyer. L&apos;AVS et la LPP ne sont pas demandées.
            </p>
          </div>
          <PersonIdentityFields
            person={input.client1}
            onChange={(p) => patchInput({ client1: p })}
            desiredAge={input.client1.ageRetraiteSouhaite ?? input.ageRetraiteSouhaite ?? null}
            onDesiredAge={(age) =>
              patchInput({
                ageRetraiteSouhaite: age,
                client1: { ...input.client1, ageRetraiteSouhaite: age },
              })
            }
          />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <CommuneSearch
              value={input.villeRecherche}
              taxLocationId={input.taxLocationId}
              taxYear={input.taxYear}
              onChange={onCommune}
              disabled={pending}
            />
            <div className="space-y-2">
              <Label>État civil</Label>
              <Select value={input.etatCivil} onValueChange={(v) => onEtatCivil(v)}>
                <SelectTrigger className="w-full" data-testid="comparatif-etat-civil">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Personne vivant seule">Personne vivant seule</SelectItem>
                  <SelectItem value="Marié(e)">Marié(e)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Conseiller</Label>
              {isAdmin ? (
                <select
                  className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                  value={input.conseillerNom || ""}
                  onChange={(e) => patchInput({ conseillerNom: e.target.value })}
                >
                  <option value="">Sélectionner</option>
                  {(input.conseillerNom && !conseillerOptions.includes(input.conseillerNom)
                    ? [input.conseillerNom, ...conseillerOptions]
                    : conseillerOptions
                  ).map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              ) : (
                <Input value={input.conseillerNom || user?.name || ""} readOnly disabled />
              )}
            </div>
          </div>
          <div className="max-w-sm space-y-2">
            <Label>Salaire brut annuel (CHF)</Label>
            <Input
              type="number"
              min={0}
              value={input.salaireClient1 || ""}
              onChange={(e) => patchInput({ salaireClient1: Number(e.target.value) || 0 })}
            />
          </div>
          {isMarried && input.conjoint && (
            <div className="space-y-4 border-t pt-4">
              <h3 className="font-medium">Assuré 2</h3>
              <PersonIdentityFields
                person={input.conjoint}
                onChange={(p) => patchInput({ conjoint: p })}
                desiredAge={input.conjoint.ageRetraiteSouhaite ?? input.ageRetraiteSouhaite ?? null}
                onDesiredAge={(age) =>
                  patchInput({
                    conjoint: { ...input.conjoint, ageRetraiteSouhaite: age },
                  })
                }
              />
              <div className="max-w-sm space-y-2">
                <Label>Salaire brut annuel de l&apos;assuré 2 (CHF)</Label>
                <Input
                  type="number"
                  min={0}
                  value={input.salaireConjoint || ""}
                  onChange={(e) => patchInput({ salaireConjoint: Number(e.target.value) || 0 })}
                />
              </div>
            </div>
          )}
        </section>

        <section className="space-y-4 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-7">
          <div>
            <h2 className="font-heading text-lg font-semibold">Offres de rente</h2>
            <p className="text-sm text-muted-foreground">
              Rente certaine : la rente garantie est encaissée, elle n&apos;est pas imposable. L&apos;assiette est 0 % de la rente garantie + 100 % de la participation aux excédents, sans AVS ni LPP.
              L&apos;impôt sur la fortune part du capital, puis retire la rente garantie chaque année.
              Rente viagère : 4 % de la rente garantie + 70 % de la participation, sans calendrier de fortune.
            </p>
          </div>
          {rows.map((row, index) => (
            <div key={row.id} className="space-y-3 rounded-xl border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">Offre {index + 1}</p>
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={Boolean(row.recommander)}
                      data-testid={`comparatif-recommander-${row.id}`}
                      onChange={(e) =>
                        patchInput({
                          renteHypotheses: withSingleRecommander(rows, row.id, e.target.checked),
                        })
                      }
                    />
                    Recommander
                  </label>
                  <ConfirmDeleteButton
                    ariaLabel="Supprimer l'offre"
                    onConfirm={() =>
                      patchInput({ renteHypotheses: rows.filter((item) => item.id !== row.id) })
                    }
                  >
                    <Trash2 className="size-4" />
                  </ConfirmDeleteButton>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div className="space-y-1">
                  <Label className="text-xs">Type de rente</Label>
                  <select
                    className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
                    value={row.type}
                    data-testid={`comparatif-type-${row.id}`}
                    onChange={(e) =>
                      updateOffer(row.id, {
                        type: e.target.value,
                        dureeAnnees: e.target.value === "viagere" ? null : row.dureeAnnees ?? 20,
                      })
                    }
                  >
                    <option value="certaine">Rente certaine</option>
                    <option value="viagere">Rente viagère</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Nom de la compagnie</Label>
                  <Input
                    value={row.compagnie}
                    data-testid={`comparatif-compagnie-${row.id}`}
                    onChange={(e) => updateOffer(row.id, { compagnie: e.target.value })}
                  />
                  {compagnieEstPax(row.compagnie) ? (
                    <p className="text-xs text-muted-foreground">* {NOTE_PAX_DIFFERE}</p>
                  ) : null}
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Capital placé (CHF)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={row.capitalPlace || ""}
                    data-testid={`comparatif-capital-${row.id}`}
                    onChange={(e) => updateOffer(row.id, { capitalPlace: Number(e.target.value) || 0 })}
                  />
                </div>
                {row.type === "certaine" && (
                  <div className="space-y-1">
                    <Label className="text-xs">Durée (années)</Label>
                    <Input
                      type="number"
                      min={1}
                      value={row.dureeAnnees ?? ""}
                      data-testid={`comparatif-duree-${row.id}`}
                      onChange={(e) =>
                        updateOffer(row.id, {
                          dureeAnnees: e.target.value === "" ? null : Number(e.target.value) || null,
                        })
                      }
                    />
                  </div>
                )}
                <div className="space-y-1">
                  <Label className="text-xs">Rente garantie annuelle (CHF)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={row.renteGarantieAnnuelle || ""}
                    data-testid={`comparatif-rente-${row.id}`}
                    onChange={(e) =>
                      updateOffer(row.id, { renteGarantieAnnuelle: Number(e.target.value) || 0 })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Participation aux excédents annuelle (CHF)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={row.participationExcedentsAnnuelle || ""}
                    onChange={(e) =>
                      updateOffer(row.id, {
                        participationExcedentsAnnuelle: Number(e.target.value) || 0,
                      })
                    }
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                {row.type === "certaine"
                  ? "Revenu imposable de l'offre = 0 % de la rente garantie + 100 % de la participation. La rente garantie est encaissée, elle n'entre pas dans l'impôt. AVS, rente LPP ou autre revenu : seulement avec le bouton +."
                  : "Revenu imposable de l'offre = 4 % de la rente garantie + 70 % de la participation. AVS, rente LPP ou autre revenu : seulement avec le bouton +."}
              </p>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="comparatif-ajouter-offre"
            onClick={() => patchInput({ renteHypotheses: [...rows, emptyOffer()] })}
          >
            <Plus className="size-4" />
            Ajouter une offre
          </Button>
          <div className="space-y-3 border-t pt-4">
            <div>
              <h3 className="font-medium">Impôt sur le revenu</h3>
              <p className="text-sm text-muted-foreground">
                Ces montants s&apos;ajoutent à l&apos;assiette de chaque offre. Ils ne vont pas dans le rapport de planification.
              </p>
            </div>
            {(input.revenusAjoutesImpot || []).map((row) => (
              <div key={row.id} className="grid gap-3 sm:grid-cols-[180px_1fr_160px_auto] sm:items-end">
                <div className="space-y-1">
                  <Label className="text-xs">Revenu</Label>
                  <select
                    className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
                    value={row.kind}
                    data-testid={`comparatif-revenu-kind-${row.id}`}
                    onChange={(e) =>
                      patchInput({
                        revenusAjoutesImpot: (input.revenusAjoutesImpot || []).map((item) =>
                          item.id === row.id ? { ...item, kind: e.target.value } : item,
                        ),
                      })
                    }
                  >
                    <option value="avs">AVS</option>
                    <option value="lpp">Rente LPP</option>
                    <option value="autre">Autre revenu</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Libellé</Label>
                  <Input
                    value={row.libelle || ""}
                    disabled={row.kind !== "autre"}
                    placeholder={row.kind === "autre" ? "Ex. location" : row.kind === "lpp" ? "Rente LPP" : "AVS"}
                    onChange={(e) =>
                      patchInput({
                        revenusAjoutesImpot: (input.revenusAjoutesImpot || []).map((item) =>
                          item.id === row.id ? { ...item, libelle: e.target.value } : item,
                        ),
                      })
                    }
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Montant annuel (CHF)</Label>
                  <Input
                    type="number"
                    min={0}
                    value={row.montant || ""}
                    data-testid={`comparatif-revenu-montant-${row.id}`}
                    onChange={(e) =>
                      patchInput({
                        revenusAjoutesImpot: (input.revenusAjoutesImpot || []).map((item) =>
                          item.id === row.id ? { ...item, montant: Number(e.target.value) || 0 } : item,
                        ),
                      })
                    }
                  />
                </div>
                <ConfirmDeleteButton
                  ariaLabel="Retirer ce revenu"
                  onConfirm={() =>
                    patchInput({
                      revenusAjoutesImpot: (input.revenusAjoutesImpot || []).filter((item) => item.id !== row.id),
                    })
                  }
                >
                  <Trash2 className="size-4" />
                </ConfirmDeleteButton>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              data-testid="comparatif-ajouter-revenu"
              onClick={() =>
                patchInput({
                  revenusAjoutesImpot: [
                    ...(input.revenusAjoutesImpot || []),
                    {
                      id: `revenu-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                      kind: "avs",
                      libelle: "",
                      montant: 0,
                    },
                  ],
                })
              }
            >
              <Plus className="size-4" />
              Ajouter AVS, rente LPP ou autre revenu
            </Button>
          </div>
        </section>

        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={saveDraft} disabled={pending}>
              Enregistrer la saisie
            </Button>
            <Button
              type="button"
              className="bg-[#002FA7] hover:bg-[#00248a]"
              onClick={calculate}
              disabled={pending || !input.taxLocationId || rows.length === 0}
              data-testid="comparatif-calculer"
            >
              {pending ? <Loader2 className="size-4 animate-spin" /> : null}
              Calculer le tableau
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={downloadPdf}
              disabled={pending || columns.length === 0}
              data-testid="comparatif-pdf"
            >
              <FileDown className="size-4" />
              Télécharger le PDF
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={integrateFolder}
              disabled={pending || !initialRecord.clientId || columns.length === 0}
              data-testid="comparatif-integrer-dossier"
            >
              Intégrer au dossier client
            </Button>
          </div>
          <label
            className="inline-flex items-center gap-2 rounded-lg border border-[#002FA7]/35 bg-[#002FA7]/5 px-3 py-2 text-sm font-medium text-slate-900"
            data-testid="comparatif-inclure-impot-fortune"
          >
            <input
              type="checkbox"
              className="size-4 accent-[#002FA7]"
              checked={inclureImpotFortune}
              onChange={(e) => setInclureImpotFortune(e.target.checked)}
            />
            Inclure l&apos;impôt sur la fortune
          </label>
        </div>
        {folderNote ? (
          <p className="text-sm text-[#255839]" data-testid="comparatif-dossier-note">{folderNote}</p>
        ) : null}

        {results?.avertissement ? (
          <Alert>
            <AlertTitle>Calcul partiel</AlertTitle>
            <AlertDescription>{results.avertissement}</AlertDescription>
          </Alert>
        ) : null}

        {results && columns.length === 0 && (
          <Alert>
            <AlertTitle>Aucune offre calculable</AlertTitle>
            <AlertDescription>
              Indiquez une compagnie, un capital ou une rente garantie pour afficher le tableau.
            </AlertDescription>
          </Alert>
        )}

        {columns.length > 0 && (
          <section className="space-y-3 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-6">
            <h2 className="text-lg font-semibold tracking-wide">COMPARATIF DES RENTES</h2>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-sm" data-testid="comparatif-rentes-table">
                <thead>
                  <tr>
                    <th className="w-[220px] border border-slate-200 bg-white" />
                    {columns.map((col) => (
                      <th
                        key={col.id}
                        className={`border px-3 py-3 text-center text-white ${col.recommander ? "bg-[#1f6b45]" : "bg-[#7B1E2B]"}`}
                      >
                        <div className="text-sm font-semibold uppercase">
                          {col.label}{compagnieEstPax(col.compagnie || col.label) ? " *" : ""}
                        </div>
                        <div className="mt-1 text-base">{money(col.capitalPlace)}</div>
                        <div className="text-xs font-normal opacity-90">
                          {col.typeLabel}{col.dureeAnnees ? ` · ${col.dureeAnnees} ans` : ""}
                        </div>
                        {col.recommander ? (
                          <div className="mt-1 text-[11px] font-semibold uppercase tracking-wide">Solution recommandée</div>
                        ) : null}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <SectionRow label="Répartition du capital" span={columns.length} />
                  <DataRow label="Capital affecté à la rente" columns={columns} cell={(col) => money(col.capitalPlace)} />
                  <SectionRow label="Caractéristiques" span={columns.length} />
                  <DataRow label="Type" columns={columns} cell={(col) => col.typeLabel} />
                  <DataRow
                    label="Durée"
                    columns={columns}
                    cell={(col) => (col.type === "viagere" ? "À vie" : col.dureeAnnees ? `${col.dureeAnnees} ans` : "—")}
                  />
                  <SectionRow label="Offre" span={columns.length} />
                  <DataRow label="Rente garantie" columns={columns} cell={(col) => money(col.renteGarantie)} />
                  <DataRow label="Participation aux excédents" columns={columns} cell={(col) => money(col.participationExcedents)} />
                  <SectionRow label="Fiscalité de l'offre" span={columns.length} />
                  <DataRow label="Part imposable" columns={columns} cell={(col) => money(col.partImposable)} />
                  {(results?.revenusAjoutes || []).map((revenu, index) => (
                    <DataRow
                      key={`${revenu.libelle}-${index}`}
                      label={revenu.libelle}
                      columns={columns}
                      cell={() => money(revenu.montant)}
                    />
                  ))}
                  <DataRow
                    label="Impôt de la rente (par an)"
                    columns={columns}
                    cell={(col) => money(col.impotRevenu)}
                  />
                  <SectionRow label="Revenus nets" span={columns.length} />
                  <DataRow
                    label="Revenu net"
                    columns={columns}
                    tone="net"
                    cell={(col) => money(col.revenuNet)}
                  />
                  {inclureImpotFortune ? (
                    <>
                      <DataRow
                        label={totalLabel}
                        columns={columns}
                        tone="net"
                        testId="comparatif-fortune-total"
                        cell={(col) => {
                          if (col.totalImpotFortune == null) return "—";
                          const amount = money(col.totalImpotFortune);
                          if (uniqueDurations.length !== 1 && col.dureeFortune) {
                            return `${amount} (sur ${col.dureeFortune} ans)`;
                          }
                          return amount;
                        }}
                      />
                      <DataRow
                        label="Impôt fortune si capital non affecté"
                        columns={columns}
                        testId="comparatif-fortune-non-affectee"
                        cell={(col) => money(col.impotFortuneSiNonAffecte)}
                      />
                    </>
                  ) : null}
                  <SectionRow label="Gain sur la durée" span={columns.length} />
                  <DataRow
                    label="Revenus nets cumulés"
                    columns={columns}
                    testId="comparatif-revenus-cumules"
                    cell={(col) => money(col.revenusNetsCumules)}
                  />
                  <DataRow
                    label="Capital initial investi"
                    columns={columns}
                    cell={(col) =>
                      col.dureeAnnees != null && col.dureeAnnees > 0
                        ? money(col.capitalPlace)
                        : "—"
                    }
                  />
                  <DataRow
                    label="Gain ou perte"
                    columns={columns}
                    tone="net"
                    testId="comparatif-gain-net"
                    cell={(col) => money(col.gainNet)}
                  />
                  {inclureImpotFortune ? (
                    <>
                      <SectionRow label="Détail de la fortune décroissante" span={columns.length} />
                      {yearCount === 0 ? (
                        <tr>
                          <td className="border border-slate-200 px-3 py-2 text-slate-600" colSpan={columns.length + 1}>
                            Rente viagère, ou rente certaine sans durée : pas de calendrier de fortune.
                          </td>
                        </tr>
                      ) : (
                        Array.from({ length: yearCount }, (_, index) => {
                          const annee = index + 1;
                          return (
                            <tr key={annee} data-testid={`comparatif-fortune-annee-${annee}`}>
                              <td className="border border-slate-200 px-3 py-2">Année {annee}</td>
                              {columns.map((col) => {
                                const row = col.fortuneAnnees?.find((item) => item.annee === annee);
                                const recommended = col.recommander ? "bg-emerald-50" : "";
                                return (
                                  <td key={col.id} className={`border border-slate-200 px-3 py-2 text-right tabular-nums ${recommended}`}>
                                    {row ? (
                                      <div>
                                        <div>{money(row.fortune)}</div>
                                        <div className="text-xs text-slate-600">
                                          impôt {money(row.impotFortune)}
                                        </div>
                                      </div>
                                    ) : "—"}
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })
                      )}
                    </>
                  ) : null}
                </tbody>
              </table>
            </div>
            {columns.some((col) => compagnieEstPax(col.compagnie || col.label)) ? (
              <p className="text-xs text-slate-600">* {NOTE_PAX_DIFFERE}</p>
            ) : null}
            <p className="text-xs text-slate-600">
              L&apos;impôt de la rente est annuel. Il n&apos;est pas multiplié par la durée.
              Les revenus ajoutés avec + (AVS, rente LPP, autre) entrent dans cet impôt.
              Gain ou perte = revenus nets cumulés − capital initial
              (le capital restant après rente garantie × durée, plancher 0, reste pris en compte dans le calcul sans être affiché).
              {inclureImpotFortune
                ? " Le total d'impôt sur la fortune est la somme des impôts sur le capital qui diminue chaque année de la rente garantie, sans descendre sous 0. L'impôt fortune si capital non affecté garde le capital constant : impôt d'une année × durée."
                : " Les lignes d'impôt sur la fortune sont masquées."}
              {" "}Sans durée, gain et impôts fortune restent vides.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}

function SectionRow({ label, span }: { label: string; span: number }) {
  return (
    <tr>
      <td className="border border-[#7B1E2B] bg-[#7B1E2B] px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-white" colSpan={span + 1}>
        {label}
      </td>
    </tr>
  );
}

function DataRow({
  label,
  columns,
  cell,
  tone = "plain",
  testId,
}: {
  label: string;
  columns: Array<{ id: string; recommander?: boolean }>;
  cell: (col: { id: string }) => string;
  tone?: "plain" | "net";
  testId?: string;
}) {
  const rowClass = tone === "net" ? "bg-slate-50 font-semibold" : "";
  return (
    <tr className={rowClass} data-testid={testId}>
      <td className="border border-slate-200 px-3 py-2">{label}</td>
      {columns.map((col) => (
        <td
          key={col.id}
          className={`border border-slate-200 px-3 py-2 text-right tabular-nums ${col.recommander ? "bg-emerald-50" : ""}`}
        >
          {cell(col)}
        </td>
      ))}
    </tr>
  );
}
