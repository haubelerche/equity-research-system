# 00 — Repository Audit

**Date:** 2026-05-22
**Status:** Complete

---

## 1. Root Structure

```text
backend/          FastAPI backend, harness runtime, database, dataset helper code
config/dataset/   Static dataset config: universe CSV, taxonomy YAML, contracts JSON
data/             Runtime raw/staging data, ignored by git
FinRobot/         Cloned reference project (do not couple to internals)
frontend/         React/Next.js frontend (secondary priority)
scripts/          Operational scripts and connectors
vnstock/          Local vnstock library (reference; wrap behind our connector)
```

---

## 2. Existing Backend (`backend/`)

| File | Role |
|---|---|
| `agents.py` | DataAgent, QuantAgent, ResearcherAgent, DebateAgent, AuditorAgent stubs |
| `orchestrator.py` | Supervisor — deterministic state machine (INGESTING → VALUATING → SYNTHESIZING → AUDITING → WAITING_APPROVAL → PUBLISHED) |
| `runtime_store.py` | In-process run state store (run lifecycle, artifacts, audit log) |
| `services.py` | BudgetGuard, RecomputePlanner, OfflineEvaluator |
| `schemas.py` | Pydantic request/response models; RunStatus, RunType enums |
| `api.py` | FastAPI endpoints for run lifecycle + approval |
| `retrieval.py` | RetrievalService stub (Milvus-backed) |
| `settings.py` | Environment-driven settings dataclass |

**Assessment:** The orchestrator skeleton is sound. Agent implementations are stubs with placeholder payloads. The budget guard and approval flow are wired. The main gap is real data flowing into agents.

---

## 3. Existing Scripts (`scripts/`)

### 3.1 Connectors (`scripts/connectors/`)

| Connector | Data | Notes |
|---|---|---|
| `vnstock_finance_connector.py` | Income statement, balance sheet, cash flow, ratios | Tries KBS then VCI fallback; alias-maps to taxonomy |
| `vnstock_price_connector.py` | EOD price history | Checksum dedup; saves JSON snapshot |
| `vnstock_company_connector.py` | Company profile, news, events | Catalyst event normalization |
| `catalyst_hose_connector.py` | HOSE disclosure feed | Regulatory catalyst ingestion |
| `catalyst_bhyt_connector.py` | BHYT reimbursement events | Vietnam-specific catalyst |
| `catalyst_tender_connector.py` | Public tender data | Vietnam-specific catalyst |
| `catalyst_dav_connector.py` | DAV drug authority events | Regulatory recall / approval |
| `vn_market_data_adapter.py` | Peer metrics adapter | Bridges fact store to agent format |

### 3.2 Database (`backend/database/`)

| Module | Role |
|---|---|
| `fact_store.py` | `PostgresFactStore` — upserts financial_facts, price_history, company_profiles, catalyst_events |
| `source_registry.py` | `SourceRegistry` — registers and deduplicates source versions; saves raw snapshots |
| `milvus_store.py` | Vector store client for document chunks |

### 3.3 Dataset Pipeline (`backend/dataset/`)

| Script | Role |
|---|---|
| `config_io.py` | ROOT path, load_universe_tickers(), load_financial_taxonomy(), load_catalyst_taxonomy() |
| `dqf.py` | Data Quality Framework — validate_financial_fact(), validate_catalyst_event(), stages_to_invalidate() |
| `chunk_pipeline.py` | Document chunking pipeline |
| `bootstrap_mvp_facts.py` | Seed golden facts from CSV template |
| `validate_contracts.py` | Contract schema validation |
| `validate_universe.py` | Universe integrity checks |
| `weekly_sync.py` | Scheduled sync orchestration |
| `manual_refresh.py` | Manual data refresh trigger |
| `offline_eval.py` | Offline evaluation scaffold |
| `check_golden_facts.py` | Golden fact completeness check |

---

## 4. Static Assets (`config/dataset/`)

| Asset | Role |
|---|---|
| `universe/pharma_vn_universe.csv` | 23-ticker universe (DHG, IMP, DMC, TRA, DBD = MVP) |
| `taxonomy/financial_taxonomy_vn_pharma.yaml` | Canonical metric names + aliases + units |
| `taxonomy/catalyst_taxonomy_vn_pharma.yaml` | Catalyst event taxonomy |
| `contracts/*.schema.json` | JSON Schema for: financial_fact, catalyst_event, source_version, document_chunk, citation, agent_message, tool_call |
| `sources/source_catalog.yaml` | Source catalog (BCTC, market feeds, regulatory) |
| `mvp/mvp5_scope.yaml` | MVP 5-ticker scope definition |
| `mvp/golden_facts_spec.yaml` | Golden fact specification |
| `mvp/financial_facts_template.csv` | Golden fact seed template |

---

## 5. FinRobot Reference — What to Reuse Conceptually

| Concept | Applicable to This Project |
|---|---|
| **Agent role separation** (DataAgent, QuantAgent, ResearcherAgent, AuditorAgent) | Adopted through `config/agents/` policy and `backend/harness` execution |
| **Supervisor / orchestrator pattern** | Already adopted in `backend/orchestrator.py` |
| **Workflow state machine** (INGESTING → AUDITING → PUBLISHED) | Already adopted |
| **Evidence grounding before synthesis** | Must implement; FinRobot shows the pattern |
| **Section-by-section report generation** | Useful for `backend/reporting/` (not yet built) |
| **Evaluation rubric structure** | Useful for `specs/07_EVALUATION_RUBRIC.md` |

**Do NOT reuse from FinRobot:**
- SEC filing connectors (US-specific)
- FMP / yfinance data sources (not Vietnam)
- Any hardcoded US market logic

---

## 6. vnstock Capabilities — Available via Our Connector

| Capability | Available |
|---|---|
| `Vnstock(symbol, source).finance.income_statement()` | Yes (KBS / VCI) |
| `Vnstock(symbol, source).finance.balance_sheet()` | Yes |
| `Vnstock(symbol, source).finance.cash_flow()` | Yes |
| `Vnstock(symbol, source).finance.ratio()` | Yes |
| `Vnstock(symbol, source).quote.history()` | Yes |
| `Vnstock(symbol, source).company.overview()` | Yes |
| `Vnstock(symbol, source).company.news()` | Yes |
| `Vnstock(symbol, source).company.events()` | Yes |
| `Vnstock(symbol, source).company.shareholders()` | Yes |
| `Vnstock(symbol, source).company.officers()` | Yes |

**Limitations:**
- Some endpoints may fail for small/illiquid tickers; KBS → VCI fallback is implemented
- Data may not be available for all historical periods
- No official PDF/BCTC document download; raw financials only
- Rate limits unknown; no retry backoff currently implemented

---

## 7. Critical Gaps

| Gap | Priority | Notes |
|---|---|---|
| `scripts/ingest_ticker.py` missing | HIGH | No unified ingestion entry point |
| No `specs/` files | HIGH | Contracts and roadmap undocumented |
| Agent stubs not connected to real data | HIGH | Agents return placeholder payloads |
| No `backend/connectors/` abstraction layer | MEDIUM | Connectors live in `scripts/`, not `backend/` |
| No valuation logic (`backend/valuation/`) | HIGH | QuantAgent is a stub |
| No retrieval/chunking connected to reports | HIGH | RetrievalService is a stub |
| No report generation (`backend/reporting/`) | HIGH | ResearcherAgent produces placeholder |
| No evaluation harness (`backend/evaluation/`) | HIGH | OfflineEvaluator returns static scores |
| PostgreSQL schema not documented here | MEDIUM | Must exist for connectors to work |

---

## 8. What Should Be Built from Scratch

- `scripts/ingest_ticker.py` — unified ingestion orchestrator
- `backend/valuation/` — deterministic ratio, DCF, multiples, sensitivity modules
- `backend/reporting/` — section-by-section grounded report builder
- `backend/evaluation/` — real citation coverage, numeric consistency, stale data checks
- `specs/` — all Phase 0 + Phase 1 documents

---

## 9. Current Technical Risks

| Risk | Severity |
|---|---|
| PostgreSQL required — no DB = connectors fail | HIGH |
| vnstock API changes may break connectors | MEDIUM |
| Agent stubs produce fake data — reports would be hallucinated | HIGH |
| No evaluation gate means no quality assurance | HIGH |
| Missing human approval integration for export | MEDIUM |