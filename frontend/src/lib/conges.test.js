import {
  computeWorkingDays,
  entriesForDay,
  formatDateFr,
  formatDays,
  monthGrid,
  periodLabel,
  shiftMonth,
  validateLeaveForm,
} from "./conges";

describe("congés : durée indicative (mêmes cas que backend/tests/test_leaves.py)", () => {
  it("compte les jours ouvrés lun–ven", () => {
    expect(computeWorkingDays("2026-11-02", "2026-11-15")).toBe(10);
    expect(computeWorkingDays("2026-11-14", "2026-11-14")).toBe(0);
  });

  it("gère les demi-journées", () => {
    expect(computeWorkingDays("2026-11-10", "2026-11-10", "morning", "morning")).toBe(0.5);
    expect(computeWorkingDays("2026-11-11", "2026-11-13", "afternoon", "morning")).toBe(2);
    expect(computeWorkingDays("2026-11-12", "2026-11-14", "full", "morning")).toBe(2);
  });

  it("ne dérive pas au changement d'heure ni en fin d'année", () => {
    expect(computeWorkingDays("2026-03-27", "2026-03-30")).toBe(2);
    expect(computeWorkingDays("2026-10-23", "2026-10-26")).toBe(2);
    expect(computeWorkingDays("2026-12-31", "2027-01-04")).toBe(3);
  });
});

describe("congés : contrôles du formulaire", () => {
  const base = { leaveType: "paid", startPart: "full", endPart: "full" };
  it("refuse une fin avant le début", () => {
    expect(validateLeaveForm({ ...base, startDate: "2026-11-12", endDate: "2026-11-10" })).toMatch(/postérieure/);
  });
  it("refuse une période sans jour ouvré", () => {
    expect(validateLeaveForm({ ...base, startDate: "2026-11-14", endDate: "2026-11-15" })).toMatch(/aucun jour ouvré/);
  });
  it("refuse un premier jour « matin » sur plusieurs jours", () => {
    expect(validateLeaveForm({ ...base, startPart: "morning", startDate: "2026-11-10", endDate: "2026-11-12" })).toMatch(/premier jour/);
  });
  it("accepte une demi-journée", () => {
    expect(validateLeaveForm({ ...base, startPart: "afternoon", endPart: "afternoon", startDate: "2026-11-10", endDate: "2026-11-10" })).toBe("");
  });
});

describe("congés : affichage", () => {
  it("formate sans fuseau", () => {
    expect(formatDateFr("2026-01-01")).toBe("01.01.2026");
    expect(formatDays(1.5)).toBe("1,5 j");
    expect(periodLabel({ start_date: "2026-11-10", end_date: "2026-11-10", start_day_part: "morning" })).toBe("10.11.2026 (matin)");
  });

  it("construit une grille lundi → dimanche", () => {
    const weeks = monthGrid("2026-11");
    expect(weeks[0][0].iso).toBe("2026-10-26");
    expect(weeks[weeks.length - 1][6].iso).toBe("2026-12-06");
    expect(weeks.flat().filter((d) => d.inMonth)).toHaveLength(30);
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  });

  it("indique la demi-journée concernée dans le calendrier", () => {
    const items = [{ employee_id: "a", start_date: "2026-11-11", end_date: "2026-11-13", start_day_part: "afternoon", end_day_part: "morning" }];
    expect(entriesForDay(items, "2026-11-11")[0].part).toBe("afternoon");
    expect(entriesForDay(items, "2026-11-12")[0].part).toBe("full");
    expect(entriesForDay(items, "2026-11-13")[0].part).toBe("morning");
    expect(entriesForDay(items, "2026-11-14")).toHaveLength(0);
  });
});
