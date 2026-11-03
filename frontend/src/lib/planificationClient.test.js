import {
  aUnePlanificationActive,
  ficheClientPlanificationPath,
  planificationsDuClient,
} from "./planificationClient";

const martinA = {
  id: "plan-a",
  clientId: "client-a",
  clientName: "René Martin",
  status: "calculee",
};
const martinB = {
  id: "plan-b",
  clientId: "client-b",
  clientName: "René Martin",
  status: "brouillon",
};
const annulee = {
  id: "plan-c",
  clientId: "client-a",
  clientName: "René Martin",
  status: "annulee",
};

describe("planification reliée au client", () => {
  test("un client seul ne voit que ses planifications, pas l'homonyme", () => {
    const rows = planificationsDuClient([martinA, martinB, annulee], "client-a");
    expect(rows.map((row) => row.id)).toEqual(["plan-a", "plan-c"]);
    expect(rows.every((row) => row.clientId === "client-a")).toBe(true);
  });

  test("le conjoint a sa propre fiche : son identifiant ne reprend pas les planifications de l'autre", () => {
    const madame = planificationsDuClient([martinA, martinB], "client-b");
    expect(madame.map((row) => row.id)).toEqual(["plan-b"]);
    expect(planificationsDuClient([martinA], "client-sans-planification")).toEqual([]);
    expect(planificationsDuClient(null, "client-a")).toEqual([]);
  });

  test("une planification annulée seule n'empêche pas d'en créer une, une active si", () => {
    expect(aUnePlanificationActive([annulee])).toBe(false);
    expect(aUnePlanificationActive([martinA, annulee])).toBe(true);
    expect(aUnePlanificationActive([])).toBe(false);
  });

  test("le retour ouvre la fiche de cet identifiant, onglet Planification", () => {
    expect(ficheClientPlanificationPath("client-a")).toBe(
      "/clients/client-a?tab=planification",
    );
    expect(ficheClientPlanificationPath("client-b")).toBe(
      "/clients/client-b?tab=planification",
    );
    expect(ficheClientPlanificationPath("")).toBeNull();
    expect(ficheClientPlanificationPath(null)).toBeNull();
  });
});
