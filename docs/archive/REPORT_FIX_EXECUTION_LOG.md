# Report Fix Execution Log

## Baseline

- command: `python scripts/render_report.py --ticker DBD --pdf --run-id BASELINE_REPORT_FIX_20260601`
- generated html path: `artifacts/reports_html/BASELINE_REPORT_FIX_20260601_DBD_report.html`
- generated pdf path: `artifacts/reports_pdf/BASELINE_REPORT_FIX_20260601_DBD_report.pdf-pending`
- observed broken glyphs: no in regenerated HTML; PDF not produced because no renderer backend is currently available
- observed zero price: no, but current output presents a final-looking BUY rating, target price `333,239`, and upside `+563.8%` in draft state with unapproved assumptions
- observed invalid charts: yes; pre-existing chart files allow valuation/sensitivity visuals to appear unless blocked by stricter artifact status
- current failing tests: none in the focused baseline set

## Baseline Test Run

- command: `python -m pytest tests/unit/test_section_builder.py tests/unit/test_html_renderer.py tests/unit/test_pdf_renderer.py tests/unit/test_chart_generator.py -q`
- result: `44 passed`
- warnings: pytest cache write permission warning under `.pytest_cache`

## Phase Status

- Phase 0: done
- Phase 1: done
- Phase 2: done
- Phase 3: done
- Phase 4: done
- Phase 5: done
- Phase 6: done
- Phase 7: done
- Phase 8: pending
- Phase 9: focused regression tests added
- Phase 10: done for current DBD draft export

## Baseline Findings

- The active entrypoint is `scripts/render_report.py`.
- The HTML renderer is `backend/reporting/html_renderer.py`.
- The PDF renderer is `backend/reporting/pdf_renderer.py`; in this environment it writes `.pdf-pending` rather than producing a PDF because `weasyprint`, `pdfkit`, and `xhtml2pdf` are not importable.
- The report context loader is `backend/reporting/report_data_loader.py`.
- The section template builder is `backend/reporting/section_builder.py`.
- The deterministic chart generator is `backend/reporting/chart_generator.py`, called by `scripts/generate_charts.py`.
- The DBD baseline HTML uses valid Vietnamese text, but the investment snapshot contradicts draft controls by showing `BUY`, a target price, and upside while assumptions and human review are not approved.
- Chart generation still has pathways that zero-fill missing data or create placeholder PNGs, which can be mistaken for valid chart artifacts by the renderer.

## Implementation Summary

- PDF export now runs HTML and PDF text preflight checks for broken Vietnamese markers and missing-glyph boxes.
- Strict PDF export no longer writes `.pdf-pending` stubs unless `allow_stub=True` is explicitly requested.
- Headless Chrome/Edge print-to-PDF is used before xhtml2pdf because xhtml2pdf produced missing glyph boxes for Vietnamese text on this Windows environment.
- The report loader now prefers the latest `artifacts/valuation_results/*_{ticker}_valuation_result.json` governance artifact for current price, target price, upside, rating, and publishability.
- Older exploratory valuation artifacts may still supply historical ratios and company context, but they cannot publish target price, upside, WACC, DCF bridge, or sensitivity unless the governance artifact passes.
- Existing chart files are filtered out of the render context when the upstream artifact is not publishable.
- Draft banners and blocked-section notices are visible without decorative icons.
- Console context output now reports missing price, target price, and upside as `N/A`.

## Verification

- command: `python -m pytest tests/unit/test_report_data_loader_gates.py tests/unit/test_section_builder.py tests/unit/test_html_renderer.py tests/unit/test_pdf_renderer.py tests/unit/test_chart_generator.py -q`
- result: `47 passed`
- warning: pytest cache write permission warning under `.pytest_cache`

- command: `python scripts/render_report.py --ticker DBD --pdf --run-id FIXPDF_FINAL_20260601`
- result: HTML and PDF generated.
- generated html path: `artifacts/reports_html/FIXPDF_FINAL_20260601_DBD_report.html`
- generated pdf path: `artifacts/reports_pdf/FIXPDF_FINAL_20260601_DBD_report.pdf`
- PDF backend used: headless Chrome fallback after WeasyPrint reported missing Windows GTK libraries.

- command: PDF text extraction preflight using `pypdf`
- result: `{'box': False, 'duoc': True, 'binh_dinh': True, 'trang_thai': True, 'target_leak': False, 'upside_leak': False, 'buy_leak': False}`

## Current DBD Behavior

- Export status: draft.
- Rating: `UNDER_REVIEW`.
- Current price: `N/A`.
- Target price: `N/A`.
- Upside/downside: `N/A`.
- DCF bridge: blocked.
- Sensitivity heatmap: blocked.
- Forecast chart/table: blocked until assumptions are approved.
- Quality gate summary and detailed valuation reproducibility are consistent at `N/A` when valuation is not publishable.

## ACBS-Style Layout Pass

- reference sample: `IMP_by_ACBS_Update_22.pdf`
- implementation intent: align the generated report structure with a broker update layout while preserving internal data-governance gates.
- structural changes: first page now uses a compact titlebar, left recommendation/sidebar column, right thesis/update narrative column, broker-style side tables, and a financial-summary table.
- follow-on pages now use compact repeated page headers similar to institutional update reports.
- generated html path: `artifacts/reports_html/ACBS_LAYOUT_FINAL_20260601_DBD_report.html`
- generated pdf path: `artifacts/reports_pdf/ACBS_LAYOUT_FINAL_20260601_DBD_report.pdf`
- PDF backend used: headless Chrome fallback after WeasyPrint reported missing Windows GTK libraries.
- focused regression command: `python -m pytest tests/unit/test_report_data_loader_gates.py tests/unit/test_section_builder.py tests/unit/test_html_renderer.py tests/unit/test_pdf_renderer.py tests/unit/test_chart_generator.py -q`
- focused regression result: `47 passed`
- PDF text extraction result: `{'box': False, 'duoc': True, 'binh_dinh': True, 'acbs_layout': True, 'dang_ra_soat': True, 'target_leak': False, 'upside_leak': False, 'buy_leak': False}`

## Client/Analyst Render-Mode Pass

- reference plans: `.claude/implement-plan.md`, `.claude/Key report.md`
- new architecture: `ClientReportViewModel` / `report_content_manifest` now separates client-facing content from internal governance artifacts.
- new render modes: `client_final`, `analyst_draft`, `internal_debug`.
- strict client command: `python scripts/render_report.py --ticker DBD --mode client_final --strict --pdf --run-id ACBS_LAYOUT_FIX_20260601`
- strict client result: blocked as expected because the latest `valuation_results` artifact has missing/zero current price, target price, and upside.
- review packet path: `artifacts/review_packets/ACBS_LAYOUT_FIX_20260601_DBD_client_final_review_packet.html`
- analyst draft command: `python scripts/render_report.py --ticker DBD --mode analyst_draft --pdf --run-id ACBS_LAYOUT_FIX_DRAFT_20260601`
- analyst draft html path: `artifacts/reports_html/ACBS_LAYOUT_FIX_DRAFT_20260601_DBD_report.html`
- analyst draft pdf path: `artifacts/reports_pdf/ACBS_LAYOUT_FIX_DRAFT_20260601_DBD_report.pdf`
- PDF backend used: headless Chrome fallback after WeasyPrint reported missing Windows GTK libraries.
- PDF text extraction result: `{'box': False, 'forbidden_count': 0, 'required_missing_count': 0, 'file_footer': False, 'chars': 5540}`
- focused regression command: `python -m pytest tests/unit/test_client_report_contract.py tests/unit/test_pdf_renderer.py tests/unit/test_report_data_loader_gates.py tests/unit/test_section_builder.py tests/unit/test_html_renderer.py tests/unit/test_chart_generator.py -q`
- focused regression result: `51 passed`

## Driver-Based Analyst Draft Pass

- reference plan: `DRIVER_BASED_FINANCIAL_MODELLING_PLAN.md`
- implementation intent: reduce missing numeric rows and replace generic narrative with driver-linked analysis tied to current DBD operating context.
- generated html path: `artifacts/reports_html/DRIVER_FIX_DRAFT_20260601_DBD_report.html`
- updated calculations: actual EPS restored for 2024A/2025A; effective tax rate renders as percentage; forecast CFO is calculated from net income, depreciation, and change in working capital; net debt, net debt/EBITDA, EV/FCF, PEG, dividend per share, dividend yield, and driver sensitivity are now populated.
- updated narrative: added current-context discussion covering ĐHĐCĐ 2026 guidance, Q1/2026 revenue/profit, GMP-EU/SVI projects, capex cycle, inventory, debt, API/FX pressure, and working-capital monitoring.
- HTML forbidden-term preflight: no matches for client-facing backend/debug blacklist.
- focused regression command: `python -m pytest tests/unit/test_client_report_contract.py tests/unit/test_pdf_renderer.py tests/unit/test_report_data_loader_gates.py tests/unit/test_section_builder.py tests/unit/test_html_renderer.py tests/unit/test_chart_generator.py -q`
- focused regression result: `52 passed`
- PDF generation status: not regenerated in this pass because the sandbox requires headless Chrome escalation and the escalation request was rejected by the runtime usage limit. Use `python scripts/render_report.py --ticker DBD --mode analyst_draft --pdf --run-id DRIVER_FIX_DRAFT_20260601` after escalation capacity is restored.
