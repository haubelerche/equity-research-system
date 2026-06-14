import { describe, it, expect } from "vitest";
import { filterReports, type ReportFilterState } from "./reportFilter";
import type { ReportItem } from "../api/types";

const base: ReportItem = {
  ticker: "DHG", company_name: "Duoc Hau Giang", exchange: "HOSE",
  segment: "pharma", is_mvp: true, has_report: true, has_explanation: true,
  preview_pages: [1], report_size: 10, updated_at: "x",
};

const rows: ReportItem[] = [
  base,
  { ...base, ticker: "IMP", company_name: "Imexpharm", has_report: false, has_explanation: false, is_mvp: true },
  { ...base, ticker: "JVC", company_name: "Viet Nhat", segment: "medical_equipment", exchange: "HOSE", is_mvp: false, has_report: false },
];

const empty: ReportFilterState = { query: "", segment: "all", exchange: "all", status: "all", mvpOnly: false };

describe("filterReports", () => {
  it("returns all with empty filter", () => {
    expect(filterReports(rows, empty).length).toBe(3);
  });
  it("matches ticker and name case-insensitively", () => {
    expect(filterReports(rows, { ...empty, query: "imex" }).map((r) => r.ticker)).toEqual(["IMP"]);
    expect(filterReports(rows, { ...empty, query: "dhg" }).map((r) => r.ticker)).toEqual(["DHG"]);
  });
  it("filters by segment and exchange", () => {
    expect(filterReports(rows, { ...empty, segment: "medical_equipment" }).map((r) => r.ticker)).toEqual(["JVC"]);
  });
  it("filters by status has_report", () => {
    expect(filterReports(rows, { ...empty, status: "has_report" }).map((r) => r.ticker)).toEqual(["DHG"]);
    expect(filterReports(rows, { ...empty, status: "pending" }).map((r) => r.ticker)).toEqual(["IMP", "JVC"]);
  });
  it("filters mvp only", () => {
    expect(filterReports(rows, { ...empty, mvpOnly: true }).map((r) => r.ticker)).toEqual(["DHG", "IMP"]);
  });
});
