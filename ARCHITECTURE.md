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

Cấu hình trong `config/dataset/universe/` và `config/dataset/mvp/mvp5_scope.yaml`.

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
│   ├── database/             - DB repositories and SQL migrations
│   ├── dataset/              - Dataset contract, taxonomy, and universe helper code
│   │
│   └── jobs/                 — Scheduled tasks
│       └── scheduler.py      — APScheduler: weekly_sync, daily_prices, monthly_valuation
│
├── config/agents/            — 5 product-agent YAML config and Markdown prompt library
├── config/dataset/           - Dataset contracts, taxonomy, universe, source catalog, and golden fixtures
├── config/harness/           - Harness policies, schemas, registries, and contracts
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
│   ├── approve_report.py     — Phase 9: run-scoped harness approval
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
