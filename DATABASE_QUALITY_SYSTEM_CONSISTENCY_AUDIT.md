# DATABASE QUALITY & SYSTEM CONSISTENCY AUDIT

**Project:** Vietnam Pharma Equity Research Multi-Agent System  
**Target domain:** Vietnamese pharmaceutical equity research, financial data ingestion, valuation, citation-backed report generation  
**Database context:** Supabase PostgreSQL / PostgreSQL-based warehouse  
**Audit focus:** Database quality, schema consistency, lineage, source trust, reconciliation, reproducibility, and report-readiness  
**Document purpose:** Provide a structured database audit that can be used by Claude Code, a backend engineer, or a data engineer to inspect, refactor, and harden the current database layer.

---

## 0. Executive Summary

The current database layer should be treated as **not yet production-grade** and **not yet academic-grade** for financial research automation. The main issue is not merely table design, but the lack of a strongly enforced data contract across the full pipeline:

```text
Public source / API / PDF
  -> raw acquisition
  -> parsed financial rows
  -> canonical financial facts
  -> reconciliation against trusted sources
  -> valuation inputs
  -> report claims
  -> citations
  -> final PDF
```

The database must answer five questions for every quantitative claim in the final report:

```text
1. What is the original source?
2. Which parser or connector produced the value?
3. Which canonical metric does the value represent?
4. Which reconciliation or verification step accepted it?
5. Which report claim, table, chart, or valuation output used it?
```

At the current maturity level, the system appears to have several structural weaknesses:

1. **Weak relational integrity**: foreign keys and hard constraints are insufficient or absent.
2. **Unstable schema governance**: runtime schema creation or patching is being used instead of a controlled migration strategy.
3. **Mixed data trust levels**: API-derived facts, official-document-derived facts, parsed facts, and unverified facts are not cleanly separated enough.
4. **Unclear provenance**: some citations point to vague data sources such as `vnstock` or database identifiers rather than auditable source documents.
5. **Period inconsistency risk**: FY and quarterly data may be mixed unless strongly constrained.
6. **Metric identity risk**: canonical financial metrics need one authoritative dictionary and strict validation.
7. **Report leakage risk**: internal audit concepts such as tiers, database IDs, or backend terminology may leak into user-facing reports.
8. **Limited reproducibility**: report outputs may not be fully reproducible from code version, config version, data snapshot, prompt version, and source version.

The database should therefore be rebuilt or hardened around a **source-traceable canonical fact model** with deterministic constraints, reconciliation tables, audit artifacts, and report-level traceability.

---

## 1. Audit Scope

This audit covers the database layer only. It does not evaluate UI code, PDF rendering quality, model prompt quality, or frontend design except where those layers depend directly on database correctness.

### 1.1. In Scope

- Database schema structure
- Table responsibility boundaries
- Foreign key integrity
- Unique constraints
- Enum consistency
- Canonical financial metric schema
- Source metadata
- Financial fact provenance
- Official document tracking
- Reconciliation between API and official documents
- Citation map design
- Report claim traceability
- Data quality gates
- Migration strategy
- Idempotent ingestion
- Audit logs and reproducibility
- Data warehouse readiness for valuation and financial reporting

### 1.2. Out of Scope

- Detailed visual PDF layout
- LLM prompt style
- Final Vietnamese narrative prose
- Model selection
- Frontend UX
- Cloud deployment topology
- Full security audit beyond database-adjacent concerns

---

## 2. Current Database Quality Assessment

### 2.1. Overall Rating

| Dimension | Current Risk | Assessment |
|---|---:|---|
| Schema consistency | High | Multiple concepts may exist without hard relational enforcement. |
| Financial fact integrity | High | Canonical metric, period, source, and unit validation need stronger constraints. |
| Source provenance | High | Source-level metadata exists conceptually, but report citations are still too vague unless claim-level source traceability is enforced. |
| Reconciliation logic | Medium-High | Official document reconciliation is necessary but must become a first-class database concept. |
| Migration maturity | High | Runtime schema initialization is not sufficient for production data governance. |
| Idempotency | Medium-High | Repeated ingestion must be provably non-duplicative. |
| Report traceability | High | Every report claim should be traceable to fact IDs, formulas, and source references. |
| Audit readiness | Medium-High | Audit artifacts exist or are planned, but the database must enforce stronger lineage. |
| Scalability to multiple tickers | Medium | The architecture can scale only if ticker, period, source, and metric contracts are normalized. |
| Academic defensibility | High risk | Weak provenance and vague citation reduce defensibility in a graduation thesis or research system. |

### 2.2. Practical Conclusion

The database should not be considered only a persistence layer. In this project, the database is the **trust backbone** of the entire equity research system.

A weak database will cause downstream failures even if the agent workflow and report renderer are improved:

```text
Bad source tracking -> weak citation
Weak canonical facts -> wrong valuation
Missing constraints -> duplicate or mixed-period data
No reconciliation -> unverifiable financial claims
No reproducible snapshot -> non-defensible report output
```

Therefore, the database should be redesigned around:

```text
Source Inventory
  -> Raw Source Versions
  -> Extracted Facts
  -> Canonical Facts
  -> Reconciled Facts
  -> Valuation Inputs
  -> Report Claims
  -> Citation Map
  -> Quality Gate Results
```

---

## 3. Key Database Quality Criteria

A good database for this project must satisfy the following criteria.

### 3.1. Relational Integrity

Every important relationship must be enforced by foreign keys, not just by naming conventions.

Examples:

```text
financial_facts.source_version_id -> source_versions.id
price_history.source_version_id   -> source_versions.id
catalyst_events.source_version_id -> source_versions.id
report_claims.report_id           -> reports.id
claim_fact_links.fact_id          -> financial_facts.id
claim_fact_links.claim_id         -> report_claims.id
fact_reconciliation.fact_id       -> financial_facts.id
```

A database that stores foreign key-like strings without actual constraints is vulnerable to orphaned rows, broken citations, and non-reproducible report generation.

### 3.2. Canonical Metric Governance

Every financial metric must have one canonical identifier.

Examples:

```text
revenue.net
cogs.total
gross_profit.total
sga.total
ebit.total
ebitda.total
finance_cost.total
profit_before_tax.total
tax_expense.total
net_income.parent
total_assets.total
total_equity.total
total_debt.total
operating_cash_flow.total
capex.total
free_cash_flow.total
```

The database must reject free-form metric names such as:

```text
revenue
sales
doanh_thu
doanh thu thuần
net sales
RevenueNet
```

These labels may appear in parser mapping tables, but not as canonical metric IDs inside core financial facts.

### 3.3. Period Consistency

For the current project requirement, financial statement facts should be FY-only unless the system explicitly supports quarter-to-year aggregation.

The database should prevent accidental mixing of:

```text
FY
Q1
Q2
Q3
Q4
TTM
annual
year
quarter
```

Recommended canonical contract:

```text
period_type: FY | Q | TTM
fiscal_year: integer
fiscal_quarter: nullable integer
period_start_date: date
period_end_date: date
```

For this specific project, final report tables and valuation should only consume:

```text
period_type = 'FY'
fiscal_year between 2021 and 2025
```

If quarterly data is ingested for operational reasons, it must live in a clearly separated staging or raw table and must not silently enter the FY reporting layer.

### 3.4. Unit and Currency Consistency

The database must track:

```text
currency
unit_scale
reported_unit
normalized_unit
value_raw
value_normalized
```

This prevents common financial data errors such as:

```text
million VND vs billion VND
VND vs thousand VND
raw API scale vs report scale
negative expenses vs positive expenses
```

Recommended normalized value convention:

```text
value_normalized: numeric
currency: VND
unit_scale: 1
```

For display, report rendering can convert to:

```text
billion VND
million VND
percentage
x multiple
```

Display scaling should not change the database truth layer.

### 3.5. Source Provenance

Each fact must be traceable to a source version.

Minimum source fields:

```text
source_versions.id
source_versions.source_type
source_versions.provider
source_versions.source_url
source_versions.local_path
source_versions.document_title
source_versions.publisher
source_versions.fiscal_year
source_versions.ticker
source_versions.retrieved_at
source_versions.content_hash
source_versions.parser_version
source_versions.raw_metadata
```

Important distinction:

```text
Source acquisition provenance != fact verification provenance
```

For example:

```text
Acquisition source: vnstock API
Verification source: DHG Annual Report 2024 PDF
```

The database must model both separately.

### 3.6. Reconciliation and Verification

The system should distinguish between:

```text
raw extracted value
canonical normalized value
verified accepted value
rejected value
conflicting value
manual review required
```

Recommended reconciliation status:

```text
MATCHED
MISMATCHED
MISSING_IN_OFFICIAL
MISSING_IN_API
SOURCE_UNAVAILABLE
PARSER_LOW_CONFIDENCE
MANUAL_REVIEW_REQUIRED
ACCEPTED_WITH_WARNING
REJECTED
```

The final report should only consume facts with acceptable status, for example:

```text
MATCHED
ACCEPTED_WITH_WARNING
MANUAL_APPROVED
```

It should not consume unverified Tier-3 or API-only facts for material quantitative claims unless explicitly marked as provisional in an internal audit artifact.

### 3.7. Report Claim Traceability

A financial report is not just a rendered document. It is a set of claims.

The database should store or generate traceability for:

```text
report_id
section_id
claim_id
claim_text
claim_type
metric_ids used
fact_ids used
formula_id used
source_version_ids used
citation_ids used
created_by
created_at
validation_status
```

Example:

```text
Claim: "Doanh thu thuần năm 2024 tăng 6.2% so với năm 2023."

Required trace:
- revenue.net FY2024 fact_id
- revenue.net FY2023 fact_id
- formula_id = yoy_growth
- source_version_id for 2024 official report
- source_version_id for 2023 official report
- calculation output = 6.2%
```

Without this layer, citations become decorative rather than auditable.

---

## 4. Current Red Flags

### 4.1. Red Flag 1: Runtime Schema Creation Instead of Controlled Migrations

If the system currently uses runtime schema initialization such as:

```text
RuntimeStore.ensure_schema()
  -> run 001_initial_schema.sql
  -> run 002_backend_runtime.sql
  -> run 003_lineage_enhancements.sql
```

then the database layer is not yet governed properly.

Problems:

1. Hard to know which schema version is actually deployed.
2. Difficult to reproduce database state.
3. Risk of silent schema drift.
4. Poor separation between application startup and database migration.
5. Risk of production mutation during runtime.

Recommended correction:

```text
Use explicit migration versioning.
Each migration must be immutable after merge.
Application startup must not patch schema silently.
Database version must be queryable.
```

Minimum required table:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum TEXT NOT NULL,
    description TEXT
);
```

### 4.2. Red Flag 2: Missing Foreign Keys

If tables contain columns such as `source_version_id` but do not enforce actual foreign keys, this is a major data integrity weakness.

Example anti-pattern:

```sql
source_version_id TEXT
```

without:

```sql
FOREIGN KEY (source_version_id) REFERENCES source_versions(id)
```

Risk:

```text
Fact rows may point to non-existing sources.
Citation map may point to deleted or invalid facts.
Reports may appear source-backed while the backing source no longer exists.
```

### 4.3. Red Flag 3: Mixed Responsibility Tables

A common database anti-pattern is one table trying to serve multiple layers:

```text
raw API result
parsed PDF result
canonical fact
verified fact
report-ready fact
```

These should not be collapsed into one ambiguous structure.

Recommended separation:

```text
source_versions             -> source inventory
raw_source_payloads          -> raw API/PDF/HTML payload metadata
extracted_financial_rows     -> parser-level extracted rows
financial_facts              -> canonical normalized facts
fact_reconciliation          -> verification result
accepted_financial_facts_v   -> view exposing report-consumable facts only
```

### 4.4. Red Flag 4: Weak Citation Model

A citation such as:

```text
Source: vnstock
Source: database
Source: source_version_id = abc123
```

is not acceptable for final financial reporting.

A strong citation should support:

```text
document title
publisher
fiscal year
page number
statement/table name
metric label in source
source URL or local archived path
retrieval timestamp
extraction method
reconciliation status
```

Internal IDs may exist in audit logs, but the final report should show human-readable source references.

### 4.5. Red Flag 5: Weak Idempotency

Ingestion must be repeatable without creating duplicate facts.

Recommended unique key for financial facts:

```text
ticker
fiscal_year
period_type
fiscal_quarter
statement_type
metric_id
consolidation_scope
source_version_id
```

For accepted canonical facts, use a stricter uniqueness policy:

```text
ticker
fiscal_year
period_type
metric_id
fact_role
```

where `fact_role` may be:

```text
reported
adjusted
forecast
consensus
```

### 4.6. Red Flag 6: Lack of Snapshot-Based Report Reproducibility

Every report should be tied to a stable data snapshot.

Required reproducibility metadata:

```text
report_id
run_id
code_commit_hash
config_version
prompt_version
model_name
model_version
data_snapshot_id
source_snapshot_id
created_at
```

Without a snapshot, two runs of the same ticker can produce different outputs and still appear valid.

### 4.7. Red Flag 7: No Hard Separation Between Internal Audit and Final Report

The database may need to store internal terms such as:

```text
Tier 1
Tier 2
Tier 3
source_version_id
parser_confidence
quality_gate
llm_verifier
backend fallback
```

However, the final report should not expose them directly.

Recommended design:

```text
Internal audit tables -> technical/debug layer
Citation rendering view -> analyst-readable source layer
Final report -> clean financial presentation layer
```

---

## 5. Recommended Target Database Architecture

### 5.1. Layered Database Model

```text
Layer 0: Source Inventory
  - companies
  - tickers
  - source_providers
  - source_versions
  - official_documents

Layer 1: Raw Acquisition
  - raw_api_payloads
  - raw_document_files
  - document_pages
  - document_tables

Layer 2: Extraction
  - extracted_financial_rows
  - extracted_text_blocks
  - extraction_runs

Layer 3: Canonical Facts
  - metric_dictionary
  - financial_facts
  - market_data_facts
  - catalyst_events

Layer 4: Verification and Reconciliation
  - fact_reconciliation
  - source_conflicts
  - manual_review_items
  - accepted_financial_facts_v

Layer 5: Valuation and Forecasting
  - valuation_runs
  - valuation_assumptions
  - forecast_facts
  - formula_outputs
  - sensitivity_results

Layer 6: Report and Citation
  - report_runs
  - report_sections
  - report_claims
  - claim_fact_links
  - citation_entries
  - report_quality_gate_results
```

### 5.2. Core Entity Relationships

```text
companies 1--n tickers
companies 1--n official_documents
official_documents 1--n source_versions
source_versions 1--n extracted_financial_rows
source_versions 1--n financial_facts
financial_facts 1--n fact_reconciliation
financial_facts n--n report_claims through claim_fact_links
report_runs 1--n report_sections
report_sections 1--n report_claims
report_claims 1--n citation_entries
valuation_runs 1--n formula_outputs
formula_outputs n--n financial_facts
```

---

## 6. Proposed Core Tables

### 6.1. `companies`

Purpose: store issuer-level identity.

```sql
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT NOT NULL,
    company_name_vi TEXT,
    exchange TEXT,
    sector TEXT,
    industry TEXT,
    country TEXT NOT NULL DEFAULT 'VN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.2. `tickers`

Purpose: support ticker-level lookup and exchange changes.

```sql
CREATE TABLE tickers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id),
    ticker TEXT NOT NULL,
    exchange TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT true,
    valid_from DATE,
    valid_to DATE,
    UNIQUE (ticker, exchange)
);
```

### 6.3. `source_versions`

Purpose: record every acquired source artifact.

```sql
CREATE TABLE source_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    ticker TEXT NOT NULL,
    source_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    document_title TEXT,
    publisher TEXT,
    source_url TEXT,
    local_path TEXT,
    fiscal_year INTEGER,
    period_type TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash TEXT,
    parser_name TEXT,
    parser_version TEXT,
    acquisition_run_id UUID,
    raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (period_type IS NULL OR period_type IN ('FY', 'Q', 'TTM'))
);
```

Recommended unique index:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_versions_hash
ON source_versions(content_hash)
WHERE content_hash IS NOT NULL;
```

### 6.4. `metric_dictionary`

Purpose: one canonical metric registry.

```sql
CREATE TABLE metric_dictionary (
    metric_id TEXT PRIMARY KEY,
    statement_type TEXT NOT NULL,
    display_name_en TEXT NOT NULL,
    display_name_vi TEXT NOT NULL,
    unit_type TEXT NOT NULL,
    normal_balance TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    formula_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

Recommended constraints:

```sql
ALTER TABLE metric_dictionary
ADD CONSTRAINT chk_metric_statement_type
CHECK (statement_type IN (
    'income_statement',
    'balance_sheet',
    'cash_flow',
    'market_data',
    'ratio',
    'forecast',
    'valuation'
));
```

### 6.5. `financial_facts`

Purpose: canonical normalized financial facts.

```sql
CREATE TABLE financial_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    ticker TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    period_type TEXT NOT NULL,
    fiscal_quarter INTEGER,
    statement_type TEXT NOT NULL,
    metric_id TEXT NOT NULL REFERENCES metric_dictionary(metric_id),
    value_raw NUMERIC,
    value_normalized NUMERIC NOT NULL,
    currency TEXT,
    reported_unit TEXT,
    normalized_unit TEXT NOT NULL,
    consolidation_scope TEXT NOT NULL DEFAULT 'consolidated',
    source_version_id UUID NOT NULL REFERENCES source_versions(id),
    extraction_method TEXT,
    parser_confidence NUMERIC,
    fact_role TEXT NOT NULL DEFAULT 'reported',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (period_type IN ('FY', 'Q', 'TTM')),
    CHECK (fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4),
    CHECK (fact_role IN ('reported', 'adjusted', 'forecast', 'consensus'))
);
```

Recommended uniqueness:

```sql
CREATE UNIQUE INDEX uq_financial_facts_source_metric_period
ON financial_facts (
    ticker,
    fiscal_year,
    period_type,
    COALESCE(fiscal_quarter, 0),
    statement_type,
    metric_id,
    consolidation_scope,
    source_version_id,
    fact_role
);
```

### 6.6. `fact_reconciliation`

Purpose: compare API-derived values with official-document-derived values.

```sql
CREATE TABLE fact_reconciliation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    period_type TEXT NOT NULL,
    metric_id TEXT NOT NULL REFERENCES metric_dictionary(metric_id),
    candidate_fact_id UUID REFERENCES financial_facts(id),
    reference_fact_id UUID REFERENCES financial_facts(id),
    candidate_source_version_id UUID REFERENCES source_versions(id),
    reference_source_version_id UUID REFERENCES source_versions(id),
    candidate_value NUMERIC,
    reference_value NUMERIC,
    absolute_diff NUMERIC,
    relative_diff NUMERIC,
    tolerance NUMERIC,
    status TEXT NOT NULL,
    decision TEXT,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (status IN (
        'MATCHED',
        'MISMATCHED',
        'MISSING_IN_OFFICIAL',
        'MISSING_IN_API',
        'SOURCE_UNAVAILABLE',
        'PARSER_LOW_CONFIDENCE',
        'MANUAL_REVIEW_REQUIRED',
        'ACCEPTED_WITH_WARNING',
        'MANUAL_APPROVED',
        'REJECTED'
    ))
);
```

### 6.7. `report_runs`

Purpose: make each report reproducible.

```sql
CREATE TABLE report_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker TEXT NOT NULL,
    fiscal_year_start INTEGER,
    fiscal_year_end INTEGER,
    report_type TEXT NOT NULL,
    status TEXT NOT NULL,
    code_commit_hash TEXT,
    config_version TEXT,
    prompt_version TEXT,
    model_name TEXT,
    model_version TEXT,
    data_snapshot_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    output_md_path TEXT,
    output_pdf_path TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (status IN ('DRAFT', 'FAILED', 'BLOCKED', 'APPROVED', 'EXPORTED'))
);
```

### 6.8. `report_claims`

Purpose: store auditable report claims.

```sql
CREATE TABLE report_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_run_id UUID NOT NULL REFERENCES report_runs(id),
    section_key TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (claim_type IN (
        'quantitative',
        'qualitative',
        'valuation',
        'forecast',
        'risk',
        'catalyst',
        'methodology'
    )),
    CHECK (validation_status IN (
        'UNVALIDATED',
        'VALIDATED',
        'PARTIALLY_VALIDATED',
        'FAILED',
        'NOT_APPLICABLE'
    ))
);
```

### 6.9. `claim_fact_links`

Purpose: connect report claims to exact facts.

```sql
CREATE TABLE claim_fact_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES report_claims(id) ON DELETE CASCADE,
    fact_id UUID NOT NULL REFERENCES financial_facts(id),
    usage_role TEXT NOT NULL,
    formula_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (claim_id, fact_id, usage_role)
);
```

Examples of `usage_role`:

```text
primary_metric
comparison_base
formula_input
valuation_input
chart_input
table_input
```

### 6.10. `citation_entries`

Purpose: render human-readable source citations.

```sql
CREATE TABLE citation_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES report_claims(id) ON DELETE CASCADE,
    source_version_id UUID NOT NULL REFERENCES source_versions(id),
    citation_text TEXT NOT NULL,
    page_number INTEGER,
    table_name TEXT,
    source_metric_label TEXT,
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

---

## 7. Recommended Database Views

### 7.1. `accepted_financial_facts_v`

Purpose: expose only report-consumable facts.

```sql
CREATE OR REPLACE VIEW accepted_financial_facts_v AS
SELECT
    f.*
FROM financial_facts f
JOIN fact_reconciliation r
  ON r.candidate_fact_id = f.id
WHERE r.status IN ('MATCHED', 'ACCEPTED_WITH_WARNING', 'MANUAL_APPROVED')
  AND f.period_type = 'FY';
```

For current project requirements, final report generation should read from this view, not directly from `financial_facts`.

### 7.2. `citation_rendering_v`

Purpose: provide analyst-readable citation output and hide backend internals.

```sql
CREATE OR REPLACE VIEW citation_rendering_v AS
SELECT
    ce.id AS citation_id,
    rc.id AS claim_id,
    sv.document_title,
    sv.publisher,
    sv.fiscal_year,
    ce.page_number,
    ce.table_name,
    ce.source_metric_label,
    ce.citation_text,
    sv.source_url,
    sv.retrieved_at
FROM citation_entries ce
JOIN report_claims rc ON rc.id = ce.claim_id
JOIN source_versions sv ON sv.id = ce.source_version_id;
```

This view should be used by the report renderer instead of raw technical tables.

### 7.3. `data_completeness_v`

Purpose: check whether each ticker has complete FY coverage.

```sql
CREATE OR REPLACE VIEW data_completeness_v AS
SELECT
    ticker,
    metric_id,
    COUNT(DISTINCT fiscal_year) AS years_available,
    MIN(fiscal_year) AS min_year,
    MAX(fiscal_year) AS max_year
FROM accepted_financial_facts_v
WHERE period_type = 'FY'
GROUP BY ticker, metric_id;
```

Expected coverage for current MVP:

```text
Ticker: DHG
Years: 2021, 2022, 2023, 2024, 2025
Period type: FY only
```

---

## 8. Data Quality Gates

The database should support deterministic gates before valuation and report export.

### 8.1. Gate 1: Source Availability

Block if material facts have no valid source.

```text
Required:
- source_version_id exists
- source_versions row exists
- source URL or archived local path exists
- content_hash exists where possible
```

### 8.2. Gate 2: FY Coverage

Block final report if required FY facts are missing.

Minimum required facts:

```text
revenue.net
cogs.total
gross_profit.total
sga.total
ebit.total
finance_cost.total
profit_before_tax.total
tax_expense.total
net_income.parent
total_assets.total
total_equity.total
total_debt.total
operating_cash_flow.total
capex.total
```

Required period coverage:

```text
2021 FY
2022 FY
2023 FY
2024 FY
2025 FY
```

### 8.3. Gate 3: Reconciliation Status

Block material quantitative claims if the facts are:

```text
MISMATCHED
MISSING_IN_OFFICIAL
SOURCE_UNAVAILABLE
PARSER_LOW_CONFIDENCE
MANUAL_REVIEW_REQUIRED
REJECTED
```

unless the report explicitly marks the section as provisional and the user-facing output is not treated as final.

### 8.4. Gate 4: Citation Coverage

For every quantitative report claim:

```text
claim_type = quantitative or valuation or forecast
```

there must be at least one valid citation or formula trace.

Required condition:

```text
report_claims.validation_status = VALIDATED
AND EXISTS claim_fact_links
AND EXISTS citation_entries for source-backed claims
```

### 8.5. Gate 5: No Internal Leakage

Final report must not contain backend terms:

```text
Tier 1
Tier 2
Tier 3
source_version_id
database id
backend
pipeline
quality gate
LLM verifier
parser confidence
```

These terms may remain in audit artifacts, not in final analyst-facing PDF.

---

## 9. Database Audit Queries

The following queries should be used to inspect the current database.

### 9.1. Find Tables Without Primary Keys

```sql
SELECT
    table_schema,
    table_name
FROM information_schema.tables t
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
  AND NOT EXISTS (
      SELECT 1
      FROM information_schema.table_constraints c
      WHERE c.table_schema = t.table_schema
        AND c.table_name = t.table_name
        AND c.constraint_type = 'PRIMARY KEY'
  );
```

### 9.2. Find Columns That Look Like Foreign Keys But Are Not Enforced

```sql
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND column_name LIKE '%_id'
ORDER BY table_name, column_name;
```

Then compare against actual foreign keys:

```sql
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
 AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public';
```

### 9.3. Detect Duplicate Financial Facts

```sql
SELECT
    ticker,
    fiscal_year,
    period_type,
    COALESCE(fiscal_quarter, 0) AS fiscal_quarter,
    metric_id,
    COUNT(*) AS duplicate_count
FROM financial_facts
GROUP BY
    ticker,
    fiscal_year,
    period_type,
    COALESCE(fiscal_quarter, 0),
    metric_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

### 9.4. Detect Non-FY Facts Used in Report Scope

```sql
SELECT *
FROM financial_facts
WHERE ticker = 'DHG'
  AND period_type <> 'FY';
```

### 9.5. Detect Facts Without Source Versions

```sql
SELECT f.*
FROM financial_facts f
LEFT JOIN source_versions sv
  ON sv.id = f.source_version_id
WHERE sv.id IS NULL;
```

### 9.6. Detect Metrics Not in Dictionary

```sql
SELECT DISTINCT f.metric_id
FROM financial_facts f
LEFT JOIN metric_dictionary m
  ON m.metric_id = f.metric_id
WHERE m.metric_id IS NULL;
```

### 9.7. Detect Report Claims Without Fact Links

```sql
SELECT rc.*
FROM report_claims rc
LEFT JOIN claim_fact_links cfl
  ON cfl.claim_id = rc.id
WHERE rc.claim_type IN ('quantitative', 'valuation', 'forecast')
  AND cfl.id IS NULL;
```

### 9.8. Detect Fact-Backed Claims Without Citations

```sql
SELECT rc.*
FROM report_claims rc
JOIN claim_fact_links cfl
  ON cfl.claim_id = rc.id
LEFT JOIN citation_entries ce
  ON ce.claim_id = rc.id
WHERE rc.claim_type IN ('quantitative', 'valuation', 'forecast')
  AND ce.id IS NULL;
```

### 9.9. Detect Source Version Rows Without Content Hash

```sql
SELECT *
FROM source_versions
WHERE content_hash IS NULL
   OR content_hash = '';
```

### 9.10. Detect Missing FY Coverage

```sql
WITH required_years AS (
    SELECT generate_series(2021, 2025) AS fiscal_year
),
required_metrics AS (
    SELECT unnest(ARRAY[
        'revenue.net',
        'cogs.total',
        'gross_profit.total',
        'sga.total',
        'ebit.total',
        'finance_cost.total',
        'profit_before_tax.total',
        'tax_expense.total',
        'net_income.parent',
        'total_assets.total',
        'total_equity.total',
        'total_debt.total',
        'operating_cash_flow.total',
        'capex.total'
    ]) AS metric_id
),
required_grid AS (
    SELECT y.fiscal_year, m.metric_id
    FROM required_years y
    CROSS JOIN required_metrics m
)
SELECT rg.*
FROM required_grid rg
LEFT JOIN accepted_financial_facts_v f
  ON f.fiscal_year = rg.fiscal_year
 AND f.metric_id = rg.metric_id
 AND f.ticker = 'DHG'
WHERE f.id IS NULL
ORDER BY rg.fiscal_year, rg.metric_id;
```

---

## 10. Migration and Refactor Plan

### Phase 0: Freeze and Inventory Current Database

Objective: capture the current state before changing schema.

Tasks:

```text
1. Export schema DDL.
2. Export table list and row counts.
3. Export foreign key list.
4. Export indexes.
5. Export duplicate fact diagnostics.
6. Export source coverage diagnostics.
7. Export report/citation diagnostics.
```

Deliverables:

```text
db_audit_schema_snapshot.sql
db_audit_table_inventory.csv
db_audit_fk_inventory.csv
db_audit_duplicate_facts.csv
db_audit_missing_sources.csv
db_audit_missing_citations.csv
```

Exit criteria:

```text
Current database state is fully documented.
No migration begins before the inventory is saved.
```

### Phase 1: Define Canonical Database Contract

Objective: create one authoritative database specification.

Tasks:

```text
1. Define canonical metric dictionary.
2. Define period contract.
3. Define source provenance contract.
4. Define reconciliation status enum.
5. Define report claim and citation contract.
6. Define accepted facts view.
```

Deliverables:

```text
DATABASE_CONTRACT.md
CANONICAL_METRIC_DICTIONARY.yaml
SOURCE_PROVENANCE_CONTRACT.md
REPORT_CITATION_CONTRACT.md
```

Exit criteria:

```text
No ingestion or report module uses free-form metric IDs or period labels.
```

### Phase 2: Build Controlled Migration System

Objective: remove runtime schema mutation as the primary schema governance mechanism.

Tasks:

```text
1. Create schema_migrations table.
2. Convert existing SQL schema files into versioned migrations.
3. Add checksums to prevent silent migration edits.
4. Add migration CLI command.
5. Ensure application startup only verifies schema version, not mutates schema.
```

Deliverables:

```text
scripts/db/migrate.py
scripts/db/migrations/001_initial.sql
scripts/db/migrations/002_source_provenance.sql
scripts/db/migrations/003_canonical_facts.sql
scripts/db/migrations/004_reconciliation.sql
scripts/db/migrations/005_report_claims_citations.sql
```

Exit criteria:

```text
Database version can be queried.
Application boot fails clearly if migration is missing.
```

### Phase 3: Normalize Source and Fact Tables

Objective: enforce clean separation of source, extraction, canonical facts, and verification.

Tasks:

```text
1. Create or harden source_versions.
2. Create metric_dictionary.
3. Create normalized financial_facts.
4. Add foreign keys.
5. Add unique constraints.
6. Add CHECK constraints for period_type, fact_role, statement_type.
7. Add source content_hash and parser_version tracking.
```

Deliverables:

```text
source_versions table
metric_dictionary table
financial_facts table
accepted_financial_facts_v view
```

Exit criteria:

```text
No financial fact can exist without metric_id and source_version_id.
No invalid period_type can be inserted.
No duplicate fact can be inserted for the same source/metric/period key.
```

### Phase 4: Implement Reconciliation Layer

Objective: make verification a first-class database function.

Tasks:

```text
1. Create fact_reconciliation table.
2. Store candidate facts and reference facts.
3. Store absolute and relative difference.
4. Store tolerance and decision.
5. Create accepted facts view based on reconciliation status.
6. Block report generation from unaccepted facts.
```

Deliverables:

```text
fact_reconciliation table
accepted_financial_facts_v view
reconciliation audit queries
```

Exit criteria:

```text
Report generation cannot consume raw financial_facts directly.
Report generation consumes accepted_financial_facts_v only.
```

### Phase 5: Implement Report Claim Traceability

Objective: make every material claim auditable.

Tasks:

```text
1. Create report_runs.
2. Create report_claims.
3. Create claim_fact_links.
4. Create citation_entries.
5. Add citation_rendering_v.
6. Add validation checks for claim-level citation coverage.
```

Deliverables:

```text
report_runs table
report_claims table
claim_fact_links table
citation_entries table
citation_rendering_v view
```

Exit criteria:

```text
Every quantitative claim has fact links.
Every fact-backed claim has source citations.
Final report renderer uses citation_rendering_v, not internal source IDs.
```

### Phase 6: Add Quality Gates

Objective: prevent bad data from reaching valuation and final report.

Tasks:

```text
1. Add completeness gate.
2. Add reconciliation gate.
3. Add citation coverage gate.
4. Add internal leakage gate.
5. Add report reproducibility gate.
6. Save gate results in report_quality_gate_results.
```

Deliverables:

```text
report_quality_gate_results table
quality gate SQL queries
quality gate runner
latest_quality_gate.json
latest_quality_gate.md
```

Exit criteria:

```text
Final PDF export is blocked if material facts are missing, unverified, uncited, or mixed-period.
```

### Phase 7: Data Cleanup and Backfill

Objective: clean the current dirty data and migrate only trusted records.

Tasks:

```text
1. Identify duplicate records.
2. Identify orphan records.
3. Identify non-FY records.
4. Identify facts without official verification.
5. Re-ingest official documents where possible.
6. Reconcile existing API data against official sources.
7. Insert only accepted facts into canonical views.
```

Deliverables:

```text
data_cleanup_report.md
duplicate_fact_resolution.csv
orphan_source_resolution.csv
fy_coverage_report.csv
reconciliation_backfill_report.csv
```

Exit criteria:

```text
DHG FY 2021-2025 has complete accepted fact coverage for required metrics.
No dirty Q data is used by final report generation.
```

### Phase 8: Regression Tests

Objective: prevent database quality regression.

Tests required:

```text
1. Cannot insert invalid period_type.
2. Cannot insert financial_fact with missing metric_id.
3. Cannot insert financial_fact with missing source_version_id.
4. Cannot insert duplicate canonical fact.
5. Cannot generate report from raw unverified facts.
6. Cannot approve quantitative claim without fact links.
7. Cannot approve fact-backed claim without citation.
8. Cannot export final report with backend terminology leakage.
9. Re-ingestion is idempotent.
10. DHG FY 2021-2025 completeness gate passes only with required facts.
```

Deliverables:

```text
tests/db/test_schema_constraints.py
tests/db/test_fact_idempotency.py
tests/db/test_reconciliation_gate.py
tests/db/test_report_claim_citations.py
tests/db/test_fy_completeness.py
```

Exit criteria:

```text
All database quality tests pass in CI.
```

---

## 11. Database Quality Rubric

Use this rubric to grade the database after remediation.

| Category | Weight | Excellent | Current Likely Status |
|---|---:|---|---|
| Schema normalization | 10% | Clear layered model with no mixed-responsibility tables | Needs hardening |
| Foreign keys | 10% | All logical relationships enforced | Weak or incomplete |
| Unique constraints | 10% | Duplicate financial facts impossible | Needs audit |
| Metric dictionary | 10% | One canonical registry used everywhere | Needs strict enforcement |
| Period governance | 10% | FY/Q/TTM clearly separated and constrained | High risk if unconstrained |
| Source provenance | 15% | Every fact traces to versioned source artifact | Partially implemented but likely insufficient |
| Reconciliation | 15% | API and official sources compared deterministically | Must be first-class |
| Citation traceability | 10% | Every quantitative claim linked to facts and citations | Current risk high |
| Reproducibility | 5% | Report tied to snapshot, code, config, model, prompt | Needs formalization |
| Migration discipline | 5% | Versioned, immutable migrations | Needs replacement of runtime schema patching |

### Suggested Current Grade

```text
Current estimated grade: C- / D+
```

This grade does not mean the database is unusable for experimentation. It means the current design is not yet strong enough for:

```text
production-grade financial reporting
academic defensibility
multi-ticker scaling
claim-level auditability
regression-safe development
```

### Target Grade

```text
Target grade after remediation: A-
```

An A-level database for this project must provide:

```text
1. Strong source lineage
2. Deterministic financial fact contracts
3. Controlled migration history
4. Full FY coverage validation
5. Official-source reconciliation
6. Claim-level citation traceability
7. Reproducible report runs
8. Quality gates that block unsafe outputs
```

---

## 12. Acceptance Criteria for a Production-Ready Database

The database can be considered production-ready for this project only if all conditions below are satisfied.

### 12.1. Schema Acceptance

```text
- All core tables have primary keys.
- All reference columns have foreign keys.
- All core enums are enforced through CHECK constraints or enum types.
- All canonical metric IDs exist in metric_dictionary.
- No report-critical table uses ambiguous free-form labels.
```

### 12.2. Data Acceptance

```text
- DHG has FY 2021-2025 coverage for all required metrics.
- No Q data is consumed by FY reports unless explicitly aggregated and marked.
- Every material financial fact has source_version_id.
- Every material fact has reconciliation status.
- Every accepted fact is traceable to source metadata.
```

### 12.3. Report Acceptance

```text
- Every quantitative claim links to exact fact IDs.
- Every fact-backed claim has citation entries.
- Citations are human-readable.
- Final report hides backend audit terminology.
- Report run has reproducibility metadata.
```

### 12.4. Operational Acceptance

```text
- Migrations are versioned and immutable.
- Application startup does not silently mutate schema.
- Re-ingestion is idempotent.
- CI runs database constraint tests.
- Quality gates block unsafe final exports.
```

---

## 13. Recommended Immediate Actions

The immediate next steps should be executed in this order.

### Step 1: Stop Treating the Current Database as Trusted

The current database should be treated as a staging or experimental store until it passes the audit gates.

### Step 2: Export a Full Database Inventory

Run schema, row count, FK, index, duplicate, and missing-source diagnostics.

### Step 3: Lock the Canonical Metric Dictionary

No further ingestion should proceed until metric IDs are stable.

### Step 4: Enforce FY-Only Consumption

Create a view or query contract that report and valuation modules must use:

```text
accepted_financial_facts_v
```

### Step 5: Add Foreign Keys and Unique Constraints

This is the highest-impact database hardening step.

### Step 6: Make Reconciliation Mandatory

No final report should use API-only material facts without official-source verification or explicit manual approval.

### Step 7: Build Claim-Level Citation Tables

Report quality cannot be fixed only in Markdown/PDF rendering. Citation must be modeled in the database.

### Step 8: Add Quality Gate Persistence

Every failed or passed gate should be saved with enough detail for debugging and academic audit.

---

## 14. Final Technical Judgment

The database layer is currently the main structural risk of the project. The core problem is not only missing tables or imperfect SQL. The deeper problem is that the database has not yet fully become the authoritative contract between:

```text
data acquisition
financial parsing
canonical normalization
official verification
valuation computation
report generation
citation rendering
quality evaluation
```

For an equity research system, this is critical. If the database cannot prove where each number came from, how it was transformed, and why it was accepted, then the final financial report is not defensible regardless of how good the agent narrative or PDF layout looks.

The correct remediation strategy is therefore:

```text
1. Freeze and inventory the current database.
2. Define a canonical schema contract.
3. Move to versioned migrations.
4. Enforce relational integrity.
5. Separate raw, canonical, verified, and report-ready data.
6. Add reconciliation as a first-class table.
7. Add claim-level citation traceability.
8. Block report export unless quality gates pass.
```

Once these steps are complete, the project will have a database foundation capable of supporting credible financial analysis, reproducible valuation, and citation-backed Vietnamese equity research reports.
