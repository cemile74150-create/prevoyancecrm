import { avsAnnuelFromMensuel } from "./avsAnnuel";

describe("avsAnnuelFromMensuel", () => {
  it("mensuel → annuel × 13, pas × 12", () => {
    expect(avsAnnuelFromMensuel(1_890)).toBe(24_570);
    expect(avsAnnuelFromMensuel(1_965)).toBe(25_545);
    expect(avsAnnuelFromMensuel(1_890) + avsAnnuelFromMensuel(1_965)).toBe(50_115);
    expect(avsAnnuelFromMensuel(1_890)).not.toBe(1_890 * 12);
    expect(avsAnnuelFromMensuel(1_965)).not.toBe(22_680);
  });
});
