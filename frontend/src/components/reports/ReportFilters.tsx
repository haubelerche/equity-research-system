import type { ReportFilterState } from "../../lib/reportFilter";

interface Props {
  value: ReportFilterState;
  onChange: (next: ReportFilterState) => void;
  segments: string[];
  exchanges: string[];
}

export function ReportFilters({ value, onChange, segments, exchanges }: Props) {
  const set = (patch: Partial<ReportFilterState>) => onChange({ ...value, ...patch });
  return (
    <div role="search">
      <input aria-label="search" placeholder="Tìm ticker / tên" value={value.query}
        onChange={(e) => set({ query: e.target.value })} />
      <select aria-label="segment" value={value.segment} onChange={(e) => set({ segment: e.target.value })}>
        <option value="all">Mọi segment</option>
        {segments.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <select aria-label="exchange" value={value.exchange} onChange={(e) => set({ exchange: e.target.value })}>
        <option value="all">Mọi sàn</option>
        {exchanges.map((x) => <option key={x} value={x}>{x}</option>)}
      </select>
      <select aria-label="status" value={value.status} onChange={(e) => set({ status: e.target.value })}>
        <option value="all">Mọi trạng thái</option>
        <option value="has_report">Đã có report</option>
        <option value="pending">Chưa sinh</option>
      </select>
      <label><input type="checkbox" checked={value.mvpOnly} onChange={(e) => set({ mvpOnly: e.target.checked })} /> MVP</label>
    </div>
  );
}
