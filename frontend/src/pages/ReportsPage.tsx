import { useEffect, useMemo, useState } from "react";
import { fetchReports } from "../api/client";
import type { ReportItem } from "../api/types";
import { UNIVERSE } from "../data/universe";
import { filterByQuery } from "../lib/reportFilter";
import { mergeUniverseWithReports } from "../lib/mergeReports";
import { TickerSearch } from "../components/reports/TickerSearch";
import { ReportRow } from "../components/reports/ReportRow";
import { PreviewPanel } from "../components/reports/PreviewPanel";

const REPORT_UNIVERSE = [...UNIVERSE].sort((a, b) => {
  if (a.ticker === "DHG") return -1;
  if (b.ticker === "DHG") return 1;
  if (a.ticker === "DBD") return 1;
  if (b.ticker === "DBD") return -1;
  return 0;
});

const REPORTS_CACHE_KEY = "reports.inventory.v1";

function loadCachedReports(): ReportItem[] {
  try {
    const raw = window.localStorage.getItem(REPORTS_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as { items?: unknown };
    return Array.isArray(parsed.items) ? (parsed.items as ReportItem[]) : [];
  } catch {
    return [];
  }
}

function cacheReports(items: ReportItem[]): void {
  try {
    window.localStorage.setItem(REPORTS_CACHE_KEY, JSON.stringify({ items }));
  } catch {
    // Cache is a UX optimization only; API data remains the source of truth.
  }
}

export function ReportsPage() {
  const [apiItems, setApiItems] = useState<ReportItem[]>(loadCachedReports);
  const [apiError, setApiError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [previewTicker, setPreviewTicker] = useState<string | null>(null);

  // Always render the full universe; enrich with live report status when the
  // backend is reachable. On failure, keep the last known report status.
  const load = () => {
    fetchReports()
      .then((r) => {
        setApiItems(r.items);
        cacheReports(r.items);
        setApiError(null);
      })
      .catch((err: unknown) => {
        setApiError(err instanceof Error ? err.message : "Cannot reach reports API");
      });
  };
  useEffect(load, []);

  const rows = useMemo(() => mergeUniverseWithReports(REPORT_UNIVERSE, apiItems), [apiItems]);
  const filtered = useMemo(() => filterByQuery(rows, query), [rows, query]);
  const previewItem = rows.find((i) => i.ticker === previewTicker) ?? null;
  const withReport = rows.filter((i) => i.has_report).length;

  return (
    <section>
      <header>
        <h1>Báo cáo dược phẩm</h1>
        <p>
          {rows.length} mã · {withReport} đã có báo cáo · {rows.length - withReport} chưa có
        </p>
      </header>

      <TickerSearch value={query} onChange={setQuery} options={REPORT_UNIVERSE} />

      {apiError && (
        <p className="reports-api-warning" role="status">
          Không thể đồng bộ trạng thái báo cáo từ API. Kiểm tra VITE_API_BASE trên Vercel.
        </p>
      )}

      <p className="reports-result-count" aria-live="polite">
        Đang hiển thị {filtered.length} / {rows.length} mã.
      </p>

      <table className="reports-table">
        <thead>
          <tr>
            <th>Mã</th>
            <th>Tên công ty</th>
            <th>Sàn</th>
            <th>Ngành</th>
            <th>Trạng thái</th>
            <th>Hành động</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 ? (
            <tr>
              <td colSpan={6}>Không có mã nào khớp lựa chọn.</td>
            </tr>
          ) : (
            filtered.map((it) => (
              <ReportRow key={it.ticker} item={it} onPreview={setPreviewTicker} onGenerated={load} />
            ))
          )}
        </tbody>
      </table>

      <PreviewPanel item={previewItem} onClose={() => setPreviewTicker(null)} />
    </section>
  );
}
