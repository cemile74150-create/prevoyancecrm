// @ts-nocheck
"use client";

import { useState } from "react";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import {
  annuelAvs,
  buildAnalyseAvsPersonne,
  formatChfAvs,
  renderAnalyseAvsHtml,
  suggestionAvsDepart,
} from "../../../../backend/analyse_prevoyance_engine/rules/analyse-avs-depart";

const CHAMPS = [
  {
    depart: 63,
    titre: "Départ à 63 ans",
    lignes: [
      ["mensuel63Avant65", "Rente AVS mensuelle de 63 à 65 ans (CHF)"],
      ["mensuel63Des65", "Rente AVS mensuelle dès 65 ans (CHF)"],
    ],
  },
  {
    depart: 64,
    titre: "Départ à 64 ans",
    lignes: [
      ["mensuel64Avant65", "Rente AVS mensuelle de 64 à 65 ans (CHF)"],
      ["mensuel64Des65", "Rente AVS mensuelle dès 65 ans (CHF)"],
    ],
  },
  {
    depart: 65,
    titre: "Départ à 65 ans",
    lignes: [["mensuel65", "Rente AVS mensuelle dès 65 ans, sans anticipation (CHF)"]],
  },
];

function nomPersonne(person, repli) {
  const nom = `${person?.prenom || ""} ${person?.nom || ""}`.trim();
  return nom || repli;
}

function valeurAffichee(person, cle, suggestion) {
  const stocke = person?.avsDepart?.[cle];
  if (stocke === undefined) return suggestion?.[cle] ?? "";
  if (stocke == null) return "";
  return stocke;
}

export function AvsDepartPanel({
  client1,
  conjoint,
  isMarried,
  onChangeClient1,
  onChangeConjoint,
}) {
  const personnes = [
    { id: "1", person: client1, onChange: onChangeClient1, repli: "Personne 1" },
    ...(isMarried && conjoint
      ? [{ id: "2", person: conjoint, onChange: onChangeConjoint, repli: "Personne 2" }]
      : []),
  ];
  const [actif, setActif] = useState("1");
  const courant = personnes.find((item) => item.id === actif) || personnes[0];
  const person = courant.person;
  const suggestion = suggestionAvsDepart(person);
  const analyse = buildAnalyseAvsPersonne(person);

  function ecrire(cle, brut) {
    const valeur = brut === "" ? null : Number(brut);
    courant.onChange({
      ...person,
      avsDepart: {
        ...(person.avsDepart || {}),
        [cle]: Number.isFinite(valeur) ? valeur : null,
      },
    });
  }

  return (
    <div className="space-y-4" data-testid="avs-depart-panel">
      {personnes.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {personnes.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`rounded-md border px-3 py-1.5 text-sm ${
                item.id === courant.id
                  ? "border-[#800000] bg-[#800000] text-white"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
              onClick={() => setActif(item.id)}
              data-testid={`avs-personne-${item.id}`}
            >
              {nomPersonne(item.person, item.repli)}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-3 rounded-md border p-3">
        <h3 className="text-sm font-semibold">{nomPersonne(person, courant.repli)}</h3>
        {analyse.avertissementAgeLegal && (
          <p className="rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-900">
            {analyse.avertissementAgeLegal}
          </p>
        )}
        <p className="text-sm font-medium">Rentes à saisir</p>
        <div className="grid gap-3 lg:grid-cols-3">
          {CHAMPS.map((bloc) => (
            <div key={bloc.depart} className="space-y-3 rounded-md bg-slate-50 p-3">
              <p className="text-sm font-medium">{bloc.titre}</p>
              {bloc.lignes.map(([cle, libelle]) => {
                const affiche = valeurAffichee(person, cle, suggestion);
                const mensuel = affiche === "" ? null : Number(affiche);
                return (
                  <div key={cle} className="space-y-1">
                    <Label className="text-xs">{libelle}</Label>
                    <Input
                      type="number"
                      min={0}
                      value={affiche}
                      onChange={(e) => ecrire(cle, e.target.value)}
                      data-testid={`avs-${cle}`}
                    />
                    <p className="text-xs text-muted-foreground">
                      {mensuel == null || !Number.isFinite(mensuel)
                        ? "Annuelle : à compléter"
                        : `Annuelle : ${formatChfAvs(annuelAvs(mensuel))} (× 13)`}
                    </p>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      <div
        className="rounded-md border bg-white p-3"
        data-testid="avs-depart-resultat"
        dangerouslySetInnerHTML={{ __html: renderAnalyseAvsHtml(analyse) }}
      />
    </div>
  );
}
