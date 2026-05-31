# Vietnam Pharma Equity Research Agent — Architecture

> Hệ thống **AI-assisted equity research pipeline** cho cổ phiếu ngành y dược Việt Nam.
> Build-state hiện tại: **Level 9 — Scale-ready (5/5 MVP tickers complete)**.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Design Principles](#2-design-principles)
3. [MVP Scope](#3-mvp-scope)
4. [Technology Stack](#4-technology-stack)
5. [Project Structure](#5-project-structure)
6. [Database Schema](#6-database-schema)
7. [Pipeline Workflow](#7-pipeline-workflow)
8. [Data Contracts](#8-data-contracts)
9. [Analytics Engine](#9-analytics-engine)
10. [Valuation Methodology](#10-valuation-methodology)
11. [Evaluation Framework](#11-evaluation-framework)
12. [Agent and Orchestration Layer](#12-agent-and-orchestration-layer)
13. [Human Review and Approval](#13-human-review-and-approval)
14. [Artifacts and Outputs](#14-artifacts-and-outputs)
15. [Testing](#15-testing)
16. [Deployment and Operations](#16-deployment-and-operations)
17. [Known Limitations](#17-known-limitations)
18. [Disclaimer](#18-disclaimer)

---

## 1. Executive Summary

Hệ thống hỗ trợ analyst sinh **bản nháp báo cáo phân tích và định giá cổ phiếu ngành y dược Việt Nam**. Mọi số liệu định lượng được tính bằng code Python xác định, mọi claim quan trọng được truy vết về nguồn, và báo cáo cuối phải được analyst phê duyệt trước khi xuất bản.

Hệ thống **không phải**:
- Bot giao dịch tự động.
- Chatbot tài chính tự do.
- Công cụ sinh số liệu bằng LLM.

Pipeline cốt lõi:

```text
Ingest → Canonical Facts → Data Quality Gates
→ Code-First Valuation → Evidence Retrieval
→ Report Generation → Evaluation Gate
→ Human Approval → Export
```

**Build state (2026-05-30):**

| Level | Name | Status |
|---|---|---|
| 1 | Spec-ready | `completed` |
| 2 | Data-ready | `completed` |
| 3 | Fact-ready | `completed` |
| 4 | Calculation-ready | `completed` |
| 5 | Grounding-ready | `completed` |
| 6 | Report-ready | `completed` |
| 7 | Eval-ready | `completed` |
| 8 | Demo-ready | `completed` |
| 9 | Scale-ready | `completed` — 5/5 MVP tickers |

---

## 2. Design Principles

### 2.1 Code-first quantitative analysis

LLM không được tính toán kết quả tài chính cuối cùng. Các thành phần sau chạy bằng code Python xác định:

- Financial ratios, growth metrics, margin analysis.
- Peer comparison.
- FCFF DCF, FCFE DCF, Blend DCF (60% FCFF + 40% FCFE).
- Relative valuation (P/E, EV/EBITDA).
- Sensitivity analysis (WACC × terminal growth grid).
- TaxPolicy, DebtSchedule, DividendSchedule.
- Numeric consistency checking.

LLM chỉ được dùng cho: tóm tắt tài liệu, trích xuất có schema, sinh narrative tiếng Việt có grounding, phát hiện mâu thuẫn.

### 2.2 Every number must be traceable

Mọi số liệu trong báo cáo phải truy vết về canonical fact record hoặc source document chunk. Nếu không truy vết được, số liệu không được xuất hiện trong report final.

### 2.3 Evaluation before scaling

Không mở rộng scope trước khi evaluation gates tồn tại. Minimum gates:

- Numeric consistency.
- Citation coverage.
- Stale data detection.
- Valuation reproducibility.
- Unsupported recommendation detection.
- Tax/CAPEX/Debt consistency (deterministic checks).

### 2.4 Human-in-the-loop

Hệ thống phải yêu cầu human approval trước khi xuất final report. `ApprovalGate` block BUY/HOLD/SELL cho đến khi analyst phê duyệt.

### 2.5 Do not over-agentize

```text
service/module = deterministic technical capability
workflow node  = one step in the run lifecycle
agent role     = LLM-assisted reasoning role
```

Ingestion, normalization, valuation, citation validation là services — không phải LLM agents.

---

## 3. MVP Scope

### 3.1 Ticker Universe (5 tickers)

```text
DHG — Dược Hậu Giang (HOSE)
IMP — Imexpharm (HOSE)
DMC — Domesco (HOSE)
TRA — Traphaco (HNX)
DBD — Dược Bình Định (HOSE)
```

Cấu hình trong `dataset/universe/` và `dataset/mvp/mvp5_scope.yaml`.

### 3.2 Fiscal year coverage

| Ticker | FY periods | Coverage gate |
|---|---|---|
| DHG | 5 FY (2021–2025) | pass |
| IMP | 4 FY (2022–2025) | pass |
| DMC | 4 FY (2022–2025) | pass |
| TRA | 4 FY (2022–2025) | pass |
| DBD | 4 FY (2022–2025) | pass |

Gate passes at ≥ 3 FY periods (per memory: `project_mvp_scope.md`).

### 3.3 Out of scope for MVP

- SEC XBRL / OpenFDA / ClinicalTrials.gov.
- Fully autonomous multi-agent planning.
- Real-time trading signals.
- Expansion to full 53-ticker pharma universe.

---

## 4. Technology Stack

| Layer | Technology | Role |
|---|---|---|
| Backend API | FastAPI | REST endpoints cho pipeline orchestration |
| Database | Supabase / PostgreSQL | 4-schema DB: `ref`, `ingest`, `fact`, `research` |
| Schema | Pydantic v2 | Data contracts, structured output |
| LLM provider | OpenAI API | Report synthesis, evidence extraction |
| Primary model | gpt-4o | Reasoning, report generation |
| Fast model | gpt-4o-mini | Routing, simple extraction, JSON validation |
| Data processing | pandas, numpy | Financial calculations |
| Valuation | Custom deterministic Python modules | DCF, multiples, sensitivity, blend |
| Data source | vnstock (via connector abstraction) | VN stock market data |
| Vector store | Milvus (local) | Document chunk indexing for evidence retrieval |
| Scheduler | APScheduler | 3 cron jobs: weekly_sync, daily_prices, monthly_valuation |
| Config | YAML + Pydantic Settings | Universe, models, thresholds |
| Reporting | Python f-strings / Markdown templates | Report rendering |
| Testing | pytest | 25 test files, 200+ tests |
| Storage | Local files + Supabase/PostgreSQL | Artifacts, run logs, facts |

### 4.1 Environment variables

```text
DATABASE_URL          — Supabase PostgreSQL connection string
OPENAI_API_KEY        — OpenAI API key
SUPABASE_URL          — Supabase project URL (optional if DATABASE_URL set)
SUPABASE_SERVICE_KEY  — Supabase service role key (optional)
```

---

## 5. Project Structure

```text
vietnam-pharma-equity-agent/
├── ARCHITECTURE.md           — This file (source-of-truth architecture doc)
├── CLAUDE.md                 — Engineering principles, phase plan, coding standards
├── CHANGELOG.md
├── README.md
├── GOAL_OUTPUT.md
├── AUDIT_SUMMARY.md
│
├── specs/                    — Canonical specs (all 7 + progress tracker)
│   ├── 00_REPO_AUDIT.md
│   ├── 01_IMPLEMENTATION_ROADMAP.md
│   ├── 02_ARCHITECTURE_DECISIONS.md
│   ├── 03_DATA_CONTRACTS.md
│   ├── 04_CANONICAL_FACT_SCHEMA.md
│   ├── 05_SOURCE_METADATA_SCHEMA.md
│   ├── 06_REPORT_TEMPLATE.md
│   ├── 07_EVALUATION_RUBRIC.md
│   └── LEVEL_PROGRESS.md     — 9-level build tracker (source-of-truth for build state)
│
├── docs/                     — Product and architecture documentation
│   ├── PRD.md
│   ├── PROBLEM-BRIEF.md
│   ├── AI_PRODUCT_SPEC.md
│   ├── DATA_ARCHITECTURE.md
│   └── SEQUENCE.md
│
├── backend/                  — Core backend modules
│   ├── main.py               — FastAPI app entry point
│   ├── api.py                — API route definitions
│   ├── orchestrator.py       — Pipeline orchestration logic
│   ├── schemas.py            — Pydantic data models
│   ├── settings.py           — Config via environment variables
│   ├── services.py           — High-level service layer
│   ├── retrieval.py          — Evidence retrieval stub (Level 5)
│   ├── utils.py
│   ├── batch.py              — Batch ticker processing
│   ├── executor.py
│   ├── runtime_store.py
│   │
│   ├── facts/                — Canonical fact layer
│   │   ├── normalizer.py     — build_fact_table(), compute_derived()
│   │   ├── completeness.py   — 3-tier DQ gate: coverage, core_keys, source_validation
│   │   ├── reconciliation.py — IS/BS/CF cross-check (with minority interest handling)
│   │   └── validation_report.py
│   │
│   ├── analytics/            — Deterministic valuation engine (NO LLM calls)
│   │   ├── ratios.py         — compute_ratios(), ratio_table_for_display()
│   │   ├── dcf.py            — run_dcf(), run_three_scenarios() (bear/base/bull)
│   │   ├── fcff.py           — FCFF DCF with WACC; CAPEX positive-outflow convention
│   │   ├── fcfe.py           — FCFE DCF with cost-of-equity; DebtSchedule integration
│   │   ├── blend.py          — Blend DCF (60% FCFF + 40% FCFE); is_draft_only flag
│   │   ├── forecasting.py    — 5-year driver-based P&L + balance sheet forecast
│   │   ├── multiples.py      — P/E, EV/EBITDA, P/B relative valuation
│   │   ├── sensitivity.py    — WACC × terminal growth sensitivity grid
│   │   ├── tax_policy.py     — Effective tax rate (historical median, fallback 20%)
│   │   ├── debt_schedule.py  — net_borrowing hierarchy (5-tier fallback)
│   │   ├── dividend_schedule.py — retained_earnings = NI × (1 − payout_ratio)
│   │   ├── approval_gate.py  — AssumptionGate: blocks BUY/HOLD/SELL until approved
│   │   └── valuation_confidence.py — per-component confidence (high/medium/low/unavailable)
│   │
│   ├── dataops/              — Data operations layer
│   │   ├── snapshot.py       — Research snapshots: frozen accepted facts
│   │   └── quality_report.py — Data quality reporting
│   │
│   ├── validation/           — Report validation layer
│   │   ├── confidence.py     — Confidence scoring
│   │   ├── market_alignment.py — Market data consistency checks
│   │   └── report_builder.py — Validation report assembly
│   │
│   ├── harness/              — LangGraph 5-agent harness, gates, checkpoints, model adapter
│   ├── agents/               — compatibility wrappers; production agent policy is config-driven
│   │
│   └── jobs/                 — Scheduled tasks
│       └── scheduler.py      — APScheduler: weekly_sync, daily_prices, monthly_valuation
│
├── config/agents/            — 5 product-agent YAML config and Markdown prompt library
│
├── scripts/                  — Runnable pipeline scripts
│   ├── ingest_ticker.py      — Phase 2: ingest raw data from vnstock
│   ├── build_facts.py        — Phase 3: normalize to canonical facts, DQ gate
│   ├── run_valuation.py      — Phase 4: DCF, multiples, sensitivity, blend
│   ├── build_index.py        — Phase 5: chunk docs, build Milvus index
│   ├── test_retrieval.py     — Phase 5b: test evidence retrieval
│   ├── generate_report.py    — Phase 6: generate Markdown report + citations
│   ├── evaluate_report.py    — Phase 7: legacy 5-gate evaluation
│   ├── evaluate_report_quality.py — Phase 7: 8-check quality gate (current)
│   ├── run_research.py       — Phase 8: full pipeline orchestration
│   ├── approve_report.py     — Phase 9: human approval + export
│   ├── validate_data.py      — Data validation across all 5 tickers
│   ├── cleanup_financial_facts.py
│   ├── debug_vnstock_financial_coverage.py
│   ├── _vnstock_path.py      — vnstock path bootstrap
│   │
│   ├── connectors/           — Data source adapters
│   │   ├── vnstock_finance_connector.py   — Financial statements via vnstock
│   │   ├── vnstock_price_connector.py     — Price/market data via vnstock
│   │   ├── vnstock_company_connector.py   — Company profile via vnstock
│   │   ├── vn_market_data_adapter.py      — Unified market data adapter
│   │   ├── catalyst_bhyt_connector.py     — BHYT tender data (stub)
│   │   ├── catalyst_dav_connector.py      — DAV regulatory data (stub)
│   │   ├── catalyst_hose_connector.py     — HOSE disclosures (stub)
│   │   └── catalyst_tender_connector.py   — Drug tender data (stub)
│   │
│   ├── db/                   — Database layer
│   │   ├── migrate.py        — Migration runner
│   │   ├── fact_store.py     — Fact CRUD operations
│   │   ├── source_registry.py — Source catalog management (upsert on conflict)
│   │   ├── milvus_store.py   — Milvus vector store operations
│   │   └── migrations/       — 9 SQL migrations (001–009)
│   │       ├── 001_ref_schema.sql
│   │       ├── 002_ingest_schema.sql
│   │       ├── 003_fact_schema.sql
│   │       ├── 004_research_schema.sql
│   │       ├── 005_seed_reference_data.sql
│   │       ├── 006_grants_and_privileges.sql
│   │       ├── 007_expand_line_items.sql
│   │       ├── 008_research_snapshots.sql
│   │       └── 009_cleanup_source_duplicates.sql
│   │
│   └── dataset/              — Dataset management utilities
│       ├── bootstrap_mvp_facts.py
│       ├── check_golden_facts.py
│       ├── chunk_pipeline.py
│       ├── config_io.py
│       ├── dqf.py
│       ├── manual_refresh.py
│       ├── offline_eval.py
│       ├── validate_contracts.py
│       ├── validate_universe.py
│       └── weekly_sync.py
│
├── dataset/                  — Dataset definitions and contracts
│   ├── contracts/            — JSON schemas for all data contracts
│   │   ├── financial_fact.schema.json
│   │   ├── source_version.schema.json
│   │   ├── document_chunk.schema.json
│   │   ├── citation.schema.json
│   │   ├── catalyst_event.schema.json
│   │   ├── agent_message.schema.json
│   │   └── tool_call.schema.json
│   ├── mvp/
│   │   ├── mvp5_scope.yaml   — 5-ticker MVP configuration
│   │   └── golden_facts_spec.yaml
│   ├── taxonomy/
│   │   ├── financial_taxonomy_vn_pharma.yaml
│   │   └── catalyst_taxonomy_vn_pharma.yaml
│   ├── sources/
│   │   └── source_catalog.yaml
│   ├── universe/             — Ticker universe definitions
│   ├── golden/               — Golden reference data per ticker
│   └── raw/                  — Raw ingested data (vnstock CSV)
│
├── artifacts/                — Generated run artifacts
│   ├── facts/                — {TICKER}_{ts}_fact_report.json
│   ├── valuation/            — {TICKER}_{ts}_valuation.json + gate.json
│   ├── forecast/             — {TICKER}_{ts}_forecast/fcff/fcfe/blend.json
│   ├── reports/              — {TICKER}_{ts}_full_report_citation.json
│   ├── evaluation/           — {TICKER}_{ts}_evaluation.json
│   ├── runs/                 — {TICKER}_{ts}_inventory.json + run_log.json
│   └── index/                — {TICKER}_{ts}_index_summary.json
│
├── reports/                  — Generated Markdown reports
│   ├── {TICKER}_{ts}_full_report.md
│   ├── approved/             — Analyst-approved final reports
│   │   ├── {ts}_APPROVED_{run_id}.md
│   │   └── {ts}_approval.json
│   ├── eval/                 — Quality gate results
│   │   ├── latest_quality_gate.json
│   │   └── latest_quality_gate.md
│   └── DATA_VALIDATION_REPORT_{TICKER}_*.md
│
├── tests/
│   ├── unit/                 — 25 test files, 200+ tests
│   │   ├── test_normalizer.py       — 17 tests
│   │   ├── test_ratios.py           — 19 tests
│   │   ├── test_dcf.py              — 19 tests
│   │   ├── test_data_quality.py     — 18 tests
│   │   ├── test_tax_policy.py       — 14 tests
│   │   ├── test_debt_schedule.py    — 16 tests
│   │   ├── test_approval_gate.py    — 14 tests
│   │   ├── test_dividend_schedule.py — 11 tests
│   │   ├── test_relative_valuation.py — 9 tests
│   │   ├── test_capex_sign_convention.py — 7 tests
│   │   ├── test_blend_draft_flag.py
│   │   ├── test_reconciliation.py
│   │   ├── test_validation_report.py
│   │   └── ... (others)
│   └── integration/
│       └── test_db_integrity.py
│
├── FinRobot/                 — Reference project (do not modify, do not import directly)
├── vnstock/                  — Local vnstock library (access via connectors only)
└── frontend/                 — Placeholder (deferred)
```

---

## 6. Database Schema

Supabase / PostgreSQL. Schema version: `009_cleanup_source_duplicates` (latest applied).

### 6.1 Schema overview

| Schema | Purpose |
|---|---|
| `ref` | Reference data: ticker universe, taxonomy, source catalog |
| `ingest` | Raw ingestion: source_versions, raw_payloads, financial_raw |
| `fact` | Canonical facts: financial_facts, accepted_financial_facts (view) |
| `research` | Research runs: snapshots, snapshot_items, runs, run_steps, run_approvals |

### 6.2 Key tables

```sql
-- ref schema
ref.tickers             -- Ticker universe (5 MVP tickers)
ref.taxonomy            -- Financial line item taxonomy
ref.source_catalog      -- Source type registry

-- ingest schema
ingest.sources          -- Source metadata (deduplicated via migration 009)
ingest.source_versions  -- Source version tracking (checksum, ingested_at)
ingest.financial_raw    -- Raw financial data rows from vnstock

-- fact schema
fact.financial_facts    -- Canonical facts (96 accepted facts per ticker)
fact.accepted_financial_facts  -- View: latest accepted facts per ticker/metric/FY

-- research schema
research.snapshots      -- Frozen accepted-fact snapshots for reproducible valuation
research.snapshot_items -- Snapshot line items
research.runs           -- Pipeline run metadata
research.run_steps      -- Individual step logs
research.run_approvals  -- Human approval records
```

### 6.3 Canonical financial fact

```sql
CREATE TABLE fact.financial_facts (
    fact_id         UUID PRIMARY KEY,
    ticker          TEXT NOT NULL,
    fiscal_year     INTEGER,
    quarter         INTEGER,        -- NULL for annual
    metric_name     TEXT NOT NULL,  -- e.g. "revenue.net"
    value           NUMERIC,
    unit            TEXT,           -- e.g. "VND_millions"
    currency        TEXT DEFAULT 'VND',
    source_id       UUID REFERENCES ingest.sources(source_id),
    confidence      NUMERIC,        -- 0.0–1.0
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## 7. Pipeline Workflow

### 7.1 Step-by-step commands

```bash
# Full pipeline for one ticker:
python scripts/ingest_ticker.py --ticker DHG --years 5
python scripts/build_facts.py --ticker DHG
python scripts/run_valuation.py --ticker DHG
python scripts/build_index.py --ticker DHG
python scripts/generate_report.py --ticker DHG --report-type full_report
python scripts/evaluate_report_quality.py --ticker DHG
python scripts/approve_report.py --ticker DHG --decision approve

# One-command wrapper:
python scripts/run_research.py --ticker DHG

# Data validation across all tickers:
python scripts/validate_data.py --ticker DHG
```

### 7.2 Stage dependencies

```text
ingest_ticker        → raw data in DB (ingest schema)
    ↓
build_facts          → canonical facts (fact schema) + DQ gate
    ↓
run_valuation        → valuation artifact + gate artifact + forecast artifact
    ↓
build_index          → Milvus chunk index (Level 5)
    ↓
generate_report      → Markdown report + citation map + ApprovalGate status
    ↓
evaluate_report_quality  → 8-check quality gate (PASS/WARN/FAIL)
    ↓
[HITL] approve_report    → approval record + final export
```

### 7.3 Run artifacts per stage

| Stage | Artifact |
|---|---|
| ingest | `artifacts/runs/{TICKER}_{ts}_inventory.json` |
| build_facts | `artifacts/facts/{TICKER}_{ts}_fact_report.json` |
| run_valuation | `artifacts/valuation/{TICKER}_{ts}_valuation.json` + `gate.json` |
| run_valuation | `artifacts/forecast/{TICKER}_{ts}_forecast/fcff/fcfe/blend.json` |
| generate_report | `reports/{TICKER}_{ts}_full_report.md` |
| generate_report | `artifacts/reports/{TICKER}_{ts}_full_report_citation.json` |
| evaluate | `artifacts/evaluation/{TICKER}_{ts}_evaluation.json` |
| approve | `reports/approved/{ts}_APPROVED_{run_id}.md` + `approval.json` |

---

## 8. Data Contracts

Data contracts are defined in `dataset/contracts/*.schema.json` and `specs/03–05_*.md`.

### 8.1 Source metadata (ingest.sources)

```yaml
source_id:       UUID
ticker:          str
source_type:     ["vnstock_finance", "vnstock_price", "vnstock_company", "golden_csv", "manual"]
source_title:    str
provider:        str          # "VCI", "KBS", etc.
fiscal_year:     int | null
quarter:         int | null
reliability_tier: int         # 1 = high, 2 = medium, 3 = low
checksum:        str
ingested_at:     datetime
```

### 8.2 Canonical financial fact

```yaml
fact_id:         UUID
ticker:          str
fiscal_year:     int
quarter:         int | null
metric_name:     str          # namespaced: "revenue.net", "equity.parent"
value:           float
unit:            str          # "VND_millions", "ratio", "percent"
currency:        str          # default "VND"
source_id:       UUID
confidence:      float        # 0.0–1.0
created_at:      datetime
```

### 8.3 Research snapshot

Snapshot = frozen copy of accepted facts at a point in time. Used for reproducible valuation.

```yaml
snapshot_id:     str
ticker:          str
created_at:      datetime
fiscal_years:    list[int]
items:           list[snapshot_item]
```

### 8.4 Valuation artifact

```yaml
valuation_id:    str
ticker:          str
method:          str          # "fcff_dcf", "fcfe_dcf", "blend_dcf", "pe", "ev_ebitda"
assumptions:     dict         # WACC, g, tax_rate, etc.
input_snapshot:  str          # snapshot_id
output_values:   dict         # intrinsic_value, equity_value_per_share, etc.
sensitivity_table: dict       # WACC × g grid
created_at:      datetime
```

### 8.5 Report approval record

```yaml
report_id:       str
ticker:          str
run_id:          str
decision:        str          # "approve" | "reject"
analyst_notes:   str | null
approved_at:     datetime
export_path:     str
```

---

## 9. Analytics Engine

Tất cả module trong `backend/analytics/` là **deterministic Python, không có LLM calls**.

### 9.1 Module summary

| Module | Function | Notes |
|---|---|---|
| `ratios.py` | `compute_ratios()`, `ratio_table_for_display()` | ROE, ROA, margins, leverage, liquidity, PE/PB/BVPS/CCC |
| `dcf.py` | `run_dcf()`, `run_three_scenarios()` | Two-stage DCF, bear/base/bull |
| `fcff.py` | `run_fcff_dcf()` | FCFF = EBIT(1-t) + Dep − ΔWC − CapEx; CAPEX positive-outflow |
| `fcfe.py` | `run_fcfe_dcf()` | FCFE = NI − ΔWC − CapEx + Net_borrowing |
| `blend.py` | `run_blend_dcf()` | 60% FCFF + 40% FCFE; `is_draft_only` flag khi gap > 25% |
| `forecasting.py` | `run_forecast()` | 5-year driver-based P&L + BS forecast (all line items) |
| `multiples.py` | `run_multiples()` | P/E, EV/EBITDA; requires peer_data_source |
| `sensitivity.py` | `run_sensitivity()` | WACC × g grid, 5×5 default |
| `tax_policy.py` | `TaxPolicy` | Historical effective rate (median), fallback 20% statutory |
| `debt_schedule.py` | `DebtSchedule` | net_borrowing: 5-tier hierarchy (CFO → BS delta → target ratio → zero → missing) |
| `dividend_schedule.py` | `DividendSchedule` | retained_earnings = NI × (1 − payout_ratio) |
| `approval_gate.py` | `AssumptionGate` | Blocks BUY/HOLD/SELL; emits `Draft / Needs Analyst Review` label |
| `valuation_confidence.py` | `ValuationConfidence` | Per-component confidence: high/medium/low/unavailable |

### 9.2 CAPEX convention

CAPEX được lưu và dùng theo **positive-outflow** convention: CapEx = 50 nghĩa là chi 50 tỷ. Cả FCFF và FCFE đều dùng quy ước này nhất quán.

---

## 10. Valuation Methodology

### 10.1 Blend DCF (primary method)

```text
Blend = 0.60 × FCFF_intrinsic + 0.40 × FCFE_intrinsic
```

Dùng Blend khi cả FCFF và FCFE đều có dữ liệu đầy đủ. `is_draft_only = True` khi:
- Chênh lệch FCFF vs FCFE > 25%, hoặc
- Một trong hai phương pháp thiếu dữ liệu.

### 10.2 FCFF DCF

```text
FCFF = EBIT × (1 − tax_rate) + Depreciation − ΔWorking_Capital − CapEx
FCFF = CFO + Interest × (1 − tax_rate) − CapEx

Firm Value = Σ FCFF_t / (1 + WACC)^t + TV / (1 + WACC)^n
Equity Value = Firm Value − Net Debt
Equity Value/Share = Equity Value / Shares Outstanding

Terminal Value = FCFF_{n+1} / (WACC − g)
```

### 10.3 FCFE DCF

```text
FCFE = NI − ΔWorking_Capital − CapEx + Net_Borrowing
FCFE = CFO − CapEx + Net_Borrowing

Equity Value = Σ FCFE_t / (1 + Ke)^t + TV / (1 + Ke)^n
```

### 10.4 Terminal value controls

```text
g < WACC (enforced)
g ≤ long-term Vietnam GDP growth (checked by ApprovalGate)
WACC, g, margin, growth assumptions must appear in valuation artifact
```

### 10.5 Relative valuation

| Multiple | Điều kiện dùng |
|---|---|
| P/E | EPS dương, lợi nhuận không bất thường |
| P/B | Book value đáng tin, equity dương |
| EV/EBITDA | Có dữ liệu EV và EBITDA |

Peer multiples yêu cầu `peer_data_source` (hiện tại: `pending_peer_dataset` — REL_01 WARN).

### 10.6 Sensitivity analysis

Minimum sensitivity grid:

```text
WACC × terminal_growth_rate (5×5 grid default)
```

Optional: revenue_growth × operating_margin.

### 10.7 Scenario analysis

| Scenario | Giả định |
|---|---|
| Bear | WACC +1%, g −0.5%, margin −2pp |
| Base | Historical median drivers |
| Bull | WACC −1%, g +0.5%, revenue growth +2pp (requires catalyst evidence) |

---

## 11. Evaluation Framework

### 11.1 Current evaluation script: `evaluate_report_quality.py`

8 deterministic checks (no LLM). Exit code: `0` for WARN, `1` for FAIL_BLOCK_EXPORT.

| Check ID | Description | Severity | DHG status |
|---|---|---|---|
| TAX_01 | Tax rate forecast = FCFF tax rate | CRITICAL | PASS |
| CAPEX_01 | CAPEX positive outflow in FCFF + FCFE | CRITICAL | PASS |
| DEBT_01 | No silent N/A in debt forecast rows | CRITICAL | PASS |
| FCFE_01 | FCFE includes non-None net_borrowing | WARNING | PASS |
| DIV_01 | Dividend schedule modeled or warned | WARNING | PASS |
| GATE_01 | No BUY/HOLD/SELL when gate not approved | WARNING | WARN |
| REL_01 | Relative valuation has peer dataset | WARNING | WARN |
| CONF_01 | Confidence artifact persisted per-run | INFO | WARN |

**All 5 MVP tickers: WARN_NEEDS_REVIEW (0 FAIL for all).**

### 11.2 Legacy evaluation: `evaluate_report.py`

5-gate evaluation (numeric/citation/staleness/reproducibility/recommendation_safety). Still used in `run_research.py` pipeline.

### 11.3 Data quality gates (build_facts.py)

Three-tier gate in `backend/facts/completeness.py`:

| Gate | Condition | Default threshold |
|---|---|---|
| `coverage_gate` | `periods_available ≥ 3 FY` | PASS if ≥ 3 |
| `core_keys_gate` | revenue.net, net_income.parent, equity.parent, total_assets.ending present | All required |
| `source_validation_gate` | Source tier ≤ 2 (medium or high) | Required |
| `valuation_gate` | All 4 gates above pass | Composite |

### 11.4 Report quality rubric

| Tiêu chí | Weight |
|---|---:|
| Factual accuracy | 25% |
| Citation completeness | 20% |
| Valuation discipline | 20% |
| Investment reasoning | 15% |
| Risk balance | 10% |
| Vietnamese financial writing | 10% |

### 11.5 Hallucination controls

Các claim sau bị cấm nếu không có evidence:

- Market leadership ("Doanh nghiệp dẫn đầu ngành...")
- Management quality
- Regulatory advantage
- Product pipeline
- Foreign investor interest
- Valuation certainty ("cổ phiếu chắc chắn đang rẻ...")

Khi thiếu dữ liệu: `"Dữ liệu hiện tại chưa đủ để kết luận về ..."`

---

## 12. Agent and Orchestration Layer

### 12.1 Product agents

Production orchestration uses a LangGraph harness with exactly five product agents. Their runtime policy is declared in `config/agents/agents.yml`; prompts live in `config/agents/prompts/`; deterministic services remain the source of truth for facts, valuation numbers, report files, quality gates, and citation checks.

| Agent | Runtime stage | Responsibilities |
|---|---|---|
| `SupervisorAgent` | `SUPERVISOR_PLAN` | execution plan, routing rationale, HITL/fallback policy |
| `DataRetrievalAgent` | `DATA_RETRIEVAL_RUN` | data inventory review, source coverage summary, missing evidence notes |
| `FinancialAnalystAgent` | `FINANCIAL_ANALYST_RUN` | qualitative interpretation of deterministic financial tables and anomaly notes |
| `ValuationAgent` | `VALUATION_RUN` | critique deterministic valuation artifacts, assumptions, sensitivity readiness, model limitations |
| `ReportWriterCriticAgent` | `REPORT_WRITER_CRITIC_RUN` | grounded narrative synthesis, factuality critique, final-readiness review |

### 12.2 LangGraph harness

The full-report workflow is:

```text
INIT
-> PREFLIGHT
-> SUPERVISOR_PLAN
-> DATA_RETRIEVAL_RUN
-> DATA_QUALITY_GATE
-> FINANCIAL_ANALYST_RUN
-> FINANCIAL_ANALYST_GATE
-> VALUATION_RUN
-> VALUATION_GATE
-> WAITING_ASSUMPTIONS_APPROVAL
-> VALUATION_LOCKED
-> REPORT_WRITER_CRITIC_RUN
-> QUALITY_EVALUATION
-> CITATION_GATE
-> EXPORT_GATE
-> WAITING_FINAL_APPROVAL
-> PUBLISHED
```

Approval is an external API transition, not an agent tool. Missing `OPENAI_API_KEY` fails in `PREFLIGHT` for v1 agent execution.

### 12.3 Pipeline orchestration

- `backend/orchestrator.py` delegates run lifecycle to `backend/harness/runner.py`.
- `scripts/run_research.py` calls the harness by default and keeps `--legacy-pipeline` for compatibility.
- `backend/jobs/scheduler.py` remains the APScheduler cron layer.
### 12.4 Scheduler (APScheduler)

3 registered cron jobs trong `backend/jobs/scheduler.py`:

| Job | Schedule | Action |
|---|---|---|
| `weekly_sync` | Weekly | Sync raw data from vnstock for all tickers |
| `daily_prices` | Daily | Update market price data |
| `monthly_valuation` | Monthly | Rebuild valuation artifacts |

---

## 13. Human Review and Approval

`ApprovalGate` (`backend/analytics/approval_gate.py`) là **hard gate** trước khi xuất recommendation.

### 13.1 Gate logic

- Khi tất cả critical flags (`dividend_schedule`, `peer_multiples`, etc.) được analyst phê duyệt → gate APPROVED.
- Khi gate chưa approved → `recommendation_label = "Draft / Needs Analyst Review"`.
- BUY / HOLD / SELL bị block cho đến khi gate APPROVED.

### 13.2 Approval workflow

```bash
# Analyst reviews report, then:
python scripts/approve_report.py --ticker DHG --decision approve --notes "Reviewed assumptions"

# Output:
# reports/approved/{ts}_APPROVED_{run_id}.md
# reports/approved/{ts}_approval.json (stored in research.run_approvals)
```

### 13.3 Gate artifact

```json
{
  "ticker": "DHG",
  "status": "draft_needs_analyst_review",
  "flags": {
    "dividend_schedule": false,
    "peer_multiples": false
  },
  "recommendation_label": "Draft / Needs Analyst Review (model-implied upside: +45.1%)",
  "created_at": "..."
}
```

---

## 14. Artifacts and Outputs

### 14.1 Report structure (generated)

Báo cáo tiếng Việt gồm:

1. Tóm tắt đầu tư và giá mục tiêu (Blend DCF + cross-checks).
2. Hồ sơ doanh nghiệp.
3. Phân tích tài chính lịch sử (ratio table: PE/PB/BVPS/ROE/ROA/Margins/Leverage/Liquidity/CCC).
4. Dự báo KQKD và BCĐKT 5 năm (tất cả line items).
5. Định giá DCF: FCFF / FCFE / Blend.
6. Sensitivity analysis (WACC × g grid).
7. Bear/Base/Bull scenarios.
8. Bộ phát hiện biến động bất thường.
9. Bảng rủi ro cấu trúc.
10. Key takeaways.
11. Phụ lục: WACC breakdown, assumptions, citation map, quality gate summary.
12. Disclaimer.

### 14.2 Report constraints

Báo cáo không được:
- Đưa lệnh mua/bán khi gate chưa approved.
- Tự tạo số liệu không trong canonical facts hoặc valuation artifact.
- Tạo citation giả.
- Khẳng định vị thế/quản lý/lợi thế pháp lý nếu không có evidence.

---

## 15. Testing

### 15.1 Test suite

```text
tests/unit/     — 25 test files
tests/integration/ — DB integrity tests

pytest tests/   — run all
pytest tests/unit/test_dcf.py -v
```

### 15.2 Key test files

| File | Tests | Coverage |
|---|---|---|
| `test_normalizer.py` | 17 | build_fact_table, compute_derived, periods_sorted |
| `test_ratios.py` | 19 | compute_ratios, ratio_table_for_display |
| `test_dcf.py` | 19 | run_dcf, run_three_scenarios |
| `test_data_quality.py` | 18 | build_fy_validation_report, completeness/freshness |
| `test_tax_policy.py` | 14 | TaxPolicy effective rate, fallback |
| `test_debt_schedule.py` | 16 | DebtSchedule 5-tier hierarchy |
| `test_approval_gate.py` | 14 | ApprovalGate block logic |
| `test_dividend_schedule.py` | 11 | DividendSchedule payout |
| `test_relative_valuation.py` | 9 | P/E, EV/EBITDA multiples |
| `test_capex_sign_convention.py` | 7 | CAPEX positive-outflow |
| `test_blend_draft_flag.py` | — | is_draft_only flag logic |
| `test_reconciliation.py` | — | IS/BS/CF reconciliation + minority interest |

### 15.3 Known test failures

`tests/unit/test_forecasting_gap.py` — 14 pre-existing failures (run_forecast() missing `n_years` param and `other_items` field). Pre-date current work. Not blocking.

---

## 16. Deployment and Operations

### 16.1 Prerequisites

```bash
pip install -r requirements.txt
# Required: DATABASE_URL, OPENAI_API_KEY
# Optional: apscheduler (for scheduler), pymilvus (for vector store)
```

### 16.2 DB setup

```bash
python scripts/db/migrate.py  # Apply all 9 migrations
```

### 16.3 First run

```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
python scripts/build_facts.py --ticker DHG
python scripts/run_valuation.py --ticker DHG
python scripts/generate_report.py --ticker DHG --report-type full_report
python scripts/evaluate_report_quality.py --ticker DHG
python scripts/approve_report.py --ticker DHG --decision approve
```

### 16.4 Batch mode (all 5 tickers)

```bash
for ticker in DHG IMP DMC TRA DBD; do
    python scripts/run_research.py --ticker $ticker
done
```

---

## 17. Known Limitations

| Issue | Impact | Status |
|---|---|---|
| REL_01: Peer multiples | P/E / EV/EBITDA cross-check uses default targets, không có real peer data | WARN — `pending_peer_dataset` |
| CONF_01: Confidence artifact | ValuationConfidence không được persist per-run | WARN — INFO severity |
| GATE_01: Gate check in eval | evaluate_report_quality không tự đọc report file để check BUY/SELL text | WARN — resolved với `--report-file` flag |
| IMP/DMC/TRA/DBD 2021 FY | vnstock VCI provider không trả 2021 data | Fallback KBS provider nếu có |
| Milvus optional | `build_index.py` requires running Milvus server | Graceful skip if unavailable |
| APScheduler optional | Scheduler silently disabled if not installed | `pip install apscheduler` |
| test_forecasting_gap.py | 14 pre-existing failures | Non-blocking, documented |
| Supabase statement_timeout | Large snapshot INSERTs cần `page_size=50` | Fixed in snapshot.py |

---

## 18. Disclaimer

Dự án này phục vụ mục đích học thuật và nghiên cứu. Kết quả phân tích không phải khuyến nghị đầu tư, không phải tư vấn tài chính cá nhân, không phải lời mời mua/bán chứng khoán và không đảm bảo lợi nhuận. Người dùng cần tự kiểm chứng dữ liệu, giả định, phương pháp định giá và rủi ro trước khi sử dụng bất kỳ kết quả nào trong thực tế.

Mọi báo cáo được đánh dấu `Draft / Needs Analyst Review` cho đến khi có phê duyệt rõ ràng từ analyst. Hệ thống không tự xuất báo cáo cuối.
