import { clientIdAfterTypeChange, showsExistingClientSearch } from "./demandesOffres";

describe("type de client — recherche", () => {
  test("masque la recherche pour un nouveau client et la garde pour un client existant", () => {
    expect(showsExistingClientSearch("nouveau")).toBe(false);
    expect(showsExistingClientSearch("existant")).toBe(true);
    expect(showsExistingClientSearch("")).toBe(true);
  });

  test("oublie l'identifiant lié dès que le type passe à nouveau client", () => {
    expect(clientIdAfterTypeChange("nouveau", "client-123")).toBeNull();
    expect(clientIdAfterTypeChange("nouveau", null)).toBeNull();
    expect(clientIdAfterTypeChange("existant", "client-123")).toBe("client-123");
    expect(clientIdAfterTypeChange("existant", null)).toBeNull();
  });
});
