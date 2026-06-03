# Phase 01 — ReportExportGate: chặn xuất final khi thiếu dữ liệu lõi

**PLAN gốc:** §2 Phase 1, §3 (gate list), §4.1, §4.3.
**Đọc trước:** `00_AUDIT.md`.

## Mục tiêu
Không cho xuất PDF/HTML "final" khi thiếu price/target/rating/shares/valuation/citation/numeric. Thiếu ⇒ chỉ `draft_review`.

## Hiện trạng code
- `backend/reporting/client_report_view_model.py`:
  - `assert_client_final_ready()` (dòng ~1087) ĐÃ chặn `client_final` khi `missing_required_fields` không rỗng.
  - `missing` được build dòng ~957: current_price/target_price/upside/forecast_rows/fcff_rows/price_chart.
  - NHƯNG `_recommendation()` (dòng ~543) trả `"ĐANG HOÀN THIỆN"` cho mode ≠ client_final ⇒ `analyst_draft` vẫn render PDF trông như final.
- `scripts/render_report.py`: `--mode` default = `analyst_draft`; chỉ gọi `assert_client_final_ready` khi `client_final` hoặc `--strict`.
- `scripts/run_full_pipeline.py`: deprecated, `_write_artifacts` ghi placeholder rỗng.

## Việc cần làm
1. **Bổ sung điều kiện numeric/shares vào `missing`** trong `build_client_report_view_model`:
   - `shares_outstanding <= 0` nhưng EPS có số ⇒ thêm `"shares_outstanding"`.
   - Thêm wiring tới `backend/evaluation/numeric_consistency.py` (EPS≈NI/shares, P/E=price/EPS…) ⇒ nếu fail thêm `"numeric_consistency"`.
   - Thêm `"citation_coverage"` nếu citation gate (Phase 08) chưa pass.
2. **Phân biệt rõ output draft vs final ở `render_report.py`:**
   - Nếu mode `analyst_draft` và có `missing` ⇒ ghi vào thư mục `artifacts/review_packets/` hoặc tên file có hậu tố `_draft_review`, KHÔNG dùng template client-facing final.
   - Header/sidebar bản draft hiển thị `BẢN NHÁP — CHƯA ĐỦ ĐIỀU KIỆN XUẤT BẢN`, không phải `ĐANG HOÀN THIỆN` lẫn lộn với final.
3. **Hard-deprecate `run_full_pipeline.py`** (đã có guard) — thêm chú thích trỏ sang `run_research.py`; cân nhắc xóa `_write_artifacts` placeholder để không ai sinh artifact rỗng.
4. **Gate tổng hợp** đối chiếu PLAN §3:
   ```
   source_gate, citation_gate, numeric_consistency_gate,
   forecast_artifact_gate, valuation_reproducibility_gate,
   sensitivity_gate, layout_render_gate == PASS  &&  human_review_gate == APPROVED
   ```
   Map sang `backend/harness/gates.py` (đã có `has_fcff/has_fcfe/has_blend/has_sensitivity` dòng 80). Bổ sung gate còn thiếu, trả `report_status = NEEDS_REVIEW/BLOCKED`, `export_final=false`, `allow_draft_export=true`.

## Acceptance
- Không còn PDF final nào chứa `ĐANG HOÀN THIỆN`.
- Thiếu bất kỳ trường lõi ⇒ chỉ ra `*_draft_review.html/pdf`.
- `shares=0` + EPS có số ⇒ gate fail (test).

## Test
- `tests/unit/test_report_data_loader_gates.py` (đã có) — mở rộng case shares=0, numeric fail.
- Thêm `tests/unit/test_export_gate_blocking.py`: dựng view model thiếu target_price ⇒ `assert_client_final_ready` raise `ClientReportDataMissing`.

## Rủi ro
- Đừng làm `analyst_draft` quá khắt khe đến mức không bao giờ render được khi đang dev — giữ `internal_debug` mode bypass.
