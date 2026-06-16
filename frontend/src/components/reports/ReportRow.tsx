import { fileUrl } from "../../api/client";
import type { ReportItem } from "../../api/types";
import { GenerateButton } from "./GenerateButton";

interface Props {
  item: ReportItem;
  onPreview: (ticker: string) => void;
  onGenerated: () => void;
}

const SEGMENT_LABEL: Record<string, string> = {
  pharma: "Dược phẩm",
  healthcare_services: "Dịch vụ y tế",
  medical_equipment: "Thiết bị y tế",
  medical_distribution: "Phân phối",
};

export function ReportRow({ item, onPreview, onGenerated }: Props) {
  const cacheToken = item.updated_at ?? item.report_size ?? null;
  const statusLabel = item.has_report
    ? item.has_explanation
      ? "Đầy đủ"
      : "Chỉ báo cáo"
    : "Chưa có";
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
              <button onClick={() => onPreview(item.ticker)}>Xem trước</button>
              <a href={fileUrl(item.ticker, "report", cacheToken)} target="_blank" rel="noreferrer">
                Tải báo cáo
              </a>
              {item.has_explanation && (
                <a href={fileUrl(item.ticker, "explanation", cacheToken)} target="_blank" rel="noreferrer">
                  Tải giải thích
                </a>
              )}
              <GenerateButton ticker={item.ticker} onComplete={onGenerated} label="Cập nhật" />
            </>
          ) : (
            <GenerateButton ticker={item.ticker} onComplete={onGenerated} label="Sinh báo cáo" />
          )}
        </div>
      </td>
    </tr>
  );
}
