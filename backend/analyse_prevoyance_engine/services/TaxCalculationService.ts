import {
  CONFESSION_DEFAULT,
  TAX_YEAR_DEFAULT,
  type CapitalTaxResult,
  type IncomeTaxResult,
  type TaxLocation,
} from "../types";

const ESTV_BASE =
  "https://swisstaxcalculator.estv.admin.ch/delegate/ost-integration/v1/lg-proxy/operation/c3b67379_ESTV";

export interface SearchLocationParams {
  search: string;
  language?: number;
  taxYear?: number;
}

export interface CapitalTaxParams {
  ageAtPayment: number;
  capital: number;
  gender: number; // 1 masculin, 2 féminin
  relationship: number; // 1 seul, 2 marié
  taxGroupId: number;
  taxYear?: number;
  confession1?: number;
  confession2?: number;
  numberOfChildren?: number;
}

export interface DetailedTaxParams {
  taxLocationId: number;
  relationship: number;
  age1: number;
  age2: number;
  revenue1: number;
  revenue2: number;
  fortune: number;
  taxYear?: number;
  confession1?: number;
  confession2?: number;
}

/**
 * Service fiscal ESTV — appels directs (pas de taux hardcodés).
 * Persiste request/response pour audit.
 */
export class TaxCalculationService {
  readonly baseUrl = ESTV_BASE;

  async searchLocation(params: SearchLocationParams): Promise<TaxLocation[]> {
    const body = {
      Search: params.search,
      Language: params.language ?? 2,
      TaxYear: params.taxYear ?? TAX_YEAR_DEFAULT,
    };
    const json = await this.post<{ response: TaxLocation[] }>(
      "API_searchLocation",
      body,
    );
    return json.response ?? [];
  }

  async calculateCapitalTax(
    params: CapitalTaxParams,
  ): Promise<CapitalTaxResult> {
    const request = {
      AgeAtPayment: params.ageAtPayment,
      Capital: params.capital,
      Confession1: params.confession1 ?? CONFESSION_DEFAULT,
      Confession2: params.confession2 ?? CONFESSION_DEFAULT,
      Gender: params.gender,
      NumberOfChildren: params.numberOfChildren ?? 0,
      Relationship: params.relationship,
      SimKey: null,
      TaxGroupID: params.taxGroupId,
      TaxYear: params.taxYear ?? TAX_YEAR_DEFAULT,
    };

    const json = await this.post<{
      response: Array<{
        TaxCity: number;
        TaxCanton: number;
        TaxFed: number;
        TaxChurch: number;
        Location?: TaxLocation;
      }>;
    }>("API_calculateManyCapitalTaxes", request);

    const r = json.response?.[0];
    if (!r) {
      throw new Error("Réponse ESTV capital vide");
    }

    const taxCity = num(r.TaxCity);
    const taxCanton = num(r.TaxCanton);
    const taxFed = num(r.TaxFed);
    const taxChurch = num(r.TaxChurch);

    return {
      age: params.ageAtPayment,
      capital: params.capital,
      gender: params.gender,
      relationship: params.relationship,
      taxGroupId: params.taxGroupId,
      taxYear: request.TaxYear,
      taxCity,
      taxCanton,
      taxFed,
      taxChurch,
      impotTotal: taxCity + taxCanton + taxFed + taxChurch,
      request,
      response: json,
    };
  }

  async calculateDetailedTaxes(
    params: DetailedTaxParams & { foyer?: string },
  ): Promise<IncomeTaxResult> {
    const relationship = params.relationship;
    const request = {
      SimKey: null,
      TaxYear: params.taxYear ?? TAX_YEAR_DEFAULT,
      TaxLocationID: params.taxLocationId,
      Relationship: relationship,
      Confession1: params.confession1 ?? CONFESSION_DEFAULT,
      Confession2:
        params.confession2 ??
        (relationship === 2 ? CONFESSION_DEFAULT : 0),
      Children: [] as unknown[],
      Budget: [] as unknown[],
      Age1: params.age1,
      Age2: params.age2,
      Revenue1: params.revenue1,
      Revenue2: params.revenue2,
      RevenueType1: 3,
      RevenueType2: params.revenue2 > 0 || relationship === 2 ? 3 : 0,
      Fortune: params.fortune,
    };

    // Excel M : RevenueType2 = 3 si conjoint sinon 0
    if (relationship !== 2) {
      request.RevenueType2 = 0;
      request.Age2 = 0;
      request.Revenue2 = 0;
    }

    const json = await this.post<{
      response: {
        TotalTax: number;
        IncomeTaxFed: number;
        IncomeTaxCanton: number;
        IncomeTaxCity: number;
        IncomeTaxChurch: number;
      };
    }>("API_calculateDetailedTaxes", request);

    const r = json.response;
    if (!r) {
      throw new Error("Réponse ESTV revenu vide");
    }

    return {
      foyer: params.foyer ?? "default",
      age: params.age1,
      taxLocationId: params.taxLocationId,
      taxYear: request.TaxYear,
      revenu1: params.revenue1,
      revenu2: relationship === 2 ? params.revenue2 : 0,
      fortune: params.fortune,
      impotRevenuTotal: num(r.TotalTax),
      impotFederal: num(r.IncomeTaxFed),
      impotCanton: num(r.IncomeTaxCanton),
      impotCommune: num(r.IncomeTaxCity),
      impotEglise: num(r.IncomeTaxChurch),
      request,
      response: json,
    };
  }

  private async post<T>(operation: string, body: unknown): Promise<T> {
    const url = `${this.baseUrl}/${operation}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(
        `ESTV ${operation} HTTP ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`,
      );
    }
    return (await res.json()) as T;
  }
}

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export const taxCalculationService = new TaxCalculationService();
