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
| `vector_store.py` | PostgreSQL/pgvector chunk embedding store for document chunks |

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

---

## 10. Web Connector Status (2026-06-03)

Live integration tests run against real Vietnamese company websites and the CafeF API.
Test file: `tests/integration/test_connector_ir_live.py`
Diagnostic log: `docs/diagnostics/diag_connector_live.txt`

| Ticker | IR URL | HTTP Status | IRConnector Candidates | Notes |
|--------|--------|-------------|----------------------|-------|
| DHG | https://dhgpharma.com.vn/vi/bao-cao-tai-chinh | 200 OK | 16 | Annual reports FY2022-2025, audited FS, quarterly BCTC, disclosures |
| DHG | https://dhgpharma.com.vn/vi/bao-cao-thuong-nien | 200 OK | (same links) | Shares document set with BCTC page |
| IMP | https://www.imexpharm.com/quan-he-co-dong | 404 Not Found | 0 | URL stale — page not found |
| DMC | https://www.domesco.com/co-dong | 200 OK (JS shell) | 0 | Page is a 2675-char JS redirect shell; no PDF links in static HTML |
| TRA | https://www.traphaco.com.vn/vi/quan-he-co-dong.html | SSL failure | 0 | CERTIFICATE_VERIFY_FAILED (hostname mismatch) |
| DBD | https://www.bidiphar.com/quan-he-co-dong | 404 Not Found | 0 | URL stale — page not found |

| Ticker | CafeF Structured Data (FY2023) | Notes |
|--------|-------------------------------|-------|
| DHG | 0 rows | CafeF API endpoint `/Ajax/PageNew/DataHistory/FinancialInfo.ashx` returns HTTP 404 — endpoint has moved or been retired |
| IMP | 0 rows | Same as DHG |

### Findings

1. **DHG IR page works correctly.** The `CompanyIRConnector` discovered 16 PDF document candidates for DHG (FY2022-2025), including annual reports, audited financial statements, quarterly BCTC, and disclosure filings. 9 were selected after deduplication/ranking.

2. **IMP, DMC, TRA, DBD IR pages are stale.** All four non-DHG IR URLs either 404, fail with SSL errors, or return JS-only shells that the static HTML scraper cannot parse. This is a blocker for multi-ticker discovery.

3. **CafeF Tier-2 API endpoint is defunct.** The endpoint `https://s.cafef.vn/Ajax/PageNew/DataHistory/FinancialInfo.ashx` returns HTTP 404. The cafef.vn main domain is reachable, indicating the API path has changed. This affects structured numeric data ingestion for all tickers.

4. **All connectors are crash-safe.** Network failures (404, SSL, timeout) are caught silently and return empty lists — no crashes on bad IR pages.

5. **Exchange connectors (HOSE/HNX/SSC) returned 0 candidates for DHG.** These may require authenticated sessions or different URL patterns than currently configured.

### IR URL Remediation Plan

| Ticker | Problem | Recommended Fix |
|--------|---------|-----------------|
| IMP | 404 on `/quan-he-co-dong` | Update to https://www.imexpharm.com/quan-he-co-dong-2/ or check current IR page |
| DMC | JS-rendered page | Add JavaScript-rendered page support or find direct document listing URL |
| TRA | SSL cert failure | Add SSL context bypass for traphaco.com.vn, or update to HTTPS URL that works |
| DBD | 404 on `/quan-he-co-dong` | Update to https://www.bidiphar.com/investor-relations or check current structure |

### CafeF API Remediation Plan

The CafeF structured data connector needs one of:
- Locate updated CafeF API endpoint (inspect browser network tab on cafef.vn ticker page)
- Replace with SSC iDocs API (official source)
- Replace with vnstock structured data connector (already in the codebase)
- Use HOSE/HNX disclosure XML feeds

### Recommendation

For the one-ticker DHG pipeline: the `CompanyIRConnector` works and provides a clean set of official PDFs. The PDF extraction + OCR path (Phase 3B) should proceed using DHG IR candidates. For multi-ticker expansion, IR URLs for IMP/DMC/TRA/DBD must be manually verified and updated in `backend/documents/company_registry.py` before running discovery on those tickers.
