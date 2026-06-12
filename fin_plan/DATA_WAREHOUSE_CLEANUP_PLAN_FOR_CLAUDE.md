# DATA_WAREHOUSE_CLEANUP_PLAN_FOR_CLAUDE

## Role

You are a **Senior PostgreSQL / Supabase Data Warehouse Architect**, **Financial Data Governance Lead**, and **Backend Refactoring Architect**.

Your task is to clean and rebuild the project data warehouse into a **single, simple, production-ready architecture**.

This is not a documentation-only task.  
This is not a temporary migration plan.  
This is not a parallel schema experiment.  
This is a real cleanup task.

---

## 1. Current Situation

The current data layer is messy, duplicated, and unsafe.

Data is scattered across:

- Supabase / PostgreSQL schemas,
- `public` business tables,
- local project folders under `backend/data`,
- local raw document folders,
- loose `artifacts/` folders,
- JSON / CSV / JSONL files,
- report files,
- valuation output files,
- agent debug outputs,
- old snapshots,
- old run artifacts,
- old fact tables.

The current design has created a split-brain data warehouse:

```text
Supabase/PostgreSQL stores some structured data.
Filesystem stores some source documents and generated artifacts.
CSV/JSON files sometimes act as hidden data sources.
public.* still contains duplicated business tables.
canonical schemas exist, but public tables still look like an old warehouse.
```

This is unacceptable for a financial equity research system.

The final architecture must have:

```text
one database schema set
one filesystem/object-storage layout
one source of truth for each data type
one canonical fact path
one run-scoped artifact path
no hidden CSV override
no latest-file fallback
no duplicated official document folders
no duplicated public business warehouse
no abandoned table kept for convenience
```

---

## 2. Final Database Architecture

The final active PostgreSQL / Supabase business schemas must be exactly:

```text
ref
ingest
fact
research
valuation
report
audit
```

Do not create or keep temporary versioned schema names.

Do not keep duplicated production schemas.

Do not keep business data in `public`.

The `public` schema must not contain project business tables. It may only contain database/platform technical objects that are strictly required, such as a migration history table if the migration runner depends on it.

---

## 3. Purpose of Each Final Schema

### 3.1 `ref`

Purpose: stable reference/master data.

Allowed tables:

```text
companies
line_items
formulas
peer_groups
peer_group_members
```

Allowed data:

- company master data,
- ticker normalization,
- exchange,
- sector/subsector,
- financial metric dictionary,
- formula registry,
- peer group definitions.

Not allowed:

- raw extracted facts,
- report text,
- valuation output files,
- connector logs,
- run artifacts.

---

### 3.2 `ingest`

Purpose: source registration and raw/staged observations.

Allowed tables:

```text
source_documents
observations
connector_runs
```

Optional only if truly needed:

```text
ingestion_runs
document_chunks
```

Allowed data:

- source document metadata,
- file checksum,
- source URI,
- source tier,
- source title,
- connector execution logs,
- raw extracted financial observations,
- raw extracted market/catalyst observations,
- parser/OCR lineage.

Not allowed:

- canonical financial facts,
- final valuation numbers,
- report claims,
- generated report text,
- random JSON dumps without schema.

---

### 3.3 `fact`

Purpose: canonical production facts only.

Allowed tables/views:

```text
canonical_facts
price_history
catalyst_events
production_facts
```

Rules:

- `canonical_facts` is the single source of truth for financial facts.
- `production_facts` should be a view exposing only accepted, production-safe facts.
- Raw observations must not live here.
- LLM-generated text must not live here.
- CSV facts must not be injected into production here without going through `ingest.source_documents` and `ingest.observations`.

---

### 3.4 `research`

Purpose: research workflow state and run reproducibility.

Allowed tables:

```text
runs
run_steps
snapshots
snapshot_items
run_artifacts
run_approvals
run_audit_events
```

Allowed data:

- research run lifecycle,
- retry/resume state,
- run steps,
- frozen fact snapshots,
- artifact metadata,
- approval state,
- run-level audit events.

Not allowed:

- actual PDF/HTML/JSON artifact blobs,
- raw financial facts,
- generated report text as the only source of truth,
- unscoped latest artifacts.

---

### 3.5 `valuation`

Purpose: valuation metadata and reproducibility.

Allowed tables:

```text
runs
assumptions
```

Optional if needed:

```text
quality_checks
```

Allowed data:

- valuation run metadata,
- snapshot reference,
- valuation method,
- model version,
- approved assumptions,
- target price summary,
- link to valuation artifact metadata.

Large valuation output JSON should be stored as a run artifact file and registered in `research.run_artifacts`.

Not allowed:

- duplicated full valuation JSON blobs if they are already in artifact storage,
- raw financial facts,
- report narrative.

---

### 3.6 `report`

Purpose: report governance, claims, citations, and approval.

Allowed tables/views:

```text
reports
claims
citation_records
gate_results
approval_records
uncited_quantitative_claims
```

Allowed data:

- report metadata,
- report sections if needed for editing,
- factual claims,
- quantitative claims,
- citation links,
- quality gate results,
- approval records,
- exported report metadata.

Report `.md`, `.html`, and `.pdf` files should live in run-scoped storage and be referenced by artifact metadata.

Not allowed:

- uncited financial claims in approved reports,
- generated report files as loose unregistered files,
- claims without citation/fact/source linkage.

---

### 3.7 `audit`

Purpose: governance, cost, schema, and quality logs.

Allowed tables:

```text
events
cost_ledger
schema_changes
```

Optional if needed:

```text
data_quality_checks
cleanup_log
```

Allowed data:

- append-only system events,
- model/token/cost ledger,
- schema migration records,
- cleanup records,
- data quality events,
- human review events.

Not allowed:

- canonical financial facts,
- report text,
- raw extracted financial data.

---

## 4. What Must Be Removed

The cleanup must remove business tables from `public`.

The following public business tables must not remain active:

```text
public.accepted_financial_facts
public.catalyst_events
public.company_profiles
public.connector_runs
public.financial_facts
public.forecast_inputs
public.ingestion_runs
public.peer_metrics_snapshot
public.price_history
public.research_runs
public.run_approvals
public.run_artifacts
public.run_audit_events
public.run_budget_ledger
public.run_steps
public.source_versions
```

Keep only platform/migration technical objects if strictly necessary, for example:

```text
public.schema_migrations
```

If any public table contains useful data, migrate it into the correct final schema first.  
If the data is dirty, duplicated, incomplete, untrusted, or tiny enough to be recreated, do not preserve it. Re-ingest clean data instead.

Since the live Supabase warehouse currently has little valuable data, prefer:

```text
backup -> drop dirty/duplicated public business tables -> re-ingest clean data
```

over complex preservation of questionable legacy data.

---

## 5. Final Filesystem / Object Storage Architecture

The filesystem must be reorganized into one canonical storage layout:

```text
storage/
  sources/
    official_documents/
      {ticker}/
        {year}/
          {source_doc_id}.pdf

  runs/
    {run_id}/
      manifest.json
      facts_snapshot.json
      valuation.json
      evidence_pack.json
      report.md
      report.html
      report.pdf
      quality_gate.json

  exports/
    approved_reports/
      {ticker}/
        {run_id}/
          report.pdf
          report.html
          report.md

  archive/
    debug/
    failed_runs/
```

Do not keep old production paths such as:

```text
artifacts/facts
artifacts/forecast
artifacts/valuation
artifacts/valuation_results
artifacts/reports
artifacts/reports_html
artifacts/reports_pdf
artifacts/evidence_packets
artifacts/review_packets
artifacts/agent_outputs
backend/data/raw/official_documents
backend/data/official_documents
```

These must be moved, deleted, or replaced.

Rules:

1. Source PDFs live only under `storage/sources`.
2. Run artifacts live only under `storage/runs/{run_id}`.
3. Approved final outputs live only under `storage/exports`.
4. Debug and failed run outputs live only under `storage/archive`.
5. Production code must not read from `storage/archive`.
6. Production code must not read loose files from `artifacts/`.
7. Production code must never use “latest file” discovery.
8. Every artifact used by a run must be explicitly tied to `run_id`.

---

## 6. Source-of-Truth Rules

| Data type | Source of truth | File allowed? | Database allowed? |
|---|---|---:|---:|
| Company/ticker master | `ref.companies` | No | Yes |
| Metric dictionary | `ref.line_items` | No | Yes |
| Official PDF document | `storage/sources` + `ingest.source_documents` metadata | Yes | Metadata only |
| Raw extracted financial value | `ingest.observations` | Temporary parser debug only | Yes |
| Canonical financial fact | `fact.canonical_facts` | Snapshot export only | Yes |
| Production-safe facts | `fact.production_facts` view | No | Yes |
| Price history | `fact.price_history` | No, except import files | Yes |
| Catalyst events | `fact.catalyst_events` | Optional import files | Yes |
| Frozen research snapshot | `research.snapshots` + `research.snapshot_items` | Optional run copy | Yes |
| Valuation assumptions | `valuation.assumptions` | Optional export copy | Yes |
| Full valuation output | `storage/runs/{run_id}/valuation.json` + `research.run_artifacts` | Yes | Metadata/summary only |
| Report claims/citations | `report.claims`, `report.citation_records` | No | Yes |
| Report `.md/.html/.pdf` | `storage/runs/{run_id}` and `storage/exports` | Yes | Metadata only |
| Audit/cost events | `audit.events`, `audit.cost_ledger` | Optional backup export | Yes |
| Debug output | `storage/archive/debug` | Yes | No production DB |

---

## 7. Unit and Scale Standardization

The current data shows inconsistent unit handling such as `vnd` and `vnd_bn` mixed in financial fact tables.

This must be fixed before any data becomes production-safe.

Final rule:

```text
canonical_facts.value = normalized numeric value
canonical_facts.unit = canonical unit
canonical_facts.currency = currency code
canonical_facts.scale = explicit numeric scale if scale is stored separately
```

Recommended contract:

```text
Monetary values:
  value = absolute VND
  unit = 'VND'
  currency = 'VND'
  scale = 1

Per-share values:
  value = VND per share
  unit = 'VND_PER_SHARE'
  currency = 'VND'
  scale = 1

Ratios:
  value = decimal ratio
  unit = 'RATIO'
  currency = NULL
  scale = 1

Percentages:
  value = decimal, e.g. 0.15 for 15%
  unit = 'PERCENT_DECIMAL'
  currency = NULL
  scale = 1
```

Do not allow downstream code to guess whether `6308` means VND, million VND, or billion VND.

If the original source reports in VND billion, normalize before promotion:

```text
source value = 6308
source unit = VND_BN
canonical value = 6,308,000,000,000
canonical unit = VND
```

If a value cannot be normalized with confidence, keep it in `ingest.observations` and mark it as `needs_review`. Do not insert it into `fact.production_facts`.

---

## 8. Required Cleanup Execution Plan

### Phase 1 — Live Inventory

Run live SQL against Supabase and document the actual current state.

Create:

```text
audits/data_warehouse_live_inventory.md
```

Must include:

- all schemas,
- all tables,
- all views,
- row counts,
- column counts,
- whether table is empty,
- whether table is business data or platform metadata,
- whether table is production, duplicate, obsolete, or technical.

Required SQL:

```sql
select schema_name
from information_schema.schemata
where schema_name in (
  'public',
  'ref',
  'ingest',
  'fact',
  'research',
  'valuation',
  'report',
  'audit'
)
order by schema_name;
```

```sql
select table_schema, table_name, table_type
from information_schema.tables
where table_schema in (
  'public',
  'ref',
  'ingest',
  'fact',
  'research',
  'valuation',
  'report',
  'audit'
)
order by table_schema, table_name;
```

Do not use estimated or expected counts. Use live row counts.

---

### Phase 2 — Backup

Before destructive cleanup, create a backup.

Create:

```text
scripts/database/backup_before_data_warehouse_cleanup.py
audits/data_warehouse_backup_report.md
```

The backup must cover:

- `public` project-owned business tables,
- `ref`,
- `ingest`,
- `fact`,
- `research`,
- `valuation`,
- `report`,
- `audit`.

The report must include:

- database name,
- timestamp,
- schemas backed up,
- backup file path,
- restore command,
- checksum if possible.

---

### Phase 3 — Drop Public Business Warehouse

Remove business tables from `public`.

Create migration:

```text
backend/database/migrations/XXX_drop_public_business_tables.sql
```

This migration must:

1. preserve `public.schema_migrations` if the migration runner needs it;
2. drop or move all project business tables from `public`;
3. verify that no business tables remain in `public`.

Before dropping, check row counts. If the tables are empty or contain disposable data, drop them. If they contain valuable data, migrate only verified rows into final schemas.

Required post-cleanup proof:

```sql
select table_schema, table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;
```

Expected: no project business tables.

---

### Phase 4 — Enforce Final Schema Set

Ensure active business schemas are only:

```text
ref
ingest
fact
research
valuation
report
audit
```

Create:

```text
audits/final_schema_set_verification.md
```

The report must prove:

- no extra production business schemas exist,
- no temporary schema naming remains,
- no duplicate schema purpose exists,
- no business tables remain in `public`.

---

### Phase 5 — Rewrite Ingestion Path

This is the most important backend task.

All ingestion must write into the final schemas only.

Rewrite or replace:

```text
scripts/ingest_ticker.py
scripts/connectors/*.py
backend/database/source_registry.py
backend/database/official_documents.py
backend/database/fact_store.py
```

Final ingestion flow:

```text
connector fetch
  -> ingest.connector_runs
  -> ingest.source_documents
  -> ingest.observations
  -> fact promotion / validation
  -> fact.canonical_facts
  -> fact.production_facts view
```

Do not write directly to final facts from connectors.

Do not write to `public.*`.

Do not write to old `financial_facts` tables.

Do not silently inject CSV files at runtime.

If golden CSV is still needed, import it as a registered source document and observations:

```text
golden CSV file
  -> ingest.source_documents
  -> ingest.observations
  -> validation
  -> fact.canonical_facts only if accepted
```

---

### Phase 6 — Rewrite Artifact Path

All artifacts must be run-scoped.

Rewrite or remove all code that reads/writes:

```text
artifacts/facts
artifacts/forecast
artifacts/valuation
artifacts/valuation_results
artifacts/reports
artifacts/reports_html
artifacts/reports_pdf
artifacts/evidence_packets
artifacts/review_packets
artifacts/agent_outputs
```

Final artifact flow:

```text
research.runs.run_id
  -> storage/runs/{run_id}/manifest.json
  -> storage/runs/{run_id}/facts_snapshot.json
  -> storage/runs/{run_id}/valuation.json
  -> storage/runs/{run_id}/evidence_pack.json
  -> storage/runs/{run_id}/report.md
  -> storage/runs/{run_id}/report.html
  -> storage/runs/{run_id}/report.pdf
  -> research.run_artifacts metadata rows
```

No latest-file fallback is allowed.

All artifact reads must use explicit:

```text
run_id
snapshot_id
artifact_id
```

---

### Phase 7 — Re-ingest Clean Data

Because the live Supabase warehouse has little valuable data, do not over-optimize preserving dirty data.

After cleanup, re-ingest clean data from controlled sources:

1. official documents,
2. verified CSVs if necessary,
3. market data connectors,
4. company metadata,
5. catalyst sources.

Required validation before facts enter production:

- ticker exists in `ref.companies`,
- metric exists in `ref.line_items`,
- source document exists in `ingest.source_documents`,
- unit is normalized,
- period is valid,
- confidence threshold passes,
- duplicate check passes,
- accepted fact has lineage.

---

### Phase 8 — Data Quality Gates

Implement hard gates:

1. no canonical fact without source lineage;
2. no production fact with confidence below threshold;
3. no mixed `vnd` / `vnd_bn` ambiguity;
4. no duplicate `(ticker, period, metric)` in production facts;
5. no orphan snapshot item;
6. no uncited quantitative report claim;
7. no valuation run without snapshot reference;
8. no report export without quality gate result;
9. no artifact used without `run_id`;
10. no code path reading from `public` business tables.

---

### Phase 9 — Tests

Add tests proving:

- no production code references `public.financial_facts`;
- no production code references `public.accepted_financial_facts`;
- no production code references `public.company_profiles`;
- no production code references loose `artifacts/facts`;
- no latest-file glob fallback exists;
- golden CSV cannot override DB facts at runtime;
- ingestion writes to `ingest.observations`;
- fact promotion writes to `fact.canonical_facts`;
- valuation reads from frozen snapshots;
- report claims link to citations/facts;
- final schemas exist;
- public business tables do not exist.

Create:

```text
tests/unit/test_data_warehouse_final_contract.py
tests/integration/test_data_warehouse_live_contract.py
```

---

## 9. Final Verification

Create:

```text
audits/final_data_warehouse_cleanup_report.md
```

This report must include:

### 9.1 Live database proof

- current schemas,
- current tables,
- row counts,
- no business tables in `public`,
- only final schema set is active.

### 9.2 Filesystem proof

Show that only this layout is production-active:

```text
storage/sources
storage/runs
storage/exports
storage/archive
```

Show that old artifact/data paths are removed, empty, or explicitly ignored by production code.

### 9.3 Code proof

Use ripgrep results to prove production code does not reference:

```text
public.financial_facts
public.accepted_financial_facts
public.company_profiles
public.research_runs
public.run_artifacts
public.run_budget_ledger
artifacts/facts
artifacts/valuation_results
artifacts/reports_html
artifacts/reports_pdf
backend/data/raw
_load_golden_fallback
latest
glob(
```

Any remaining reference must be classified as:

```text
test-only
migration-only
archive-only
production blocker
```

Production blockers must be fixed before completion.

---

## 10. Final Acceptance Criteria

The task is complete only when all are true:

1. Active business schemas are exactly `ref`, `ingest`, `fact`, `research`, `valuation`, `report`, `audit`.
2. `public` contains no project business tables.
3. No duplicated fact tables exist.
4. No duplicated run tables exist.
5. No duplicated report/citation tables exist.
6. No loose artifact path is used in production.
7. Source documents live under `storage/sources`.
8. Run artifacts live under `storage/runs/{run_id}`.
9. Approved exports live under `storage/exports`.
10. Canonical facts live only in `fact.canonical_facts`.
11. Production facts are exposed only through `fact.production_facts`.
12. Golden CSV cannot override facts at runtime.
13. No latest-file fallback exists.
14. All financial units are normalized.
15. All production facts have lineage.
16. All valuation runs reference a frozen snapshot.
17. All quantitative report claims have citations.
18. Ingestion path writes to `ingest`, not directly to `fact`.
19. Tests pass.
20. Final verification report includes live SQL proof.

---

## 11. Final Instruction

Do not return another plan-only report.

Perform the cleanup.

If live database access is missing, stop and report the exact missing connection configuration.

If a destructive change is blocked, say exactly what blocks it.

If the database has little valuable data, prefer clean reset and re-ingestion over preserving questionable legacy rows.

The final result must be a clean, minimal, production-ready data warehouse.
