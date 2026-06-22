import { describe, expect, it } from "vitest";
import { UNIVERSE, segmentCounts } from "./universe";

const INVALID_LISTING_MISMATCHES = [
  "HBH",
  "VMC",
  "NDT",
  "BID",
  "BCR",
  "VNP",
  "CPC",
  "HDA",
  "TMP",
  "DRG",
  "PVD",
  "DGW",
  "TNT",
];

describe("report universe", () => {
  it("excludes ticker symbols that resolve to non-healthcare listed companies", () => {
    const tickers = new Set(UNIVERSE.map((item) => item.ticker));

    for (const ticker of INVALID_LISTING_MISMATCHES) {
      expect(tickers.has(ticker)).toBe(false);
    }
  });

  it("keeps all report-ready healthcare tickers unique", () => {
    const tickers = UNIVERSE.map((item) => item.ticker);

    expect(tickers).not.toContain("AGP");
    expect(new Set(tickers).size).toBe(tickers.length);
    expect(segmentCounts().pharma).toBeGreaterThan(0);
  });
});
