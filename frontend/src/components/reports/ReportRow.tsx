import { fileUrl } from "../../api/client";
import type { ReportItem } from "../../api/types";
import { GenerateButton } from "./GenerateButton";

interface Props {
  item: ReportItem;
  onPreview: (ticker: string) => void;
  onGenerated: () => void;
}

const SEGMENT_LABEL: Record<string, string> = {
  pharma: "Du?c ph?m",
  healthcare_services: "D?ch v? y t?",
  medical_equipment: "Thi?t b? y t?",
  medical_distribution: "Ph�n ph?i",
};

export function ReportRow({ item, onPreview, onGenerated }: Props) {
  const cacheToken = item.updated_at ?? item.report_size ?? null;
  const statusLabel = item.has_report
    ? item.has_explanation
      ? "? �?y d?"
      : "? Ch? b�o c�o"
    : "? Chua c�";
  return (
    <tr>
      <td className="ticker-cell">{item.ticker}</td>
      <td>{item.company_name}</td>
      <td>{item.exchange}</td>
      <td>{SEGMENT_LABEL[item.segment] ?? item.segment}</td>
      <td>
        <span className={`status-cell status-cell--${item.has_report ? "ready" : "pending"}`}>
          {statusLabel}
        </span>
      </td>
      <td>
        <div className="row-actions">
          {item.has_report ? (
            <>
              <button onClick={() => onPreview(item.ticker)}>Xem tru?c</button>
              <a href={fileUrl(item.ticker, "report", cacheToken)} target="_blank" rel="noreferrer">
                T?i b�o c�o
              </a>
              {item.has_explanation && (
                <a href={fileUrl(item.ticker, "explanation", cacheToken)} target="_blank" rel="noreferrer">
                  T?i gi?i th�ch
                </a>
              )}
              <GenerateButton ticker={item.ticker} onComplete={onGenerated} label="C?p nh?t" />
            </>
          ) : (
            <GenerateButton ticker={item.ticker} onComplete={onGenerated} label="Sinh b�o c�o" />
          )}
        </div>
      </td>
    </tr>
  );
}
