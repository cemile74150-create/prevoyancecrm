import {
  PDF_NEED_CALCULATE,
  PDF_POPUP_BLOCKED,
  PDF_STALE_WARNING,
  openAnalysePdfWindow,
  planAnalysePdf,
} from "./analysePdfAction";

describe("planAnalysePdf", () => {
  it("refuse sans analyse enregistrée", () => {
    expect(
      planAnalysePdf({ hasId: false, hasResults: true, isCurrent: true }),
    ).toEqual({
      allow: false,
      message: PDF_NEED_CALCULATE,
      tone: "error",
    });
  });

  it("refuse sans calcul", () => {
    expect(
      planAnalysePdf({ hasId: true, hasResults: false, isCurrent: false }),
    ).toEqual({
      allow: false,
      message: PDF_NEED_CALCULATE,
      tone: "error",
    });
  });

  it("ouvre le dernier calcul même si le formulaire a changé", () => {
    expect(
      planAnalysePdf({ hasId: true, hasResults: true, isCurrent: false }),
    ).toEqual({
      allow: true,
      message: PDF_STALE_WARNING,
      tone: "warning",
    });
  });

  it("ouvre sans message si le calcul est à jour", () => {
    expect(
      planAnalysePdf({ hasId: true, hasResults: true, isCurrent: true }),
    ).toEqual({
      allow: true,
      message: null,
      tone: null,
    });
  });
});

describe("openAnalysePdfWindow", () => {
  it("s'appuie sur window.open quand le pop-up est autorisé", () => {
    const popup = { closed: false };
    const openWindow = jest.fn(() => popup);
    expect(openAnalysePdfWindow(openWindow, "/api/analyses-prevoyance/x/pdf")).toBe(
      true,
    );
    expect(openWindow).toHaveBeenCalledWith(
      "/api/analyses-prevoyance/x/pdf",
      "_blank",
      "noopener",
    );
  });

  it("passe par un lien si window.open est bloqué", () => {
    const openWindow = jest.fn(() => null);
    expect(openAnalysePdfWindow(openWindow, "/api/analyses-prevoyance/x/pdf")).toBe(
      true,
    );
    expect(PDF_POPUP_BLOCKED).toMatch(/pop-ups/);
  });
});
