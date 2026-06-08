# Audit A: Calculation Lineage Map
**Date:** 2026-06-07
**Scope:** End-to-end data flow from raw source → canonical fact → valuation number → report cell

---

## A1. Pipeline Entry Points (CLI Commands)

| Command | Script | Purpose |
|---------|--------|---------|
| `python scripts/run_valuation.py --ticker DHG` | `scripts/run_valuation.py` | Full valuation run: ingest facts → compute FCFF/blend → write artifact |
| `python scripts/auto_ingest_official_documents.py --ticker DBD` | `scripts/auto_ingest_official_documents.py` | PDF extraction → canonical facts |
| `python scripts/render_report.py --ticker DHG` | `scripts/render_report.py` | Load artifact → render HTML/PDF |

---

## A2. Pipeline Stage Sequence

```
Stage 1:  PDF/CSV Ingestion
          scripts/auto_ingest_official_documents.py
          scripts/connectors/vnstock_finance_connector.py
                ↓
Stage 2:  Raw fact extraction
          backend/documents/pdf_extractor.py  (OCR + regex)
          backend/facts/normalizer.py         (unit conversion + FactEntry wrapping)
                ↓
Stage 3:  Canonical fact store
          FactTable = dict[str, dict[str, FactEntry]]
          Persisted to PostgresFactStore or in-memory dict
                ↓
Stage 4:  Data quality gate
          backend/analytics/approval_gate.py  (data_quality_passed flag)
          Minimum: ≥3 FY periods, required fields present, confidence ≥ 0.80
                ↓
Stage 5:  Analytics computation (deterministic Python only)
          backend/analytics/ratios.py         → gross_margin, net_margin, ROE, ROA
          backend/analytics/forecasting.py    → 5-year P&L + balance sheet forecast
          backend/analytics/debt_schedule.py  → net_borrowing schedule
          backend/analytics/fcff.py           → FCFF + WACC + terminal value + EV → equity
          backend/analytics/fcfe.py           → FCFE + Re + terminal value → equity (supplementary)
          backend/analytics/blend.py          → 60% FCFF + 40% P/E Forward → target price
          backend/analytics/sensitivity.py    → WACC×g grid, EPS×PE grid
          backend/analytics/core_pe_net_cash.py → Core EPS + net cash variant
          backend/analytics/net_debt_bridge.py  → net debt = debt - cash - STI
                ↓
Stage 6:  Valuation artifact write
          artifacts/valuation/{TICKER}_{timestamp}_valuation.json
                ↓
Stage 7:  Report data loading
          backend/reporting/report_data_loader.py  → extracts prices, ratios, multiples, sensitivity
          backend/reporting/client_report_view_model.py  → typed view model
          backend/reporting/section_builder.py  → 8 editorial sections
                ↓
Stage 8:  Rendering
          backend/reporting/html_renderer.py  → Jinja2 → HTML
          backend/reporting/pdf_renderer.py   → WeasyPrint/Chrome → PDF
```

---

## A3. HITL Pause Points

| Stage | Gate | What analyst must approve |
|-------|------|--------------------------|
| After Stage 5 (valuation) | `assumption_status == "approved"` | WACC, terminal growth, forecast margins, target P/E, peer group |
| After Stage 7 (report draft) | `final_recommendation_approved == True` | Final recommendation, narrative, citation coverage |

Until `final_recommendation_approved = True`, the report shows "ĐANG HOÀN THIỆN" (not the computed rating) and `is_draft_only = True`.

---

## A4. Artifact Types and Locations

| Artifact | Location Pattern | Format |
|----------|-----------------|--------|
| Raw PDF extraction | `artifacts/raw/{ticker}_{doc_id}.json` | JSON |
| Valuation artifact | `artifacts/valuation/{ticker}_{ts}_valuation.json` | JSON |
| Report HTML | `artifacts/reports/{ticker}_{ts}_report.html` | HTML |
| Report PDF | `artifacts/reports/{ticker}_{ts}_report.pdf` | PDF |
| Golden CSV facts | `config/dataset/golden/financials/{ticker}.csv` | CSV |
| Provenance metadata | `config/dataset/golden/financials/{ticker}_golden_provenance.json` | JSON |
| Universe registry | `config/dataset/universe/pharma_vn_universe.csv` | CSV (53 tickers) |

---

## A5. Data Flow: Single Number Trace (DBD Revenue 2025)

```
Source: Official BCTC PDF  (Tier 0 — audited)
  → pdf_extractor.py  →  raw_value = 1865.380, raw_unit = "vnd_bn"
  → normalizer.validate_and_normalize("revenue.net", 1865.380, "vnd_bn")
  → multiplier = 1_000_000_000.0  (VND bn → absolute VND)
  → FactEntry(value=1865.380, source_tier=0, confidence=0.95, source_uri=<url>)
  → FactTable["revenue.net"]["2025FY"] = FactEntry(...)
  → ratios.py: gross_margin = gross_profit / revenue.net = 884.379 / 1865.380 = 0.4741
  → forecasting.py: revenue_growth_base = CAGR(2022..2025)
  → fcff.py: ebit * (1 - tax_rate) + dep - capex - delta_nwc = FCFF_2026F
  → blend.py: 0.60 × price_fcff + 0.40 × (eps_fy1 × target_pe)
  → artifact: blend_dcf.target_price_dcf_vnd = <result>
  → report_data_loader._extract_prices(): target_price = artifact["blend_dcf"]["target_price_dcf_vnd"]
  → ClientReportViewModel.target_price_vnd = <result>
  → report HTML: displayed in cover hero table
```

---

## A6. LLM Involvement Map

| Stage | LLM Used? | What LLM Does |
|-------|-----------|---------------|
| Stages 1–6 (all analytics) | **NO** | Zero LLM in any of 19 analytics modules |
| Stage 7 (narrative sections) | **YES — draft text only** | investment_thesis, risk_narrative, company_description prose |
| Stage 7 (numbers in report) | **NO** | All numbers from locked artifact, not from LLM |
| Stage 8 (rendering) | **NO** | Pure template rendering |

All 19 `backend/analytics/*.py` modules contain explicit docstring: `"All arithmetic is deterministic Python — no LLM involvement."`

---

## A7. Missing Data Handling

| Input | Missing Behavior | Blocks what |
|-------|-----------------|-------------|
| `total_debt` fact | `net_debt_bridge.status = "blocked"` | FCFF target price |
| `shares_outstanding` | `target_price = None` + warning | All per-share prices |
| WACC ≤ terminal_growth | `status = "INVALID"`, target_price blocked | FCFF terminal value |
| Re ≤ terminal_growth | `status = "INVALID"`, target_price blocked | FCFE terminal value |
| `peer_data_source = None` | `implied_price_pe = null` | Multiples relative valuation |
| Forecast confidence < high | `is_fcfe_publishable = False` | FCFE publishability |
