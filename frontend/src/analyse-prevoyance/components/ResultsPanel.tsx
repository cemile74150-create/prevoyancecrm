// @ts-nocheck
"use client";

import { AlertCircle, FileText } from "lucide-react";
import { analyseFetch, analyseUrl } from "@/analyse-prevoyance/api";
import { Alert, AlertDescription, AlertTitle } from "@/analyse-prevoyance/ui/alert";
import { Badge } from "@/analyse-prevoyance/ui/badge";
import { buttonVariants } from "@/analyse-prevoyance/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/analyse-prevoyance/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/analyse-prevoyance/ui/table";
import { formatChf, formatPct } from "@/analyse-prevoyance/lib/mappers";
import type { AnalyseRecord } from "@/analyse-prevoyance/lib/types";

interface Props {
  record: AnalyseRecord | null;
}

export function ResultsPanel({ record }: Props) {
  if (!record?.results) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Synthèse des résultats</CardTitle>
          <CardDescription>
            Après « Calculer », la situation, les impôts, la lacune et les
            scénarios 60–65 s’affichent ici.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Aucun résultat pour le moment.
          </p>
        </CardContent>
      </Card>
    );
  }

  const { results, id, input } = record;
  const r1 = results.client1;
  const r2 = results.conjoint;
  const couple1 = results.incomeScenarios.find((s) => s.foyer === "Couple1");
  const cap65 = results.capitalScenarios.find((s) => s.age === 65);

  return (
    <div className="space-y-6" id="resultats">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-heading text-xl font-semibold tracking-tight">
            Synthèse des résultats
          </h2>
          <p className="text-sm text-muted-foreground">
            Calculé le{" "}
            {new Date(results.computedAt).toLocaleString("fr-CH")}
            {results.taxLocation && (
              <> · TaxLocationID {results.taxLocation.TaxLocationID}</>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={analyseUrl(`/${id}/report`)}
            target="_blank"
            rel="noreferrer"
            className={buttonVariants({ variant: "outline" })}
          >
            <FileText className="size-4" />
            Prévisualiser le rapport
          </a>
        </div>
      </div>

      {results.errors.length > 0 && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertTitle>Alertes</AlertTitle>
          <AlertDescription>
            <ul className="mt-1 list-disc pl-4 text-sm">
              {results.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* Situation actuelle */}
      <Card className="border-[var(--ap-accent)]/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Situation actuelle</CardTitle>
          <CardDescription>
            {input.villeRecherche || "—"} · {input.etatCivil}
            {input.conseillerNom ? ` · ${input.conseillerNom}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Info
            label="Assuré 1"
            value={`${input.client1.prenom} ${input.client1.nom}`.trim() || "—"}
          />
          {r2 && (
            <Info
              label="Assuré 2"
              value={
                `${input.conjoint?.prenom || ""} ${input.conjoint?.nom || ""}`.trim() ||
                "—"
              }
            />
          )}
          <Info label="Revenu avant retraite" value={formatChf(results.lacune.salaireAvant)} />
          <Info label="Fortune fiscale" value={formatChf(input.fortune)} />
        </CardContent>
      </Card>

      {/* Âge / date retraite */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Âge légal & date de retraite</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead></TableHead>
                <TableHead>Assuré 1</TableHead>
                {r2 && <TableHead>Assuré 2</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>Âge légal AVS</TableCell>
                <TableCell>
                  <Badge variant="secondary">{r1.ageLegalLabel}</Badge>
                </TableCell>
                {r2 && (
                  <TableCell>
                    <Badge variant="secondary">{r2.ageLegalLabel}</Badge>
                  </TableCell>
                )}
              </TableRow>
              <TableRow>
                <TableCell>Date de départ</TableCell>
                <TableCell>{r1.dateDepart}</TableCell>
                {r2 && <TableCell>{r2.dateDepart}</TableCell>}
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* KPI */}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard title="AVS annuel" value={formatChf(r1.avsAnnuel)} hint={r2 ? `Assuré 2 : ${formatChf(r2.avsAnnuel)}` : undefined} />
        <MetricCard
          title="Rente LPP 65"
          value={formatChf(r1.renteLpp65)}
          hint={`Capital ${formatChf(r1.capitalLpp65)} · disponible ${r1.lppPctDeblocable} % → retiré ${formatChf(r1.capitalLppRetire65)}`}
        />
        <MetricCard
          title="Revenu après retraite"
          value={formatChf(results.lacune.revenuApres)}
          hint="AVS + LPP 65 (foyer)"
        />
        <MetricCard
          title="Impôt sur le capital"
          value={formatChf(results.capitalPathFoyer?.impot ?? cap65?.impot)}
          hint={`Retiré ${formatChf(results.capitalPathFoyer?.capitalRetireTotal ?? cap65?.capital)} · net ${formatChf(results.capitalPathFoyer?.net ?? cap65?.net)}`}
        />
        <MetricCard
          title="Impôt revenu Couple1"
          value={formatChf(couple1?.impot?.impotRevenuTotal)}
          hint={
            couple1?.impot
              ? `IFD ${formatChf(couple1.impot.impotFederal)} · Canton ${formatChf(couple1.impot.impotCanton)} · Commune ${formatChf(couple1.impot.impotCommune)}`
              : undefined
          }
        />
        <MetricCard
          title="Lacune (cible 80 %)"
          value={formatChf(results.lacune.lacune)}
          hint={`Remplacement ${formatPct(results.lacune.tauxRemplacementReel)} · manque 80 % ${formatChf(results.lacune.manquePour80)}`}
        />
      </div>

      {/* Chemin capital foyer + LP */}
      {results.capitalPathFoyer && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              Chemin capital foyer (LPP × % + libres passages × %)
            </CardTitle>
            <CardDescription>
              Impôt agrégé par personne sur les montants effectivement
              retirés — pas de reproduction de l’incohérence Excel J7/J15.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Info
              label="LPP retirées"
              value={formatChf(results.capitalPathFoyer.lppRetireTotal)}
            />
            <Info
              label="LP retirés"
              value={formatChf(results.capitalPathFoyer.librePassageRetireTotal)}
            />
            <Info
              label="Capital retiré total"
              value={formatChf(results.capitalPathFoyer.capitalRetireTotal)}
            />
            <Info
              label="Impôt / net"
              value={`${formatChf(results.capitalPathFoyer.impot)} / ${formatChf(results.capitalPathFoyer.net)}`}
            />
          </CardContent>
        </Card>
      )}

      {/* Planification retraits */}
      {results.withdrawalPlanning &&
        results.withdrawalPlanning.scenarios.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                Planification des retraits — comparaison scénarios
              </CardTitle>
              <CardDescription>
                Agrégation personne + année fiscale · calcul fiscal réel · sans
                qualifier « meilleur ». PDF = scénarios « Inclure dans le
                rapport » uniquement.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Scénario</TableHead>
                    <TableHead>Rapport</TableHead>
                    <TableHead>Capital retiré</TableHead>
                    <TableHead>Impôt</TableHead>
                    <TableHead>Net</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {results.withdrawalPlanning.scenarios.map((s) => {
                    const optIn = input.withdrawalScenarios.find(
                      (x) => x.id === s.scenarioId,
                    )?.includeInReport;
                    return (
                      <TableRow key={s.scenarioId}>
                        <TableCell className="font-medium">
                          {s.scenarioName}
                        </TableCell>
                        <TableCell>{optIn ? "Oui" : "Non"}</TableCell>
                        <TableCell>{formatChf(s.capitalRetireTotal)}</TableCell>
                        <TableCell>{formatChf(s.impotTotal)}</TableCell>
                        <TableCell>{formatChf(s.capitalNet)}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              {results.withdrawalPlanning.comparisons.length > 0 && (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Comparaison</TableHead>
                      <TableHead>Base</TableHead>
                      <TableHead>Δ Impôt</TableHead>
                      <TableHead>Δ Capital net</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {results.withdrawalPlanning.comparisons.map((c) => (
                      <TableRow key={`${c.fromId}-${c.toId}`}>
                        <TableCell>
                          {c.fromName} → {c.toName}
                          {!c.sameCapitalBase && c.warning && (
                            <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">
                              {c.warning}
                            </p>
                          )}
                        </TableCell>
                        <TableCell>
                          {c.sameCapitalBase ? (
                            <Badge variant="secondary">Identique</Badge>
                          ) : (
                            <Badge variant="outline">Différente</Badge>
                          )}
                        </TableCell>
                        <TableCell>{formatChf(c.deltaImpot)}</TableCell>
                        <TableCell>{formatChf(c.deltaCapitalNet)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}

              {/* Calendrier résumé tous scénarios */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium">Calendrier (par scénario)</h4>
                {results.withdrawalPlanning.scenarios.map((s) => (
                  <div key={`cal-${s.scenarioId}`} className="rounded border p-2">
                    <p className="mb-2 text-sm font-medium">{s.scenarioName}</p>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {s.byYear.map((y) => (
                        <div
                          key={`${s.scenarioId}-${y.year}`}
                          className="rounded bg-muted/30 p-2 text-xs"
                        >
                          <p className="font-semibold text-[var(--ap-accent)]">
                            {y.year}
                          </p>
                          <ul className="my-1 space-y-0.5">
                            {(y.lines || []).map((l, i) => (
                              <li key={i}>
                                {l.titulaire === "client1"
                                  ? "Assuré 1"
                                  : "Assuré 2"}{" "}
                                — {l.kind}
                                {l.institution ? ` / ${l.institution}` : ""} :{" "}
                                {formatChf(l.montantRetire)}
                              </li>
                            ))}
                          </ul>
                          <p>
                            Total {formatChf(y.capitalRetire)} · Impôt{" "}
                            {formatChf(y.impot)} · Net {formatChf(y.net)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">
                  Détail fiscalité technique
                </summary>
                <ul className="mt-2 space-y-2 text-xs">
                  {results.withdrawalPlanning.scenarios.flatMap((s) =>
                    s.audits.map((a, i) => (
                      <li
                        key={`${s.scenarioId}-${a.year}-${a.titulaire}-${i}`}
                        className="rounded border p-2"
                      >
                        <strong>{s.scenarioName}</strong> · {a.year} ·{" "}
                        {a.titulaire === "client1" ? "Assuré 1" : "Assuré 2"} ·
                        âge {a.ageAtPayment} · TaxLocationID {a.taxLocationId} ·
                        soumis {formatChf(a.montantSoumis)} · impôt{" "}
                        {formatChf(a.impotTotal)}
                        {a.error ? ` · erreur ${a.error}` : ""}
                        <br />
                        Capitaux :{" "}
                        {a.capitauxInclus
                          .map(
                            (c) =>
                              `${c.label} (${c.kind} ${formatChf(c.montantRetire)})`,
                          )
                          .join(" · ")}
                        <details className="mt-1">
                          <summary className="cursor-pointer text-muted-foreground">
                            Paramètres fiscaux
                          </summary>
                          <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/40 p-2 text-[10px]">
                            {JSON.stringify(a.request, null, 2)}
                          </pre>
                        </details>
                      </li>
                    )),
                  )}
                </ul>
              </details>
            </CardContent>
          </Card>
        )}

      {/* Scénarios capital */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Scénarios capital 60–65 (impôt)
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Âge</TableHead>
                <TableHead>Capital brut</TableHead>
                <TableHead>Retiré</TableHead>
                <TableHead>Impôt</TableHead>
                <TableHead>Net</TableHead>
                <TableHead>Rente résid.</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.capitalScenarios.map((s) => (
                <TableRow key={s.age}>
                  <TableCell className="font-medium">{s.age}</TableCell>
                  <TableCell>{formatChf(s.capitalBrut)}</TableCell>
                  <TableCell>{formatChf(s.capital)}</TableCell>
                  <TableCell>
                    {s.error ? (
                      <span className="text-xs text-destructive">{s.error}</span>
                    ) : (
                      formatChf(s.impot)
                    )}
                  </TableCell>
                  <TableCell>{formatChf(s.net)}</TableCell>
                  <TableCell>{formatChf(s.rente)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Scénarios rente */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Scénarios rente / impôts ICC & IFD
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Foyer</TableHead>
                <TableHead>Âge</TableHead>
                <TableHead>Rev. 1</TableHead>
                <TableHead>Rev. 2</TableHead>
                <TableHead>Fortune</TableHead>
                <TableHead>Impôt total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.incomeScenarios.map((s) => (
                <TableRow key={s.foyer}>
                  <TableCell>
                    <div className="font-medium">{s.foyer}</div>
                    <div className="text-xs text-muted-foreground">{s.label}</div>
                  </TableCell>
                  <TableCell>{s.age}</TableCell>
                  <TableCell>{formatChf(s.revenu1)}</TableCell>
                  <TableCell>{formatChf(s.revenu2)}</TableCell>
                  <TableCell>{formatChf(s.fortune)}</TableCell>
                  <TableCell>
                    {s.error ? (
                      <span className="text-xs text-destructive">{s.error}</span>
                    ) : (
                      formatChf(s.impot?.impotRevenuTotal)
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {results.renteHypotheses?.columns?.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Hypothèses de rente</CardTitle>
            <CardDescription>
              Revenu encaissé, revenu fiscal et impôt sont séparés.
              {results.renteHypotheses.ageRetraite
                ? ` Âge de retraite souhaité : ${results.renteHypotheses.ageRetraite} ans.`
                : " Âge applicable au dossier."}
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead />
                  {results.renteHypotheses.columns.map((col) => (
                    <TableHead key={col.id}>{col.label}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {[
                  ["Capital placé", (col) => formatChf(col.capitalPlace)],
                  ["Compagnie", (col) => col.compagnie || "—"],
                  ["Type", (col) => col.typeLabel],
                  ["Rente AVS", (col) => formatChf(col.renteAvs)],
                  ["Rente LPP résiduelle", (col) => col.kind === "lpp" ? "—" : formatChf(col.renteLppResiduelle)],
                  ["Rente garantie", (col) => formatChf(col.renteGarantie)],
                  ["Participation", (col) => col.kind === "lpp" ? "—" : formatChf(col.participationExcedents)],
                  ["Revenu total encaissé", (col) => formatChf(col.revenuBrutEncaisse)],
                  ["Revenu fiscal imposable", (col) => formatChf(col.revenuFiscalImposable)],
                  ["Impôts ICC & IFD", (col) => formatChf(col.impotEstv)],
                  ["Revenu net annuel", (col) => formatChf(col.revenuNetApresImpot)],
                ].map(([label, cell]) => (
                  <TableRow key={label}>
                    <TableCell className="font-medium">{label}</TableCell>
                    {results.renteHypotheses.columns.map((col) => (
                      <TableCell key={col.id} className="tabular-nums">{cell(col)}</TableCell>
                    ))}
                  </TableRow>
                ))}
                {results.renteHypotheses.comparerAvecRenteLpp && (
                  <TableRow>
                    <TableCell className="font-medium">Écart net annuel vs LPP</TableCell>
                    {results.renteHypotheses.columns.map((col) => (
                      <TableCell key={col.id} className="tabular-nums">
                        {col.kind === "lpp" ? "—" : formatChf(col.ecartNetAnnuelVsLpp)}
                      </TableCell>
                    ))}
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Comparatif */}
      {results.comparative && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Comparatif rente / capital</CardTitle>
            <CardDescription>
              {results.comparative.vaudoiseRenteManquante
                ? "Rentes Vaudoise non saisies (cellules Excel C5/D5 vides) — fiscalité AVS-seul affichée."
                : "Inclut la variante Vaudoise du rapport Excel."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Info label="Capital LPP 65" value={formatChf(results.comparative.capitalVsRente.capital65)} />
              <Info label="Impôt capital" value={formatChf(results.comparative.capitalVsRente.impotCapital65)} />
              <Info label="Capital net" value={formatChf(results.comparative.capitalVsRente.capitalNet65)} />
              <Info label="Rente nette estimée" value={formatChf(results.comparative.capitalVsRente.renteNetteEstimee)} />
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Indicateur</TableHead>
                  {results.comparative.columns.map((c) => (
                    <TableHead key={c.id}>{c.label}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell>Rente AVS</TableCell>
                  {results.comparative.columns.map((c) => (
                    <TableCell key={c.id}>{formatChf(c.renteAvs)}</TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell>Rente LPP / certaine</TableCell>
                  {results.comparative.columns.map((c) => (
                    <TableCell key={c.id}>{formatChf(c.renteLppOuCertaine)}</TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell>Impôts ICC & IFD</TableCell>
                  {results.comparative.columns.map((c) => (
                    <TableCell key={c.id}>{formatChf(c.impotIccIfd)}</TableCell>
                  ))}
                </TableRow>
                <TableRow>
                  <TableCell>Rente nette</TableCell>
                  {results.comparative.columns.map((c) => (
                    <TableCell key={c.id}>{formatChf(c.renteNette)}</TableCell>
                  ))}
                </TableRow>
              </TableBody>
            </Table>
            {results.comparative.indicateurs.economieFiscaleAnnuelle != null && (
              <p className="text-sm text-muted-foreground">
                Économie fiscale annuelle (LPP vs voie AVS-seul / Vaudoise) :{" "}
                <strong>{formatChf(results.comparative.indicateurs.economieFiscaleAnnuelle)}</strong>
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Frise */}
      {results.timeline && results.timeline.years.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Frise chronologique</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Année</TableHead>
                  <TableHead>Prestations</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.timeline.years.map((y) => (
                  <TableRow key={y}>
                    <TableCell className="font-medium">{y}</TableCell>
                    <TableCell>
                      <ul className="space-y-1 text-sm">
                        {(results.timeline!.byYear[y] || []).map((ev, i) => (
                          <li key={`${y}-${i}`}>
                            {ev.label} · {formatChf(ev.amount)}
                          </li>
                        ))}
                      </ul>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Évolution 90% */}
      {results.evolution && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              Évolution après retraite (objectif 90 %)
            </CardTitle>
            <CardDescription>
              Référence salaire {formatChf(results.evolution.salaireReference)} ·
              rente {formatChf(results.evolution.renteReference)}
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Année</TableHead>
                  <TableHead>Phase</TableHead>
                  <TableHead>Revenu</TableHead>
                  <TableHead>Écart vs 90 %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.evolution.rows.slice(0, 20).map((row) => (
                  <TableRow key={row.year}>
                    <TableCell>{row.year}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{row.phase}</Badge>
                    </TableCell>
                    <TableCell>{formatChf(row.revenu)}</TableCell>
                    <TableCell>{formatChf(row.lacune90)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function MetricCard({
  title,
  value,
  hint,
}: {
  title: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">{value}</CardTitle>
      </CardHeader>
      {hint && (
        <CardContent>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </CardContent>
      )}
    </Card>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-medium tabular-nums">{value}</p>
    </div>
  );
}
