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
  const displayStatus: MetricStatus = status === "pass" ? "pass" : "fail";
  return (
    <span className={`pill pill--${displayStatus}`} data-status={displayStatus}>
      {LABEL[displayStatus]}
    </span>
  );
}
