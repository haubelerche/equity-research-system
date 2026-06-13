# Thiết kế: File diễn giải định giá (.md) song song PDF/HTML

- Ngày: 2026-06-12
- Trạng thái: Đã chốt (chờ review spec)
- Phạm vi: Sinh thêm một tài liệu Markdown diễn giải chi tiết toàn bộ chuỗi tính
  toán định giá, mỗi lần báo cáo được publish, song song với PDF/HTML.

## 1. Mục tiêu & bối cảnh

Báo cáo PDF/HTML khách hàng cố tình **ngắn gọn** và **ẩn thuật ngữ nội bộ** (gate,
tier, công thức, lineage) theo CLAUDE.md §8. Điều này khiến việc **kiểm định** số
liệu định giá khó khăn: người review không thấy công thức, input, bước trung gian.

Tài liệu này thêm một **file Markdown nội bộ** trình bày đầy đủ: mỗi phép tính, công
thức, input, bước trung gian, kết quả, giả định, cảnh báo — để kiểm định và diễn
giải song song với tiến trình xuất PDF. File này KHÔNG phải deliverable khách hàng,
nên ĐƯỢC phép phơi bày chi tiết nội bộ.

### Quyết định đã chốt (brainstorm)

| Quyết định | Lựa chọn |
|---|---|
| Phạm vi nội dung | Toàn bộ chuỗi: forecast drivers → chỉ số tài chính → FCFF → FCFE → blend → P/E forward → sensitivity |
| Trigger | Hook vào `ClientReportPublisher.publish()` → cả pipeline đầy đủ lẫn `generate_fast_report.py` |
| Mức chi tiết | Đầy đủ kiểm định: công thức, giá trị trung gian, assumptions, lineage, warnings, reproducibility_hash |
| Xử lý lỗi | Không chặn PDF — log warning, `workings=None`, vẫn xuất PDF/HTML |
| Ngôn ngữ | Tiếng Việt; thuật ngữ kỹ thuật giữ tiếng Anh (WACC, FCFF, terminal value) |

## 2. Kiến trúc

Tuân thủ CLAUDE.md §10 — tách tính toán thuần khỏi I/O:

- **Lớp thuần** `build_valuation_workings_md(...) -> str`: nhận các dict đã nạp
  (valuation, forecast, facts) và `view_model`, trả về chuỗi Markdown. Không I/O,
  không side-effect → test golden ổn định.
- **Lớp I/O** trong `ClientReportPublisher.publish()`: nạp dict gốc qua manifest đã
  có, ghi file `report_workings.md`, upload artifact, đính vào `PublishedReport`.

File mới: `backend/reporting/valuation_workings.py`.

### Boundaries

| Unit | Làm gì | Phụ thuộc |
|---|---|---|
| `build_valuation_workings_md` | Dựng chuỗi Markdown từ dict đã nạp | Chỉ stdlib + `ClientReportViewModel` (đọc) |
| `load_workings_inputs` (I/O helper) | Đọc manifest → trả `(valuation, forecast, facts)` | `report_data_loader._read_manifest_or_raise` |
| `ClientReportPublisher.publish` | Orchestrate: render → build md → persist | 2 unit trên + storage |

Builder **phòng thủ về tên khóa**: chấp nhận cả `fcff`/`fcff_dcf`, `fcfe`/`fcfe_dcf`,
`blend`/`blend_dcf` — y hệt fallback đã có trong loaders của `client_report_view_model`.
Mọi giá trị thiếu hiển thị `—` (không bịa số).

## 3. Cấu trúc nội dung file .md

1. **Header** — ticker, công ty, sàn, run_id, valuation_date, snapshot_id,
   `reproducibility_hash`.
2. **Tóm tắt kết quả** — giá hiện tại, target price (blend), upside/downside, khuyến
   nghị + diễn giải luật rating (total return = upside + dividend yield; >20% MUA,
   <−10% BÁN, còn lại NẮM GIỮ).
3. **Bảng giả định** — WACC, cost of equity, terminal growth, số năm dự phóng, thuế
   suất, target P/E, premium/discount + ghi chú "giá trị mặc định cần HITL duyệt".
4. **Dự phóng (driver-based)** — mỗi năm F: tăng trưởng doanh thu, biên LN gộp/ròng,
   EBIT, LNST, capex, D&A, ΔNWC, lịch nợ vay (`net_borrowing = phát hành − trả nợ`),
   lịch cổ tức (payout ratio). Diễn giải logic driver.
5. **Chỉ số tài chính** — ROE, ROA, biên LN, P/E, P/B kèm công thức + giá trị từng kỳ.
6. **FCFF** — `FCFF = EBIT×(1−t) + D&A − CAPEX − ΔNWC`; bảng FCFF từng năm; chiết khấu
   PV theo WACC; terminal value (Gordon: `FCFF_n×(1+g)/(WACC−g)`); PV terminal; EV;
   cầu nối nợ ròng → equity value; ÷ shares = implied price. Hiện rõ số học từng bước.
7. **FCFE** — công thức, cost of equity, equity value, implied price (hoặc nêu lý do
   None khi thiếu input).
8. **Blend** — `Target = 0.60×Price_FCFF + 0.40×Price_FCFE`; số học có trọng số; kiểm
   tra `fcff_fcfe_gap_pct` (>25% cảnh báo); cờ `is_draft_only`.
9. **P/E Forward cross-check** — EPS forward (LNST cổ đông mẹ ÷ shares pha loãng),
   peer table, peer median P/E, premium/discount + rationale, target P/E, target
   price, ma trận độ nhạy EPS×P/E.
10. **Bảng độ nhạy** — render từng ma trận có trong artifact (`fcff_wacc_g`,
    `fcfe_re_g`, `blend_grid`, `pe`, `ev_ebitda`) thành bảng Markdown có nhãn trục.
11. **Đối chiếu & cảnh báo** — kiểm tra nhất quán số (implied price vs blend), gom
    `warnings[]` từ các artifact, `reproducibility_hash`, ghi chú lineage nguồn fact.

## 4. Luồng dữ liệu

```
publish(run_id, ticker, mode)
  → build_client_report_view_model(...)         [đã có]
  → render PDF/HTML + persist                    [đã có]
  → load_workings_inputs(run_id) qua manifest    [MỚI, I/O]
  → build_valuation_workings_md(...) -> str       [MỚI, thuần]
  → ghi report_workings.md + _publish_run_file    [MỚI]
  → PublishedReport(html, pdf, workings)          [mở rộng]
```

## 5. Thay đổi giao diện

### `PublishedReport` (final_report_renderer.py)

Thêm trường optional:

```python
@dataclass(frozen=True)
class PublishedReport:
    html: PublishedReportArtifact
    pdf: PublishedReportArtifact
    workings: PublishedReportArtifact | None = None

    def artifact_refs(self) -> list[dict]:
        refs = [self.html.to_ref(), self.pdf.to_ref()]
        if self.workings is not None:
            refs.append(self.workings.to_ref())
        return refs

    def to_dict(self) -> dict:
        out = {"html": self.html.to_ref(), "pdf": self.pdf.to_ref()}
        if self.workings is not None:
            out["workings_md"] = self.workings.to_ref()
        return out
```

Artifact metadata: `artifact_type="report_workings_md"`,
`section_key="report_workings_md"`, `content_type="text/markdown; charset=utf-8"`,
tên file run-bucket `report_workings.md`.

### `generate_fast_report.py`

Sau khi tải PDF/HTML, nếu `result_dict.get("workings_md")`: tải về
`output/{ticker}_valuation_workings.md` và thêm `workings_path` vào dict kết quả.

## 6. Xử lý lỗi

Build .md bọc trong `try/except` trong `publish()`:
- Lỗi → `_logger.warning(...)` + `workings=None`. KHÔNG raise.
- PDF/HTML vẫn publish bình thường. Fast-report bỏ qua tải khi không có `workings_md`.

## 7. Test (regression bắt buộc — CLAUDE.md §2)

`tests/reporting/test_valuation_workings.py`:
1. Builder thuần từ artifact mẫu sinh đủ 11 mục (kiểm tra tiêu đề).
2. Chứa dòng công thức FCFF và giá trị WACC từ artifact.
3. Ma trận sensitivity (`blend_grid`) render thành bảng Markdown có nhãn trục.
4. Giá trị thiếu → `—`, không raise, không bịa.
5. Phòng thủ tên khóa: artifact dùng `fcff_dcf` lẫn `fcff` đều render được.

`tests/reporting/test_final_report_renderer.py` (mở rộng):
6. `publish()` đính `workings` ref; `to_dict()` có khóa `workings_md`.
7. Builder lỗi → `publish()` vẫn trả PDF/HTML, `workings=None` (không raise).

`tests/scripts/test_generate_fast_report.py` (mở rộng):
8. Khi published có `workings_md`, fast-report tải file .md về `output/`.

## 8. Ngoài phạm vi (YAGNI)

- Không render workings thành PDF/HTML.
- Không thêm gate mới cho workings.
- Không đổi nội dung/format PDF khách hàng.
- Không đưa workings vào báo cáo client hay manifest gate.
