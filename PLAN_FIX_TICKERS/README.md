# PLAN_FIX_TICKERS — Index

Kế hoạch sửa lỗi output báo cáo PDF/HTML, cắt nhỏ từ `PLAN_FIX_ALL_TICKERS_REPORT_OUTPUT_FOR_CLAUDE.md`
để thực thi từng phase độc lập (tránh đứt mạch API khi làm một lượt quá lớn).

**Nguyên tắc xuyên suốt:** ticker-agnostic (không `if ticker=="DHG"`), code-first valuation,
HTML là single source of truth, production path = `scripts/run_research.py` (harness).

## Đọc theo thứ tự
1. **[00_AUDIT.md](00_AUDIT.md)** — ĐỌC TRƯỚC. Root cause + map 12 lỗi → file + module đã có/còn thiếu.

## Thứ tự thực thi (ROI cao → thấp)
| Bước | File | Việc | Trạng thái |
|------|------|------|-----------|
| 1 | [03_PHASE_forecast_periods_drivers.md](03_PHASE_forecast_periods_drivers.md) | Bug `_derive_periods` (mất cột forecast) + driver thật | ✅ DONE (commit edfd83d) |
| 2 | [02_PHASE_market_snapshot.md](02_PHASE_market_snapshot.md) | MarketSnapshotArtifact → shares + sidebar | ✅ DONE (85015b8, 62cbc1c) |
| 3 | [05_PHASE_valuation_blend.md](05_PHASE_valuation_blend.md) | Target price/rating + `valuation_result.json` (GOAL §13) | ✅ DONE (44f154b) — bridge + is_publishable; client_final resolves target |
| 4 | [01_PHASE_export_gate.md](01_PHASE_export_gate.md) | ReportExportGate: chặn xuất final khi thiếu lõi | ✅ DONE (2305d47) — shares↔EPS guard; draft/final đã tách sẵn |
| 5 | [04_PHASE_schedules.md](04_PHASE_schedules.md) | WC/debt/dividend/cash sweep vào bảng BS/CF | ✅ DONE (18a1794) — net borrowing, net debt/EBITDA, dividend yield |
| 6 | [06_PHASE_sensitivity.md](06_PHASE_sensitivity.md) | Sensitivity recompute thật | ✅ DONE (7693146) — WACC×g matrix giá trị thật |
| 7 | [07_PHASE_narrative.md](07_PHASE_narrative.md) | Narrative ≥300 chữ bám artifact | ☐ |
| 8 | [08_PHASE_citations.md](08_PHASE_citations.md) | Citation + nguồn tham khảo | ☐ |
| 9 | [09_PHASE_charts_layout_font.md](09_PHASE_charts_layout_font.md) | Charts + layout IMP + font QA | ☐ |

### Verified end-to-end (DBD, 2026-06-03)
Full `generate_report.py` run produces: periods `2022FY..2030F`; driver table real
(rev growth 6.26%, gross margin 48.27%); blend `target=30,409 = 0.6×35,767 + 0.4×22,372`;
rating **BÁN** (upside −39.4%); sidebar cap/shares/52w/volume/foreign filled.

## Definition of Done (PLAN §5)
Rating + target price tính được · không `—` thừa · forecast 5 năm driver thật · FCFF+FCFE blend 60/40 ·
sensitivity ra giá · mỗi phần ≥300 chữ có số + citation · chart nhỏ đúng vị trí có nguồn ·
font tiếng Việt đúng · không thuật ngữ backend · gate fail ⇒ chỉ xuất draft.

## Cách làm mỗi phase
Theo CLAUDE.md §13: inspect → summarize → sửa nhỏ nhất → cập nhật spec → thêm test → chạy `pytest` subset →
cập nhật `.claude/EXECUTION_STATE.md` → báo cáo theo format §21. Mỗi phase chỉ chạm file của phase đó.
