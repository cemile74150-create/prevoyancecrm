// @ts-nocheck
"use client";

import { useMemo, useState, useTransition } from "react";
import { Calculator, FileText, Loader2, RotateCcw } from "lucide-react";
import { CommuneSearch } from "@/analyse-prevoyance/components/CommuneSearch";
import { PersonIdentityFields } from "@/analyse-prevoyance/components/PersonIdentityFields";
import { AvsFields } from "@/analyse-prevoyance/components/AvsFields";
import { LppFields } from "@/analyse-prevoyance/components/LppFields";
import { ThirdPillarFields } from "@/analyse-prevoyance/components/ThirdPillarFields";
import { LibrePassageFields } from "@/analyse-prevoyance/components/LibrePassageFields";
import { RenteHypothesisFields } from "@/analyse-prevoyance/components/RenteHypothesisFields";
import { WithdrawalPlanningFields } from "@/analyse-prevoyance/components/WithdrawalPlanningFields";
import { ResultsPanel } from "@/analyse-prevoyance/components/ResultsPanel";
import { Alert, AlertDescription, AlertTitle } from "@/analyse-prevoyance/ui/alert";
import { buttonVariants } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/analyse-prevoyance/ui/select";
import { Separator } from "@/analyse-prevoyance/ui/separator";
import {
  emptyAnalyseInput,
  emptyPerson,
  type AnalyseInput,
  type AnalyseRecord,
  type EtatCivil,
  type TaxLocation,
} from "@/analyse-prevoyance/lib/types";
import { FERREYRES } from "@/analyse-prevoyance/lib/fixtures/ferreyres";
import { HELFER_EXCEL, helferAnalyseInput } from "@/analyse-prevoyance/lib/fixtures/helfer";
import { cn } from "@/analyse-prevoyance/utils";
import { analyseFetch, analyseUrl } from "@/analyse-prevoyance/api";

function sampleFerreyres(): AnalyseInput {
  const base = emptyAnalyseInput();
  return {
    ...base,
    villeRecherche: FERREYRES.ville,
    taxLocationId: FERREYRES.taxLocationId,
    taxGroupId: FERREYRES.taxLocationId,
    etatCivil: "Marié(e)",
    salaireClient1: 120_000,
    salaireConjoint: 40_000,
    fortune: FERREYRES.fortuneCouple1,
    autresRevenus: 0,
    conseillerNom: "Conseiller démo",
    client1: {
      ...emptyPerson("Monsieur"),
      nom: "Exemple",
      prenom: "Jean",
      dateNaissance: "1960-03-15",
      avsAnnuel: FERREYRES.revenues.avsClient1,
      avsMensuel: Math.round(FERREYRES.revenues.avsClient1 / 13),
      lpp: [
        { age: 65, capital: 1_081_456, rente: FERREYRES.revenues.lppClient1 },
        { age: 64, capital: 1_021_035, rente: 53_000 },
        { age: 63, capital: 955_233, rente: 48_700 },
        { age: 62, capital: 891_807, rente: 44_500 },
        { age: 61, capital: 830_667, rente: 40_700 },
        { age: 60, capital: 771_897, rente: 37_000 },
      ],
      troisiemePilier: [
        {
          id: "demo-3p",
          compagnie: "Generali",
          police: "3A-001",
          echeance: "2025-12-31",
          montant: 170_000,
          prime: 6_883,
        },
      ],
    },
    conjoint: {
      ...emptyPerson("Madame"),
      nom: "Exemple",
      prenom: "Marie",
      dateNaissance: "1962-07-20",
      avsAnnuel: FERREYRES.revenues.avsConjoint,
      avsMensuel: Math.round(FERREYRES.revenues.avsConjoint / 13),
      lpp: [
        { age: 65, capital: 0, rente: 0 },
        { age: 64, capital: 0, rente: 0 },
        { age: 63, capital: 0, rente: 0 },
        { age: 62, capital: 0, rente: 0 },
        { age: 61, capital: 0, rente: 0 },
        { age: 60, capital: 0, rente: 0 },
      ],
      troisiemePilier: [],
    },
  };
}

function payloadFrom(source: AnalyseInput) {
  return {
    ...source,
    conjoint:
      source.etatCivil === "Marié(e)"
        ? source.conjoint ?? emptyPerson("Madame")
        : null,
  };
}

function Section({
  title,
  children,
  hint,
}: {
  title: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-heading text-lg font-semibold tracking-tight">
          {title}
        </h2>
        {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

export function AnalysePrevoyanceApp({
  initialRecord = null,
  linkedClientId = null,
  onSaved,
}: {
  /** Réouverture d’une analyse enregistrée. */
  initialRecord?: AnalyseRecord | null;
  /** clientId LeoSoft lié à la sauvegarde. */
  linkedClientId?: string | null;
  onSaved?: () => void;
}) {
  const [input, setInput] = useState<AnalyseInput>(
    () => initialRecord?.input ?? emptyAnalyseInput(),
  );
  const [record, setRecord] = useState<AnalyseRecord | null>(
    () => initialRecord,
  );
  const [error, setError] = useState<string | null>(null);
  const [calculatedSnapshot, setCalculatedSnapshot] = useState<string | null>(
    () =>
      initialRecord?.results
        ? JSON.stringify(payloadFrom(initialRecord.input))
        : null,
  );
  const [pending, startTransition] = useTransition();
  const clientId = linkedClientId ?? record?.clientId ?? null;

  const isMarried = input.etatCivil === "Marié(e)";
  const showAssure2 = isMarried || Boolean(input.conjoint);
  const assure2Person =
    input.conjoint ??
    emptyPerson(input.client1.civilite === "Madame" ? "Monsieur" : "Madame");

  const canCalculate = useMemo(() => {
    return (
      !!input.client1.dateNaissance &&
      !!input.villeRecherche.trim() &&
      input.taxLocationId != null
    );
  }, [input]);

  function patchInput(partial: Partial<AnalyseInput>) {
    setInput((prev) => ({ ...prev, ...partial }));
  }

  function onEtatCivil(v: EtatCivil) {
    if (v === "Marié(e)") {
      patchInput({
        etatCivil: v,
        conjoint: input.conjoint ?? emptyPerson("Madame"),
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

  function reset() {
    setInput(emptyAnalyseInput());
    setError(null);
  }

  function loadSample() {
    setInput(sampleFerreyres());
    setError(null);
  }

  function loadHelfer() {
    setInput(helferAnalyseInput());
    setError(null);
  }

  async function saveDraft() {
    const id = record?.id;
    if (!id) {
      setError("Analyse non enregistrée");
      return;
    }
    setError(null);
    try {
      const res = await analyseFetch(`/${id}`, {
        method: "PUT",
        body: JSON.stringify({
          input,
          status: record.status === "annulee"
            ? "annulee"
            : (record?.results ? record.status : "brouillon"),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || "Enregistrement impossible");
        return;
      }
      setRecord(data);
      onSaved?.();
    } catch {
      setError("Erreur réseau pendant l'enregistrement");
    }
  }

  async function saveToClientFolder() {
    const id = record?.id;
    if (!id || !record?.results) {
      setError("Calculez l'analyse avant de l'enregistrer dans le dossier client.");
      return;
    }
    if (!resultsAreCurrent()) {
      setError(
        "Les données ont changé depuis le dernier calcul. Recalculez avant d'enregistrer le PDF.",
      );
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const res = await analyseFetch(`/${id}/enregistrer-dossier`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) {
          setError(data.detail || "Enregistrement dans le dossier impossible");
          return;
        }
        setRecord((prev) => prev ? { ...prev, status: "finalisee", documentId: data.documentId } : prev);
        onSaved?.();
      } catch {
        setError("Erreur réseau pendant l'enregistrement du PDF");
      }
    });
  }

  function calculate() {
    setError(null);
    startTransition(async () => {
      try {
        const payload = payloadFrom(input);
        const id = record?.id;
        if (!id) {
          setError("Analyse non enregistrée");
          return;
        }
        const res = await analyseFetch(`/${id}/calculate`, {
          method: "POST",
          body: JSON.stringify({ input: payload }),
        });
        const data = await res.json();
        if (!res.ok) {
          setError(data.detail || data.error || "Échec du calcul");
          return;
        }
        setRecord(data);
        setInput(data.input);
        setCalculatedSnapshot(JSON.stringify(payloadFrom(data.input)));
        onSaved?.();
        requestAnimationFrame(() => {
          document.getElementById("resultats")?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        });
      } catch {
        setError("Erreur réseau pendant le calcul ESTV");
      }
    });
  }

  function resultsAreCurrent() {
    if (!record?.results || !calculatedSnapshot) return false;
    return JSON.stringify(payloadFrom(input)) === calculatedSnapshot;
  }

  function createPdf() {
    if (!record?.id || !record?.results) {
      setError("Calculez l'analyse avant de générer le PDF.");
      return;
    }
    if (!resultsAreCurrent()) {
      setError(
        "Les données ont changé depuis le dernier calcul. Recalculez avant de générer le PDF.",
      );
      return;
    }
    setError(null);
    window.open(analyseUrl(`/${record.id}/pdf`), "_blank", "noopener");
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8 space-y-3">
        <p className="text-sm font-medium tracking-[0.12em] text-[var(--ap-accent)] uppercase">
          LeoSoft · Effectuer une analyse
        </p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Analyse de prévoyance
        </h1>
        <p className="max-w-2xl text-muted-foreground">
          Saisie conseiller → calculs AVS / LPP / 3e pilier → impôts ESTV →
          scénarios, frise, planif retraits, rapport PDF.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap gap-2">
        <button
          type="button"
          className={cn(buttonVariants({ variant: "outline" }))}
          onClick={saveDraft}
          disabled={pending || !record?.id}
        >
          Enregistrer le brouillon
        </button>
        <button
          type="button"
          className={cn(buttonVariants({ variant: "secondary" }))}
          onClick={saveToClientFolder}
          disabled={pending || !record?.results || !clientId}
        >
          Enregistrer dans le dossier client
        </button>
        <button
          type="button"
          className={cn(buttonVariants({ variant: "outline" }))}
          onClick={loadSample}
          disabled={pending}
        >
          Charger l&apos;exemple Ferreyres
        </button>
        <button
          type="button"
          className={cn(buttonVariants({ variant: "outline" }))}
          onClick={loadHelfer}
          disabled={pending}
          title={`${HELFER_EXCEL.ville} · LP ${HELFER_EXCEL.conjoint.librePassage}`}
        >
          Charger HELFER
        </button>
        <button
          type="button"
          className={cn(buttonVariants({ variant: "ghost" }))}
          onClick={reset}
          disabled={pending}
        >
          <RotateCcw className="size-4" />
          Réinitialiser
        </button>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!canCalculate && (
        <Alert className="mb-6">
          <AlertTitle>Prêt à calculer ?</AlertTitle>
          <AlertDescription>
            Renseignez au minimum la date de naissance du client et
            sélectionnez une commune fiscale (TaxLocationID).
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-8 rounded-xl border bg-card/80 p-4 shadow-sm sm:p-6">
        <Section
          title="1. Client"
          hint="Identité, commune fiscale et état civil du foyer."
        >
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
              <Select
                value={input.etatCivil}
                onValueChange={(v) => onEtatCivil(v as EtatCivil)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Personne vivant seule">
                    Personne vivant seule
                  </SelectItem>
                  <SelectItem value="Marié(e)">Marié(e)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Conseiller</Label>
              <Input
                value={input.conseillerNom || ""}
                onChange={(e) => patchInput({ conseillerNom: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Âge de retraite souhaité</Label>
              <select
                className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
                value={input.ageRetraiteSouhaite ?? ""}
                onChange={(e) =>
                  patchInput({
                    ageRetraiteSouhaite:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              >
                <option value="">Âge applicable au dossier</option>
                {[65, 64, 63, 62, 61, 60].map((age) => (
                  <option key={age} value={age}>
                    {age} ans
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Âge de fin d'activité</Label>
              <Input
                type="number"
                min={50}
                max={70}
                placeholder="distinct"
                value={input.ageFinActivite ?? ""}
                onChange={(e) =>
                  patchInput({
                    ageFinActivite: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Âge de perception AVS</Label>
              <Input
                type="number"
                min={50}
                max={70}
                placeholder="distinct"
                value={input.agePerceptionAvs ?? ""}
                onChange={(e) =>
                  patchInput({
                    agePerceptionAvs: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Âge de retrait LPP</Label>
              <Input
                type="number"
                min={50}
                max={70}
                placeholder="distinct"
                value={input.ageRetraitLpp ?? ""}
                onChange={(e) =>
                  patchInput({
                    ageRetraitLpp: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </div>
          </div>
          <PersonIdentityFields
            person={input.client1}
            onChange={(p) => patchInput({ client1: p })}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Salaire brut annuel (CHF)</Label>
              <Input
                type="number"
                min={0}
                value={input.salaireClient1 || ""}
                onChange={(e) =>
                  patchInput({ salaireClient1: Number(e.target.value) || 0 })
                }
              />
            </div>
          </div>
        </Section>

        {isMarried && input.conjoint && (
          <>
            <Separator />
            <Section title="2. Assuré 2">
              <PersonIdentityFields
                person={input.conjoint}
                onChange={(p) => patchInput({ conjoint: p })}
              />
              <div className="max-w-sm space-y-2">
                <Label>Salaire brut annuel de l'assuré 2 (CHF)</Label>
                <Input
                  type="number"
                  min={0}
                  value={input.salaireConjoint || ""}
                  onChange={(e) =>
                    patchInput({
                      salaireConjoint: Number(e.target.value) || 0,
                    })
                  }
                />
              </div>
            </Section>
          </>
        )}

        <Separator />
        <Section
          title={isMarried ? "3. AVS" : "2. AVS"}
          hint="Saisissez le mensuel : l’annuel est calculé × 13 (sauf si annuel forcé)."
        >
          <AvsFields
            title="Assuré 1"
            person={input.client1}
            onChange={(p) => patchInput({ client1: p })}
          />
          {isMarried && input.conjoint && (
            <AvsFields
              title="Assuré 2"
              person={input.conjoint}
              onChange={(p) => patchInput({ conjoint: p })}
            />
          )}
        </Section>

        <Separator />
        <Section
          title={isMarried ? "4. LPP" : "3. LPP"}
          hint="Capital, rente annuelle par âge, et % déblocable en capital (paramétrable)."
        >
          <LppFields
            title="Assuré 1"
            person={input.client1}
            onChange={(p) => patchInput({ client1: p })}
          />
          {isMarried && input.conjoint && (
            <LppFields
              title="Assuré 2"
              person={input.conjoint}
              showRentePont
              onChange={(p) => patchInput({ conjoint: p })}
            />
          )}
        </Section>

        <Separator />
        <Section
          title={isMarried ? "5. 3e piliers" : "4. 3e piliers"}
          hint="Jusqu’à 4 contrats par personne — ajout / suppression."
        >
          <div className="space-y-4">
            <ThirdPillarFields
              title="Assuré 1"
              person={input.client1}
              onChange={(p) => patchInput({ client1: p })}
            />
            {showAssure2 && (
              <ThirdPillarFields
                title="Assuré 2"
                person={assure2Person}
                onChange={(p) => patchInput({ conjoint: p })}
              />
            )}
          </div>
        </Section>

        <Separator />
        <Section
          title={isMarried ? "6. Libres passages" : "5. Libres passages"}
          hint="0..N avoirs — montant retiré = montant × % / 100 (impôt sur le retiré uniquement)."
        >
          <LibrePassageFields
            input={input}
            onChange={(libresPassages) => patchInput({ libresPassages })}
          />
        </Section>

        <Separator />
        <Section
          title={
            isMarried
              ? "7. Planification des retraits / Fiscalité"
              : "6. Planification des retraits / Fiscalité"
          }
          hint="LPP, libres passages, 3e piliers — scénarios A regroupé / B réparti / C perso. Agrégation ESTV : personne + année."
        >
          <WithdrawalPlanningFields
            input={input}
            onChange={(withdrawalScenarios) =>
              patchInput({ withdrawalScenarios })
            }
            previewBasics={
              record?.results
                ? {
                    client1: record.results.client1,
                    conjoint: record.results.conjoint,
                  }
                : null
            }
            planningResults={record?.results?.withdrawalPlanning?.scenarios}
            onRecalculate={calculate}
            recalculatePending={pending}
          />
        </Section>

        <Separator />
        <Section
          title={
            isMarried
              ? "8. Fortune / autres revenus"
              : "7. Fortune / autres revenus"
          }
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label>Fortune fiscale (CHF)</Label>
              <Input
                type="number"
                min={0}
                value={input.fortune || ""}
                onChange={(e) =>
                  patchInput({ fortune: Number(e.target.value) || 0 })
                }
              />
              <p className="text-xs text-muted-foreground">
                Excel Couple1 : fortune vide → 0. Couple4 force 0.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Autres revenus annuels (CHF)</Label>
              <Input
                type="number"
                min={0}
                value={input.autresRevenus || ""}
                onChange={(e) =>
                  patchInput({ autresRevenus: Number(e.target.value) || 0 })
                }
              />
            </div>
          </div>
        </Section>

        <Separator />
        <Section
          title={
            isMarried
              ? "9. Hypothèses de rente"
              : "8. Hypothèses de rente"
          }
          hint="Offres saisies à la main. L'âge de retraite choisi en tête du dossier alimente l'AVS et la rente LPP de référence."
        >
          <div className="mb-4 max-w-xs space-y-2">
            <Label>Année fiscale ESTV</Label>
            <Input
              type="number"
              value={input.taxYear}
              onChange={(e) =>
                patchInput({ taxYear: Number(e.target.value) || 2025 })
              }
            />
          </div>
          <RenteHypothesisFields input={input} onChange={patchInput} />
        </Section>
      </div>

      <div
        id="actions-calcul-pdf"
        className="mt-8 flex flex-wrap items-center gap-3 border-t border-border pt-6"
      >
        <button
          type="button"
          className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-[#002FA7] px-6 text-base font-semibold text-white hover:bg-[#00248a] disabled:opacity-50"
          onClick={calculate}
          disabled={pending || !canCalculate}
        >
          {pending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Calculator className="size-4" />
          )}
          {pending ? "Calcul ESTV en cours…" : "Calculer"}
        </button>
        <button
          type="button"
          className="inline-flex h-12 items-center justify-center gap-2 rounded-md border-2 border-[#002FA7] bg-white px-6 text-base font-semibold text-[#002FA7] hover:bg-[#002FA7]/5 disabled:opacity-50"
          onClick={createPdf}
          disabled={pending || !record?.results}
        >
          <FileText className="size-4" />
          Générer le PDF
        </button>
      </div>

      <div className="mt-10">
        <ResultsPanel record={record} />
      </div>
    </div>
  );
}
