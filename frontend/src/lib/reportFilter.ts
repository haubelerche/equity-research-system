import type { ReportItem } from "../api/types";

export interface ReportFilterState {
  query: string;
  segment: string;   // "all" | segment
  exchange: string;  // "all" | exchange
  status: string;    // "all" | "has_report" | "pending"
  mvpOnly: boolean;
}

export function filterReports(rows: ReportItem[], f: ReportFilterState): ReportItem[] {
  const q = f.query.trim().toLowerCase();
  return rows.filter((r) => {
    if (q && !(`${r.ticker} ${r.company_name}`.toLowerCase().includes(q))) return false;
    if (f.segment !== "all" && r.segment !== f.segment) return false;
    if (f.exchange !== "all" && r.exchange !== f.exchange) return false;
    if (f.status === "has_report" && !r.has_report) return false;
    if (f.status === "pending" && r.has_report) return false;
    if (f.mvpOnly && !r.is_mvp) return false;
    return true;
  });
}
