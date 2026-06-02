# Schema Gap Analysis — Phase 0

**Date:** 2026-05-30  
**Scope:** Compare every table currently in the DB against the target Data Trust Layer schema. Identify what exists, what is missing, and what needs to be altered.

---

## Existing Tables (by schema)

### Schema: `ref`
| Table | Purpose | Status |
|---|---|---|
| `ref.companies` | Ticker registry (DHG, IMP, ...) | ✅ Sufficient |
| `ref.line_items` | Canonical metric taxonomy | ✅ Sufficient |
| `ref.periods` | Reference period table | ✅ Sufficient |
| `ref.exchanges` | Exchange codes | ✅ Sufficient |

### Schema: `ingest`
| Table | Purpose | Gap vs. target model |
|---|---|---|
| `ingest.sources` | Source registry | ⚠️ Has `reliability_tier` (1–3 scale) but plan needs `source_tier` (0–4 scale). Missing `source_tier` column. Missing `source_document_type` (distinct from `source_type`). No `publisher`, `local_path`, `language`. `reliability_tier CHECK` blocks tier 0. |
| `ingest.raw_payloads` | Raw data storage | ⚠️ Has `source_id`, `content_type`, `payload_json`, `checksum`. Missing `connector_name`, `connector_version`, `request_uri`, `request_params`, `response_path`, `response_checksum`. Current `checksum` is the payload checksum — needs distinction between payload checksum and response checksum. |
| `ingest.document_chunks` | Text chunks for RAG | ⚠️ Exists. Missing `source_document_id` (links to planned `source_documents` table), `embedding_model`, `content_hash`. Current `source_id` links to `ingest.sources` which is a merge of source registry and document registry. |
| `ingest.connector_runs` | Ingestion run tracking | ✅ Covers `ingestion_runs` requirement. Has `run_id`, `ticker`, `connector_name`, `status`, `started_at`, `finished_at`, `error_message`. Missing `connector_version`, `source_document_ids_created`. |
| `ingest.validation_issues` | Parser/ingestion errors | ✅ Covers `parser_run` error tracking. Does not replace `parser_runs` (no `parser_name`, `parser_version`, `started_at`, `completed_at` as a run entity). |
| `ingest.company_snapshots` | Company profile cache | ✅ Sufficient for its purpose |

### Schema: `fact`
| Table | Purpose | Gap vs. target model |
|---|---|---|
| `fact.financial_facts` | All financial facts | ⚠️ Currently serves as both `fact_observations` and `canonical_facts`. The `uq_fact_current_accepted` partial unique index enforces one accepted row per metric/period — but this means all competing source observations are discarded rather than preserved. No `selected_observation_id`, no `selection_policy`, no `canonical_version`. Has `source_id` FK but it's discarded at normalization. |
| `fact.price_history` | Market price EOD | ✅ Sufficient for its purpose |
| `fact.catalyst_events` | Regulatory/market events | ⚠️ Missing `causality_level`, `fiscal_period_overlap`, `driver_type`. `event_type` CHECK constraint doesn't include all planned types (`catalyst_policy`, `regulatory_recall`, etc.). No link to `fact.financial_facts`. |
| `fact.accepted_financial_facts` | View: accepted FY facts | ⚠️ Useful view but strips `source_id` and `connector_version` from the SELECT output (they are not in the view definition at lines 97–115 of 003_fact_schema.sql). This means consumers of the view cannot see source provenance. |

### Schema: `research`
| Table | Purpose | Gap vs. target model |
|---|---|---|
| `research.snapshots` | Research run snapshots | ⚠️ Covers partial `valuation_artifacts` functionality. Has `snapshot_id`, `ticker`, `as_of_date`, `facts_count`, `status`. Missing `input_fact_ids`, `formula_versions`, `checksum`, `canonical_version`, `assumptions_json`. |
| `research.snapshot_facts` | Facts included in snapshot | ✅ Partial coverage of `valuation_artifact_input_facts` junction table |
| `research.dq_reports` | Data quality reports | ⚠️ Covers partial `quality_gate_results` functionality. Missing `gate_name`, `severity`, `failed_claim_ids`, `failed_fact_ids`. |

---

## Missing Tables (required by plan, do not exist)

| Table | Migration | Priority |
|---|---|---|
| `source_documents` | 010 | P0 — foundation for all Tier tracking |
| `parser_runs` | 010 | P0 — needed for Gate 2 lineage chain |
| `fact_observations` | 011 | P0 — needed to preserve multiple source candidates per metric |
| `canonical_facts` | 011 | P0 — needed to store selected winner with `selected_observation_id` |
| `fact_reconciliation` | 011 | P0 — needed for Gate 3 (conflict audit) |
| `schema_migrations` | 010 | P0 — needed to track migration state |
| `derived_metrics` | 011 | P1 — needed for valuation lineage |
| `valuation_artifacts` | 012 | P1 — needed to lock versioned valuation output |
| `reports` | 012 | P1 — needed for report versioning and status |
| `report_sections` | 012 | P1 — needed for section-level tracking |
| `report_claims` | 012 | P0 — needed for Gate 4 (structured numeric consistency) |
| `citation_records` | 012 | P0 — needed for Gate 5 (citation grounding) |
| `quality_gate_results` | 012 | P1 — needed for deterministic gate result persistence |
| `approval_records` | 012 | P1 — needed for HITL approval trace |
| `manual_verification_records` | 012 | P1 — needed for golden dataset provenance |

---

## Tables That Need Alteration

### `ingest.sources` → becomes `source_documents` (or sources gets extended)

Required changes:
```sql
-- Add source_tier column (0-4 scale) — DO NOT copy reliability_tier values directly.
-- The two scales are not equivalent:
--   Old reliability_tier: 1 = primary (BCTC), 2 = market reference, 3 = supplemental API
--   New source_tier:       0 = audited filing, 1 = company IR, 2 = reputable media,
--                          3 = vnstock/API aggregator, 4 = LLM output (forbidden)
-- Every row must be mapped by connector/source_type, not by numeric translation.
ALTER TABLE ingest.sources ADD COLUMN source_tier SMALLINT;

-- Mapping policy (apply per source_type, not per old tier number):
UPDATE ingest.sources SET source_tier = 0 WHERE source_type IN ('financial_statement', 'annual_report', 'regulatory_filing', 'disclosure');
UPDATE ingest.sources SET source_tier = 1 WHERE source_type IN ('manual');
UPDATE ingest.sources SET source_tier = 2 WHERE source_type IN ('industry_report', 'news');
UPDATE ingest.sources SET source_tier = 3 WHERE source_type IN ('vnstock_financial', 'vnstock_price', 'vnstock_company', 'market_reference', 'tender', 'bidding', 'regulatory');
-- Any row still NULL after the above gets Tier 3 (safe default for unknown API sources)
UPDATE ingest.sources SET source_tier = 3 WHERE source_tier IS NULL;

-- Note: Tier 0 for financial_statement/disclosure is aspirational. In current data,
-- these source_types are fetched via vnstock API, not from actual audited PDFs.
-- The connector upgrades in Phase 1B will correct this by introducing separate source_types
-- (e.g., 'bctc_audited', 'hose_filing') that genuinely correspond to Tier 0 documents.
-- Until Phase 1B is complete, source_type='financial_statement' rows should be reviewed
-- and may require manual downgrade to Tier 3 if no direct filing PDF was ingested.

-- Add NOT NULL constraint after backfill, then update CHECK to allow tier 0:
ALTER TABLE ingest.sources ADD CONSTRAINT chk_source_tier CHECK (source_tier BETWEEN 0 AND 3);
-- Update CHECK: allow tier 0 (currently blocked by reliability_tier CHECK (1 AND 3))

-- Add missing columns
ALTER TABLE ingest.sources ADD COLUMN publisher VARCHAR(200);
ALTER TABLE ingest.sources ADD COLUMN local_path TEXT;
ALTER TABLE ingest.sources ADD COLUMN language VARCHAR(10) DEFAULT 'vi';
```

Note: The plan uses `source_documents` as the new table name, but these columns can be added to `ingest.sources` to avoid a full table rename. The `source_id` FK chain must continue to work.

---

### `ingest.raw_payloads` needs connector metadata

Required changes:
```sql
ALTER TABLE ingest.raw_payloads ADD COLUMN connector_name VARCHAR(60);
ALTER TABLE ingest.raw_payloads ADD COLUMN connector_version VARCHAR(40);
ALTER TABLE ingest.raw_payloads ADD COLUMN request_uri TEXT;
ALTER TABLE ingest.raw_payloads ADD COLUMN request_params JSONB;
ALTER TABLE ingest.raw_payloads ADD COLUMN response_path TEXT;
ALTER TABLE ingest.raw_payloads ADD COLUMN response_checksum VARCHAR(64);
```

---

### `fact.accepted_financial_facts` view must expose `source_id`

Current view at `003_fact_schema.sql:97–115` does not SELECT `source_id` or `connector_version`. All consumers of this view lose source provenance immediately.

Required fix:
```sql
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
    source_id,           -- ADD
    connector_version,   -- ADD
    confidence,
    effective_date,
    ingested_at
FROM fact.financial_facts
WHERE validation_status = 'accepted'
  AND fiscal_period      = 'FY'
  AND is_current         = TRUE;
```

---

### `fact.catalyst_events` needs causality support

Required changes:
```sql
ALTER TABLE fact.catalyst_events ADD COLUMN causality_level VARCHAR(40) 
    DEFAULT 'contextual_event'
    CHECK (causality_level IN (
        'contextual_event', 'potential_driver', 
        'management_disclosed_driver', 'validated_driver'
    ));
ALTER TABLE fact.catalyst_events ADD COLUMN fiscal_period_overlap VARCHAR(10);
ALTER TABLE fact.catalyst_events ADD COLUMN driver_type VARCHAR(60);
```

Also update `event_type` CHECK to add: `'catalyst_policy'`, `'regulatory_recall'`, `'regulatory_approval'`, `'capacity_expansion'`.

---

### `research.snapshots` needs versioning columns

Required changes:
```sql
ALTER TABLE research.snapshots ADD COLUMN canonical_version VARCHAR(40);
ALTER TABLE research.snapshots ADD COLUMN formula_versions TEXT[];
ALTER TABLE research.snapshots ADD COLUMN assumptions_json JSONB;
ALTER TABLE research.snapshots ADD COLUMN checksum VARCHAR(64);
ALTER TABLE research.snapshots ADD COLUMN input_fact_ids VARCHAR(64)[];
```

---

## Missing Config Files

| File | Purpose | Status |
|---|---|---|
| `config/material_metrics.yml` | Defines which metrics require Tier 0/1 corroboration | ❌ Missing |
| `source_tier_policy.yml` | Maps connector names → source_tier | ❌ Missing |
| `config/dataset/golden/financials/DHG_golden_provenance.json` | Provenance for DHG golden CSV | ❌ Missing |

---

## Migration Sequence

```
010_source_documents.sql      -- source_tier on ingest.sources, parser_runs, schema_migrations
011_observation_canonical.sql -- fact_observations, canonical_facts, fact_reconciliation, derived_metrics
012_claim_citations.sql        -- reports, report_sections, report_claims, citation_records,
                               -- quality_gate_results, approval_records, manual_verification_records
013_view_fixes.sql             -- fix accepted_financial_facts view to expose source_id
014_catalyst_causality.sql     -- causality_level and driver_type on catalyst_events
```

Each migration must be idempotent (`IF NOT EXISTS`, `IF NOT EXISTS` for columns via `DO $$ ... $$`). The `schema_migrations` table created in migration 010 will track which migrations have been applied.

---

## Backfill Plan (for existing data)

After creating new tables, the following backfill is required to avoid breaking the current pipeline:

1. **Backfill `fact_observations`** from current `fact.financial_facts`:
   ```sql
   INSERT INTO fact.fact_observations (ticker, period, metric, value, unit, currency, 
       source_document_id, confidence, source_tier, extraction_method, created_at)
   SELECT ticker, 
          CONCAT(fiscal_year, 'FY') AS period,
          line_item_code,
          value, unit, currency,
          source_id AS source_document_id,
          confidence,
          3 AS source_tier,  -- legacy data = Tier 3 (vnstock/API aggregator; not independently verified)
          'legacy_api' AS extraction_method,
          ingested_at
   FROM fact.financial_facts;
   ```

2. **Backfill `canonical_facts`** from `fact.accepted_financial_facts`:
   ```sql
   INSERT INTO fact.canonical_facts (fact_id, ticker, period, metric, value, unit, currency,
       selected_observation_id, selection_policy, confidence, quality_status, created_at)
   SELECT ...; -- mapped from the view
   ```

3. Create `fact.financial_facts_legacy` view pointing to old table.

4. Switch `build_facts.py` and `run_valuation.py` to read from `canonical_facts`.

5. Run E2E diff on DHG — valuation output must be within 0.1% of old path.

6. Deprecate `fact.financial_facts` only after diff passes.
