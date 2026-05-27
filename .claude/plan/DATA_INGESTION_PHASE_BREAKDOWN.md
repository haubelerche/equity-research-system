# Data Ingestion Phase Breakdown — Supabase + Vnstock

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Build the complete ingestion pipeline that pulls data from Vnstock, validates and normalizes it, stores canonical financial facts in Supabase with full lineage, and makes golden-ticker datasets ready for report agents to consume — without any LLM involvement in fact creation.

**Architecture:** Python workers poll a Supabase job queue, call the Vnstock adapter, store raw payloads, normalize into typed canonical rows, run deterministic quality gates, and compute derived ratios — all traceable back to a `source_id`. Report agents read only from `canonical.*` and `derived.*`; they never touch raw payloads or call Vnstock directly.

**Tech Stack:** Python 3.11 · Supabase (PostgreSQL) · `vnstock` Python library · `pydantic` v2 · `pandas` · `pytest` · `python-dotenv` / `pydantic-settings`

---

## 1. Executive Summary

This document breaks the Supabase + Vnstock ingestion plan into six sequential phases. Each phase produces independently testable, mergeable software. Phases build strictly on top of each other — no phase may begin until its predecessor's acceptance criteria are met.

The ingestion system is the **data foundation** for all downstream analytics, valuation, and report generation. No analytical or LLM agent may run on unvalidated data. Every canonical financial fact must have a `source_id`, an `ingestion_run_id`, and a `fact_lineage` record before it is marked `quality_status = 'passed'`.

---

## 2. Non-Negotiable Architecture Decisions

| # | Decision | Rationale |
|---|---|---|
| DA-01 | Vnstock is the **only** structured connector in MVP | Avoids FireAnt auth risk, rate-limit complexity, and source reconciliation overhead |
| DA-02 | Supabase is the canonical store; not a raw API cache | Every fact must be queryable, typed, and auditable |
| DA-03 | Python worker executes ingestion; cron only enqueues | No business logic in SQL triggers or cron expressions |
| DA-04 | Raw payloads are immutable; normalization is a separate step | Enables parser replay when `parser_version` changes |
| DA-05 | Canonical financial facts are typed columns, **not** opaque JSON blobs | Allows column-level lineage, quality checks, and deterministic ratio calculation |
| DA-06 | Ratios are `derived.*` artifacts, calculated by Python code | LLM must never compute or modify any financial fact |
| DA-07 | Every canonical fact requires `source_id` + `fact_lineage` | No `source_id` = no report number; no lineage = fact is blocked |
| DA-08 | Universe config lives in `data/universe/pharma_vn_53.yaml` | Ticker list is never hardcoded in Python |
| DA-09 | Unit normalization to VND is mandatory before canonical insert | All downstream code assumes `currency = VND`, `unit = VND` |
| DA-10 | Worker must be idempotent | Same `ticker + period + line_item_code + source_id` cannot create duplicate facts |

---

## 3. Phase Overview Table

| Phase | Name | Deliverable | Depends On |
|---|---|---|---|
| 0 | Schema + Universe Config | Supabase migrations + YAML universe | — |
| 1 | Vnstock Connector + Raw Store | Adapter + raw payload storage | Phase 0 |
| 2 | Normalization + Canonical Facts | Typed canonical rows from raw payloads | Phase 1 |
| 3 | Data Quality Gates | Quality checks + completeness scoring | Phase 2 |
| 4 | Derived Artifacts | Financial ratios + peer metrics | Phase 3 |
| 5 | Golden Dataset Backfill | 5 golden tickers report-ready | Phase 4 |

---

## 4. Detailed Phase Plans

---

### Phase 0 — Schema + Universe Config

**Goal:** Create all Supabase schemas and tables, and validate the 53-ticker universe config.

**Scope:**
- Six schemas: `ref`, `raw`, `canonical`, `derived`, `governance`, `ops`
- All tables from `DATA_INGESTION_PLAN_SUPABASE_VNSTOCK.md §5–10`
- `data/universe/pharma_vn_53.yaml` with all 53 tickers
- Python validator for the YAML universe config

**Out of Scope:**
- Any Vnstock API call
- Any Python worker logic
- Any data ingestion

**Files to Create:**
- `supabase/migrations/001_ref_schema.sql`
- `supabase/migrations/002_raw_schema.sql`
- `supabase/migrations/003_canonical_schema.sql`
- `supabase/migrations/004_derived_schema.sql`
- `supabase/migrations/005_governance_schema.sql`
- `supabase/migrations/006_ops_schema.sql`
- `data/universe/pharma_vn_53.yaml`
- `backend/app/core/universe_validator.py`
- `backend/tests/unit/test_universe_validator.py`

**Files to Modify:**
- `backend/app/core/config.py` — add `SUPABASE_URL`, `SUPABASE_KEY`
- `.env.example` — add `SUPABASE_URL`, `SUPABASE_KEY`

**Supabase Tables / Migrations:**

`001_ref_schema.sql`: `ref.companies`, `ref.ticker_universe`, `ref.peer_groups`
`002_raw_schema.sql`: `raw.ingestion_runs`, `raw.source_payloads`
`003_canonical_schema.sql`: `canonical.market_prices_daily`, `canonical.market_snapshots`, `canonical.financial_facts`, `canonical.company_profiles`, `canonical.news_events`
`004_derived_schema.sql`: `derived.financial_ratios`, `derived.peer_metrics`
`005_governance_schema.sql`: `governance.source_manifest`, `governance.fact_lineage`, `governance.data_quality_checks`
`006_ops_schema.sql`: `ops.ingestion_jobs`

**Implementation Tasks:**

- [ ] Write `001_ref_schema.sql` with `ref.companies`, `ref.ticker_universe` (with `coverage_status` check constraint), `ref.peer_groups`
- [ ] Write `002_raw_schema.sql` with `raw.ingestion_runs` (status check constraint), `raw.source_payloads` (unique on `source_provider + source_endpoint + payload_hash`)
- [ ] Write `003_canonical_schema.sql` — `canonical.financial_facts` with typed columns for `statement_type`, `period_type`, `quality_status`; unique constraint on `(ticker, statement_type, line_item_code, period_type, fiscal_year, quarter, source_id)`
- [ ] Write `004_derived_schema.sql`, `005_governance_schema.sql`, `006_ops_schema.sql`
- [ ] Apply migrations to Supabase and verify all tables exist with expected constraints
- [ ] Create `data/universe/pharma_vn_53.yaml` with all 53 tickers, coverage tiers (golden: DHG, TRA, IMP, DBD, DMC), and peer groups
- [ ] Implement `universe_validator.py`: load YAML, check `expected_ticker_count == 53`, no duplicate tickers, all golden tickers present, each ticker has `exchange`, `company_name`, `subsector`, `coverage_status`
- [ ] Write `test_universe_validator.py` with cases for: valid YAML passes, duplicate ticker fails, missing `company_name` fails, golden count < 3 fails

**Tests to Write:**
```python
# test_universe_validator.py
def test_valid_universe_passes():
    ...
def test_duplicate_ticker_raises():
    ...
def test_missing_required_field_raises():
    ...
def test_golden_tickers_minimum_three():
    ...
def test_expected_count_mismatch_raises():
    ...
```

**Acceptance Criteria:**
- All 6 migrations apply without error on a clean Supabase instance
- `canonical.financial_facts` has typed columns (not JSONB for value fields)
- `data/universe/pharma_vn_53.yaml` validates: 53 tickers, no duplicates, 5 golden tickers
- `pytest backend/tests/unit/test_universe_validator.py -q` → all pass
- `SUPABASE_URL` and `SUPABASE_KEY` declared in `config.py` and `.env.example`

**Risks:**
- Supabase free tier may require schema name prefixing — test migrations early
- `pharma_vn_53.yaml` ticker list needs manual verification against official exchange listings

**Compact Handoff Prompt for Coding Agent:**
```
Task: Implement Phase 0 — Supabase schema migrations and universe config validator.

Scope:
- Write 6 SQL migration files in supabase/migrations/ (001–006).
- Create data/universe/pharma_vn_53.yaml with 53 pharma tickers.
- Implement backend/app/core/universe_validator.py.
- Write backend/tests/unit/test_universe_validator.py.

Files allowed:
- supabase/migrations/*.sql
- data/universe/pharma_vn_53.yaml
- backend/app/core/universe_validator.py
- backend/app/core/config.py (add SUPABASE_URL, SUPABASE_KEY only)
- .env.example (add SUPABASE_URL, SUPABASE_KEY only)
- backend/tests/unit/test_universe_validator.py

Files forbidden:
- backend/app/agents/*, backend/app/workflows/*
- Any file outside the above list

Acceptance criteria:
- Migrations apply clean on Supabase.
- canonical.financial_facts has typed columns, not opaque JSONB.
- YAML validates: 53 tickers, no duplicates, 5 golden tickers present.
- All unit tests pass.

Do not:
- Call Vnstock.
- Write Python ingestion logic.
- Hardcode ticker lists in Python.
```

---

### Phase 1 — Vnstock Connector + Raw Store

**Goal:** Implement the Vnstock adapter and the raw payload store worker step. No normalization yet — only fetch and persist.

**Scope:**
- `vnstock_client.py` adapter wrapping all Vnstock calls
- `raw_repository.py` for inserting `raw.ingestion_runs` and `raw.source_payloads`
- `source_registry.py` for creating `governance.source_manifest` entries
- `job_runner.py` skeleton: poll `ops.ingestion_jobs`, lock, create run, call connector, save raw payload, update status

**Out of Scope:**
- Normalization into canonical tables
- Data quality checks
- Any LLM call

**Files to Create:**
- `backend/app/connectors/vnstock_client.py`
- `backend/app/connectors/source_registry.py`
- `backend/app/repositories/supabase_client.py`
- `backend/app/repositories/raw_repository.py`
- `backend/app/repositories/ops_repository.py`
- `backend/app/dataops/job_runner.py`
- `backend/tests/unit/test_vnstock_client.py`
- `backend/tests/integration/test_raw_store.py`

**Files to Modify:**
- `backend/app/core/config.py` — add `VNSTOCK_SOURCE_PROVIDER = "vnstock"`

**Supabase Tables Used:**
- `raw.ingestion_runs` (insert + update status)
- `raw.source_payloads` (insert with payload_hash dedup)
- `governance.source_manifest` (insert per fetch)
- `ops.ingestion_jobs` (poll + lock + update)

**Implementation Tasks:**

- [ ] Implement `supabase_client.py`: initialize `supabase-py` client from env vars; expose typed `execute`, `insert`, `upsert`, `select` helpers
- [ ] Implement `vnstock_client.py` with methods:
  - `fetch_company_profile(ticker: str) -> dict`
  - `fetch_price_history(ticker: str, start_date: str, end_date: str) -> list[dict]`
  - `fetch_market_snapshot(ticker: str) -> dict`
  - `fetch_financial_statements(ticker: str, period_type: str) -> dict` (returns income, balance, cashflow)
  - `fetch_news_events(ticker: str) -> list[dict]` (optional, returns empty list if unsupported)
  - All methods must return `{"ticker": ..., "source_endpoint": ..., "request_params": ..., "retrieved_at": ..., "data": ...}`
  - No Vnstock imports allowed outside this file
- [ ] Implement `raw_repository.py`:
  - `create_ingestion_run(job_type, ticker, connector_version, parser_version) -> UUID`
  - `update_ingestion_run_status(run_id, status, records_fetched, records_inserted, records_rejected, error_message)`
  - `save_source_payload(ingestion_run_id, ticker, source_endpoint, request_params, response_payload) -> UUID` (compute `payload_hash = sha256(json(response_payload))`, skip insert if hash exists for same endpoint + parser_version)
- [ ] Implement `source_registry.py`:
  - `register_source(source_type, source_name, ticker, period, reliability) -> UUID` (inserts into `governance.source_manifest`, returns `source_id`)
- [ ] Implement `ops_repository.py`:
  - `poll_queued_jobs(limit: int) -> list[dict]`
  - `lock_job(job_id, worker_id) -> bool`
  - `update_job_status(job_id, status, error_message)`
- [ ] Implement `job_runner.py` skeleton:
  - Poll `ops.ingestion_jobs` where `status = 'queued'` and `scheduled_for <= now()`
  - Lock job with `locked_by = worker_id`
  - Create `raw.ingestion_runs` entry
  - Dispatch to correct connector method based on `job_type`
  - Save raw payload via `raw_repository`
  - Register source manifest entry
  - Update job and run status (`success` or `failed` with `error_message`)
- [ ] Write `test_vnstock_client.py` with mocked Vnstock responses
- [ ] Write `test_raw_store.py` verifying: payload hash dedup (duplicate payload not re-inserted), ingestion_run status transitions

**Tests to Write:**
```python
# test_vnstock_client.py
def test_fetch_company_profile_returns_expected_keys():
    ...
def test_fetch_price_history_returns_list():
    ...
def test_fetch_financial_statements_returns_three_statement_types():
    ...
def test_no_vnstock_import_outside_adapter():
    # grep-based: assert vnstock not imported in any file except vnstock_client.py
    ...

# test_raw_store.py
def test_duplicate_payload_hash_not_reinserted():
    ...
def test_ingestion_run_status_updated_on_success():
    ...
def test_ingestion_run_status_updated_on_failure():
    ...
def test_job_locked_before_processing():
    ...
```

**Acceptance Criteria:**
- `vnstock_client.py` is the only file importing from `vnstock`
- Raw payload for a ticker can be fetched and persisted end-to-end
- Duplicate payload (same `source_endpoint + payload_hash`) is not re-inserted
- Failed job sets `status = 'failed'` and `error_message` in both `ops.ingestion_jobs` and `raw.ingestion_runs`
- `governance.source_manifest` row is created for every fetch
- All unit tests pass; integration test passes against a test Supabase instance

**Risks:**
- Vnstock API may return inconsistent column names across quarters — log raw shape before normalizing
- Rate limiting: implement exponential backoff in `vnstock_client.py`
- `supabase-py` async vs sync — decide once; do not mix

**Compact Handoff Prompt for Coding Agent:**
```
Task: Implement Phase 1 — Vnstock connector adapter and raw payload store.

Scope:
- backend/app/connectors/vnstock_client.py
- backend/app/connectors/source_registry.py
- backend/app/repositories/supabase_client.py
- backend/app/repositories/raw_repository.py
- backend/app/repositories/ops_repository.py
- backend/app/dataops/job_runner.py (fetch + raw store steps only)
- backend/tests/unit/test_vnstock_client.py
- backend/tests/integration/test_raw_store.py

Files forbidden:
- backend/app/dataops/normalization.py
- backend/app/dataops/quality_checks.py
- backend/app/agents/*
- backend/app/analytics/*

Acceptance criteria:
- Only vnstock_client.py imports vnstock.
- Duplicate payloads (same hash + endpoint) are skipped.
- Every fetch creates a governance.source_manifest row.
- Job status and ingestion_run status always updated (success or failed).
- All tests pass.

Do not:
- Normalize into canonical tables.
- Call any LLM.
- Add FireAnt imports.
```

---

### Phase 2 — Normalization + Canonical Facts

**Goal:** Transform raw Vnstock payloads into typed canonical rows with full lineage. This is the most critical phase.

**Scope:**
- `normalization.py` — map Vnstock raw columns to internal taxonomy; convert units to VND
- `canonical_repository.py` — typed upsert into `canonical.financial_facts`, `canonical.market_prices_daily`, `canonical.market_snapshots`, `canonical.company_profiles`
- `governance_repository.py` — insert `governance.fact_lineage` for every canonical fact
- `lineage.py` — build and persist `fact_lineage` records linking `fact_id → source_id → raw_payload_id`
- Line item taxonomy YAML: `data/taxonomy/financial_line_items.yaml`
- Extend `job_runner.py` to call normalization step after raw store

**Out of Scope:**
- Quality scoring (Phase 3)
- Ratio calculation (Phase 4)
- Any LLM call

**Files to Create:**
- `backend/app/dataops/normalization.py`
- `backend/app/dataops/lineage.py`
- `backend/app/repositories/canonical_repository.py`
- `backend/app/repositories/governance_repository.py`
- `data/taxonomy/financial_line_items.yaml`
- `backend/tests/unit/test_normalization.py`
- `backend/tests/unit/test_lineage.py`

**Files to Modify:**
- `backend/app/dataops/job_runner.py` — add normalization + lineage steps
- `backend/app/repositories/raw_repository.py` — expose `get_payload_by_id`

**Supabase Tables Used:**
- `canonical.financial_facts` (upsert)
- `canonical.market_prices_daily` (upsert)
- `canonical.market_snapshots` (upsert)
- `canonical.company_profiles` (upsert)
- `governance.fact_lineage` (insert)

**Implementation Tasks:**

- [ ] Create `data/taxonomy/financial_line_items.yaml` mapping Vnstock raw column names to internal `line_item_code` (e.g., `"Doanh thu thuần" → "revenue"`, `"Lợi nhuận sau thuế" → "net_income"`); include `aliases` list per item; cover income_statement, balance_sheet, cash_flow
- [ ] Implement `normalization.py`:
  - `load_taxonomy(path: str) -> dict` — load and cache taxonomy YAML
  - `map_line_item(raw_name: str, statement_type: str) -> str | None` — return `line_item_code` or `None` if unmapped (log warning)
  - `normalize_unit(raw_value: float, raw_unit: str) -> tuple[float, str]` — convert `billion_vnd` → VND (×1e9), `million_vnd` → VND (×1e6), return `(canonical_value, transformation_method)`
  - `normalize_financial_statements(raw_payload: dict, ticker: str, source_id: UUID, ingestion_run_id: UUID, parser_version: str) -> list[CanonicalFactRow]`
  - `normalize_price_history(raw_payload: dict, ticker: str, source_id: UUID, ingestion_run_id: UUID) -> list[PriceRow]`
  - `normalize_market_snapshot(raw_payload: dict, ticker: str, source_id: UUID, ingestion_run_id: UUID) -> SnapshotRow`
  - `normalize_company_profile(raw_payload: dict, ticker: str, source_id: UUID, ingestion_run_id: UUID) -> ProfileRow`
- [ ] All normalization functions must return typed Pydantic models (define in `backend/app/schemas/financials.py`)
- [ ] Implement `canonical_repository.py`:
  - `upsert_financial_fact(row: CanonicalFactRow) -> UUID` — upsert on unique constraint; return `fact_id`
  - `upsert_price(row: PriceRow) -> UUID`
  - `upsert_snapshot(row: SnapshotRow) -> UUID`
  - `upsert_company_profile(row: ProfileRow) -> UUID`
- [ ] Implement `lineage.py`:
  - `create_fact_lineage(fact_id, source_id, ingestion_run_id, raw_payload_id, transformation_method, parser_version, validation_status) -> UUID`
- [ ] Implement `governance_repository.py`:
  - `insert_fact_lineage(record: FactLineageRow) -> UUID`
  - `get_lineage_for_fact(fact_id: UUID) -> FactLineageRow | None`
- [ ] Extend `job_runner.py`: after raw payload saved, call normalization, upsert canonical rows, create lineage record for each fact; set `quality_status = 'pending'` on all new facts
- [ ] Write `test_normalization.py`: unit conversion (billion → VND), unmapped line item returns None, duplicate upsert does not create new row, all required output fields are present
- [ ] Write `test_lineage.py`: every canonical fact has exactly one lineage record, lineage `fact_id` matches canonical fact

**Tests to Write:**
```python
# test_normalization.py
def test_billion_vnd_converts_to_vnd():
    value, method = normalize_unit(1234.0, "billion_vnd")
    assert value == 1_234_000_000_000
    assert method == "multiply_by_1e9_from_billion_vnd"

def test_unmapped_line_item_returns_none():
    result = map_line_item("Unknown Field XYZ", "income_statement")
    assert result is None

def test_normalize_financial_statements_returns_typed_rows():
    rows = normalize_financial_statements(mock_raw, "DHG", source_id, run_id, "v1")
    assert all(isinstance(r, CanonicalFactRow) for r in rows)
    assert all(r.currency == "VND" for r in rows)
    assert all(r.unit == "VND" for r in rows)

def test_duplicate_upsert_does_not_create_duplicate_row():
    ...

# test_lineage.py
def test_every_canonical_fact_has_lineage():
    ...
def test_lineage_fact_id_matches_canonical():
    ...
```

**Acceptance Criteria:**
- All canonical `financial_facts` rows have `currency = 'VND'`, `unit = 'VND'`
- No Vnstock raw column names appear in `canonical.financial_facts.line_item_code`
- Every canonical fact has a corresponding `governance.fact_lineage` record
- `quality_status = 'pending'` on all newly inserted facts (Phase 3 sets final status)
- Normalization for DHG produces canonical rows for `revenue`, `net_income`, `total_assets`, `total_equity`, `operating_cash_flow`
- All unit tests pass

**Risks:**
- Vnstock may change column name formatting between API versions — taxonomy YAML must cover aliases
- Some tickers may have partial BCTC data — normalization must produce partial rows (not fail entirely) and log missing items

**Compact Handoff Prompt for Coding Agent:**
```
Task: Implement Phase 2 — normalization layer and canonical fact persistence with lineage.

Scope:
- backend/app/dataops/normalization.py
- backend/app/dataops/lineage.py
- backend/app/repositories/canonical_repository.py
- backend/app/repositories/governance_repository.py
- data/taxonomy/financial_line_items.yaml
- backend/app/schemas/financials.py (add Pydantic row models)
- backend/tests/unit/test_normalization.py
- backend/tests/unit/test_lineage.py
- backend/app/dataops/job_runner.py (extend with normalization step)

Files forbidden:
- backend/app/dataops/quality_checks.py
- backend/app/analytics/*
- backend/app/agents/*

Acceptance criteria:
- All canonical financial facts: currency=VND, unit=VND.
- No raw Vnstock column names in line_item_code.
- Every fact has a governance.fact_lineage record.
- New facts have quality_status='pending'.
- All unit tests pass.

Do not:
- Calculate any financial ratios.
- Set quality_status='passed' — that is Phase 3.
- Call any LLM.
```

---

### Phase 3 — Data Quality Gates

**Goal:** Implement deterministic quality checks that gate facts from `pending` to `passed`, `warning`, or `failed`. Compute completeness scores per ticker.

**Scope:**
- `quality_checks.py` — all check rules
- `governance.data_quality_checks` table population
- Completeness score computation
- `canonical.financial_facts.quality_status` update from `pending` to final state
- Hard-fail detection: missing revenue, net_income, total_assets, total_equity, market_price; < 3 fiscal years; missing lineage
- Extend `job_runner.py` to trigger quality check after normalization

**Out of Scope:**
- Ratio calculation
- Any report generation
- Any LLM call

**Files to Create:**
- `backend/app/dataops/quality_checks.py`
- `backend/tests/unit/test_quality_checks.py`
- `backend/tests/integration/test_quality_gate_e2e.py`

**Files to Modify:**
- `backend/app/dataops/job_runner.py` — add quality check trigger
- `backend/app/repositories/canonical_repository.py` — add `update_fact_quality_status`
- `backend/app/repositories/governance_repository.py` — add `insert_quality_check_result`

**Supabase Tables Used:**
- `canonical.financial_facts` (update `quality_status`)
- `governance.data_quality_checks` (insert check results)

**Implementation Tasks:**

- [ ] Implement `quality_checks.py`:
  - `check_required_fields(ticker, facts: list[CanonicalFactRow]) -> list[QualityCheckResult]` — hard fail if any of `revenue`, `net_income`, `total_assets`, `total_equity` missing
  - `check_fiscal_year_coverage(ticker, facts) -> QualityCheckResult` — fail if < 3 distinct fiscal years
  - `check_lineage_coverage(ticker, fact_ids: list[UUID], db) -> QualityCheckResult` — fail if any fact has no lineage record
  - `check_unit_consistency(ticker, facts) -> QualityCheckResult` — fail if any fact has `unit != 'VND'`
  - `check_market_price_availability(ticker, snapshots: list[SnapshotRow]) -> QualityCheckResult` — fail if no current close price
  - `check_source_manifest_not_empty(ticker, source_ids: list[UUID]) -> QualityCheckResult` — fail if empty
  - `compute_completeness_score(ticker, check_results: list[QualityCheckResult]) -> float` — weighted formula:
    ```
    0.25 * price_data_score
    + 0.35 * financial_statement_score
    + 0.15 * company_profile_score
    + 0.10 * peer_data_score
    + 0.10 * source_lineage_score
    + 0.05 * news_event_score
    ```
  - `run_all_checks(ticker, db) -> DataQualityReport` — orchestrates all checks, returns `DataQualityReport` with `completeness_score`, `pass_gate: bool`, `missing_fields`, `warnings`
- [ ] Add `update_fact_quality_status(fact_ids: list[UUID], status: str)` to `canonical_repository.py`
- [ ] Add `insert_quality_check_result(record: QualityCheckResult)` to `governance_repository.py`
- [ ] Extend `job_runner.py`: after normalization, call `run_all_checks`; update `quality_status` on all facts; persist results to `governance.data_quality_checks`
- [ ] Define `QualityCheckResult` and `DataQualityReport` Pydantic models in `backend/app/schemas/evaluation.py`
- [ ] Write `test_quality_checks.py`: hard fail for missing revenue, pass for complete dataset, < 3 years triggers fail, unit mismatch triggers fail
- [ ] Write `test_quality_gate_e2e.py`: golden ticker DHG with seeded data passes completeness >= 0.85

**Tests to Write:**
```python
# test_quality_checks.py
def test_missing_revenue_is_hard_fail():
    ...
def test_missing_net_income_is_hard_fail():
    ...
def test_fewer_than_three_fiscal_years_fails():
    ...
def test_unit_not_vnd_fails_consistency_check():
    ...
def test_complete_golden_ticker_passes_gate():
    ...
def test_completeness_score_between_zero_and_one():
    ...
def test_facts_marked_passed_when_all_checks_pass():
    ...
def test_facts_marked_failed_when_hard_fail():
    ...
```

**Acceptance Criteria:**
- No canonical fact remains with `quality_status = 'pending'` after quality check run
- All hard-fail conditions block facts from `quality_status = 'passed'`
- Golden ticker DHG: `completeness_score >= 0.85` with seeded BCTC data
- `governance.data_quality_checks` has rows for every check run
- `pass_gate = True` only when `completeness_score >= 0.85` and no hard fails
- All unit tests pass

**Risks:**
- Vnstock data gaps may prevent golden tickers from reaching 0.85 without manual data supplement — have golden CSV fallback ready
- Completeness weights need calibration against real data; mark as `v1` and log formula version

**Compact Handoff Prompt for Coding Agent:**
```
Task: Implement Phase 3 — deterministic data quality gates.

Scope:
- backend/app/dataops/quality_checks.py
- backend/app/schemas/evaluation.py (QualityCheckResult, DataQualityReport models)
- backend/app/dataops/job_runner.py (extend with quality check step)
- backend/app/repositories/canonical_repository.py (add update_fact_quality_status)
- backend/app/repositories/governance_repository.py (add insert_quality_check_result)
- backend/tests/unit/test_quality_checks.py
- backend/tests/integration/test_quality_gate_e2e.py

Files forbidden:
- backend/app/analytics/*
- backend/app/agents/*

Acceptance criteria:
- Hard fail conditions block quality_status='passed'.
- Golden ticker DHG completeness_score >= 0.85.
- No fact remains quality_status='pending' after run.
- All tests pass.

Do not:
- Calculate ratios.
- Set quality_status='passed' unless all hard checks pass.
- Call any LLM.
```

---

### Phase 4 — Derived Artifacts (Ratios + Peer Metrics)

**Goal:** Calculate financial ratios and peer comparison metrics from `quality_status = 'passed'` canonical facts. Store in `derived.*` tables. No LLM involvement.

**Scope:**
- `ratios.py` — profitability, growth, leverage, liquidity, cash flow ratios
- `peer_analysis.py` — relative valuation metrics, peer comparison aggregates
- `derived_repository.py` — upsert into `derived.financial_ratios`, `derived.peer_metrics`
- Extend `job_runner.py` to trigger ratio recompute after quality check passes

**Out of Scope:**
- DCF or multiples valuation (analytics engine — separate phase)
- Report generation
- Any LLM call

**Files to Create:**
- `backend/app/analytics/ratios.py`
- `backend/app/analytics/peer_analysis.py`
- `backend/app/repositories/derived_repository.py`
- `backend/tests/unit/test_ratios.py`
- `backend/tests/unit/test_peer_analysis.py`

**Files to Modify:**
- `backend/app/dataops/job_runner.py` — add `derived_ratio_recompute` job type handler

**Supabase Tables Used:**
- `canonical.financial_facts` (read, `quality_status = 'passed'` only)
- `canonical.market_snapshots` (read)
- `derived.financial_ratios` (upsert)
- `derived.peer_metrics` (upsert)

**Implementation Tasks:**

- [ ] Implement `ratios.py`:
  - `calculate_profitability_ratios(facts: dict) -> dict` — gross margin, operating margin, net margin, ROE, ROA
  - `calculate_growth_metrics(facts_by_year: dict) -> dict` — revenue CAGR, net income CAGR, EPS growth
  - `calculate_leverage_metrics(facts: dict) -> dict` — debt/equity, debt/assets, interest coverage
  - `calculate_liquidity_metrics(facts: dict) -> dict` — current ratio, quick ratio
  - `calculate_cash_flow_metrics(facts: dict) -> dict` — FCF margin, CFO/net income
  - All functions: handle zero denominator (return `None`, not exception); return dict with `ratio_code → value`
  - Zero-denominator rule: `if denominator == 0 or denominator is None: return None`
- [ ] Implement `peer_analysis.py`:
  - `calculate_peer_multiples(ticker_snapshot: SnapshotRow, peer_snapshots: list[SnapshotRow]) -> list[PeerMetricRow]` — P/E, P/B, EV/EBITDA vs peer median and mean
  - `build_peer_comparison_table(ticker: str, peer_group: list[str], db) -> list[PeerMetricRow]`
- [ ] Implement `derived_repository.py`:
  - `upsert_financial_ratio(row: FinancialRatioRow) -> UUID` — unique on `(ticker, period_type, fiscal_year, quarter, ratio_code, formula_version)`
  - `upsert_peer_metric(row: PeerMetricRow) -> UUID`
  - `get_ratios_for_ticker(ticker: str, period_type: str) -> list[FinancialRatioRow]`
- [ ] Add `FinancialRatioRow` and `PeerMetricRow` Pydantic models to `backend/app/schemas/financials.py`
- [ ] Extend `job_runner.py` with `derived_ratio_recompute` job type: load passed facts, call ratio functions, upsert derived rows
- [ ] Write `test_ratios.py`: known input → known output; zero denominator → None (not exception); all required ratio codes present
- [ ] Write `test_peer_analysis.py`: peer multiples computed for at least 3 peers; handles missing peer data gracefully

**Tests to Write:**
```python
# test_ratios.py
def test_gross_margin_calculation():
    facts = {"revenue": 1_000_000, "cost_of_goods": 600_000}
    result = calculate_profitability_ratios(facts)
    assert result["gross_margin"] == pytest.approx(0.40)

def test_zero_denominator_returns_none():
    facts = {"revenue": 0, "net_income": 100_000}
    result = calculate_profitability_ratios(facts)
    assert result["net_margin"] is None

def test_revenue_cagr_three_years():
    facts_by_year = {2021: {"revenue": 1e9}, 2022: {"revenue": 1.1e9}, 2023: {"revenue": 1.21e9}}
    result = calculate_growth_metrics(facts_by_year)
    assert result["revenue_cagr_3y"] == pytest.approx(0.10, abs=0.001)

def test_no_llm_calls_in_ratios(monkeypatch):
    # assert openai client never called
    ...
```

**Acceptance Criteria:**
- 100% of ratio calculation unit tests pass
- Zero denominator never raises exception — returns `None`
- No LLM call in `ratios.py` or `peer_analysis.py`
- `derived.financial_ratios` populated for all golden tickers after recompute
- `input_fact_ids` in `derived.financial_ratios` traces back to actual `canonical.financial_facts` rows
- Ratios computed only from `quality_status = 'passed'` facts

**Risks:**
- Peer group may have fewer than 3 valid peers if data coverage is sparse — compute with available peers, flag warning if < 3
- CAGR calculation requires consistent fiscal year coverage — validate before computing, skip and warn if data incomplete

**Compact Handoff Prompt for Coding Agent:**
```
Task: Implement Phase 4 — financial ratio engine and peer comparison.

Scope:
- backend/app/analytics/ratios.py
- backend/app/analytics/peer_analysis.py
- backend/app/repositories/derived_repository.py
- backend/app/schemas/financials.py (add FinancialRatioRow, PeerMetricRow)
- backend/app/dataops/job_runner.py (add derived_ratio_recompute handler)
- backend/tests/unit/test_ratios.py
- backend/tests/unit/test_peer_analysis.py

Files forbidden:
- backend/app/analytics/dcf.py
- backend/app/agents/*
- backend/app/workflows/*

Acceptance criteria:
- 100% unit tests pass.
- Zero denominator returns None, never raises exception.
- No LLM calls.
- Only quality_status='passed' facts are used as inputs.
- input_fact_ids in derived rows trace to real canonical fact UUIDs.

Do not:
- Implement DCF or multiples valuation.
- Read quality_status!='passed' facts.
- Call any LLM.
```

---

### Phase 5 — Golden Dataset Backfill + Report Readiness

**Goal:** Run the full pipeline end-to-end for 5 golden tickers. Seed Supabase via backfill scripts. Validate completeness >= 0.85 and report-agent readiness.

**Scope:**
- Backfill scripts for 5 golden tickers: DHG, TRA, IMP, DBD, DMC
- Manual golden CSV/YAML fixtures as audit baseline
- End-to-end integration test: ingest → normalize → quality gate → ratios → verify completeness
- `data/golden/{TICKER}/` file structure

**Out of Scope:**
- DCF / multiples valuation engine
- LangGraph agent wiring
- Report synthesis

**Files to Create:**
- `backend/scripts/seed_universe.py`
- `backend/scripts/backfill_golden_tickers.py`
- `data/golden/DHG/financial_facts_audited.csv`
- `data/golden/DHG/market_prices_sample.csv`
- `data/golden/DHG/company_profile.yaml`
- `data/golden/DHG/expected_ratios.csv`
- `data/golden/DHG/source_manifest.yaml`
- (same structure for TRA, IMP, DBD, DMC)
- `backend/tests/e2e/test_golden_pipeline.py`

**Files to Modify:**
- None (scripts only)

**Supabase Tables Validated:**
- All `canonical.*` and `derived.*` tables populated for 5 tickers
- `governance.data_quality_checks` has pass results for all 5
- `governance.source_manifest` non-empty for all 5

**Implementation Tasks:**

- [ ] Create `backend/scripts/seed_universe.py`: read `pharma_vn_53.yaml`, insert all tickers into `ref.companies` and `ref.ticker_universe`, insert peer groups into `ref.peer_groups`; idempotent (upsert)
- [ ] Create `backend/scripts/backfill_golden_tickers.py`: for each golden ticker, enqueue jobs in `ops.ingestion_jobs` for `company_profile_refresh`, `daily_price_refresh`, `financial_statement_refresh`; then run `job_runner` until all jobs complete
- [ ] Seed `data/golden/DHG/` with manually audited CSV/YAML files (use actual DHG public BCTC data)
- [ ] Repeat golden files for TRA, IMP, DBD, DMC
- [ ] Write `test_golden_pipeline.py`:
  - `test_dhg_completeness_score_meets_threshold()` — assert `completeness_score >= 0.85`
  - `test_dhg_required_line_items_present()` — assert revenue, net_income, total_assets, total_equity, operating_cash_flow present for >= 3 years
  - `test_dhg_all_facts_have_lineage()` — assert no orphaned facts
  - `test_dhg_ratios_computed()` — assert `derived.financial_ratios` has rows for gross_margin, net_margin, ROE, ROA
  - `test_agent_cannot_access_raw_payloads()` — assert no report-agent code imports `raw_repository`
  - Repeat for TRA, IMP (at minimum)

**Acceptance Criteria:**
- `completeness_score >= 0.85` for all 5 golden tickers
- `canonical.financial_facts` has revenue, net_income, total_assets, total_equity, operating_cash_flow for 3+ fiscal years per golden ticker
- Every canonical fact has a `governance.fact_lineage` record
- `derived.financial_ratios` populated for all golden tickers
- Zero facts with `quality_status = 'pending'` after full run
- End-to-end tests pass for DHG, TRA, IMP (minimum 3 of 5)
- Manual golden CSVs match within tolerance: field extraction accuracy >= 98%

**Risks:**
- Vnstock may not have complete BCTC for all 5 golden tickers → supplement with manual CSV ingestion path
- Historical price gaps may lower completeness score → log as warning, not hard fail

**Compact Handoff Prompt for Coding Agent:**
```
Task: Implement Phase 5 — golden dataset backfill and end-to-end pipeline validation.

Scope:
- backend/scripts/seed_universe.py
- backend/scripts/backfill_golden_tickers.py
- data/golden/{DHG,TRA,IMP,DBD,DMC}/ (CSV + YAML fixtures)
- backend/tests/e2e/test_golden_pipeline.py

Files forbidden:
- backend/app/analytics/dcf.py
- backend/app/agents/*
- backend/app/workflows/*

Acceptance criteria:
- completeness_score >= 0.85 for all 5 golden tickers.
- 3+ fiscal years of required line items in canonical.financial_facts.
- Zero facts with quality_status='pending' after full run.
- All facts have fact_lineage records.
- E2E tests pass for DHG, TRA, IMP.

Do not:
- Implement report synthesis.
- Call any LLM.
- Modify existing schema migrations.
```

---

## 5. PR Strategy

| PR | Phase | Branch Name | Description |
|---|---|---|---|
| PR-01 | Phase 0 | `feat/schema-universe-config` | Schema migrations + universe YAML + validator |
| PR-02 | Phase 1 | `feat/vnstock-connector-raw-store` | Vnstock adapter + raw payload persistence |
| PR-03 | Phase 2 | `feat/normalization-canonical-facts` | Taxonomy mapping + canonical fact upsert + lineage |
| PR-04 | Phase 3 | `feat/data-quality-gates` | Quality checks + completeness scoring |
| PR-05 | Phase 4 | `feat/derived-ratios-peer-metrics` | Financial ratio engine + peer analysis |
| PR-06 | Phase 5 | `feat/golden-backfill-e2e` | Backfill scripts + golden fixtures + E2E tests |

**Rules:**
- Each PR must pass its own acceptance criteria before merging
- PRs are sequential — no parallel merges that skip a phase
- Each PR updates `CHANGELOG.md [Unreleased]`
- No PR may introduce LLM calls in ingestion or analytics modules

---

## 6. Testing Strategy

| Layer | Framework | Scope |
|---|---|---|
| Unit | `pytest` | Pure functions: normalization, ratio calculation, quality checks, universe validator |
| Integration | `pytest` + test Supabase instance | Repository write/read, dedup behavior, lineage creation |
| End-to-End | `pytest` | Full pipeline for golden tickers; completeness score; no orphaned facts |
| Regression | `pytest` + golden CSV fixtures | Extracted values match audited CSVs within tolerance |

**Test isolation rules:**
- Unit tests must not call Supabase or Vnstock — use Pydantic model fixtures
- Integration tests use a dedicated `SUPABASE_TEST_URL` from `.env.test`
- E2E tests run against seeded golden data only; never against production Supabase

**Tolerance policy for numeric assertions:**
- Revenue, net income, total assets: `±0.1%` or rounding tolerance
- Ratio percentages: `±0.1 percentage points`
- CAGR: `±0.1 percentage points`

---

## 7. Definition of Done

**Per phase:** All acceptance criteria in the phase's section are met AND all tests introduced in that phase pass.

**Full data foundation done when:**

```
□ Supabase has all 6 schemas with expected tables and constraints
□ data/universe/pharma_vn_53.yaml validates: 53 tickers, 5 golden tickers, no duplicates
□ Only vnstock_client.py imports vnstock
□ Every canonical financial fact has source_id, lineage, and quality_status != 'pending'
□ All canonical financial fact values use currency='VND', unit='VND'
□ No raw Vnstock column names appear in line_item_code
□ All 5 golden tickers: completeness_score >= 0.85
□ derived.financial_ratios populated for golden tickers
□ Zero LLM calls in any ingestion, normalization, quality, or ratio module
□ Report agents cannot import raw_repository (enforced by test)
□ E2E tests pass for DHG, TRA, IMP
□ CHANGELOG.md updated for all 6 PRs
```

---

## 8. What Not to Build Yet

| Item | When |
|---|---|
| DCF engine (`dcf.py`) | Phase after data foundation — analytics engine phase |
| Multiples valuation (`multiples.py`) | Same as DCF |
| Sensitivity analysis (`sensitivity.py`) | After DCF + multiples are stable |
| LangGraph agent wiring | After analytics engine validated |
| Report synthesis (`synthesis_auditor.py`) | After all agents wired |
| Claim ledger + citation eval | After synthesis agent |
| FastAPI endpoints for research runs | After LangGraph graph is testable |
| FireAnt connector | Explicitly out of MVP |
| Celery/Redis queue | When batch 53-ticker concurrent jobs needed |
| MinIO/S3 artifact store | When local file storage is insufficient |
| Streamlit HITL dashboard | After backend pipeline is end-to-end validated |
| Flash memo and catalyst refresh run types | After full report pipeline is stable |
| Scale-up beyond 5 golden tickers | After E2E tests confirm golden pipeline correctness |

---

*Plan version: v1.0 · Date: 2026-05-08 · Source: DATA_INGESTION_PLAN_SUPABASE_VNSTOCK.md + README.md + specs/PRD.md*
