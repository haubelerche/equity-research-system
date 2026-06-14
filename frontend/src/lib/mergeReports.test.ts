import { describe, it, expect } from "vitest";
import { mergeUniverseWithReports } from "./mergeReports";
import type { UniverseTicker } from "../data/universe";
import type { ReportItem } from "../api/types";

const uni: UniverseTicker[] = [
  { ticker: "DHG", company_name: "Duoc Hau Giang", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "IMP", company_name: "Imexpharm", exchange: "HOSE", segment: "pharma", is_mvp: true },
];

describe("mergeUniverseWithReports", () => {
  it("returns one row per universe ticker even with empty api (offline fallback)", () => {
    const rows = mergeUniverseWithReports(uni, []);
    expect(rows.map((r) => r.ticker)).toEqual(["DHG", "IMP"]);
    expect(rows.every((r) => r.has_report === false)).toBe(true);
    expect(rows.every((r) => r.preview_pages.length === 0)).toBe(true);
  });

  it("merges status from api by ticker; identity stays from universe", () => {
    const api: ReportItem[] = [
      {
        ticker: "DHG", company_name: "API NAME", exchange: "XXX", segment: "other",
        is_mvp: false, has_report: true, has_explanation: true,
        preview_pages: [1, 2], report_size: 5, updated_at: "t",
      },
    ];
    const rows = mergeUniverseWithReports(uni, api);
    const dhg = rows.find((r) => r.ticker === "DHG")!;
    expect(dhg.has_report).toBe(true);
    expect(dhg.has_explanation).toBe(true);
    expect(dhg.preview_pages).toEqual([1, 2]);
    expect(dhg.company_name).toBe("Duoc Hau Giang"); // identity from universe, not api
    expect(dhg.exchange).toBe("HOSE");
    expect(rows.find((r) => r.ticker === "IMP")!.has_report).toBe(false);
  });
});
