import type { MetricStatus } from "../../lib/evalStatus";

const LABEL: Record<MetricStatus, string> = {
  pass: "Đạt",
  fail: "Chưa đạt",
  warning: "Cảnh báo",
  not_evaluable: "Chưa đánh giá",
  blocked: "Bị chặn",
  not_measured: "Chưa đo",
};

export function StatusPill({ status }: { status: MetricStatus }) {
  return (
    <span className={`pill pill--${status}`} data-status={status}>
      {LABEL[status]}
    </span>
  );
}
