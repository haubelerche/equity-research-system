import type { MetricStatus } from "../../lib/evalStatus";

const LABEL: Record<MetricStatus, string> = {
  pass: "Pass", fail: "Fail", measured_only: "Measured-only",
};

export function StatusPill({ status }: { status: MetricStatus }) {
  return <span className={`pill pill--${status}`} data-status={status}>{LABEL[status]}</span>;
}
