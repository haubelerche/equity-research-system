import type { MetricStatus } from "../../lib/evalStatus";

const LABEL: Record<MetricStatus, string> = {
  pass: "Dat",
  fail: "Chua dat",
  warning: "Canh bao",
  not_evaluable: "Chua danh gia",
  blocked: "Bi chan",
  not_measured: "Chua do",
};

export function StatusPill({ status }: { status: MetricStatus }) {
  return <span className={`pill pill--${status}`} data-status={status}>{LABEL[status]}</span>;
}
