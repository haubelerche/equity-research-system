import { describe, it, expect } from "vitest";
import { filterByQuery } from "./reportFilter";
import type { ReportItem } from "../api/types";

const mk = (ticker: string, name: string): ReportItem => ({
  ticker,
  company_name: name,
  exchange: "HOSE",
  segment: "pharma",
  is_mvp: false,
  has_report: false,
  has_explanation: false,
  preview_pages: [],
  report_size: null,
  updated_at: null,
});

const rows = [mk("DHG", "Duoc Hau Giang"), mk("IMP", "Imexpharm"), mk("DMC", "Domesco")];

describe("filterByQuery", () => {
  it("returns all rows for empty query", () => {
    expect(filterByQuery(rows, "").length).toBe(3);
    expect(filterByQuery(rows, "   ").length).toBe(3);
  });
  it("matches ticker case-insensitively", () => {
    expect(filterByQuery(rows, "dhg").map((r) => r.ticker)).toEqual(["DHG"]);
  });
  it("matches company name", () => {
    expect(filterByQuery(rows, "imex").map((r) => r.ticker)).toEqual(["IMP"]);
  });
  it("returns empty for no match", () => {
    expect(filterByQuery(rows, "zzz").length).toBe(0);
  });
});
