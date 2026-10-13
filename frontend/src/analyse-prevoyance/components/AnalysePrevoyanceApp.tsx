// @ts-nocheck
"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";
import { Calculator, ChevronLeft, ChevronRight, FileText, Loader2, RotateCcw } from "lucide-react";
import { CommuneSearch } from "@/analyse-prevoyance/components/CommuneSearch";
import { PersonIdentityFields } from "@/analyse-prevoyance/components/PersonIdentityFields";
import { AvsFields } from "@/analyse-prevoyance/components/AvsFields";
import { LppFields } from "@/analyse-prevoyance/components/LppFields";
import { ThirdPillarFields } from "@/analyse-prevoyance/components/ThirdPillarFields";
import { LibrePassageFields } from "@/analyse-prevoyance/components/LibrePassageFields";
import { RenteHypothesisFields } from "@/analyse-prevoyance/components/RenteHypothesisFields";
import { WithdrawalPlanningFields } from "@/analyse-prevoyance/components/WithdrawalPlanningFields";
import { ResultsPanel } from "@/analyse-prevoyance/components/ResultsPanel";
import { FiscalUpdateAlert } from "@/analyse-prevoyance/components/FiscalUpdateAlert";
import { AnalyseWizardNav } from "@/analyse-prevoyance/components/AnalyseWizardNav";
import { AnalyseDossierRecap } from "@/analyse-prevoyance/components/AnalyseDossierRecap";
import {
  ANALYSE_STEPS,
  adjacentStep,
  autosaveLabel,
  buildDossierRecap,
  isStepComplete,
  type AnalyseStepId,
  type AutosavePhase,
} from "@/analyse-prevoyance/lib/analyseWizard";
import { avsAnnuelFromMensuel } from "@/analyse-prevoyance/lib/avsAnnuel";
import {
  PDF_POPUP_BLOCKED,
  openAnalysePdfWindow,
  planAnalysePdf,
} from "@/analyse-prevoyance/lib/analysePdfAction";
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

function withMonthlyAvs(person) {
  if (!person) return person;
  const mensuel = Number(person.avsMensuel) || 0;
  if (mensuel > 0) {
    return { ...person, avsAnnuel: avsAnnuelFromMensuel(mensuel) };
  }
  return person;
}

const AUTOSAVE_DELAY_MS = 1200;

function fingerprintInput(source: AnalyseInput) {
  return JSON.stringify(payloadFrom(source));
}

function statusForSave(record: AnalyseRecord | null) {
  if (record?.status === "annulee") return "annulee";
  if (record?.results) return record.status;
  return "brouillon";
}

function payloadFrom(source: AnalyseInput) {
  const client1 = withMonthlyAvs(source.client1);
  const married = source.etatCivil === "Marié(e)";
  const conjointSource = married ? source.conjoint ?? emptyPerson("Madame") : null;
  const conjoint = conjointSource ? withMonthlyAvs(conjointSource) : null;
  const age1 = client1?.ageRetraiteSouhaite ?? source.ageRetraiteSouhaite ?? null;
  return {
    ...source,
    client1: { ...client1, ageRetraiteSouhaite: age1 },
    ageRetraiteSouhaite: age1,
    conjoint: conjoint
      ? {
          ...conjoint,
          ageRetraiteSouhaite:
            conjoint.ageRetraiteSouhaite ?? source.ageRetraiteSouhaite ?? null,
        }
      : null,
    libresPassages: (source.libresPassages || []).map((lp) => ({
      ...lp,
      pctRetire: 100,
    })),
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
  const [autosavePhase, setAutosavePhase] = useState<AutosavePhase>("idle");
  const [pdfHint, setPdfHint] = useState("");
  const [stepId, setStepId] = useState<AnalyseStepId>("client");
  const clientId = linkedClientId ?? record?.clientId ?? null;
  const inputRef = useRef(input);
  const recordRef = useRef(record);
  const onSavedRef = useRef(onSaved);
  inputRef.current = input;
  recordRef.current = record;
  onSavedRef.current = onSaved;
  const savedFpRef = useRef(fingerprintInput(initialRecord?.input ?? emptyAnalyseInput()));
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chainRef = useRef(Promise.resolve());
  const enqueueRef = useRef((job: () => Promise<unknown>) => {
    const next = chainRef.current.then(job, job);
    chainRef.current = next.then(
      () => undefined,
      () => undefined,
    );
    return next;
  });
  const persistRef = useRef<(opts: { autosave: boolean }) => Promise<boolean>>(
    async () => false,
  );

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

  async function persist({ autosave }: { autosave: boolean }) {
    const current = recordRef.current;
    if (!current?.id) {
      if (!autosave) setError("Analyse non enregistrée");
      return false;
    }
    const bodyInput = payloadFrom(inputRef.current);
    const fp = JSON.stringify(bodyInput);
    if (autosave && fp === savedFpRef.current) return true;
    if (!autosave) setError(null);
    if (autosave) setAutosavePhase("saving");
    try {
      const res = await analyseFetch(`/${current.id}`, {
        method: "PUT",
        body: JSON.stringify(
          autosave
            ? { input: bodyInput, autosave: true }
            : { input: bodyInput, status: statusForSave(current) },
        ),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "";
        if (autosave) setAutosavePhase("error");
        else setError(detail || "Enregistrement impossible");
        return false;
      }
      savedFpRef.current = fp;
      setRecord(data);
      if (autosave) setAutosavePhase("saved");
      else onSavedRef.current?.();
      return true;
    } catch {
      if (autosave) setAutosavePhase("error");
      else setError("Erreur réseau pendant l'enregistrement");
      return false;
    }
  }
  persistRef.current = persist;

  function saveDraft() {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    return enqueueRef.current(() => persistRef.current({ autosave: false }));
  }

  useEffect(() => {
    if (!record?.id || pending) return undefined;
    const fp = fingerprintInput(input);
    if (fp === savedFpRef.current) return undefined;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void enqueueRef.current(() => persistRef.current({ autosave: true }));
    }, AUTOSAVE_DELAY_MS);
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [input, record?.id, pending]);

  useEffect(() => {
    const flush = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (!recordRef.current?.id) return;
      if (fingerprintInput(inputRef.current) === savedFpRef.current) return;
      void enqueueRef.current(() => persistRef.current({ autosave: true }));
    };
    const onHide = () => {
      if (document.visibilityState === "hidden") flush();
    };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("pagehide", flush);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, []);

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
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    startTransition(async () => {
      try {
        await chainRef.current;
        const payload = payloadFrom(inputRef.current);
        const id = recordRef.current?.id;
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
        savedFpRef.current = fingerprintInput(data.input);
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
        setError("Erreur réseau pendant le calcul");
      }
    });
  }

  function resultsAreCurrent() {
    if (!record?.results || !calculatedSnapshot) return false;
    return JSON.stringify(payloadFrom(input)) === calculatedSnapshot;
  }

  function createPdf() {
    const plan = planAnalysePdf({
      hasId: Boolean(record?.id),
      hasResults: Boolean(record?.results),
      isCurrent: resultsAreCurrent(),
    });
    if (!plan.allow) {
      setPdfHint("");
      setError(plan.message);
      return;
    }
    setError(null);
    setPdfHint(plan.message || "");
    const opened = openAnalysePdfWindow(
      (...args) => window.open(...args),
      analyseUrl(`/${record.id}/pdf`),
    );
    if (!opened) setError(PDF_POPUP_BLOCKED);
  }

  const completed = useMemo(() => {
    const map = {};
    for (const step of ANALYSE_STEPS) {
      map[step.id] = isStepComplete(step.id, input);
    }
    return map;
  }, [input]);

  const recap = useMemo(
    () =>
      buildDossierRecap(
        input,
        record,
        autosavePhase,
        record?.results?.taxLocation?.Canton,
      ),
    [input, record, autosavePhase],
  );

  const stepMeta = ANALYSE_STEPS.find((s) => s.id === stepId) || ANALYSE_STEPS[0];
  const autosaveHint = autosaveLabel(autosavePhase);

  function renderActiveSection() {
    switch (stepId) {
      case "client":
        return (
          <Section
            title="1. Client"
            hint="Identité, commune fiscale et état civil du foyer."
          >
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
            </div>
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
        );
      case "assure2":
        return (
          <Section
            title="2. Assuré 2"
            hint="Identité et âge de retraite souhaité du conjoint. Visible pour les couples."
          >
            {isMarried && input.conjoint ? (
              <>
                <PersonIdentityFields
                  person={input.conjoint}
                  onChange={(p) => patchInput({ conjoint: p })}
                  desiredAge={
                    input.conjoint.ageRetraiteSouhaite ?? input.ageRetraiteSouhaite ?? null
                  }
                  onDesiredAge={(age) =>
                    patchInput({
                      conjoint: { ...input.conjoint, ageRetraiteSouhaite: age },
                    })
                  }
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
              </>
            ) : (
              <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
                Choisissez l&apos;état civil « Marié(e) » à l&apos;étape Client
                pour saisir l&apos;assuré 2. Les autres étapes restent
                accessibles.
              </p>
            )}
          </Section>
        );
      case "avs":
        return (
          <Section
            title="3. AVS"
            hint="Saisissez la rente mensuelle. L’annuelle s’affiche tout de suite : mensuelle × 13."
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
        );
      case "lpp":
        return (
          <Section
            title="4. LPP"
            hint="Capital, rente annuelle par âge, et % LPP disponible."
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
        );
      case "piliers3":
        return (
          <Section
            title="5. 3e piliers"
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
        );
      case "libresPassages":
        return (
          <Section
            title="6. Libres passages"
            hint="0..N avoirs — montant retiré = montant × % / 100 (impôt sur le retiré uniquement). % disponible fixé à 100 %."
          >
            <LibrePassageFields
              input={input}
              onChange={(libresPassages) => patchInput({ libresPassages })}
            />
          </Section>
        );
      case "retraits":
        return (
          <Section
            title="7. Retraits / Fiscalité"
            hint="LPP, libres passages, 3e piliers — scénarios A regroupé / B réparti / C perso. Année prévue en lecture seule, 1re possible saisie. Agrégation fiscale : personne + année."
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
        );
      case "fortune":
        return (
          <Section title="8. Fortune / autres revenus">
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
        );
      case "hypotheses":
        return (
          <Section
            title="9. Hypothèses de rente"
            hint="Offres saisies à la main. Cochez « Inclure / Recommander » pour le cadre vert du PDF. L'âge de retraite souhaité de chaque assuré alimente l'AVS et la rente LPP de référence."
          >
            <RenteHypothesisFields input={input} onChange={patchInput} />
          </Section>
        );
      default:
        return null;
    }
  }

  return (
    <div className="mx-auto max-w-[1680px] px-4 pt-3 pb-8 sm:px-6 lg:px-8 [&_.rounded-md.border]:rounded-xl">
      <header className="mb-6 space-y-2">
        <p className="text-sm font-medium tracking-[0.12em] text-[var(--ap-accent)] uppercase">
          LeoSoft · Effectuer une analyse
        </p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Analyse de prévoyance
        </h1>
        <p className="max-w-2xl text-muted-foreground">
          Saisie conseiller → calculs AVS / LPP / 3e pilier → impôts →
          scénarios, frise, planif retraits, rapport PDF.
        </p>
      </header>
      <FiscalUpdateAlert />

      <div className="mb-6 flex flex-wrap gap-2">
        <button
          type="button"
          className={cn(buttonVariants({ variant: "outline" }))}
          onClick={saveDraft}
          disabled={pending || !record?.id}
        >
          Enregistrer le brouillon
        </button>
        {autosaveHint ? (
          <span className="self-center text-sm text-muted-foreground" data-testid="analyse-autosave-status">
            {autosaveHint}
          </span>
        ) : null}
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

      <div className="grid items-start gap-4 lg:grid-cols-[240px_minmax(0,1fr)_280px]">
        <AnalyseWizardNav
          activeId={stepId}
          completed={completed}
          onSelect={setStepId}
        />

        <div className="space-y-4">
          <div
            className="space-y-6 rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm sm:p-7"
            data-testid={`analyse-step-panel-${stepId}`}
          >
            {renderActiveSection()}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white px-4 py-3 shadow-sm">
            <button
              type="button"
              className={cn(buttonVariants({ variant: "outline" }))}
              onClick={() => setStepId(adjacentStep(stepId, -1))}
              disabled={stepId === "client"}
              data-testid="analyse-step-prev"
            >
              <ChevronLeft className="size-4" />
              Précédent
            </button>
            <p className="text-xs text-slate-500">
              Étape {stepMeta.n} / {ANALYSE_STEPS.length}
            </p>
            <button
              type="button"
              className={cn(buttonVariants({ variant: "outline" }))}
              onClick={() => setStepId(adjacentStep(stepId, 1))}
              disabled={stepId === "hypotheses"}
              data-testid="analyse-step-next"
            >
              Suivant
              <ChevronRight className="size-4" />
            </button>
          </div>

          <div id="actions-calcul-pdf" className="space-y-3 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm">
            {pdfHint ? (
              <p className="text-sm text-amber-800" data-testid="analyse-pdf-hint">
                {pdfHint}
              </p>
            ) : null}
            <div className="flex flex-wrap items-center gap-3">
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
                {pending ? "Calcul en cours…" : "Calculer"}
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
          </div>

        </div>

        <AnalyseDossierRecap recap={recap} />
      </div>

      <div className="mt-10">
        <ResultsPanel record={record} />
      </div>
    </div>
  );
}
