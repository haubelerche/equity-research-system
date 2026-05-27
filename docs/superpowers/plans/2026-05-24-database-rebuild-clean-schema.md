# Database Rebuild — Clean 4-Schema Migration Plan PATCHED

> **Scope:** PostgreSQL/Supabase rebuild for Vietnam Pharma Equity Research Agent.

---

## 0. Executive Decision

The current Supabase database is experimental, dirty, and not worth preserving. Rebuild from scratch, but do it through controlled migrations rather than manual table creation.

The target design remains four schemas:

```text
ref       -> reference/config/taxonomy/formula metadata
ingest    -> source registry, raw payloads, document chunks, validation issues
fact      -> accepted source-derived financial facts, prices, catalyst events
research  -> runs, deterministic metrics, valuation, report claims, evidence, evaluation, approvals, artifacts
```

This patched plan fixes the blocking issues in the previous plan:

1. Formula IDs now match `FORMULA_FINANCE.md` exactly.
2. `ingest.sources` no longer has global `UNIQUE(checksum)`.
3. `document_chunks` moves from `research` to `ingest`.
4. `valuation_results.assumption_set_id` is `NOT NULL`.
5. Quantitative claim evidence is enforced by a final approval gate.
6. Migration runner transaction handling is corrected.
7. Supabase grants/default privileges are explicit.
8. Runtime tables support idempotency, retry, error tracking, and hashes.
9. Artifacts support versioning, checksum, storage path, and lock state.
10. MVP line items are expanded for valuation and financial ratios.

---

## 1. Non-Negotiable Design Rules

```text
1. Do not preserve dirty DHG test data.
2. Do not patch the old public-schema monolith.
3. Use migration-first rebuild only.
4. Keep exactly four logical schemas: ref, ingest, fact, research.
5. Do not create table-per-ticker or source-specific fact tables.
6. Do not store derived metrics inside fact.financial_facts.
7. All valuation/report numbers must come from accepted facts, deterministic metrics, or valuation results.
8. Formula IDs must be canonical F001-F030 from FORMULA_FINANCE.md.
9. Quantitative claims in approved reports must have evidence.
10. LLMs must not create or mutate canonical financial facts.
```

---

## 2. File Map

### New migration files

```text
scripts/db/migrations/_legacy/                         # archive old 001-006 SQL files
scripts/db/migrations/001_ref_schema.sql
scripts/db/migrations/002_ingest_schema.sql
scripts/db/migrations/003_fact_schema.sql
scripts/db/migrations/004_research_schema.sql
scripts/db/migrations/005_seed_reference_data.sql
scripts/db/migrations/006_grants_and_privileges.sql
```

### Modified files

```text
scripts/db/migrate.py
scripts/db/fact_store.py
scripts/db/source_registry.py
backend/runtime_store.py
backend/facts/normalizer.py
scripts/build_facts.py
scripts/connectors/vnstock_finance_connector.py
scripts/connectors/vnstock_price_connector.py
scripts/connectors/vnstock_company_connector.py
tests/integration/test_db_integrity.py
```

### Optional helper files

```text
backend/evaluation/citation_gate.py
backend/evaluation/evidence_validator.py
```

Create optional helpers only if equivalent evaluation utilities do not already exist.

---

## 3. Column Rename Reference

| Old object | New object |
|---|---|
| `public.financial_facts` | `fact.financial_facts` |
| `financial_facts.company_ticker` | `fact.financial_facts.ticker` |
| `financial_facts.taxonomy_key` | `fact.financial_facts.line_item_code` |
| `financial_facts.source_version_id` | `fact.financial_facts.source_id` |
| `financial_facts.parser_version` | `fact.financial_facts.connector_version` |
| `public.source_versions` | `ingest.sources` |
| `source_versions.id` | `ingest.sources.source_id` |
| `source_versions.source_id` | `ingest.sources.logical_id` |
| `public.price_history` | `fact.price_history` |
| `price_history.date` | `fact.price_history.trade_date` |
| `price_history.value` | `fact.price_history.traded_value` |
| `price_history.source_version_id` | `fact.price_history.source_id` |
| `public.catalyst_events` | `fact.catalyst_events` |
| `catalyst_events.company_ticker` | `fact.catalyst_events.ticker` |
| `catalyst_events.source_version_id` | `fact.catalyst_events.source_id` |
| `public.company_profiles` | `ref.companies` + `ingest.company_snapshots` |
| `public.research_runs` | `research.runs` |
| `research_runs.current_state` | `research.runs.current_stage` |
| `research_runs.policy_json` | removed; use `request_json`, `config_snapshot_json`, `flags_json` |
| `public.run_steps` | `research.run_steps` |
| `public.run_artifacts` | `research.run_artifacts` |
| `public.run_approvals` | `research.run_approvals` |
| `public.run_budget_ledger` | `research.run_budget_ledger` |
| `public.run_audit_events` | `research.run_audit_events` |
| `public.accepted_financial_facts` | `fact.accepted_financial_facts` |
| `research.document_chunks` from old plan | `ingest.document_chunks` |

---

# Task 1 — Archive Legacy Migrations

Move old migration files:

```text
scripts/db/migrations/00{1-6}_*.sql
```

to:

```text
scripts/db/migrations/_legacy/
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force "scripts\db\migrations\_legacy"
Move-Item "scripts\db\migrations\00*.sql" "scripts\db\migrations\_legacy\"
```

Bash:

```bash
mkdir -p scripts/db/migrations/_legacy
mv scripts/db/migrations/00*.sql scripts/db/migrations/_legacy/
```

Verification:

```bash
find scripts/db/migrations -maxdepth 2 -name "*.sql" -print
```

---

# Task 2 — Migration 001: `ref` Schema

File:

```text
scripts/db/migrations/001_ref_schema.sql
```

Important: migration runner owns transaction boundaries. Do **not** include `BEGIN;` or `COMMIT;` inside migration files.

```sql
-- Migration: 001_ref_schema.sql
-- Purpose: Create canonical reference schema.

CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE IF NOT EXISTS ref.companies (
    ticker           VARCHAR(10) PRIMARY KEY,
    company_name_vi  TEXT        NOT NULL,
    company_name_en  TEXT,
    exchange         VARCHAR(10) NOT NULL,
    sector           TEXT        NOT NULL DEFAULT 'pharma',
    subsector        TEXT,
    currency         CHAR(3)     NOT NULL DEFAULT 'VND',
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ref.universes (
    universe_id      VARCHAR(64) PRIMARY KEY,
    universe_name    TEXT        NOT NULL UNIQUE,
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ref.universe_members (
    universe_id      VARCHAR(64) NOT NULL REFERENCES ref.universes(universe_id) ON DELETE CASCADE,
    ticker           VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    peer_group       TEXT,
    enabled_methods  TEXT[]      NOT NULL DEFAULT ARRAY['dcf', 'pe', 'pb'],
    is_enabled       BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (universe_id, ticker)
);

CREATE TABLE IF NOT EXISTS ref.line_items (
    line_item_code   VARCHAR(100) PRIMARY KEY,
    statement_type   VARCHAR(40)  NOT NULL CHECK (
        statement_type IN ('income_statement', 'balance_sheet', 'cash_flow', 'market', 'assumption', 'other')
    ),
    display_name_vi  TEXT         NOT NULL,
    display_name_en  TEXT,
    canonical_unit   VARCHAR(40)  NOT NULL,
    is_derived       BOOLEAN      NOT NULL DEFAULT FALSE,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    description      TEXT
);

CREATE TABLE IF NOT EXISTS ref.formulas (
    formula_id       VARCHAR(20)  PRIMARY KEY,
    formula_name     TEXT         NOT NULL,
    formula_group    TEXT         NOT NULL,
    function_name    TEXT         NOT NULL,
    formula_text     TEXT         NOT NULL,
    output_unit      VARCHAR(40)  NOT NULL,
    description      TEXT,
    version          VARCHAR(20)  NOT NULL DEFAULT 'v1',
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE
);
```

Verification:

```bash
python - <<'PY'
from pathlib import Path
sql = Path('scripts/db/migrations/001_ref_schema.sql').read_text()
for required in ['ref.companies', 'ref.universes', 'ref.universe_members', 'ref.line_items', 'ref.formulas', 'function_name']:
    assert required in sql, required
print('001_ref_schema.sql OK')
PY
```

---

# Task 3 — Migration 002: `ingest` Schema

File:

```text
scripts/db/migrations/002_ingest_schema.sql
```

Key fixes:

```text
- No global UNIQUE(checksum).
- Use UNIQUE(logical_id, source_uri, checksum).
- Add ingest.raw_payloads.
- Put document_chunks under ingest, not research.
- Keep checksum indexed for dedup/search.
```

```sql
-- Migration: 002_ingest_schema.sql
-- Purpose: Source registry, raw payloads, document chunks, connector runs, validation issues.

CREATE SCHEMA IF NOT EXISTS ingest;

CREATE TABLE IF NOT EXISTS ingest.sources (
    source_id         VARCHAR(64) PRIMARY KEY,
    logical_id        VARCHAR(120) NOT NULL,
    ticker            VARCHAR(10) REFERENCES ref.companies(ticker),
    source_type       VARCHAR(50) NOT NULL CHECK (
        source_type IN (
            'vnstock_financial', 'vnstock_price', 'vnstock_company',
            'financial_statement', 'annual_report', 'disclosure', 'news',
            'regulatory', 'regulatory_filing', 'tender', 'bidding',
            'industry_report', 'market_reference', 'manual'
        )
    ),
    source_uri        TEXT NOT NULL,
    source_title      TEXT,
    published_at      TIMESTAMPTZ,
    fiscal_year       SMALLINT,
    fiscal_period     VARCHAR(4) CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
    reliability_tier  SMALLINT NOT NULL DEFAULT 2 CHECK (reliability_tier BETWEEN 1 AND 3),
    connector_version VARCHAR(40) NOT NULL,
    checksum          CHAR(64) NOT NULL,
    raw_path          TEXT,
    metadata_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (logical_id, source_uri, checksum)
);

CREATE INDEX IF NOT EXISTS idx_ingest_sources_ticker
    ON ingest.sources(ticker, ingested_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingest_sources_checksum
    ON ingest.sources(checksum);

CREATE INDEX IF NOT EXISTS idx_ingest_sources_type_year
    ON ingest.sources(source_type, fiscal_year);

CREATE TABLE IF NOT EXISTS ingest.raw_payloads (
    id           BIGSERIAL PRIMARY KEY,
    source_id    VARCHAR(64) NOT NULL REFERENCES ingest.sources(source_id) ON DELETE CASCADE,
    content_type VARCHAR(80) NOT NULL,
    payload_json JSONB,
    payload_text TEXT,
    storage_path TEXT,
    checksum     CHAR(64) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingest_raw_payloads_source
    ON ingest.raw_payloads(source_id);

CREATE INDEX IF NOT EXISTS idx_ingest_raw_payloads_checksum
    ON ingest.raw_payloads(checksum);

CREATE TABLE IF NOT EXISTS ingest.document_chunks (
    chunk_id      BIGSERIAL PRIMARY KEY,
    source_id     VARCHAR(64) NOT NULL REFERENCES ingest.sources(source_id) ON DELETE CASCADE,
    ticker        VARCHAR(10) REFERENCES ref.companies(ticker),
    chunk_index   INTEGER NOT NULL,
    section_title TEXT,
    chunk_text    TEXT NOT NULL,
    fiscal_year   SMALLINT,
    language      VARCHAR(10) NOT NULL DEFAULT 'vi',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_ingest_document_chunks_ticker
    ON ingest.document_chunks(ticker);

CREATE INDEX IF NOT EXISTS idx_ingest_document_chunks_metadata
    ON ingest.document_chunks USING GIN(metadata_json);

CREATE INDEX IF NOT EXISTS idx_ingest_document_chunks_fts
    ON ingest.document_chunks USING GIN(to_tsvector('simple', chunk_text));

CREATE TABLE IF NOT EXISTS ingest.connector_runs (
    run_id          VARCHAR(64) PRIMARY KEY,
    ticker          VARCHAR(10) REFERENCES ref.companies(ticker),
    connector_name  VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL CHECK (
        status IN ('running', 'completed', 'failed', 'partial', 'skipped')
    ),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    sources_created INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    stats_json      JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ingest_connector_runs_ticker
    ON ingest.connector_runs(ticker, started_at DESC);

CREATE TABLE IF NOT EXISTS ingest.validation_issues (
    id               BIGSERIAL PRIMARY KEY,
    source_id        VARCHAR(64) REFERENCES ingest.sources(source_id) ON DELETE CASCADE,
    connector_run_id VARCHAR(64) REFERENCES ingest.connector_runs(run_id),
    issue_type       VARCHAR(50) NOT NULL CHECK (
        issue_type IN (
            'missing_value', 'out_of_range', 'failed_checksum', 'duplicate',
            'taxonomy_mismatch', 'stale_data', 'parse_error', 'unit_mismatch', 'other'
        )
    ),
    field_name       TEXT,
    description      TEXT NOT NULL,
    severity         VARCHAR(10) NOT NULL CHECK (severity IN ('blocking', 'error', 'warning', 'info')),
    details_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingest_validation_issues_source
    ON ingest.validation_issues(source_id);

CREATE TABLE IF NOT EXISTS ingest.company_snapshots (
    id                BIGSERIAL PRIMARY KEY,
    ticker            VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    source_id         VARCHAR(64) REFERENCES ingest.sources(source_id),
    overview_json     JSONB,
    shareholders_json JSONB,
    officers_json     JSONB,
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingest_company_snapshots_ticker
    ON ingest.company_snapshots(ticker, synced_at DESC);
```

Verification:

```bash
python - <<'PY'
from pathlib import Path
sql = Path('scripts/db/migrations/002_ingest_schema.sql').read_text()
assert 'UNIQUE (checksum)' not in sql
assert 'UNIQUE (logical_id, source_uri, checksum)' in sql
for required in ['ingest.sources', 'ingest.raw_payloads', 'ingest.document_chunks', 'idx_ingest_sources_checksum']:
    assert required in sql, required
print('002_ingest_schema.sql OK')
PY
```

---

# Task 4 — Migration 003: `fact` Schema

File:

```text
scripts/db/migrations/003_fact_schema.sql
```

Key fixes:

```text
- price_history.value -> traded_value.
- Add adjusted_close and market_cap.
- Add CHECK for catalyst_events.event_type.
- Keep duplicate-free accepted financial facts.
```

```sql
-- Migration: 003_fact_schema.sql
-- Purpose: Canonical source-derived facts, market prices, catalyst events, accepted facts view.

CREATE SCHEMA IF NOT EXISTS fact;

CREATE TABLE IF NOT EXISTS fact.financial_facts (
    id                BIGSERIAL PRIMARY KEY,
    ticker            VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    fiscal_year       SMALLINT NOT NULL,
    fiscal_period     VARCHAR(4) NOT NULL CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
    line_item_code    VARCHAR(100) NOT NULL REFERENCES ref.line_items(line_item_code),
    value             NUMERIC NOT NULL,
    unit              VARCHAR(40) NOT NULL,
    currency          CHAR(3) NOT NULL DEFAULT 'VND',
    source_id         VARCHAR(64) NOT NULL REFERENCES ingest.sources(source_id),
    connector_version VARCHAR(40) NOT NULL,
    validation_status VARCHAR(25) NOT NULL CHECK (
        validation_status IN ('raw', 'validated', 'accepted', 'rejected', 'needs_review')
    ),
    confidence        NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    is_current        BOOLEAN NOT NULL DEFAULT TRUE,
    effective_date    DATE,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, fiscal_year, fiscal_period, line_item_code, source_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_financial_facts_ticker_period
    ON fact.financial_facts(ticker, fiscal_year, fiscal_period);

CREATE INDEX IF NOT EXISTS idx_fact_financial_facts_line_item
    ON fact.financial_facts(line_item_code, fiscal_year);

CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_current_accepted
    ON fact.financial_facts(ticker, fiscal_year, fiscal_period, line_item_code)
    WHERE is_current = TRUE AND validation_status = 'accepted';

CREATE TABLE IF NOT EXISTS fact.price_history (
    ticker         VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    trade_date     DATE NOT NULL,
    open           NUMERIC,
    high           NUMERIC,
    low            NUMERIC,
    close          NUMERIC,
    adjusted_close NUMERIC,
    volume         BIGINT,
    traded_value   NUMERIC,
    market_cap     NUMERIC,
    source_id      VARCHAR(64) REFERENCES ingest.sources(source_id),
    ingested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_price_history_ticker_date
    ON fact.price_history(ticker, trade_date DESC);

CREATE TABLE IF NOT EXISTS fact.catalyst_events (
    event_id          VARCHAR(64) PRIMARY KEY,
    ticker            VARCHAR(10) REFERENCES ref.companies(ticker),
    event_type        VARCHAR(50) NOT NULL CHECK (
        event_type IN (
            'news', 'disclosure', 'regulatory', 'tender', 'bidding',
            'drug_registration', 'dividend', 'corporate_action', 'other'
        )
    ),
    title             TEXT NOT NULL,
    summary           TEXT,
    occurred_at       TIMESTAMPTZ NOT NULL,
    effective_date    DATE,
    materiality_hint  VARCHAR(10) CHECK (materiality_hint IN ('high', 'medium', 'low', 'unknown')),
    source_url        TEXT,
    source_id         VARCHAR(64) NOT NULL REFERENCES ingest.sources(source_id),
    confidence        NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    validation_status VARCHAR(25) NOT NULL CHECK (
        validation_status IN ('raw', 'validated', 'accepted', 'rejected', 'needs_review')
    ),
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_catalyst_ticker_date
    ON fact.catalyst_events(ticker, occurred_at DESC);

CREATE OR REPLACE VIEW fact.accepted_financial_facts AS
SELECT
    id,
    ticker,
    fiscal_year,
    fiscal_period,
    line_item_code,
    value,
    unit,
    currency,
    source_id,
    connector_version,
    confidence,
    effective_date,
    ingested_at
FROM fact.financial_facts
WHERE validation_status = 'accepted'
  AND fiscal_period = 'FY'
  AND is_current = TRUE;

COMMENT ON VIEW fact.accepted_financial_facts IS
    'Valuation-safe subset: accepted, FY, current facts only. Valuation/reporting code must read from this view.';
```

Verification:

```bash
python - <<'PY'
from pathlib import Path
sql = Path('scripts/db/migrations/003_fact_schema.sql').read_text()
for required in ['fact.financial_facts', 'uq_fact_current_accepted', 'trade_date', 'traded_value', 'adjusted_close', 'market_cap', 'event_type IN', 'fact.accepted_financial_facts']:
    assert required in sql, required
print('003_fact_schema.sql OK')
PY
```

---

# Task 5 — Migration 004: `research` Schema

File:

```text
scripts/db/migrations/004_research_schema.sql
```

Key fixes:

```text
- Add idempotency_key, request_json, config_snapshot_json.
- Add retry_count, error_message, input_hash, output_hash.
- Add artifact versioning, checksum, storage_path, and lock state.
- Make valuation result assumption trace mandatory.
- Keep document chunks out of research; they are in ingest.
- Add missing-evidence and invalid-evidence views.
- Add trigger blocking final approval if quantitative claims lack evidence.
```

```sql
-- Migration: 004_research_schema.sql
-- Purpose: Research runtime, metrics, valuation, report claims, evidence, evaluation, approvals.

CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.runs (
    run_id               VARCHAR(64) PRIMARY KEY,
    ticker               VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    run_type             VARCHAR(32) NOT NULL CHECK (
        run_type IN ('full_report', 'flash_memo', 'catalyst_refresh', 'valuation_only', 'data_refresh')
    ),
    objective            TEXT NOT NULL,
    status               VARCHAR(32) NOT NULL CHECK (
        status IN (
            'initialized', 'running', 'data_ready', 'analysis_ready', 'valuation_ready',
            'report_ready', 'needs_human_review', 'approved', 'failed', 'cancelled'
        )
    ),
    current_stage        VARCHAR(64) NOT NULL DEFAULT 'initialized',
    idempotency_key      VARCHAR(128) UNIQUE,
    org_id               VARCHAR(64),
    requested_by         VARCHAR(128),
    request_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    config_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    flags_json           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_research_runs_ticker
    ON research.runs(ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_runs_status
    ON research.runs(status, created_at DESC);

CREATE TABLE IF NOT EXISTS research.run_steps (
    id             BIGSERIAL PRIMARY KEY,
    run_id         VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    step_name      VARCHAR(64) NOT NULL,
    agent_name     VARCHAR(64) NOT NULL,
    status         VARCHAR(32) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    retry_count    INTEGER NOT NULL DEFAULT 0,
    input_hash     TEXT,
    output_hash    TEXT,
    policy_reason  TEXT,
    error_message  TEXT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at       TIMESTAMPTZ,
    duration_ms    BIGINT,
    metadata_json  JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_research_run_steps_run
    ON research.run_steps(run_id, started_at DESC);

CREATE TABLE IF NOT EXISTS research.run_artifacts (
    artifact_id        VARCHAR(64) PRIMARY KEY,
    run_id             VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    artifact_type      VARCHAR(64) NOT NULL CHECK (
        artifact_type IN (
            'data_inventory', 'metric_table', 'valuation_result_json', 'source_manifest_json',
            'claim_ledger_json', 'eval_result_json', 'run_log_json', 'report_md',
            'report_html', 'report_pdf', 'other'
        )
    ),
    section_key        VARCHAR(64),
    version            INTEGER NOT NULL DEFAULT 1,
    payload_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    storage_path       TEXT,
    checksum           CHAR(64),
    is_locked          BOOLEAN NOT NULL DEFAULT FALSE,
    confidence         NUMERIC(6,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_by_agent   VARCHAR(64),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_run_artifacts_run
    ON research.run_artifacts(run_id, artifact_type);

CREATE UNIQUE INDEX IF NOT EXISTS uq_research_run_artifact_version
    ON research.run_artifacts(run_id, artifact_type, COALESCE(section_key, ''), version);

CREATE TABLE IF NOT EXISTS research.run_budget_ledger (
    id                BIGSERIAL PRIMARY KEY,
    run_id            VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    step_name         VARCHAR(64) NOT NULL,
    model_name        VARCHAR(80) NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(12,6) NOT NULL DEFAULT 0,
    budget_policy     VARCHAR(32),
    fallback_model    VARCHAR(80),
    stop_reason       VARCHAR(80),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_budget_run
    ON research.run_budget_ledger(run_id);

CREATE TABLE IF NOT EXISTS research.run_audit_events (
    id            BIGSERIAL PRIMARY KEY,
    run_id        VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    actor         VARCHAR(128) NOT NULL,
    action        VARCHAR(64) NOT NULL,
    rule_reason   TEXT,
    policy_reason TEXT,
    payload_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_audit_run
    ON research.run_audit_events(run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS research.metric_values (
    id                BIGSERIAL PRIMARY KEY,
    run_id            VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    ticker            VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    fiscal_year       SMALLINT,
    fiscal_period     VARCHAR(4) CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4', 'TTM')),
    formula_id        VARCHAR(20) NOT NULL REFERENCES ref.formulas(formula_id),
    metric_key        VARCHAR(100) NOT NULL,
    value             NUMERIC(28,8),
    unit              VARCHAR(40) NOT NULL,
    input_fact_ids    BIGINT[] NOT NULL DEFAULT '{}',
    input_values_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_metric_values_run
    ON research.metric_values(run_id, metric_key);
CREATE INDEX IF NOT EXISTS idx_research_metric_values_ticker
    ON research.metric_values(ticker, fiscal_year, formula_id);

CREATE TABLE IF NOT EXISTS research.valuation_assumption_sets (
    id               BIGSERIAL PRIMARY KEY,
    run_id           VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    method           VARCHAR(32) NOT NULL CHECK (method IN ('dcf', 'pe', 'pb', 'ev_ebitda', 'mixed')),
    scenario         VARCHAR(20) NOT NULL CHECK (scenario IN ('bear', 'base', 'bull')),
    assumptions_json JSONB NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    approved_by      VARCHAR(128),
    approved_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, method, scenario)
);

CREATE TABLE IF NOT EXISTS research.valuation_results (
    id                   BIGSERIAL PRIMARY KEY,
    run_id               VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    assumption_set_id    BIGINT NOT NULL REFERENCES research.valuation_assumption_sets(id),
    method               VARCHAR(32) NOT NULL CHECK (method IN ('dcf', 'pe', 'pb', 'ev_ebitda', 'mixed')),
    scenario             VARCHAR(20) NOT NULL CHECK (scenario IN ('bear', 'base', 'bull')),
    target_price         NUMERIC(18,4),
    valuation_range_low  NUMERIC(18,4),
    valuation_range_high NUMERIC(18,4),
    enterprise_value     NUMERIC(28,4),
    equity_value         NUMERIC(28,4),
    result_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, method, scenario)
);

CREATE INDEX IF NOT EXISTS idx_research_valuation_results_run
    ON research.valuation_results(run_id, method, scenario);

CREATE TABLE IF NOT EXISTS research.report_sections (
    section_id       BIGSERIAL PRIMARY KEY,
    run_id           VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    section_key      VARCHAR(64) NOT NULL,
    section_title    TEXT NOT NULL,
    section_order    INTEGER NOT NULL,
    content_markdown TEXT NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    status           VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected', 'needs_revision')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, section_key, version)
);

CREATE TABLE IF NOT EXISTS research.report_claims (
    claim_id          BIGSERIAL PRIMARY KEY,
    run_id            VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    section_id        BIGINT REFERENCES research.report_sections(section_id) ON DELETE SET NULL,
    section_key       VARCHAR(64),
    claim_text        TEXT NOT NULL,
    claim_type        VARCHAR(20) NOT NULL CHECK (claim_type IN ('quantitative', 'qualitative', 'inference')),
    numbers_used_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence        NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    verdict           VARCHAR(20) NOT NULL CHECK (verdict IN ('pass', 'fail', 'needs_review')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_report_claims_run
    ON research.report_claims(run_id, verdict, claim_type);

CREATE TABLE IF NOT EXISTS research.claim_evidence (
    id              BIGSERIAL PRIMARY KEY,
    claim_id        BIGINT NOT NULL REFERENCES research.report_claims(claim_id) ON DELETE CASCADE,
    evidence_type   VARCHAR(32) NOT NULL CHECK (
        evidence_type IN ('financial_fact', 'metric_value', 'valuation_result', 'source', 'document_chunk', 'catalyst_event')
    ),
    evidence_id     TEXT NOT NULL,
    source_id       VARCHAR(64) REFERENCES ingest.sources(source_id),
    quote_text      TEXT,
    relevance_score NUMERIC(5,4) CHECK (relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 1)),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_claim_evidence_claim
    ON research.claim_evidence(claim_id);

CREATE TABLE IF NOT EXISTS research.evaluation_results (
    id           BIGSERIAL PRIMARY KEY,
    run_id       VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    eval_name    VARCHAR(80) NOT NULL CHECK (
        eval_name IN (
            'numeric_consistency', 'citation_coverage', 'citation_validity', 'claim_evidence_validity',
            'quantitative_claim_evidence', 'stale_data', 'valuation_reproducibility', 'unsupported_claims', 'overall'
        )
    ),
    score        NUMERIC(8,4),
    threshold    NUMERIC(8,4),
    passed       BOOLEAN NOT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_evaluation_results_run
    ON research.evaluation_results(run_id, eval_name);

CREATE TABLE IF NOT EXISTS research.run_approvals (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              VARCHAR(64) NOT NULL REFERENCES research.runs(run_id) ON DELETE CASCADE,
    approval_stage      VARCHAR(32) NOT NULL CHECK (approval_stage IN ('valuation_assumptions', 'report_draft', 'final_report')),
    decision            VARCHAR(16) NOT NULL CHECK (decision IN ('approved', 'rejected', 'needs_revision')),
    reviewer            VARCHAR(128),
    feedback_patch_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE VIEW research.quantitative_claims_without_evidence AS
SELECT rc.run_id, rc.claim_id, rc.claim_text
FROM research.report_claims rc
LEFT JOIN research.claim_evidence ce ON ce.claim_id = rc.claim_id
WHERE rc.claim_type = 'quantitative'
GROUP BY rc.run_id, rc.claim_id, rc.claim_text
HAVING COUNT(ce.id) = 0;

CREATE OR REPLACE VIEW research.invalid_claim_evidence AS
SELECT ce.*
FROM research.claim_evidence ce
WHERE
    (ce.evidence_type = 'financial_fact' AND NOT (ce.evidence_id ~ '^[0-9]+$' AND EXISTS (SELECT 1 FROM fact.financial_facts ff WHERE ff.id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'metric_value' AND NOT (ce.evidence_id ~ '^[0-9]+$' AND EXISTS (SELECT 1 FROM research.metric_values mv WHERE mv.id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'valuation_result' AND NOT (ce.evidence_id ~ '^[0-9]+$' AND EXISTS (SELECT 1 FROM research.valuation_results vr WHERE vr.id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'source' AND NOT EXISTS (SELECT 1 FROM ingest.sources s WHERE s.source_id = ce.evidence_id))
    OR (ce.evidence_type = 'document_chunk' AND NOT (ce.evidence_id ~ '^[0-9]+$' AND EXISTS (SELECT 1 FROM ingest.document_chunks dc WHERE dc.chunk_id = ce.evidence_id::BIGINT)))
    OR (ce.evidence_type = 'catalyst_event' AND NOT EXISTS (SELECT 1 FROM fact.catalyst_events ev WHERE ev.event_id = ce.evidence_id));

CREATE OR REPLACE FUNCTION research.final_report_approval_guard()
RETURNS TRIGGER AS $$
DECLARE
    missing_count INTEGER;
    invalid_count INTEGER;
BEGIN
    IF NEW.approval_stage = 'final_report' AND NEW.decision = 'approved' THEN
        SELECT COUNT(*) INTO missing_count
        FROM research.quantitative_claims_without_evidence
        WHERE run_id = NEW.run_id;

        IF missing_count > 0 THEN
            RAISE EXCEPTION 'Cannot approve final_report: % quantitative claims have no evidence', missing_count;
        END IF;

        SELECT COUNT(*) INTO invalid_count
        FROM research.invalid_claim_evidence ce
        JOIN research.report_claims rc ON rc.claim_id = ce.claim_id
        WHERE rc.run_id = NEW.run_id;

        IF invalid_count > 0 THEN
            RAISE EXCEPTION 'Cannot approve final_report: % claim evidence rows are invalid', invalid_count;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_final_report_approval_guard ON research.run_approvals;

CREATE TRIGGER trg_final_report_approval_guard
BEFORE INSERT OR UPDATE ON research.run_approvals
FOR EACH ROW
EXECUTE FUNCTION research.final_report_approval_guard();
```

Verification:

```bash
python - <<'PY'
from pathlib import Path
sql = Path('scripts/db/migrations/004_research_schema.sql').read_text()
required = ['idempotency_key', 'request_json', 'config_snapshot_json', 'retry_count', 'input_hash', 'output_hash', 'error_message', 'is_locked', 'storage_path', 'checksum', 'assumption_set_id    BIGINT NOT NULL', 'research.quantitative_claims_without_evidence', 'research.invalid_claim_evidence', 'research.final_report_approval_guard']
for item in required:
    assert item in sql, item
assert 'research.document_chunks' not in sql
print('004_research_schema.sql OK')
PY
```

---

# Task 6 — Migration 005: Seed Reference Data

File:

```text
scripts/db/migrations/005_seed_reference_data.sql
```

Critical rule:

```text
ref.formulas must match FORMULA_FINANCE.md exactly.
Do not redefine formula IDs.
```

```sql
-- Migration: 005_seed_reference_data.sql
-- Purpose: Seed MVP companies, universe, line items, and canonical formula metadata.

INSERT INTO ref.companies
    (ticker, company_name_vi, company_name_en, exchange, sector, subsector)
VALUES
    ('DHG', 'Công ty Cổ phần Dược Hậu Giang', 'Duoc Hau Giang Pharmaceutical JSC', 'HOSE', 'pharma', 'duoc_pham'),
    ('IMP', 'Công ty Cổ phần Imexpharm', 'Imexpharm Corporation', 'HOSE', 'pharma', 'duoc_pham'),
    ('DMC', 'Công ty Cổ phần Xuất nhập khẩu Y tế Domesco', 'Domesco Medical Import-Export JSC', 'HOSE', 'pharma', 'duoc_pham'),
    ('TRA', 'Công ty Cổ phần Traphaco', 'Traphaco JSC', 'HNX', 'pharma', 'duoc_pham'),
    ('DBD', 'Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định', 'Bidiphar JSC', 'HOSE', 'pharma', 'duoc_pham_thiet_bi_y_te')
ON CONFLICT (ticker) DO UPDATE
SET company_name_vi = EXCLUDED.company_name_vi,
    company_name_en = EXCLUDED.company_name_en,
    exchange = EXCLUDED.exchange,
    sector = EXCLUDED.sector,
    subsector = EXCLUDED.subsector,
    updated_at = NOW();

INSERT INTO ref.universes (universe_id, universe_name, description)
VALUES ('vietnam_pharma_mvp_5', 'Vietnam Pharma MVP 5', 'MVP universe: DHG, IMP, DMC, TRA, DBD')
ON CONFLICT (universe_id) DO NOTHING;

INSERT INTO ref.universe_members (universe_id, ticker, peer_group, enabled_methods)
VALUES
    ('vietnam_pharma_mvp_5', 'DHG', 'duoc_pham', ARRAY['dcf', 'pe', 'pb']),
    ('vietnam_pharma_mvp_5', 'IMP', 'duoc_pham', ARRAY['dcf', 'pe', 'pb', 'ev_ebitda']),
    ('vietnam_pharma_mvp_5', 'DMC', 'duoc_pham', ARRAY['dcf', 'pe', 'pb']),
    ('vietnam_pharma_mvp_5', 'TRA', 'duoc_pham', ARRAY['dcf', 'pe', 'pb']),
    ('vietnam_pharma_mvp_5', 'DBD', 'duoc_pham_thiet_bi_y_te', ARRAY['dcf', 'pe', 'pb', 'ev_ebitda'])
ON CONFLICT (universe_id, ticker) DO UPDATE
SET peer_group = EXCLUDED.peer_group,
    enabled_methods = EXCLUDED.enabled_methods,
    is_enabled = TRUE;

INSERT INTO ref.line_items
    (line_item_code, statement_type, display_name_vi, display_name_en, canonical_unit)
VALUES
    ('revenue.net', 'income_statement', 'Doanh thu thuần', 'Net revenue', 'vnd_bn'),
    ('cogs.total', 'income_statement', 'Giá vốn hàng bán', 'COGS', 'vnd_bn'),
    ('gross_profit.total', 'income_statement', 'Lợi nhuận gộp', 'Gross profit', 'vnd_bn'),
    ('sga.total', 'income_statement', 'Chi phí bán hàng và quản lý doanh nghiệp', 'SG&A', 'vnd_bn'),
    ('ebit.total', 'income_statement', 'Lợi nhuận trước lãi vay và thuế', 'EBIT', 'vnd_bn'),
    ('ebitda.total', 'income_statement', 'EBITDA', 'EBITDA', 'vnd_bn'),
    ('profit_before_tax.total', 'income_statement', 'Lợi nhuận trước thuế', 'Profit before tax', 'vnd_bn'),
    ('interest_expense.total', 'income_statement', 'Chi phí lãi vay', 'Interest expense', 'vnd_bn'),
    ('tax_expense.total', 'income_statement', 'Chi phí thuế thu nhập doanh nghiệp', 'Tax expense', 'vnd_bn'),
    ('net_income.parent', 'income_statement', 'Lợi nhuận sau thuế cổ đông công ty mẹ', 'Net income attributable to parent', 'vnd_bn'),
    ('eps.basic', 'income_statement', 'EPS cơ bản', 'Basic EPS', 'vnd'),
    ('cash_and_equivalents.ending', 'balance_sheet', 'Tiền và tương đương tiền cuối kỳ', 'Cash and equivalents', 'vnd_bn'),
    ('short_term_investments.ending', 'balance_sheet', 'Đầu tư tài chính ngắn hạn cuối kỳ', 'Short-term investments', 'vnd_bn'),
    ('inventory.ending', 'balance_sheet', 'Hàng tồn kho cuối kỳ', 'Inventory', 'vnd_bn'),
    ('accounts_receivable.ending', 'balance_sheet', 'Phải thu khách hàng cuối kỳ', 'Accounts receivable', 'vnd_bn'),
    ('accounts_payable.ending', 'balance_sheet', 'Phải trả người bán cuối kỳ', 'Accounts payable', 'vnd_bn'),
    ('current_assets.ending', 'balance_sheet', 'Tài sản ngắn hạn cuối kỳ', 'Current assets', 'vnd_bn'),
    ('current_liabilities.ending', 'balance_sheet', 'Nợ ngắn hạn cuối kỳ', 'Current liabilities', 'vnd_bn'),
    ('short_term_debt.ending', 'balance_sheet', 'Nợ vay ngắn hạn cuối kỳ', 'Short-term debt', 'vnd_bn'),
    ('total_debt.ending', 'balance_sheet', 'Tổng nợ vay cuối kỳ', 'Total debt', 'vnd_bn'),
    ('total_liabilities.ending', 'balance_sheet', 'Tổng nợ phải trả cuối kỳ', 'Total liabilities', 'vnd_bn'),
    ('total_assets.ending', 'balance_sheet', 'Tổng tài sản cuối kỳ', 'Total assets', 'vnd_bn'),
    ('equity.parent', 'balance_sheet', 'Vốn chủ sở hữu công ty mẹ', 'Equity attributable to parent', 'vnd_bn'),
    ('ppe.net', 'balance_sheet', 'Tài sản cố định hữu hình ròng', 'Net PPE', 'vnd_bn'),
    ('depreciation.total', 'cash_flow', 'Khấu hao', 'Depreciation', 'vnd_bn'),
    ('capex.total', 'cash_flow', 'Chi tiêu vốn', 'Capital expenditure', 'vnd_bn'),
    ('operating_cash_flow.total', 'cash_flow', 'Lưu chuyển tiền thuần từ hoạt động kinh doanh', 'Operating cash flow', 'vnd_bn'),
    ('shares_outstanding.weighted_avg', 'market', 'Số cổ phiếu lưu hành bình quân', 'Weighted average shares outstanding', 'shares'),
    ('shares_outstanding.ending', 'market', 'Số cổ phiếu lưu hành cuối kỳ', 'Shares outstanding at period end', 'shares'),
    ('market_price.close', 'market', 'Giá đóng cửa', 'Close price', 'vnd'),
    ('market_cap.total', 'market', 'Vốn hóa thị trường', 'Market capitalization', 'vnd_bn')
ON CONFLICT (line_item_code) DO UPDATE
SET statement_type = EXCLUDED.statement_type,
    display_name_vi = EXCLUDED.display_name_vi,
    display_name_en = EXCLUDED.display_name_en,
    canonical_unit = EXCLUDED.canonical_unit;

INSERT INTO ref.formulas
    (formula_id, formula_name, formula_group, function_name, formula_text, output_unit, description)
VALUES
    ('F001', 'CAGR', 'growth', 'cagr', '(V_end / V_begin) ** (1 / n) - 1', 'ratio', 'Compound annual growth rate.'),
    ('F002', 'YoY Revenue Growth', 'growth', 'yoy_revenue_growth', '(current_revenue - previous_revenue) / previous_revenue', 'ratio', 'Year-over-year revenue growth.'),
    ('F003', 'YoY Net Income Growth', 'growth', 'yoy_net_income_growth', '(current_net_income - previous_net_income) / previous_net_income', 'ratio', 'Year-over-year net income growth.'),
    ('F004', 'Component Ratio', 'growth', 'component_ratio', 'component_value / total_value', 'ratio', 'Component as percentage of total.'),
    ('F005', 'EPS', 'market_valuation', 'eps', '(net_income_after_tax - preferred_dividends) / weighted_avg_common_shares', 'currency_per_share', 'Earnings per share.'),
    ('F006', 'P/E', 'market_valuation', 'pe_ratio', 'market_price_per_share / eps_value', 'multiple', 'Price to earnings ratio.'),
    ('F007', 'P/B', 'market_valuation', 'pb_ratio', 'market_price_per_share / bvps_value', 'multiple', 'Price to book ratio.'),
    ('F008', 'P/S', 'market_valuation', 'ps_ratio', 'market_price_per_share / sales_per_share_value', 'multiple', 'Price to sales ratio.'),
    ('F009', 'EV/EBITDA', 'market_valuation', 'ev_to_ebitda', 'enterprise_value / ebitda', 'multiple', 'Enterprise value to EBITDA.'),
    ('F010', 'BVPS', 'market_valuation', 'bvps', '(total_equity - intangible_assets) / common_shares_outstanding', 'currency_per_share', 'Book value per share.'),
    ('F011', 'ROA', 'profitability', 'roa', 'net_income_after_tax / average_total_assets', 'ratio', 'Return on assets.'),
    ('F012', 'ROE', 'profitability', 'roe', 'net_income_after_tax / average_total_equity', 'ratio', 'Return on equity.'),
    ('F013', 'ROS', 'profitability', 'ros', 'net_income_after_tax / net_revenue', 'ratio', 'Return on sales.'),
    ('F014', 'Debt to Equity', 'capital_structure', 'debt_to_equity', 'total_debt_or_liabilities / total_equity', 'multiple', 'Debt-to-equity ratio.'),
    ('F015', 'Cash Ratio', 'liquidity', 'cash_ratio', '(cash_and_equivalents + short_term_investments) / current_liabilities', 'multiple', 'Cash ratio.'),
    ('F016', 'DSO', 'operating_cycle', 'days_sales_outstanding', '(average_accounts_receivable / net_revenue) * days', 'days', 'Days sales outstanding.'),
    ('F017', 'DIO', 'operating_cycle', 'days_inventory_outstanding', '(average_inventory / cost_of_goods_sold) * days', 'days', 'Days inventory outstanding.'),
    ('F018', 'Quick Ratio', 'liquidity', 'quick_ratio', '(current_assets - inventory) / current_liabilities', 'multiple', 'Quick ratio.'),
    ('F019', 'DPO', 'operating_cycle', 'days_payable_outstanding', '(average_accounts_payable / cost_of_goods_sold) * days', 'days', 'Days payable outstanding.'),
    ('F020', 'Gross Profit Margin', 'profitability', 'gross_profit_margin', '(net_revenue - cost_of_goods_sold) / net_revenue', 'ratio', 'Gross profit margin.'),
    ('F021', 'Net Profit Margin', 'profitability', 'net_profit_margin', 'net_income_after_tax / net_revenue', 'ratio', 'Net profit margin.'),
    ('F022', 'Current Ratio', 'liquidity', 'current_ratio', 'current_assets / current_liabilities', 'multiple', 'Current ratio.'),
    ('F023', 'Fixed Asset Turnover', 'operating_cycle', 'fixed_asset_turnover', 'net_revenue / average_net_fixed_assets', 'turnover', 'Fixed asset turnover.'),
    ('F024', 'FCFF', 'cash_flow', 'fcff', 'EBIT * (1 - tax_rate) + depreciation - CAPEX - change_in_net_working_capital', 'currency', 'Free cash flow to firm.'),
    ('F025', 'EBIT', 'cash_flow', 'ebit', 'profit_before_tax + interest_expense', 'currency', 'Earnings before interest and tax.'),
    ('F026', 'Straight-Line Depreciation', 'cash_flow', 'straight_line_depreciation', '(cost - salvage_value) / useful_life_years', 'currency', 'Straight-line depreciation.'),
    ('F027', 'CAPEX', 'cash_flow', 'capex', 'delta_ppe + depreciation', 'currency', 'Capital expenditure.'),
    ('F028', 'Change in NWC', 'cash_flow', 'change_in_nwc', 'current_nwc - previous_nwc', 'currency', 'Change in net working capital.'),
    ('F029', 'WACC', 'cost_of_capital', 'wacc', '(E/V * Re) + (D/V * Rd * (1 - tax_rate))', 'ratio', 'Weighted average cost of capital.'),
    ('F030', 'CAPM Cost of Equity', 'cost_of_capital', 'capm_cost_of_equity', 'risk_free_rate + beta * (market_return - risk_free_rate)', 'ratio', 'Cost of equity using CAPM.')
ON CONFLICT (formula_id) DO UPDATE
SET formula_name = EXCLUDED.formula_name,
    formula_group = EXCLUDED.formula_group,
    function_name = EXCLUDED.function_name,
    formula_text = EXCLUDED.formula_text,
    output_unit = EXCLUDED.output_unit,
    description = EXCLUDED.description,
    version = EXCLUDED.version,
    is_active = TRUE;
```

Verification:

```bash
python - <<'PY'
from pathlib import Path
sql = Path('scripts/db/migrations/005_seed_reference_data.sql').read_text()
assert "('F001', 'CAGR'" in sql
assert "('F006', 'P/E'" in sql
assert "('F012', 'ROE'" in sql
assert "('F024', 'FCFF'" in sql
assert "('F029', 'WACC'" in sql
assert "('F030', 'CAPM Cost of Equity'" in sql
for item in ['current_assets.ending', 'current_liabilities.ending', 'shares_outstanding.weighted_avg', 'market_price.close', 'market_cap.total']:
    assert item in sql, item
print('005_seed_reference_data.sql OK')
PY
```

---

# Task 7 — Migration 006: Supabase Grants and Default Privileges

File:

```text
scripts/db/migrations/006_grants_and_privileges.sql
```

Security rule:

```text
service_role can operate the backend.
anon/authenticated only get minimal ref schema read access by default.
Do not grant direct public access to fact/research unless the app explicitly needs it.
```

```sql
-- Migration: 006_grants_and_privileges.sql
-- Purpose: Supabase-compatible grants for application/service roles.

DO $$
DECLARE
    r TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA ref, ingest, fact, research TO service_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ref, ingest, fact, research TO service_role';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ref, ingest, fact, research TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ref GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ingest GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA fact GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA research GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ref GRANT USAGE, SELECT ON SEQUENCES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ingest GRANT USAGE, SELECT ON SEQUENCES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA fact GRANT USAGE, SELECT ON SEQUENCES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA research GRANT USAGE, SELECT ON SEQUENCES TO service_role';
    END IF;

    FOREACH r IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('GRANT USAGE ON SCHEMA ref TO %I', r);
            EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA ref TO %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA ref GRANT SELECT ON TABLES TO %I', r);
        END IF;
    END LOOP;
END $$;
```

Verification:

```bash
python - <<'PY'
from pathlib import Path
sql = Path('scripts/db/migrations/006_grants_and_privileges.sql').read_text()
for item in ['service_role', 'GRANT USAGE ON SCHEMA', 'ALTER DEFAULT PRIVILEGES']:
    assert item in sql, item
print('006_grants_and_privileges.sql OK')
PY
```

---

# Task 8 — Update `scripts/db/migrate.py`

Required changes:

```text
1. CURRENT_SCHEMA_VERSION = "006_grants_and_privileges".
2. Bootstrap public.schema_migrations before reading it.
3. Migration runner owns transaction boundaries.
4. Strip BEGIN/COMMIT robustly in case any migration accidentally contains them.
```

Patch `_apply_migration`:

```python
import re

sql = path.read_text(encoding="utf-8")
sql = re.sub(r"(?im)^\s*BEGIN\s*;\s*$", "", sql)
sql = re.sub(r"(?im)^\s*COMMIT\s*;\s*$", "", sql)
```

Set:

```python
CURRENT_SCHEMA_VERSION = "006_grants_and_privileges"
```

Verification:

```bash
python -m pytest tests/unit/test_migrate_runner.py -v
```

---

# Task 9 — Update `scripts/db/source_registry.py`

Required `SourceInput`:

```python
@dataclass(frozen=True)
class SourceInput:
    logical_id: str
    ticker: str | None
    source_uri: str
    source_type: str
    checksum: str
    connector_version: str
    raw_path: str | None = None
    published_at: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    source_title: str | None = None
    metadata_json: dict[str, Any] | None = None
```

Source ID:

```python
source_id = sha256(f"{logical_id}|{source_uri}|{checksum}")
```

Target table:

```text
ingest.sources
```

Add raw payload registration:

```python
def register_raw_payload(
    self,
    source_id: str,
    content_type: str,
    payload_json: dict | None = None,
    payload_text: str | None = None,
    storage_path: str | None = None,
    checksum: str | None = None,
) -> int:
    ...
```

Keep temporary backward compatibility:

```python
SourceVersionInput = SourceInput
register_version = register_source
```

---

# Task 10 — Update `scripts/db/fact_store.py`

## Dataclass changes

`FinancialFact`:

```text
ticker
fiscal_year
fiscal_period
line_item_code
value
unit
currency
source_id
connector_version
validation_status
confidence
effective_date
ingested_at
```

`PriceRow`:

```text
ticker
trade_date
open
high
low
close
adjusted_close
volume
traded_value
market_cap
source_id
ingested_at
```

Do not keep ambiguous `value` for price rows except as a temporary compatibility alias inside connector transformation code.

## SQL target map

| Method | Target |
|---|---|
| `upsert_financial_facts` | `fact.financial_facts` |
| `get_accepted_financial_facts` | `fact.accepted_financial_facts` |
| `upsert_price_rows` | `fact.price_history` |
| `upsert_catalyst_events` | `fact.catalyst_events` |
| `upsert_company_snapshot` | `ref.companies` + `ingest.company_snapshots` |

---

# Task 11 — Update `backend/runtime_store.py`

Required:

```python
REQUIRED_SCHEMA_VERSION = "006_grants_and_privileges"
```

Use:

```text
research.runs
research.run_steps
research.run_artifacts
research.run_approvals
research.run_budget_ledger
research.run_audit_events
```

`create_run()` must support:

```text
idempotency_key
request_json
config_snapshot_json
flags_json
```

`add_step()` / `close_step()` must support:

```text
retry_count
input_hash
output_hash
error_message
```

`save_artifact()` must support:

```text
version
storage_path
checksum
is_locked
```

`add_approval()` must be prepared for the final approval trigger to raise an exception if quantitative claim evidence is missing or invalid.

---

# Task 12 — Update Normalizer, Build Scripts, and Connectors

## `backend/facts/normalizer.py`

Replace:

```text
taxonomy_key
```

with:

```text
line_item_code
```

## `scripts/build_facts.py`

Replace dict keys:

```text
taxonomy_key -> line_item_code
source_version_id -> source_id
parser_version -> connector_version
```

If old CSV uses `canonical_key`, map it to `line_item_code` in Python:

```python
"line_item_code": row["canonical_key"].strip()
```

The CSV column does not need to be renamed immediately.

## Finance connector

Replace constructor fields:

```text
company_ticker -> ticker
taxonomy_key -> line_item_code
source_version_id -> source_id
parser_version -> connector_version
```

Replace:

```text
SourceVersionInput(source_id=...)
```

with:

```text
SourceInput(logical_id=..., ticker=..., ...)
```

## Price connector

Replace:

```text
PriceRow(date=..., value=...)
```

with:

```text
PriceRow(trade_date=..., traded_value=..., adjusted_close=..., market_cap=...)
```

## Company connector

Replace:

```text
upsert_company_profile
```

with:

```text
upsert_company_snapshot
```

---

# Task 13 — Rewrite Integration Tests

File:

```text
tests/integration/test_db_integrity.py
```

Required tests:

```text
1. schema_migrations exists.
2. migrations 001-006 are applied.
3. schemas ref, ingest, fact, research exist.
4. ref.companies contains DHG, IMP, DMC, TRA, DBD.
5. ref.line_items contains MVP valuation line items.
6. ref.formulas contains F001-F030 with canonical names.
7. ingest.sources has no global UNIQUE(checksum).
8. ingest.sources allows same checksum for different logical_id/source_uri.
9. ingest.document_chunks exists and references ingest.sources.
10. fact.financial_facts rejects unknown line_item_code.
11. fact.financial_facts rejects duplicate accepted current fact.
12. fact.accepted_financial_facts excludes non-FY, non-current, raw/rejected rows.
13. research.metric_values rejects unknown formula_id.
14. research.valuation_results rejects NULL assumption_set_id.
15. research.quantitative_claims_without_evidence returns missing quantitative claims.
16. final_report approval is blocked when quantitative claims lack evidence.
17. research.invalid_claim_evidence detects invalid polymorphic evidence.
18. run_cost_usd sums research.run_budget_ledger correctly.
19. run_artifacts supports version/checksum/storage_path/is_locked.
20. Supabase grants migration exists and includes service_role/default privileges.
```

Formula test must include:

```python
expected = {
    "F001": "CAGR",
    "F006": "P/E",
    "F012": "ROE",
    "F024": "FCFF",
    "F029": "WACC",
    "F030": "CAPM Cost of Equity",
}
```

---

# Task 14 — Supabase Reset and Migration Execution

## Precondition

Current database is dirty and disposable. No data backup is required.

## Reset SQL

Run manually in Supabase SQL editor only when ready:

```sql
DROP SCHEMA IF EXISTS research CASCADE;
DROP SCHEMA IF EXISTS fact CASCADE;
DROP SCHEMA IF EXISTS ingest CASCADE;
DROP SCHEMA IF EXISTS ref CASCADE;

DROP VIEW IF EXISTS public.accepted_financial_facts CASCADE;

DROP TABLE IF EXISTS public.run_audit_events CASCADE;
DROP TABLE IF EXISTS public.run_budget_ledger CASCADE;
DROP TABLE IF EXISTS public.run_approvals CASCADE;
DROP TABLE IF EXISTS public.run_artifacts CASCADE;
DROP TABLE IF EXISTS public.run_steps CASCADE;
DROP TABLE IF EXISTS public.research_runs CASCADE;
DROP TABLE IF EXISTS public.forecast_inputs CASCADE;
DROP TABLE IF EXISTS public.peer_metrics_snapshot CASCADE;
DROP TABLE IF EXISTS public.catalyst_events CASCADE;
DROP TABLE IF EXISTS public.price_history CASCADE;
DROP TABLE IF EXISTS public.financial_facts CASCADE;
DROP TABLE IF EXISTS public.company_profiles CASCADE;
DROP TABLE IF EXISTS public.source_versions CASCADE;
DROP TABLE IF EXISTS public.ingestion_runs CASCADE;
DROP TABLE IF EXISTS public.connector_runs CASCADE;
```

Do not drop `public` schema itself unless the Supabase project is fully disposable and you understand the consequences.

## Run migrations

```bash
python scripts/db/migrate.py
```

Expected:

```text
Applying: 001_ref_schema ... done
Applying: 002_ingest_schema ... done
Applying: 003_fact_schema ... done
Applying: 004_research_schema ... done
Applying: 005_seed_reference_data ... done
Applying: 006_grants_and_privileges ... done
```

## Run tests

```bash
pytest tests/integration/test_db_integrity.py -v
python -m pytest tests/unit/ -v
```

---

# Task 15 — Re-ingest DHG Cleanly

After schema tests pass:

```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
python scripts/build_facts.py --ticker DHG
```

Expected:

```text
- ingest.sources rows created
- ingest.raw_payloads rows created or raw_path populated
- fact.financial_facts accepted rows created
- fact.accepted_financial_facts returns no duplicates
- research.metric_values can be generated from accepted facts
```

Do not expand to TRA/IMP/DMC/DBD until DHG passes:

```text
source -> raw payload -> accepted facts -> deterministic metrics -> valuation -> claim evidence
```

---

# Final Acceptance Criteria

The rebuild is accepted only when all conditions pass:

```text
1. Old public-schema project tables no longer drive the application.
2. New schemas exist: ref, ingest, fact, research.
3. public.schema_migrations includes 001-006.
4. ref.formulas contains canonical F001-F030 from FORMULA_FINANCE.md.
5. No global UNIQUE(checksum) exists on ingest.sources.
6. ingest.raw_payloads exists.
7. ingest.document_chunks exists under ingest, not research.
8. fact.financial_facts requires source_id and line_item_code FK.
9. fact.financial_facts prevents duplicate accepted current facts.
10. fact.accepted_financial_facts returns only accepted + FY + current facts.
11. fact.price_history uses trade_date, traded_value, adjusted_close, market_cap.
12. fact.catalyst_events has controlled event_type values.
13. research.runs supports idempotency_key, request_json, config_snapshot_json.
14. research.run_steps supports retry_count, error_message, input_hash, output_hash.
15. research.metric_values requires canonical formula_id.
16. research.valuation_results requires assumption_set_id.
17. research.run_artifacts supports version, storage_path, checksum, is_locked.
18. research.quantitative_claims_without_evidence view exists.
19. final_report approval is blocked if quantitative claims lack evidence.
20. research.invalid_claim_evidence view exists.
21. Supabase grants/default privileges are included.
22. Integration tests cover all critical constraints.
23. DHG clean ingest works end-to-end.
24. No table duplicates another table's purpose.
```

---

# Self-Review Checklist for Implementation Agent

Before committing the patched rebuild, confirm:

```text
[ ] No migration file contains BEGIN/COMMIT.
[ ] migrate.py strips BEGIN/COMMIT robustly anyway.
[ ] CURRENT_SCHEMA_VERSION = "006_grants_and_privileges".
[ ] ref.formulas seed has F001-F030 exactly.
[ ] Formula ID mapping does not redefine FORMULA_FINANCE.md.
[ ] ingest.sources does not have UNIQUE(checksum).
[ ] ingest.raw_payloads exists.
[ ] ingest.document_chunks exists.
[ ] research.document_chunks does not exist.
[ ] valuation_results.assumption_set_id is NOT NULL.
[ ] run_artifacts has version/checksum/storage_path/is_locked.
[ ] final_report approval guard exists.
[ ] quantitative_claims_without_evidence view exists.
[ ] invalid_claim_evidence view exists.
[ ] integration tests reject duplicate accepted facts.
[ ] integration tests reject unknown formula_id.
[ ] integration tests reject NULL assumption_set_id.
[ ] integration tests verify F001/F006/F012/F024/F029/F030 names.
```

---

# Future Migrations, Not MVP

Do not implement these now unless the MVP passes DHG end-to-end:

```text
007_peer_group_taxonomy.sql
008_data_quality_reconciliation.sql
009_report_export_tables.sql
010_pgvector_embedding_extension.sql
```

Do not add pgvector until document retrieval has a clear evaluation baseline using full-text + metadata filters.
