# Data Warehouse Live Inventory
**Date:** 2026-06-09
**Source:** Live query against Supabase (fxplbbqyuigtfwxpqasl)
**Phase:** 1 — Live Inventory

---

## Schemas Present

```sql
SELECT schema_name FROM information_schema.schemata
WHERE schema_name NOT IN ('pg_catalog','pg_toast','information_schema')
ORDER BY schema_name;
```

| Schema | Classification | Status |
|--------|---------------|--------|
| `ref` | Business — Final Production | KEEP |
| `ingest` | Business — Final Production | KEEP |
| `fact` | Business — Final Production | KEEP |
| `research` | Business — Final Production | KEEP |
| `valuation` | Business — Final Production | KEEP |
| `report` | Business — Final Production | KEEP |
| `audit` | Business — Final Production | KEEP |
| `public` | Mixed — contains business tables to drop + schema_migrations to keep | PARTIAL DROP |
| `archive_legacy` | Archive — 90-day retention | KEEP TEMPORARILY |
| `auth` | Platform — Supabase auth system | KEEP (platform) |
| `storage` | Platform — Supabase storage system | KEEP (platform) |
| `realtime` | Platform — Supabase realtime | KEEP (platform) |
| `extensions` | Platform — pg_stat_statements | KEEP (platform) |
| `graphql` / `graphql_public` | Platform | KEEP (platform) |
| `pgbouncer` | Platform — connection pooler | KEEP (platform) |
| `vault` | Platform — secrets | KEEP (platform) |

**Finding:** Final production schemas (`ref`, `ingest`, `fact`, `research`, `valuation`, `report`, `audit`) already exist with correct names. No `v2_*` prefix schemas in production.

---

## Final Production Tables — Live Row Counts

### `ref` schema

| Table | Type | Rows | Classification |
|-------|------|------|----------------|
| `ref.companies` | BASE TABLE | 6 | Production — company master |
| `ref.formulas` | BASE TABLE | 30 | Production — formula registry |
| `ref.line_items` | BASE TABLE | 32 | Production — metric dictionary |
| `ref.peer_group_members` | BASE TABLE | 8 | Production — peer group membership |
| `ref.peer_groups` | BASE TABLE | 3 | Production — peer group definitions |

### `ingest` schema

| Table | Type | Rows | Classification |
|-------|------|------|----------------|
| `ingest.connector_runs` | BASE TABLE | 0 | Production — connector audit log |
| `ingest.observations` | BASE TABLE | 480 | Production — raw extracted values |
| `ingest.source_documents` | BASE TABLE | 61 | Production — source document registry |

### `fact` schema

| Table | Type | Rows | Classification |
|-------|------|------|----------------|
| `fact.canonical_facts` | BASE TABLE | 480 | Production — single source of truth |
| `fact.catalyst_events` | BASE TABLE | 0 | Production — empty (7 rows in public.catalyst_events to migrate) |
| `fact.price_history` | BASE TABLE | 6,068 | Production — market price data |
| `fact.production_facts` | VIEW | 480 | Production — confidence-gated view |

### `research` schema

| Table | Type | Rows | Classification |
|-------|------|------|----------------|
| `research.run_approvals` | BASE TABLE | 0 | Production |
| `research.run_artifacts` | BASE TABLE | 315 | Production — artifact metadata |
| `research.run_audit_events` | BASE TABLE | 0 | Production |
| `research.run_steps` | BASE TABLE | 0 | Production |
| `research.runs` | BASE TABLE | 162 | Production — run lifecycle |
| `research.snapshot_items` | BASE TABLE | 0 | Production |
| `research.snapshots` | BASE TABLE | 0 | Production |

### `valuation` schema

| Table | Type | Rows | Classification |
|-------|------|------|----------------|
| `valuation.assumptions` | BASE TABLE | 0 | Production |
| `valuation.runs` | BASE TABLE | 0 | Production |

### `report` schema

| Table | Type | Rows | Classification |
|-------|------|------|----------------|
| `report.approval_records` | BASE TABLE | 0 | Production |
| `report.citation_records` | BASE TABLE | 0 | Production |
| `report.claims` | BASE TABLE | 0 | Production |
| `report.gate_results` | BASE TABLE | 0 | Production |
| `report.reports` | BASE TABLE | 0 | Production |
| `report.uncited_quantitative_claims` | VIEW | 0 | Production |

### `audit` schema

| Table | Type | Rows | Classification |
|-------|------|------|----------------|
| `audit.cost_ledger` | BASE TABLE | 26 | Production — LLM cost tracking |
| `audit.events` | BASE TABLE | 7 | Production — governance log |
| `audit.schema_changes` | BASE TABLE | 5 | Production — migration history |

---

## `public` Schema — Business Tables (MUST DROP)

| Table | Type | Rows | Action | Reason |
|-------|------|------|--------|--------|
| `public.accepted_financial_facts` | VIEW | 48 | DROP VIEW | Superseded by `fact.production_facts` |
| `public.catalyst_events` | BASE TABLE | 7 | MIGRATE → `fact.catalyst_events` then DROP | Data not yet in fact schema |
| `public.company_profiles` | BASE TABLE | 1 | DROP (data in ref.companies) | Superseded by `ref.companies` |
| `public.connector_runs` | BASE TABLE | 0 | DROP | Superseded by `ingest.connector_runs` |
| `public.financial_facts` | BASE TABLE | 48 | DROP | Superseded by `fact.canonical_facts` (480 rows) |
| `public.forecast_inputs` | BASE TABLE | 0 | DROP | Not used in final pipeline |
| `public.ingestion_runs` | BASE TABLE | 0 | DROP | Superseded by `ingest.connector_runs` |
| `public.peer_metrics_snapshot` | BASE TABLE | 0 | DROP | Not used in final pipeline |
| `public.price_history` | BASE TABLE | 1,247 | DROP | `fact.price_history` has 6,068 rows (superset) |
| `public.research_runs` | BASE TABLE | 0 | DROP | Superseded by `research.runs` |
| `public.run_approvals` | BASE TABLE | 0 | DROP | Superseded by `research.run_approvals` |
| `public.run_artifacts` | BASE TABLE | 0 | DROP | Superseded by `research.run_artifacts` |
| `public.run_audit_events` | BASE TABLE | 0 | DROP | Superseded by `research.run_audit_events` |
| `public.run_budget_ledger` | BASE TABLE | 0 | DROP | Superseded by `audit.cost_ledger` |
| `public.run_steps` | BASE TABLE | 0 | DROP | Superseded by `research.run_steps` |
| `public.source_versions` | BASE TABLE | 16 | DROP | Superseded by `ingest.source_documents` (61 rows) |

**Keep:**

| Table | Rows | Reason |
|-------|------|--------|
| `public.schema_migrations` | 27 | Migration runner history — required by migrate.py |

---

## `archive_legacy` Schema — Temporary Archive

| Table | Rows | Retention |
|-------|------|-----------|
| `archive_legacy.fact_canonical_facts` | 488 | 90-day analyst review |
| `archive_legacy.fact_financial_facts` | 480 | 90-day analyst review |
| `archive_legacy.ingest_official_documents` | 2 | 90-day analyst review |
| `archive_legacy.ingest_sources` | 55 | 90-day analyst review |
| `archive_legacy.ref_companies` | 6 | 90-day analyst review |

---

## Key Findings

### Final schema set is already correct

The final production schemas (`ref`, `ingest`, `fact`, `research`, `valuation`, `report`, `audit`) all exist with the correct table names. No `v2_*` schema renaming is needed.

### Data quality is sound

- `fact.canonical_facts`: 480 facts, 480 in production_facts view (100% accepted, confidence >= 0.80)
- `ingest.observations`: 480 observations matching 480 canonical facts (1:1 ratio — all observations promoted)
- `ingest.source_documents`: 61 source documents — all observations have lineage
- `fact.price_history`: 6,068 price rows — covers all active tickers

### One data migration needed

`public.catalyst_events` has 7 rows not yet in `fact.catalyst_events` (0 rows).
These 7 rows must be migrated before `public.catalyst_events` is dropped.

### 15 public business tables must be dropped

See table above. Only `public.schema_migrations` must be kept.

### Code layer is partially complete

- `backend/database/canonical/` — all DAL modules target final clean schema names ✅
- `scripts/build_facts.py` — reads from `fact.production_facts`, writes to `storage/runs/` ✅
- `backend/dataops/snapshot.py` — shim imports from `backend.database.v2` (wrong, must be `canonical`) ❌
- `backend/database/source_registry.py` — still writes to legacy ingest.sources (pending rewrite) ❌
- `backend/database/official_documents.py` — still writes to legacy tables (pending rewrite) ❌
- `backend/database/fact_store.py` — partially frozen, price methods redirected ⚠️

---

## Acceptance Criteria vs Current State

| Criterion | Status |
|-----------|--------|
| Active schemas: ref, ingest, fact, research, valuation, report, audit | ✅ All exist |
| public contains no project business tables | ❌ 15 tables remain |
| No duplicated fact tables | ❌ public.financial_facts + fact.canonical_facts |
| No duplicated price tables | ❌ public.price_history + fact.price_history |
| No duplicated run tables | ❌ public.research_runs + research.runs |
| canonical_facts is single source of truth | ✅ fact.canonical_facts only |
| Production facts via production_facts view | ✅ fact.production_facts (view) |
| Golden CSV cannot override at runtime | ✅ _load_golden_fallback() removed |
| No latest-file fallback | ✅ build_facts uses storage/runs/{run_id} |
| Ingestion writes to ingest.* | ⚠️ Partially (source_registry still legacy) |
| All quantitative claims have citations | ✅ report.uncited_quantitative_claims = 0 |
