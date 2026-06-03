# EXECUTION STATE

> Auto-updated after each task. Source of truth for current build position.

---

## Current State

```
Active workstream:   PLAN_FIX_TICKERS/ — fix client-facing report output (PLAN_FIX_ALL_TICKERS + GOAL_OUTPUT)
                     DONE (7 phases): 03 forecast columns+drivers, 02 MarketSnapshot+shares,
                       05 target price + valuation_result.json (GOAL §13), 01 export gate
                       (shares↔EPS guard), 04 debt/dividend schedules + net debt/EBITDA +
                       dividend yield, 06 WACC×g sensitivity matrix, 09-core C1 price chart.
                     DBD end-to-end: rating BÁN, target 30,409 (=0.6×35,767+0.4×22,372),
                       periods 2022FY..2030F, sidebar filled, sensitivity matrix real,
                       client_final missing_required_fields = ['approval_status'] ONLY.
                       766 unit tests pass.
                     REMAINING: 07 narrative (≥300 words/section, artifact-grounded),
                       08 citation rendering + sources table, 09 CSS layout (IMP style) + font QA.
                     KEY FILES: backend/reporting/client_report_view_model.py,
                       backend/reporting/market_snapshot.py (NEW),
                       scripts/generate_report.py + run_valuation.py (inject shares),
                       scripts/generate_charts.py (C1 from vnstock Quote).
                     KEY FACT: shares_outstanding is market-source (vnstock VCI overview
                       issue_share), absent from canonical facts; injected at valuation time.
                       Both generate_report.py AND run_valuation.py do the injection.

Current Level:       Level 10 — Render-ready
Target Level:        Level 10 — Render-ready (charts + HTML + PDF + 5 artifact contracts per GOAL_OUTPUT.md)
Current Phase:       Phase 16 — Database Quality & Schema Cleanup — 2026-06-02
Last Completed Task: DATABASE_QUALITY_SYSTEM_CONSISTENCY_AUDIT.md — schema cleanup.
                     - Migration 015: drops 7 unused research schema tables (metric_values,
                       valuation_assumption_sets, valuation_results, report_sections,
                       report_claims, claim_evidence, evaluation_results) + their trigger/
                       views; drops fact.financial_facts_legacy dead-alias view.
                     - Migration 015: fixes corrupted Vietnamese company names in ref.companies
                       (005 had N'' T-SQL prefix that stored '?' instead of UTF-8 chars).
                     - 005_seed_reference_data.sql: removed N'' prefix, corrected all
                       Vietnamese display_name_vi strings to proper UTF-8.
                     - CURRENT_SCHEMA_VERSION bumped to 015_cleanup_redundant_schema.
                     - Removed 2 dead integration tests for dropped schema objects.
                     - 553 unit tests pass, 0 failures.
```

---

## Phase Completion Summary

| Phase | Script / Module | Status | Evidence |
|-------|----------------|--------|----------|
| 0 — Repo Audit | `specs/00_REPO_AUDIT.md` | DONE | Specs written |
| 1 — Data Contracts | `specs/03–07_*.md` | DONE | Specs written |
| 2 — Ingestion MVP | `scripts/ingest_ticker.py` | DONE | All 5 tickers ingested |
| 3 — Canonical Facts | `scripts/build_facts.py` | DONE | DQ gates pass for all 5 |
| 4 — Valuation | `scripts/run_valuation.py` | DONE | DCF/P-E/EV-EBITDA artifacts |
| 5 — Evidence Index | `scripts/build_index.py` | DONE | Chunks indexed in DB |
| 5b — Retrieval Test | `scripts/test_retrieval.py` | DONE | 4/4 gates pass for DHG |
| 6 — Report Generation | `scripts/generate_report.py` | DONE | Markdown + citations |
| 7 — Evaluation | `scripts/evaluate_report.py` | DONE | 5 deterministic gates |
| 8 — Stateful Workflow | `scripts/run_research.py` | DONE | Full pipeline + DB logging |
| 9 — Human Approval | `scripts/approve_report.py` | DONE | Export + approval record |
| 9b — Scheduler | `backend/jobs/scheduler.py` | DONE | 3 cron jobs registered |
| 10 — DataFoundationAgent | `backend/agents/data_foundation_agent.py` | DONE | All 5 tickers READY |
| 11 — Unit Tests | `tests/unit/` | DONE | 94 tests, 0 failures |
| 12 — Data Trust Layer | `backend/citations/`, `backend/evaluation/` | DONE | 468 tests, 0 failures; FactEntry provenance; 6-gate evaluator; catalyst rendering |
| 13 — Evidence Retrieval + Citation Pipeline | `scripts/build_index.py`, `backend/retrieval.py`, `scripts/evaluate_citations.py` | DONE | 670 tests, 0 failures; OCR page indexing; DB retrieval with tier priority; citation coverage gate |
| 14 — Full Rendering Pipeline | `backend/reporting/`, `scripts/generate_charts.py`, `scripts/render_report.py`, `scripts/run_full_pipeline.py` | DONE | 726 tests, 0 failures; all 5 tickers: charts=6, html=yes, artifacts=5 |
| 15 — Code Quality Audit | `CODE_QUALITY_SYSTEM_CONSISTENCY_AUDIT.md` | DONE | 779 tests, 0 failures; encoding fixed, period regex hardened, source_id coercion removed, forbidden terms corrected |
| 16 — DB Schema Cleanup | `DATABASE_QUALITY_SYSTEM_CONSISTENCY_AUDIT.md` | DONE | 553 tests, 0 failures; migration 015, 7 dead tables dropped, company names fixed, schema_version 015 |

---

## Level 3 Completion Evidence (Fact-Ready)

| Ticker | FY Periods | coverage_gate | core_keys_gate | source_validation_gate | valuation_gate | valuation_ready |
|--------|-----------|--------------|----------------|----------------------|----------------|-----------------|
| DHG    | 5 (2021–2025) | pass | pass | pass | pass | True |
| IMP    | 4 (2022–2025) | pass | pass | pass | pass | True |
| DMC    | 4 (2022–2025) | pass | pass | pass | pass | True |
| TRA    | 4 (2022–2025) | pass | pass | pass | pass | True |
| DBD    | 4 (2022–2025) | pass | pass | pass | pass | True |

---

## Level 4+ Completion Evidence (Calculation + Report + Evaluation)

### DHG Full Pipeline Run (latest)
- **snapshot_id**: `snap_0c2fbaf394e8fbc5ac14`
- **DCF base**: 137,010 VND/share (intrinsic)
- **Market price**: 94,400 VND/share → upside 45.1%
- **P/E 15x implied**: 94,620 VND/share
- **EV/EBITDA 10x implied**: 109,608 VND/share
- **Evaluation**: WARN (numeric_consistency), 4x PASS → OVERALL: WARN
- **Status**: REPORT_READY → approved and exported

Artifact paths:
- `artifacts/valuation/DHG_*_valuation.json`
- `artifacts/facts/DHG_*_fact_report.json`
- `artifacts/evaluation/DHG_*_evaluation.json`
- `reports/DHG_*_full_report.md`
- `reports/approved/DHG_*_APPROVED*.md`

---

## Unit Test Suite

```
tests/unit/                        — normalizer, ratios, dcf, data_quality, gate_validation, etc.
tests/citations/                   — citation_map, event_linker, validator, driver_evidence,
                                     evaluate_citations (19 new)
tests/evaluation/                  — numeric_claim_gates, catalyst_evidence_gates, final_source_gates
tests/catalysts/                   — event_extraction
tests/reconciliation/              — financial_fact_reconciliation
tests/sources/                     — source_registry, document_fetcher
tests/official_sources/            — official_document_ingestion, build_index_ocr (11 new)
tests/schema/                      — dual_source_schema
tests/documents/                   — company_ir_connector

Total: 726 passed, 0 failed (as of 2026-06-01)
```

---

## Key Architecture Files

| Module | Purpose |
|--------|---------|
| `backend/facts/normalizer.py` | Build fact table, compute derived metrics (EBITDA, FCF, margins) |
| `backend/facts/completeness.py` | Three-tier DQ gate: coverage, core_keys, source_validation |
| `backend/analytics/ratios.py` | Deterministic ratio calculations |
| `backend/analytics/dcf.py` | Two-stage DCF + 3-scenario (bear/base/bull) |
| `backend/analytics/multiples.py` | P/E and EV/EBITDA valuation |
| `backend/analytics/sensitivity.py` | WACC × terminal growth sensitivity table |
| `backend/dataops/snapshot.py` | Research snapshots: frozen accepted facts for reproducible valuation |
| `backend/jobs/scheduler.py` | APScheduler: weekly_sync, daily_prices, monthly_valuation |
| `backend/agents/data_foundation_agent.py` | Orchestrates data preparation; assess/prepare/readiness report |

---

## Known Issues / Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Supabase pooler statement_timeout | Snapshot INSERT must use `execute_values(page_size=50)` | Fixed in snapshot.py |
| vnstock price unit (× 1000 error) | Price stored in thousands VND | Fixed: `return price * 1000` in run_valuation.py |
| EBITDA not ingested from API | EV/EBITDA unavailable without derivation | Fixed: derived from gross_profit + sga + depreciation |
| evaluation numeric_consistency WARN | Numbers in report differ slightly from source | Acceptable: formatting tolerance issue |
| APScheduler optional dependency | Scheduler silently disabled if not installed | `pip install apscheduler` |
| 2021FY data for IMP/DMC/TRA/DBD | vnstock API doesn't return 2021 data | Use golden CSV fallback when available |

---

## How to Run Full Pipeline (DHG)

```bash
# Step-by-step
python scripts/ingest_ticker.py --ticker DHG --years 5
python scripts/build_facts.py --ticker DHG
python scripts/run_valuation.py --ticker DHG
python scripts/build_index.py --ticker DHG
python scripts/test_retrieval.py --ticker DHG
python scripts/generate_report.py --ticker DHG --report-type full_report
python scripts/evaluate_report.py --ticker DHG
python scripts/approve_report.py --ticker DHG --decision approve

# Or one command:
python scripts/run_research.py --ticker DHG
python scripts/approve_report.py --ticker DHG --decision approve

# Data foundation check:
python -m backend.agents.data_foundation_agent --all
```

---

## DB State

- Schema version: `007_expand_line_items` (latest migration applied)
- All 5 tickers: 96 accepted facts each in `fact.financial_facts`
- Schemas: `ref`, `ingest`, `fact`, `research` all active
- `fact.accepted_financial_facts` view: 4–5 FY periods × 24 line items per ticker
- `research.snapshots` + `research.snapshot_items`: DHG snapshot active
- `research.runs` + `research.run_steps`: DHG pipeline run logged
- `research.run_approvals`: DHG approval record saved
