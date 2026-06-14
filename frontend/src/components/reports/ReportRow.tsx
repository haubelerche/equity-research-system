import { fileUrl } from "../../api/client";
import type { ReportItem } from "../../api/types";
import { GenerateButton } from "./GenerateButton";

interface Props {
  item: ReportItem;
  onPreview: (ticker: string) => void;
  onGenerated: () => void;
}

export function ReportRow({ item, onPreview, onGenerated }: Props) {
  const statusLabel = item.has_report
    ? item.has_explanation ? "✓ Đầy đủ" : "◑ Chỉ report"
    : "⏳ Chưa sinh";
  return (
    <tr>
      <td>{item.ticker}</td>
      <td>{item.company_name}</td>
      <td>{item.exchange}</td>
      <td>{item.segment}</td>
      <td>{item.is_mvp ? "MVP" : ""}</td>
      <td>{statusLabel}</td>
      <td>
        {item.has_report && (
          <button onClick={() => onPreview(item.ticker)}>Xem trước</button>
        )}
        {item.has_report ? (
          <a href={fileUrl(item.ticker, "report")} target="_blank" rel="noreferrer">Tải report</a>
        ) : null}
        {item.has_explanation ? (
          <a href={fileUrl(item.ticker, "explanation")} target="_blank" rel="noreferrer">Tải explanation</a>
        ) : null}
        {!item.has_report && <GenerateButton ticker={item.ticker} onComplete={onGenerated} />}
      </td>
    </tr>
  );
}
