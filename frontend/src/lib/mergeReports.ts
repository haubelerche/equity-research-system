import type { UniverseTicker } from "../data/universe";
import type { ReportItem } from "../api/types";

/**
 * Build the full per-ticker list the Reports page renders: one row for EVERY
 * universe ticker (so all 53 always show, even offline), enriched with live
 * report-availability status from the `/reports` API where present.
 *
 * Identity fields (name/exchange/segment/is_mvp) come from the static universe;
 * status fields (has_report/has_explanation/preview_pages/...) come from the API.
 */
export function mergeUniverseWithReports(
  universe: UniverseTicker[],
  apiItems: ReportItem[]
): ReportItem[] {
  const byTicker = new Map(apiItems.map((i) => [i.ticker, i]));
  return universe.map((u) => {
    const api = byTicker.get(u.ticker);
    return {
      ticker: u.ticker,
      company_name: u.company_name,
      exchange: u.exchange,
      segment: u.segment,
      is_mvp: u.is_mvp,
      has_report: api?.has_report ?? false,
      has_explanation: api?.has_explanation ?? false,
      preview_pages: api?.preview_pages ?? [],
      report_size: api?.report_size ?? null,
      updated_at: api?.updated_at ?? null,
    };
  });
}
