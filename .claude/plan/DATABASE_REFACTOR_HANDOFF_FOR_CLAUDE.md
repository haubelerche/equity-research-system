# Database Refactor Handoff for Claude

## 0. Mục tiêu tài liệu

Tài liệu này tóm gọn kết quả audit database PostgreSQL/Supabase hiện tại của dự án **Vietnam Pharma Equity Research Agent** và chuyển thành kế hoạch triển khai rõ ràng cho Claude Code/Codex/Cursor.

Mục tiêu không phải là xây data warehouse lớn hoặc overengineering. Mục tiêu là harden database hiện tại để phục vụ đúng bài toán:

```text
canonical facts -> deterministic metrics -> valuation artifacts -> grounded report claims -> citation audit -> human approval
```

Database phải chứng minh được:

1. Số liệu tài chính đến từ nguồn nào.
2. Số liệu nào là fact gốc, số liệu nào là metric tính toán.
3. Valuation dùng assumption nào và formula nào.
4. Report claim nào dựa vào fact/metric/source nào.
5. Research run nào đã chạy step nào, sinh artifact nào, tốn cost bao nhiêu và được approve bởi ai.

---

## 1. Context dự án

Dự án là hệ thống AI Agent hỗ trợ phân tích và định giá cổ phiếu ngành dược/y tế Việt Nam.

Nguyên tắc kiến trúc đã chốt:

- PostgreSQL/Supabase là primary operational database.
- Không để LLM tự tạo hoặc tự tính số liệu tài chính cuối cùng.
- Financial ratios, valuation, DCF, multiples, sensitivity phải tính bằng Python deterministic code.
- Mỗi số liệu trong report phải trace được về fact, metric, valuation result hoặc document evidence.
- Report phải có claim ledger, source manifest, valuation result, eval result và audit trail.
- Không cần Neo4j, ClickHouse, warehouse phức tạp hoặc table theo từng ticker trong MVP.

Target database nên phục vụ 4 lớp logic:

```text
ref       -- reference/config/taxonomy/formula metadata
ingest    -- source, raw payload, parser/connector run, validation issue, document chunk
fact      -- canonical accepted financial facts, market prices, events
research  -- research runs, deterministic metrics, valuation, report claims, evidence, eval, approval, cost
```

Hiện tại các table đang chủ yếu nằm trong `public`. Refactor không nhất thiết phải move toàn bộ table ngay, nhưng các migration mới nên đi theo ranh giới logic trên hoặc ít nhất không làm public-schema monolith nặng thêm.

---

## 2. Hiện trạng database đã kiểm tra

Các migration hiện có:

```text
001_initial_schema.sql
002_backend_runtime.sql
003_lineage_enhancements.sql
004_schema_versioning.sql
005_fk_constraints.sql
006_accepted_facts_view.sql
```

### 2.1. Các table chính đang có

Từ `001_initial_schema.sql`:

```text
financial_facts
price_history
catalyst_events
source_versions
company_profiles
peer_metrics_snapshot
ingestion_runs
connector_runs
forecast_inputs
```

Từ `002_backend_runtime.sql`:

```text
research_runs
run_steps
run_artifacts
run_approvals
run_budget_ledger
run_audit_events
```

Từ `003_lineage_enhancements.sql`:

```text
source_versions.embedding_version
source_versions.run_id
financial_facts.run_id
catalyst_events.run_id
```

Từ `004_schema_versioning.sql`:

```text
schema_migrations
```

Từ `005_fk_constraints.sql`:

Đã thêm FK từ nhiều bảng về `ref.companies(ticker)`, `source_versions(id)`, và `research_runs(run_id)`.

Từ `006_accepted_facts_view.sql`:

```text
accepted_financial_facts
```

View này lọc:

```sql
validation_status = 'accepted'
AND fiscal_period = 'FY'
```

---

## 3. Đánh giá tổng quan

Database hiện tại **không nên bỏ đi**. Nó đã có foundation tốt cho ingestion, lineage và runtime audit. Tuy nhiên hiện tại database mới đạt mức "MVP ingestion foundation", chưa đủ mạnh cho valuation-safe reporting.

### 3.1. Điểm mạnh

| Hạng mục | Đánh giá |
|---|---|
| `financial_facts` long-format | Đúng hướng, phù hợp dữ liệu BCTC Việt Nam |
| `source_versions` | Có nền tảng lineage tốt |
| `research_runs`, `run_steps` | Phù hợp stateful workflow |
| `run_budget_ledger`, `run_audit_events` | Tốt cho cost governance và observability |
| `accepted_financial_facts` view | Đúng hướng vì valuation không nên đọc trực tiếp base table |

### 3.2. Vấn đề chính

| Vấn đề | Mức độ | Tác động |
|---|---:|---|
| Hầu hết table nằm trong `public` | Medium | Lẫn boundary giữa source, fact, research runtime |
| `005_fk_constraints.sql` phụ thuộc `ref.companies` nhưng chưa thấy migration tạo `ref.companies` trong 6 file | High | Migration có thể fail hoặc database bị phụ thuộc vào table tạo tay |
| `accepted_financial_facts` có nguy cơ trả nhiều accepted facts cho cùng một ticker/year/taxonomy_key từ nhiều source | High | Valuation có thể đọc duplicate facts |
| `validation_status`, `status`, `run_type`, `event_type`, `materiality_hint` là string tự do | High | Data quality gate dễ bị phá bởi typo |
| `confidence` chưa có range constraint `[0, 1]` | Medium | Dữ liệu quality/confidence không đáng tin |
| Chưa có `ref.line_items` | High | `taxonomy_key` là string tự do, dễ lệch taxonomy |
| Chưa có `ref.formulas` | Medium | Không trace được formula metadata ở DB layer |
| Chưa có table normalized cho deterministic metrics | High | ROE/ROA/P/E/WACC/FCFF dễ bị nhồi vào artifact JSON |
| Chưa có normalized valuation tables | High | DCF/multiples/sensitivity khó audit |
| Chưa có `report_claims` và `claim_evidence` | Critical | Không chứng minh được claim-level citation và anti-hallucination |
| Chưa có `document_chunks` | Medium | Chưa cite tốt annual report/news/disclosure |
| `schema_migrations` chưa ghi version 005/006 | Medium | Version tracking chưa hoàn chỉnh |

### 3.3. Đánh giá theo năng lực

```text
MVP ingestion foundation:       65-70%
Valuation-safe fact layer:      50-55%
Research workflow runtime:      70%
Citation/report audit layer:    30-40%
Production data integrity:      50%
```

Kết luận:

```text
Schema hiện tại đủ để tiếp tục build, nhưng phải làm một migration hardening phase trước khi implement valuation/report agent.
```

---

## 4. Nguyên tắc thiết kế cần giữ

### 4.1. Tách fact gốc và dữ liệu tính toán

Không lưu derived metric vào `financial_facts`.

Đúng:

```text
financial_facts            = canonical accepted source-derived facts
research_metric_values     = deterministic metrics computed from facts
valuation_results          = valuation output from code-first engine
report_claims              = claims in report
claim_evidence             = evidence mapping for each claim
```

Sai:

```text
financial_facts(taxonomy_key='roe')
financial_facts(taxonomy_key='pe_ratio')
financial_facts(taxonomy_key='dcf_target_price')
```

### 4.2. Không table theo ticker hoặc source

Sai:

```text
DHG_financials
TRA_financials
vnstock_income_statement
manual_income_statement
```

Đúng:

```text
financial_facts(company_ticker, fiscal_year, fiscal_period, taxonomy_key, value, source_version_id)
source_versions(source_id, source_uri, source_type, checksum, connector_version)
```

### 4.3. Source manifest và claim ledger là export artifact, không phải source of truth

Source of truth:

```text
source_versions
report_claims
claim_evidence
```

Export artifact:

```text
source_manifest.json
claim_ledger.json
```

### 4.4. `run_artifacts` không được gánh toàn bộ audit logic

`run_artifacts.payload_json` chỉ dùng cho artifact tổng hợp hoặc export file.

Không dùng `run_artifacts` làm nơi duy nhất lưu:

```text
metrics
valuation result
claim ledger
claim evidence
evaluation details
```

Vì các dữ liệu này cần query/audit bằng SQL.

---

## 5. Target design tối thiểu

Không bắt buộc move tất cả table sang schema mới ngay. Nhưng target logical design nên là:

```text
ref.companies                 -- source of truth cho ticker/company identity
ref.line_items                -- canonical financial taxonomy
ref.formulas                  -- formula metadata F001-F030

public/source_versions        -- existing source registry, keep/harden
public/financial_facts        -- existing canonical fact table, keep/harden
public/price_history          -- existing market price table, keep/harden
public/catalyst_events        -- existing event/catalyst table, keep/harden

public/research_runs          -- existing workflow run table, keep/harden
public/run_steps              -- existing workflow step table, keep/harden
public/run_artifacts          -- existing artifact table, keep but narrow purpose
public/run_approvals          -- existing approval table, keep/harden
public/run_budget_ledger      -- existing cost table, keep
public/run_audit_events       -- existing audit table, keep

public/research_metric_values -- new deterministic metrics table
public/valuation_assumption_sets -- new valuation assumptions table
public/valuation_results      -- new valuation result table
public/report_claims          -- new normalized claim ledger table
public/claim_evidence         -- new claim-to-evidence table
public/document_chunks        -- new document citation/retrieval table
public/evaluation_results     -- new normalized eval table
```

---

## 6. Required migration plan

Create a new migration, recommended name:

```text
007_database_hardening_for_valuation_audit.sql
```

This migration should be idempotent.

### 6.1. Step 1 — Ensure `ref` schema and reference tables

Create `ref` schema if missing.

Required tables:

```text
ref.companies
ref.line_items
ref.formulas
```

#### `ref.companies`

Use `ticker` as primary key to match existing FK strategy in `005_fk_constraints.sql`.

```sql
CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE IF NOT EXISTS ref.companies (
    ticker VARCHAR(10) PRIMARY KEY,
    exchange VARCHAR(10),
    company_name_vi TEXT NOT NULL,
    company_name_en TEXT,
    sector TEXT,
    subsector TEXT,
    currency CHAR(3) NOT NULL DEFAULT 'VND',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

If `company_profiles` already has data, seed `ref.companies` from it:

```sql
INSERT INTO ref.companies (ticker, exchange, company_name_vi, sector)
SELECT ticker, exchange, COALESCE(company_name, ticker), segment
FROM public.company_profiles
ON CONFLICT (ticker) DO NOTHING;
```

#### `ref.line_items`

```sql
CREATE TABLE IF NOT EXISTS ref.line_items (
    line_item_code VARCHAR(60) PRIMARY KEY,
    statement_type VARCHAR(40) NOT NULL CHECK (
        statement_type IN ('income_statement', 'balance_sheet', 'cash_flow', 'market', 'other')
    ),
    display_name_vi TEXT NOT NULL,
    display_name_en TEXT,
    canonical_unit VARCHAR(30) NOT NULL,
    sign_convention TEXT,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

Seed at least the core line items needed by valuation:

```text
revenue
cogs
gross_profit
ebit
profit_before_tax
interest_expense
net_income
total_assets
total_equity
cash_and_equivalents
short_term_investments
current_assets
current_liabilities
inventory
accounts_receivable
accounts_payable
total_debt
interest_bearing_debt
short_term_interest_bearing_debt
net_ppe
intangible_assets
cfo
capex
depreciation
shares_outstanding
weighted_avg_common_shares
market_price
market_cap
```

#### `ref.formulas`

```sql
CREATE TABLE IF NOT EXISTS ref.formulas (
    formula_id VARCHAR(20) PRIMARY KEY,
    formula_name TEXT NOT NULL,
    formula_group TEXT NOT NULL,
    function_name TEXT NOT NULL,
    output_unit VARCHAR(40) NOT NULL,
    formula_text TEXT NOT NULL,
    version VARCHAR(20) NOT NULL DEFAULT 'v1',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

Seed formula metadata from `FORMULA_FINANCE.md`, at least F001-F030.

---

### 6.2. Step 2 — Harden existing fact/source/runtime tables

#### Add missing constraints for `financial_facts`

Add `is_current`:

```sql
ALTER TABLE public.financial_facts
ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT TRUE;
```

Add confidence range constraint:

```sql
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'financial_facts'
          AND constraint_name = 'chk_financial_facts_confidence_range'
    ) THEN
        ALTER TABLE public.financial_facts
        ADD CONSTRAINT chk_financial_facts_confidence_range
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
    END IF;
END $$;
```

Add validation status constraint:

```sql
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'financial_facts'
          AND constraint_name = 'chk_financial_facts_validation_status'
    ) THEN
        ALTER TABLE public.financial_facts
        ADD CONSTRAINT chk_financial_facts_validation_status
        CHECK (validation_status IN ('raw', 'validated', 'accepted', 'rejected', 'needs_review'));
    END IF;
END $$;
```

Add FK `taxonomy_key -> ref.line_items(line_item_code)` only after seeding required line items:

```sql
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'financial_facts'
          AND constraint_name = 'financial_facts_taxonomy_key_fkey'
    ) THEN
        ALTER TABLE public.financial_facts
        ADD CONSTRAINT financial_facts_taxonomy_key_fkey
        FOREIGN KEY (taxonomy_key) REFERENCES ref.line_items(line_item_code);
    END IF;
END $$;
```

Add partial unique index to prevent duplicate accepted current facts:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_current_accepted_financial_fact
ON public.financial_facts (company_ticker, fiscal_year, fiscal_period, taxonomy_key)
WHERE is_current = TRUE AND validation_status = 'accepted';
```

Important: before creating this index, check whether duplicates already exist. If duplicates exist, migration should not blindly fail without a cleanup plan.

Duplicate check:

```sql
SELECT company_ticker, fiscal_year, fiscal_period, taxonomy_key, COUNT(*)
FROM public.financial_facts
WHERE validation_status = 'accepted'
  AND is_current = TRUE
GROUP BY company_ticker, fiscal_year, fiscal_period, taxonomy_key
HAVING COUNT(*) > 1;
```

#### Update `accepted_financial_facts` view

Replace current view with:

```sql
CREATE OR REPLACE VIEW public.accepted_financial_facts AS
SELECT
    id,
    company_ticker,
    fiscal_year,
    fiscal_period,
    taxonomy_key,
    value,
    unit,
    currency,
    source_version_id,
    parser_version,
    confidence,
    effective_date,
    ingested_at
FROM public.financial_facts
WHERE validation_status = 'accepted'
  AND fiscal_period = 'FY'
  AND is_current = TRUE;
```

#### Harden `source_versions`

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_versions_checksum
ON public.source_versions(checksum);
```

Add optional CHECK for `source_type` if current source types are known. If not known yet, skip strict CHECK to avoid breaking existing data.

#### Harden `research_runs`

Add FK to `ref.companies` if missing:

```sql
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND table_name = 'research_runs'
          AND constraint_name = 'research_runs_ticker_fkey'
    ) THEN
        ALTER TABLE public.research_runs
        ADD CONSTRAINT research_runs_ticker_fkey
        FOREIGN KEY (ticker) REFERENCES ref.companies(ticker);
    END IF;
END $$;
```

Add status/run_type CHECK only if existing rows are compatible.

Recommended allowed statuses:

```text
initialized
running
data_ready
analysis_ready
valuation_ready
needs_human_review
report_ready
failed
cancelled
```

Recommended allowed run types:

```text
full_report
flash_memo
catalyst_refresh
```

---

### 6.3. Step 3 — Add deterministic metric table

Create `research_metric_values`:

```sql
CREATE TABLE IF NOT EXISTS public.research_metric_values (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES public.research_runs(run_id) ON DELETE CASCADE,
    ticker VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    fiscal_year SMALLINT,
    fiscal_period VARCHAR(4),
    formula_id VARCHAR(20) NOT NULL REFERENCES ref.formulas(formula_id),
    metric_key VARCHAR(80) NOT NULL,
    value NUMERIC(28, 8),
    unit VARCHAR(40) NOT NULL,
    input_fact_ids BIGINT[] NOT NULL DEFAULT '{}',
    input_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    formula_version VARCHAR(20) NOT NULL DEFAULT 'v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_metric_values_run
ON public.research_metric_values(run_id, metric_key);

CREATE INDEX IF NOT EXISTS idx_research_metric_values_ticker_period
ON public.research_metric_values(ticker, fiscal_year, fiscal_period);
```

Purpose:

```text
Store ROE, ROA, CAGR, margins, P/E, P/B, EV/EBITDA, FCFF, WACC, etc.
```

Do not put these into `financial_facts`.

---

### 6.4. Step 4 — Add valuation tables

```sql
CREATE TABLE IF NOT EXISTS public.valuation_assumption_sets (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES public.research_runs(run_id) ON DELETE CASCADE,
    method VARCHAR(32) NOT NULL CHECK (method IN ('dcf', 'pe', 'pb', 'ev_ebitda', 'mixed')),
    scenario VARCHAR(20) NOT NULL CHECK (scenario IN ('bear', 'base', 'bull')),
    assumptions_json JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    approved_by VARCHAR(128),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.valuation_results (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES public.research_runs(run_id) ON DELETE CASCADE,
    assumption_set_id BIGINT REFERENCES public.valuation_assumption_sets(id),
    method VARCHAR(32) NOT NULL,
    scenario VARCHAR(20) NOT NULL,
    target_price NUMERIC(18, 4),
    valuation_range_low NUMERIC(18, 4),
    valuation_range_high NUMERIC(18, 4),
    enterprise_value NUMERIC(28, 4),
    equity_value NUMERIC(28, 4),
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_valuation_results_run
ON public.valuation_results(run_id, method, scenario);
```

Purpose:

```text
Store DCF, relative valuation, sensitivity, target price, valuation range, and scenario outputs.
```

---

### 6.5. Step 5 — Add normalized report claim and evidence tables

```sql
CREATE TABLE IF NOT EXISTS public.report_claims (
    claim_id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES public.research_runs(run_id) ON DELETE CASCADE,
    section_key VARCHAR(64),
    claim_text TEXT NOT NULL,
    claim_type VARCHAR(20) NOT NULL CHECK (
        claim_type IN ('quantitative', 'qualitative', 'inference')
    ),
    numbers_used_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    verdict VARCHAR(20) NOT NULL CHECK (
        verdict IN ('pass', 'fail', 'needs_review')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.claim_evidence (
    id BIGSERIAL PRIMARY KEY,
    claim_id BIGINT NOT NULL REFERENCES public.report_claims(claim_id) ON DELETE CASCADE,
    evidence_type VARCHAR(32) NOT NULL CHECK (
        evidence_type IN ('financial_fact', 'metric_value', 'valuation_result', 'source_version', 'document_chunk', 'event')
    ),
    evidence_id TEXT NOT NULL,
    source_version_id VARCHAR(64) REFERENCES public.source_versions(id),
    quote_text TEXT,
    relevance_score NUMERIC(5,4) CHECK (relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_claims_run
ON public.report_claims(run_id, verdict, claim_type);

CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim
ON public.claim_evidence(claim_id);
```

Purpose:

```text
Enable claim-level citation, numeric consistency evaluation, and hallucination audit.
```

Every quantitative claim in report should have at least one evidence row pointing to one of:

```text
financial_fact
metric_value
valuation_result
source_version
document_chunk
event
```

---

### 6.6. Step 6 — Add document chunks table

```sql
CREATE TABLE IF NOT EXISTS public.document_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    source_version_id VARCHAR(64) NOT NULL REFERENCES public.source_versions(id) ON DELETE CASCADE,
    ticker VARCHAR(10) REFERENCES ref.companies(ticker),
    chunk_index INTEGER NOT NULL,
    section_title TEXT,
    chunk_text TEXT NOT NULL,
    fiscal_year SMALLINT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_version_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_ticker
ON public.document_chunks(ticker);

CREATE INDEX IF NOT EXISTS idx_document_chunks_metadata
ON public.document_chunks USING GIN(metadata_json);

CREATE INDEX IF NOT EXISTS idx_document_chunks_fts
ON public.document_chunks
USING GIN(to_tsvector('simple', chunk_text));
```

Do not add pgvector yet unless the retrieval pipeline is already implemented. Full-text + metadata filtering is enough for MVP.

---

### 6.7. Step 7 — Add evaluation results table

```sql
CREATE TABLE IF NOT EXISTS public.evaluation_results (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL REFERENCES public.research_runs(run_id) ON DELETE CASCADE,
    eval_name VARCHAR(80) NOT NULL,
    score NUMERIC(8,4),
    threshold NUMERIC(8,4),
    passed BOOLEAN NOT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_results_run
ON public.evaluation_results(run_id, eval_name, passed);
```

Purpose:

```text
Store citation coverage, numeric consistency, hallucination risk, data quality, calculation eval, and final confidence score.
```

---

### 6.8. Step 8 — Record migration version

At the end of migration:

```sql
INSERT INTO public.schema_migrations (version, description)
VALUES ('007_database_hardening_for_valuation_audit', 'Add ref tables, harden accepted facts, add metric, valuation, claim, evidence, document chunk, and eval tables')
ON CONFLICT (version) DO NOTHING;
```

Also add missing records for migrations 005 and 006 if not already inserted:

```sql
INSERT INTO public.schema_migrations (version, description) VALUES
    ('005_fk_constraints', 'Add foreign key constraints'),
    ('006_accepted_facts_view', 'Create accepted financial facts view')
ON CONFLICT (version) DO NOTHING;
```

---

## 7. Required verification queries

Claude must include or document these verification queries.

### 7.1. Check `ref.companies`

```sql
SELECT COUNT(*) FROM ref.companies;
```

### 7.2. Check duplicate accepted facts before enforcing partial unique index

```sql
SELECT company_ticker, fiscal_year, fiscal_period, taxonomy_key, COUNT(*)
FROM public.financial_facts
WHERE validation_status = 'accepted'
  AND is_current = TRUE
GROUP BY company_ticker, fiscal_year, fiscal_period, taxonomy_key
HAVING COUNT(*) > 1;
```

Expected: zero rows before creating unique index.

### 7.3. Check accepted facts view

```sql
SELECT *
FROM public.accepted_financial_facts
LIMIT 20;
```

### 7.4. Check FK constraints

```sql
SELECT constraint_name, table_name
FROM information_schema.table_constraints
WHERE constraint_schema = 'public'
  AND constraint_type = 'FOREIGN KEY'
ORDER BY table_name, constraint_name;
```

### 7.5. Check new core audit tables exist

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name IN (
    'research_metric_values',
    'valuation_assumption_sets',
    'valuation_results',
    'report_claims',
    'claim_evidence',
    'document_chunks',
    'evaluation_results'
)
ORDER BY table_name;
```

---

## 8. Implementation constraints for Claude

Claude must follow these constraints:

1. Do not drop existing tables.
2. Do not rename existing columns unless explicitly required.
3. Do not move existing data between schemas in this task.
4. Use idempotent SQL: `IF NOT EXISTS`, guarded `DO $$ BEGIN ... END $$`, `ON CONFLICT DO NOTHING`.
5. Before adding strict constraints, consider whether existing rows may violate them.
6. Do not store derived financial metrics in `financial_facts`.
7. Do not use `run_artifacts` as the only place to store valuation/claim/evidence data.
8. Keep `accepted_financial_facts` as the read path for valuation-safe annual facts.
9. Do not add pgvector unless retrieval implementation already needs it.
10. Keep the migration small enough to review, but complete enough to support valuation/report audit.

---

## 9. Acceptance criteria

The task is complete only when all criteria pass:

### 9.1. Database integrity

- `ref.companies` exists and is seeded from current company data or ready for universe seed.
- `ref.line_items` exists with core financial taxonomy.
- `ref.formulas` exists with F001-F030 metadata placeholder or seed data.
- `financial_facts.taxonomy_key` can be constrained to `ref.line_items`.
- `financial_facts.confidence` is constrained to `[0, 1]` when not null.
- `financial_facts.validation_status` has controlled values.
- `accepted_financial_facts` filters `is_current = TRUE`.
- Duplicate current accepted facts are prevented.

### 9.2. Valuation readiness

- `research_metric_values` exists and can store deterministic formula outputs.
- `valuation_assumption_sets` exists and can store bear/base/bull assumptions.
- `valuation_results` exists and can store DCF/multiples result, target price and valuation range.

### 9.3. Report audit readiness

- `report_claims` exists.
- `claim_evidence` exists.
- Quantitative claims can reference facts, metrics or valuation results.
- Qualitative claims can reference source versions, document chunks or events.

### 9.4. Retrieval/citation readiness

- `document_chunks` exists.
- It has FK to `source_versions`.
- It has ticker, chunk index, text and metadata.
- It has full-text index.

### 9.5. Evaluation readiness

- `evaluation_results` exists.
- It can store eval name, score, threshold, pass/fail and details.

### 9.6. Migration tracking

- `schema_migrations` records 005, 006 and the new migration 007.

---

## 10. Suggested task prompt for Claude Code

Copy/paste this prompt to Claude Code:

```text
You are working on the PostgreSQL/Supabase database for the Vietnam Pharma Equity Research Agent.

Read the existing migrations first:
- 001_initial_schema.sql
- 002_backend_runtime.sql
- 003_lineage_enhancements.sql
- 004_schema_versioning.sql
- 005_fk_constraints.sql
- 006_accepted_facts_view.sql

Then implement a new idempotent migration:
- 007_database_hardening_for_valuation_audit.sql

Objective:
Harden the current database so it can safely support:
canonical facts -> deterministic metrics -> valuation artifacts -> grounded report claims -> citation audit -> human approval.

Do not rebuild the database. Do not drop existing tables. Do not move existing data across schemas. Add only the minimum required tables, constraints, indexes, and view updates.

Required changes:
1. Ensure `ref` schema exists.
2. Create `ref.companies` if missing, compatible with existing FK references to `ref.companies(ticker)`.
3. Create `ref.line_items` for canonical financial taxonomy.
4. Create `ref.formulas` for formula metadata F001-F030.
5. Add `financial_facts.is_current BOOLEAN NOT NULL DEFAULT TRUE`.
6. Add safe constraints for confidence range and validation_status.
7. Add FK from `financial_facts.taxonomy_key` to `ref.line_items(line_item_code)` after seeding required line items.
8. Prevent duplicate accepted current facts using a partial unique index, but include duplicate-check logic/comment so migration does not silently hide existing data issues.
9. Update `accepted_financial_facts` view to require `is_current = TRUE`.
10. Add `research_metric_values` table for deterministic formula outputs.
11. Add `valuation_assumption_sets` and `valuation_results` tables.
12. Add `report_claims` and `claim_evidence` tables.
13. Add `document_chunks` table with full-text index.
14. Add `evaluation_results` table.
15. Record migrations 005, 006 and 007 in `schema_migrations`.

Hard constraints:
- Use idempotent SQL.
- Do not store ROE/ROA/P/E/WACC/DCF target price in `financial_facts`.
- Do not make `run_artifacts` the only storage for metrics, valuation, claims or evidence.
- Do not add pgvector in this task unless already configured.
- Use CHECK constraints for controlled statuses where safe.
- Preserve compatibility with current public tables.

Acceptance criteria:
- The migration can be run repeatedly without failing.
- All new tables exist.
- `accepted_financial_facts` exposes only accepted, FY, current facts.
- There is a normalized path from report claim -> evidence -> source/fact/metric/valuation.
- Valuation outputs and assumptions are queryable without parsing run_artifacts JSON.
- schema_migrations includes 005, 006 and 007.

After implementation, provide:
1. The new SQL migration file.
2. A short explanation of each table/constraint added.
3. Verification SQL queries.
4. Any manual cleanup required if duplicate accepted facts already exist.
```

---

## 11. What not to do

Do not implement these in this task:

```text
Neo4j schema
ClickHouse/TimescaleDB
large data warehouse star schema
separate table for every ticker
separate table for every source
pgvector migration unless retrieval is ready
full RLS policy design
frontend API changes
valuation Python code
agent prompt logic
```

This task is database hardening only.

---

## 12. Final target after this migration

After the hardening migration, the database should support this clean flow:

```text
1. Ingest source
   -> source_versions
   -> raw/document chunks if applicable

2. Validate and accept facts
   -> financial_facts(validation_status='accepted', is_current=true)
   -> accepted_financial_facts view

3. Run deterministic analytics
   -> research_metric_values

4. Run valuation
   -> valuation_assumption_sets
   -> valuation_results

5. Generate report
   -> run_artifacts for report files/export payloads
   -> report_claims for normalized claim ledger
   -> claim_evidence for citation evidence

6. Evaluate and approve
   -> evaluation_results
   -> run_approvals
   -> run_audit_events
   -> run_budget_ledger
```

This is the minimum database foundation needed for a credible equity research agent that can produce auditable financial reports without overengineering.
