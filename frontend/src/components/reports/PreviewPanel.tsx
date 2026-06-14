import { previewUrl, fileUrl } from "../../api/client";
import type { ReportItem } from "../../api/types";

interface Props { item: ReportItem | null; onClose: () => void; }

export function PreviewPanel({ item, onClose }: Props) {
  if (!item) return null;
  return (
    <aside aria-label="preview">
      <header>
        <span>{item.ticker} — {item.company_name}</span>
        <button onClick={onClose}>Đóng</button>
      </header>
      {item.preview_pages.length > 0 ? (
        item.preview_pages.map((p) => (
          <img key={p} src={previewUrl(item.ticker, p)} alt={`${item.ticker} trang ${p}`} loading="lazy" />
        ))
      ) : (
        <iframe title="report-pdf" src={fileUrl(item.ticker, "report")} style={{ width: "100%", height: "80vh" }} />
      )}
    </aside>
  );
}
