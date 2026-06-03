# Phase 09 — Charts + layout IMP-style + font QA

**PLAN gốc:** §1.10, §1.11, §1.12, §2 Phase 9, §4.10.
**Đọc trước:** `00_AUDIT.md`.

## Mục tiêu
PDF chuyên nghiệp giống mẫu IMP: sidebar có chart giá, chart nhỏ trái/phải, bảng gọn, font tiếng Việt ổn định.

## Hiện trạng code
- ĐÃ có: `backend/reporting/chart_generator.py`, `scripts/generate_charts.py`, `html_renderer.py`, `pdf_renderer.py`, `scripts/setup_fonts.py`.
- `artifacts/charts/` **RỖNG** ⇒ chưa sinh chart.
- `client_report_view_model._charts` (dòng ~907) chỉ tìm C1/C2/C4 PNG.

## Việc cần làm
1. **Sinh chart artifact** (`generate_charts.py`) trong harness trước render, lưu PNG/SVG cố định:
   - C1 giá + volume (sidebar trang 1), C2 revenue & net profit, C4 margin/ROE trend, + forecast revenue/EBIT/FCFF, + sensitivity heatmap.
2. **CSS component (PLAN §4.10):** `two-column-grid`, `sidebar-chart-card`, `small-chart-left/right`, `metric-card`, `valuation-bridge-table`, `source-caption`.
   - Chart width 40–55%, float left/right, `page-break-inside: avoid`, max-height cố định; KHÔNG center full-width trừ sensitivity/valuation matrix.
   - Table ≤8–10 cột; quá rộng ⇒ appendix/chia bảng.
3. **Page template:** 1 snapshot+sidebar+chart giá; 2 business update; 3 financial performance + 2 chart nhỏ; 4 forecast & drivers; 5 valuation FCFF/FCFE + bridge; 6 sensitivity+scenario+peer; 7 catalysts & risks; 8 conclusion+quality summary+sources+disclaimer. CSS page-break rõ, tránh trang trắng.
4. **Font:** embed Noto Sans/DejaVu Sans (hỗ trợ tiếng Việt). `setup_fonts.py` đảm bảo.
5. **Render QA:** xuất PNG từng trang, kiểm tofu/mất dấu, chart không vỡ/quá to, bảng không tràn, không trang trống lớn. Đây là `layout_render_gate` (Phase 01).

## Acceptance
- Output gần chuẩn IMP: sidebar có chart, phần chính phân tích dài, chart nhỏ có caption nguồn, footer/header rõ (ticker/date/project/page).
- PNG QA: tiếng Việt đúng, không chart full-width thừa.

## Test
- `tests/unit/test_artifact_writer.py` (đang sửa theo git status) — đồng bộ.
- `tests/unit/test_chart_generator.py`: sinh đủ chart cho ticker.
- Smoke: `scripts/demo/demo_render_dhg.py` render PNG QA.

## Rủi ro
- PDF render phụ thuộc engine (weasyprint/playwright) — kiểm môi trường Windows. Font embed bắt buộc để khỏi tofu trên môi trường khác.
