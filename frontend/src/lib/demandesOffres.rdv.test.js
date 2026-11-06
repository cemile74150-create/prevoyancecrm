import { rdvClientAffiche } from "./demandesOffres";

describe("rdvClientAffiche", () => {
  it("reprend la date du formulaire quand date_prochain_rdv est vide", () => {
    expect(rdvClientAffiche({
      date_prochain_rdv: "",
      heure_rdv: "",
      date_envoi: "2026-11-06",
      created_at: "2026-11-06T08:00:00",
      rdv_client_formulaire: { date: "2026-11-09", heure: "" },
    })).toEqual({ date: "2026-11-09", heure: "" });
  });

  it("garde date_prochain_rdv et son heure quand elles sont déjà renseignées", () => {
    expect(rdvClientAffiche({
      date_prochain_rdv: "2026-12-01",
      heure_rdv: "08:15",
      rdv_client_formulaire: { date: "2026-11-09", heure: "14:30" },
    })).toEqual({ date: "2026-12-01", heure: "08:15" });
  });

  it("n'affiche rien sans date de formulaire ni date_prochain_rdv", () => {
    expect(rdvClientAffiche({
      date_prochain_rdv: "",
      date_envoi: "2026-11-06",
      created_at: "2026-11-06",
      rdv_client_formulaire: { date: "", heure: "" },
    })).toEqual({ date: "", heure: "" });
  });
});
