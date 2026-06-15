import { describe, it, expect } from "vitest";
import { UNIVERSE, segmentCounts } from "./universe";

describe("universe", () => {
  it("has the active configured universe", () => {
    expect(UNIVERSE.length).toBe(42);
  });
  it("segment breakdown matches the universe CSV", () => {
    const c = segmentCounts();
    expect(c.pharma).toBe(35);
    expect(c.healthcare_services).toBe(2);
    expect(c.medical_equipment).toBe(2);
    expect(c.medical_distribution).toBe(3);
  });
  it("DHG is MVP", () => {
    expect(UNIVERSE.find((t) => t.ticker === "DHG")?.is_mvp).toBe(true);
  });
});
