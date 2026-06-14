import {
  evalMetricStatus,
  formatMetricNumber,
  formatPassCondition,
  type MetricDef,
} from "../../lib/evalStatus";
import { StatusPill } from "./StatusPill";

interface Props { def: MetricDef; value: number | null | undefined; }

export function MetricRow({ def, value }: Props) {
  const status = evalMetricStatus(def, value);
  return (
    <tr>
      <td>
        <strong>{def.label}</strong>
        <span className="metric-technology">{def.technology}</span>
      </td>
      <td className="num">{formatPassCondition(def)}</td>
      <td className="num">{value === null || value === undefined ? "Thiếu dữ liệu" : formatMetricNumber(def, value)}</td>
      <td><StatusPill status={status} /></td>
    </tr>
  );
}
