import { describe, it, expect } from "vitest";
import { UNIVERSE, segmentCounts } from "./universe";

describe("universe", () => {
  it("has 53 tickers", () => {
    expect(UNIVERSE.length).toBe(53);
  });
  it("segment breakdown matches the universe CSV", () => {
    const c = segmentCounts();
    expect(c.pharma).toBe(44);
    expect(c.healthcare_services).toBe(3);
    expect(c.medical_equipment).toBe(3);
    expect(c.medical_distribution).toBe(3);
  });
  it("DHG is MVP", () => {
    expect(UNIVERSE.find((t) => t.ticker === "DHG")?.is_mvp).toBe(true);
  });
});
