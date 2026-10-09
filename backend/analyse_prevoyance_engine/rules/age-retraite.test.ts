import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ageRetraitePersonne } from "./age-retraite.ts";

describe("ageRetraitePersonne — âge souhaité fractionnel", () => {
  it("conserve 64.75 (64 ans et 9 mois) sans l'arrondir", () => {
    assert.equal(
      ageRetraitePersonne({ ageRetraiteSouhaite: 64.75 }, null),
      64.75,
    );
  });
});
