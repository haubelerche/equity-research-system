import { useEffect, useMemo, useState } from "react";
import { fetchReports } from "../api/client";
import type { ReportItem } from "../api/types";
import { filterReports, type ReportFilterState } from "../lib/reportFilter";
import { ReportFilters } from "../components/reports/ReportFilters";
import { ReportRow } from "../components/reports/ReportRow";
import { PreviewPanel } from "../components/reports/PreviewPanel";

const EMPTY: ReportFilterState = { query: "", segment: "all", exchange: "all", status: "all", mvpOnly: false };

export function ReportsPage() {
  const [items, setItems] = useState<ReportItem[]>([]);
  const [filter, setFilter] = useState<ReportFilterState>(EMPTY);
  const [previewTicker, setPreviewTicker] = useState<string | null>(null);

  const load = () => { void fetchReports().then((r) => setItems(r.items)); };
  useEffect(load, []);

  const filtered = useMemo(() => filterReports(items, filter), [items, filter]);
  const segments = useMemo(() => [...new Set(items.map((i) => i.segment))], [items]);
  const exchanges = useMemo(() => [...new Set(items.map((i) => i.exchange))], [items]);
  const previewItem = items.find((i) => i.ticker === previewTicker) ?? null;
  const withReport = items.filter((i) => i.has_report).length;

  return (
    <section>
      <header>
        <h1>Báo cáo dược phẩm</h1>
        <p>{items.length} ticker · {withReport} đã có báo cáo · {items.length - withReport} chưa sinh</p>
      </header>
      <ReportFilters value={filter} onChange={setFilter} segments={segments} exchanges={exchanges} />
      <table>
        <thead><tr><th>Ticker</th><th>Tên</th><th>Sàn</th><th>Segment</th><th>MVP</th><th>Trạng thái</th><th>Hành động</th></tr></thead>
        <tbody>
          {filtered.map((it) => (
            <ReportRow key={it.ticker} item={it} onPreview={setPreviewTicker} onGenerated={load} />
          ))}
        </tbody>
      </table>
      <PreviewPanel item={previewItem} onClose={() => setPreviewTicker(null)} />
    </section>
  );
}
