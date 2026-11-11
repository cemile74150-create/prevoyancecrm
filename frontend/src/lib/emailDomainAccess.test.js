import {
  LEAVES_EMAIL_DOMAIN,
  canAccessLeavesModule,
  emailEndsWithDomain,
  normalizeEmail,
} from "./emailDomainAccess";
import { hasPerm } from "./permissions";

describe("emailDomainAccess (congés @agencemendes.ch)", () => {
  it("normalise trim + minuscules", () => {
    expect(normalizeEmail("  Agent@AgenceMendes.CH ")).toBe("agent@agencemendes.ch");
    expect(LEAVES_EMAIL_DOMAIN).toBe("agencemendes.ch");
  });

  it("accepte uniquement le suffixe @domaine", () => {
    expect(emailEndsWithDomain("  Agent@AgenceMendes.CH ")).toBe(true);
    expect(emailEndsWithDomain("agent@other.ch")).toBe(false);
    expect(emailEndsWithDomain("")).toBe(false);
    expect(emailEndsWithDomain(null)).toBe(false);
  });

  it("expose canAccessLeavesModule sur l'utilisateur", () => {
    expect(canAccessLeavesModule({ email: "rh@agencemendes.ch" })).toBe(true);
    expect(canAccessLeavesModule({ email: "admin@externe.ch" })).toBe(false);
  });
});

describe("hasPerm leaves.access / leaves.manage + domaine", () => {
  it("accorde leaves.access au domaine, refuse hors domaine", () => {
    expect(hasPerm({ email: "agent@agencemendes.ch", role: "conseiller" }, "leaves.access")).toBe(true);
    expect(hasPerm({ email: "  RH@AgenceMendes.CH  ", role: "admin" }, "leaves.access")).toBe(true);
    expect(hasPerm({ email: "boss@externe.ch", role: "admin" }, "leaves.access")).toBe(false);
  });

  it("refuse leaves.manage hors domaine même pour admin avec permission stockée", () => {
    const outsider = {
      email: "boss@externe.ch",
      role: "admin",
      permissions: { "leaves.manage": true },
    };
    expect(hasPerm(outsider, "leaves.manage")).toBe(false);
    expect(hasPerm(outsider, "leaves.access")).toBe(false);

    const insiderAdmin = { email: "admin@agencemendes.ch", role: "admin" };
    expect(hasPerm(insiderAdmin, "leaves.manage")).toBe(true);
    expect(hasPerm(insiderAdmin, "leaves.access")).toBe(true);

    const insiderGranted = {
      email: "rh@agencemendes.ch",
      role: "ceo",
      permissions: { "leaves.manage": true },
    };
    expect(hasPerm(insiderGranted, "leaves.manage")).toBe(true);
  });
});
