import type { ReportItem } from "../api/types";

/**
 * Filter the merged report rows by a free-text query over ticker + company name.
 * Empty query returns all rows. Case-insensitive substring match.
 */
export function filterByQuery(rows: ReportItem[], query: string): ReportItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((r) => `${r.ticker} ${r.company_name}`.toLowerCase().includes(q));
}
