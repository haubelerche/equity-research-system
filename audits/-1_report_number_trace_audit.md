# Audit G: Report Number Trace Audit
**Date:** 2026-06-07
**Scope:** How each number in the rendered report is traced back to its source

---

## G1. Report Data Loading Architecture

**File:** `backend/reporting/report_data_loader.py` (1304 lines)

The loader reads from the valuation artifact JSON and provides structured data to
`ClientReportViewModel`. It does **not** recompute any numbers — it only extracts
and formats values from locked artifacts.

---

## G2. Price, Target, Upside — Extraction

**File:** `backend/reporting/report_data_loader.py:463-507`

```python
def _extract_prices(val: dict) -> tuple[float|None, float|None, float|None]:
    # New format (DHG+): blend_dcf section
    current_price = val.get("blend_dcf", {}).get("current_price_vnd")
    target_price = val.get("blend_dcf", {}).get("target_price_dcf_vnd")

    # Old format (DBD legacy): root-level fields
    if not current_price:
        current_price = val.get("current_price_vnd")
    if not target_price:
        target_price = val.get("dcf", {}).get("base", {}).get("intrinsic_value_per_share_vnd")

    upside = (target - current) / current if target and current else None
    return (current_price, target_price, upside)
```

**Upside unit:** decimal (0.20 = 20%). **Not percentage points.**

---

## G3. Financial Ratios — Extraction

**File:** `backend/reporting/report_data_loader.py:570+`

```python
def _build_fin_table(val: dict) -> list[FinTableRow]:
    ratios = val.get("ratios", {})
    # Uses latest 4 periods (or all if <4 available)
    # Converts to percentage display format
    # Sources: gross_margin, net_margin, roe, roa, revenue_growth
    # All from ratios artifact — no hardcoded values
```

**No independent recomputation** — all ratio values come from the artifact.
DHG 2025FY gross margin from artifact: 0.4741 → displayed as "47.4%"

---

## G4. FCFF Schedule — Extraction

**File:** `backend/reporting/report_data_loader.py:510-530`

```python
def _extract_fcff(val: dict) -> dict:
    # New format:
    return val.get("fcff", {})
    # Returns: wacc, terminal_growth, forecast_schedule, assumption_status
```

The forecast_schedule table (per-year FCFF rows) is passed directly to the template.
No recomputation at the report stage.

---

## G5. Multiples — Extraction

```python
def _extract_multiples(val: dict) -> dict:
    return val.get("multiples", {})    # report_data_loader.py:533-535
```

This is a direct accessor — no transformation.

---

## G6. Sensitivity Tables — Extraction

**File:** `backend/reporting/report_data_loader.py:538-565`

```python
def _extract_sensitivity(val: dict) -> dict:
    # New format: val['sensitivity']['fcff_wacc_g']['matrix']
    # Old format: val['sensitivity']['matrix']
    # Returns: {wacc_range, g_range, matrix}
```

Matrix values are passed directly to the Jinja2 template.

---

## G7. View Model Construction

**File:** `backend/reporting/client_report_view_model.py`

`build_client_report_view_model(ticker, mode, allow_latest_artifacts)` factory:
1. Loads latest valuation artifact for ticker
2. Calls `_extract_prices()`, `_extract_fcff()`, `_extract_multiples()`, etc.
3. Populates `ClientReportViewModel` typed fields
4. Computes recommendation from upside (via `_recommendation()`)
5. Marks `is_draft_only` if blend gates fired

**Target price source priority:**
1. `core_pe_net_cash.target_price_vnd` (if present and non-None)
2. `blend_dcf.target_price_dcf_vnd` (primary)
3. None (if both missing)

---

## G8. Section Builder

**File:** `backend/reporting/section_builder.py`

`build_client_report_sections(vm)` creates 8 sections:
1. Cover / Executive Summary
2. Company Overview
3. Industry Overview
4. Financial Analysis
5. Valuation (FCFF, blend, P/E)
6. Sensitivity Analysis
7. Risks
8. Disclaimer

Each section receives the `ClientReportViewModel` — there is no independent number
computation in `section_builder.py`. All numbers come from the `vm` object.

---

## G9. HTML / PDF Rendering

**Files:** `backend/reporting/html_renderer.py`, `backend/reporting/pdf_renderer.py`

- `HTMLRenderer.render(ctx)` → Jinja2 template → `report.html.j2`
- `PDFRenderer.render(html_bytes)` → WeasyPrint or Chrome headless → PDF

Template: `backend/reporting/templates/report.html.j2`

Vietnamese Unicode preserved throughout the render chain.

---

## G10. Number Integrity Checks

| Check | Where | Status |
|-------|-------|--------|
| All numbers from locked artifact | report_data_loader.py | ✓ |
| No recomputation at report stage | section_builder.py | ✓ |
| Upside in decimal, not % | client_report_view_model.py | ✓ |
| Missing → None (not 0) | _pct(), _latest_val_or_none() | ✓ |
| Fallback to DB if artifact missing | _load_db_facts() lines 249-274 | ✓ |
| Recommendation gated by approval | `approved_for_display` flag | ✓ |

---

## G11. Export Gate

**File:** `backend/reporting/export_gate.py`

The export gate runs a final validation checklist before rendering the final PDF:
- 100% quantitative citation coverage (approved reports only)
- Numeric consistency within tolerance
- Valuation reproducible from saved assumptions
- No internal terms (gate names, tier labels, stack traces) in output
- HITL approval flags set

Any `severity: critical` finding → blocks export, sets status `NEEDS_REVIEW`.
