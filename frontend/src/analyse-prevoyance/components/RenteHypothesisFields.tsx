// @ts-nocheck
"use client";

import { Plus, Trash2 } from "lucide-react";
import { ConfirmDeleteButton } from "@/analyse-prevoyance/components/ConfirmDeleteButton";
import { Button } from "@/analyse-prevoyance/ui/button";
import { Input } from "@/analyse-prevoyance/ui/input";
import { Label } from "@/analyse-prevoyance/ui/label";
import { withSingleRecommander } from "@/analyse-prevoyance/lib/analyseWizard";
import { compagnieEstPax, NOTE_PAX_DIFFERE } from "@/analyse-prevoyance/lib/compagniePax";
import { formatChf } from "@/analyse-prevoyance/lib/mappers";
import {
  commitOffres,
  emptyOffre,
  offresDeHypothese,
  titreOffre,
  totauxAnneeCommune,
} from "@/analyse-prevoyance/lib/offreCombinee";
import type { AnalyseInput, RenteHypothesisInput, RenteOffreSaisie } from "@/analyse-prevoyance/lib/types";

function emptyHypothesis(): RenteHypothesisInput {
  return {
    id: `rh-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    type: "certaine",
    compagnie: "",
    capitalPlace: 0,
    dureeAnnees: null,
    dureeDiffereAnnees: null,
    renteGarantieAnnuelle: 0,
    participationExcedentsAnnuelle: 0,
    recommander: false,
  };
}

function OfferFields({
  offer,
  onChange,
}: {
  offer: RenteOffreSaisie;
  onChange: (partial: Partial<RenteOffreSaisie>) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <div className="space-y-1">
        <Label className="text-xs">Type de rente</Label>
        <select
          className="border-input bg-background h-8 w-full rounded-md border px-2 text-sm"
          value={offer.type}
          onChange={(e) =>
            onChange({
              type: e.target.value,
              dureeAnnees: e.target.value === "viagere" ? null : offer.dureeAnnees,
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
          value={offer.compagnie}
          onChange={(e) => onChange({ compagnie: e.target.value })}
        />
        {compagnieEstPax(offer.compagnie) ? (
          <p className="text-xs text-muted-foreground" data-testid={`pax-differe-${offer.id}`}>
            * {NOTE_PAX_DIFFERE}
          </p>
        ) : null}
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Capital placé (timbre fédéral compris) (CHF)</Label>
        <Input
          type="number"
          min={0}
          value={offer.capitalPlace || ""}
          onChange={(e) => onChange({ capitalPlace: Number(e.target.value) || 0 })}
        />
      </div>
      {offer.type === "certaine" && (
        <div className="space-y-1">
          <Label className="text-xs">Durée du versement de la rente (années)</Label>
          <Input
            type="number"
            min={1}
            value={offer.dureeAnnees ?? ""}
            onChange={(e) =>
              onChange({
                dureeAnnees: e.target.value === "" ? null : Number(e.target.value) || null,
              })
            }
          />
        </div>
      )}
      <div className="space-y-1">
        <Label className="text-xs">Durée du différé (années)</Label>
        <Input
          type="number"
          min={0}
          value={offer.dureeDiffereAnnees ?? ""}
          data-testid={`rente-differe-${offer.id}`}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") {
              onChange({ dureeDiffereAnnees: null });
              return;
            }
            const years = Math.floor(Number(raw));
            onChange({
              dureeDiffereAnnees: Number.isFinite(years) && years >= 0 ? years : null,
            });
          }}
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Rente garantie annuelle (CHF)</Label>
        <Input
          type="number"
          min={0}
          value={offer.renteGarantieAnnuelle || ""}
          onChange={(e) =>
            onChange({ renteGarantieAnnuelle: Number(e.target.value) || 0 })
          }
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Participation aux excédents annuelle (CHF)</Label>
        <Input
          type="number"
          min={0}
          value={offer.participationExcedentsAnnuelle || ""}
          onChange={(e) =>
            onChange({ participationExcedentsAnnuelle: Number(e.target.value) || 0 })
          }
        />
      </div>
    </div>
  );
}

export function RenteHypothesisFields({
  input,
  onChange,
}: {
  input: AnalyseInput;
  onChange: (partial: Partial<AnalyseInput>) => void;
}) {
  const rows = input.renteHypotheses || [];

  function replaceRow(id: string, next: RenteHypothesisInput) {
    onChange({
      renteHypotheses: rows.map((row) => (row.id === id ? next : row)),
    });
  }

  function updateOffer(row: RenteHypothesisInput, offerId: string, partial: Partial<RenteOffreSaisie>) {
    const offers = offresDeHypothese(row).map((offer) =>
      offer.id === offerId ? { ...offer, ...partial } : offer,
    );
    replaceRow(row.id, commitOffres(row, offers));
  }

  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={Boolean(input.comparerAvecRenteLpp)}
          onChange={(e) => onChange({ comparerAvecRenteLpp: e.target.checked })}
        />
        Comparer avec la rente LPP
      </label>
      {rows.map((row, index) => {
        const offers = offresDeHypothese(row);
        const combined = offers.length >= 2;
        const totaux = totauxAnneeCommune(offers);
        return (
          <div key={row.id} className="space-y-3 rounded-md border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium">Hypothèse {index + 1}</p>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={Boolean(row.recommander)}
                    onChange={(e) =>
                      onChange({
                        renteHypotheses: withSingleRecommander(
                          rows,
                          row.id,
                          e.target.checked,
                        ),
                      })
                    }
                    data-testid={`rente-recommander-${row.id}`}
                  />
                  Inclure / Recommander
                </label>
                <ConfirmDeleteButton
                  ariaLabel="Supprimer l'hypothèse"
                  onConfirm={() =>
                    onChange({
                      renteHypotheses: rows.filter((item) => item.id !== row.id),
                    })
                  }
                >
                  <Trash2 className="size-4" />
                </ConfirmDeleteButton>
              </div>
            </div>
            {offers.map((offer, offerIndex) => (
              <div key={offer.id} className="space-y-2">
                {combined ? (
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{titreOffre(offer, offerIndex)}</p>
                    <ConfirmDeleteButton
                      ariaLabel="Supprimer l'offre"
                      onConfirm={() =>
                        replaceRow(
                          row.id,
                          commitOffres(
                            row,
                            offers.filter((item) => item.id !== offer.id),
                          ),
                        )
                      }
                    >
                      <Trash2 className="size-4" />
                    </ConfirmDeleteButton>
                  </div>
                ) : null}
                <OfferFields
                  offer={offer}
                  onChange={(partial) => updateOffer(row, offer.id, partial)}
                />
              </div>
            ))}
            {combined ? (
              <div
                className="space-y-1 rounded-md bg-muted/40 px-3 py-2 text-xs"
                data-testid={`offre-combinee-recap-${row.id}`}
              >
                <p>Capital total : {formatChf(totaux.capitalTotal)}</p>
                <p>Total rentes garanties : {formatChf(totaux.rentesGaranties)}</p>
                <p>Total participations : {formatChf(totaux.participations)}</p>
                <p>Total prestations annuelles : {formatChf(totaux.prestationsAnnuelles)}</p>
                <p className="text-muted-foreground">
                  Pour une année où les deux rentes sont versées.
                </p>
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground">
              {combined
                ? "Une seule assiette : AVS et rente LPP résiduelle une fois, plus la part imposable de chaque rente versée cette année-là. Viagère : 4 % de la rente garantie et 70 % de la participation. Certaine : 0 % de la rente garantie et 100 % de la participation."
                : offers[0]?.type === "certaine"
                  ? "Revenu fiscal = rente AVS + rente LPP résiduelle + 100 % de la participation. La rente garantie est encaissée, elle n'entre pas dans l'impôt."
                  : "Revenu fiscal = rente AVS + rente LPP résiduelle + 4 % de la rente garantie + 70 % de la participation."}
            </p>
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                data-testid={`offre-combinee-${row.id}`}
                onClick={() => {
                  const actuelle = offers[0]?.type === "viagere" ? "certaine" : "viagere";
                  replaceRow(row.id, commitOffres(row, [...offers, emptyOffre(actuelle)]));
                }}
              >
                <Plus className="size-3" />
                Offre combinée
              </Button>
            </div>
          </div>
        );
      })}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange({ renteHypotheses: [...rows, emptyHypothesis()] })}
      >
        <Plus className="size-4" />
        Ajouter une hypothèse
      </Button>
    </div>
  );
}
