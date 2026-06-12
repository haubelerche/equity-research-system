-- Migration 025: Final constraint enforcement on v2_* schemas
-- Date: 2026-06-09
-- Purpose: Add/verify all production constraints after legacy schemas are gone.
--          Enforce NOT NULL where previously deferred, add missing indexes,
--          remove any compatibility-only columns.
-- Pre-condition: migrations 021â€“024 must have run.

BEGIN;

-- â”€â”€â”€ 1. v2_fact.canonical_facts â€” enforce NOT NULL on critical columns â”€â”€â”€â”€â”€â”€â”€â”€
ALTER TABLE v2_fact.canonical_facts
    ALTER COLUMN ticker              SET NOT NULL,
    ALTER COLUMN period              SET NOT NULL,
    ALTER COLUMN metric              SET NOT NULL,
    ALTER COLUMN value               SET NOT NULL,
    ALTER COLUMN unit                SET NOT NULL,
    ALTER COLUMN canonical_version   SET NOT NULL,
    ALTER COLUMN quality_status      SET NOT NULL;

-- â”€â”€â”€ 2. v2_fact.canonical_facts â€” confidence range check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ALTER TABLE v2_fact.canonical_facts
    DROP CONSTRAINT IF EXISTS chk_canonical_confidence_range;

ALTER TABLE v2_fact.canonical_facts
    ADD CONSTRAINT chk_canonical_confidence_range
        CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0));

-- â”€â”€â”€ 3. v2_fact.canonical_facts â€” source_tier range check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ALTER TABLE v2_fact.canonical_facts
    DROP CONSTRAINT IF EXISTS chk_canonical_source_tier;

ALTER TABLE v2_fact.canonical_facts
    ADD CONSTRAINT chk_canonical_source_tier
        CHECK (source_tier IS NULL OR source_tier BETWEEN 0 AND 3);

-- â”€â”€â”€ 4. v2_ingest.observations â€” enforce NOT NULL on critical columns â”€â”€â”€â”€â”€â”€â”€â”€â”€
ALTER TABLE v2_ingest.observations
    ALTER COLUMN ticker              SET NOT NULL,
    ALTER COLUMN period              SET NOT NULL,
    ALTER COLUMN metric              SET NOT NULL,
    ALTER COLUMN value               SET NOT NULL,
    ALTER COLUMN source_tier         SET NOT NULL;

-- â”€â”€â”€ 5. v2_ingest.observations â€” confidence range check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ALTER TABLE v2_ingest.observations
    DROP CONSTRAINT IF EXISTS chk_observation_confidence_range;

ALTER TABLE v2_ingest.observations
    ADD CONSTRAINT chk_observation_confidence_range
        CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0));

-- â”€â”€â”€ 6. v2_ingest.source_documents â€” enforce NOT NULL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ALTER TABLE v2_ingest.source_documents
    ALTER COLUMN source_type         SET NOT NULL,
    ALTER COLUMN source_tier         SET NOT NULL,
    ALTER COLUMN checksum            SET NOT NULL;

-- â”€â”€â”€ 7. v2_report.claims â€” enforce NOT NULL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
ALTER TABLE v2_report.claims
    ALTER COLUMN report_id           SET NOT NULL,
    ALTER COLUMN claim_text          SET NOT NULL,
    ALTER COLUMN claim_type          SET NOT NULL;

-- â”€â”€â”€ 8. Add missing indexes for frequent query patterns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

-- production_facts view filtering (ticker + canonical_version + period)
CREATE INDEX IF NOT EXISTS idx_canonical_facts_ticker_version_period
    ON v2_fact.canonical_facts (ticker, canonical_version, period);

-- observation lookup by ticker + period + metric (winner-selection query)
CREATE INDEX IF NOT EXISTS idx_observations_ticker_period_metric
    ON v2_ingest.observations (ticker, period, metric, source_tier DESC);

-- snapshot items lookup by snapshot_id (load_snapshot_facts query)
CREATE INDEX IF NOT EXISTS idx_snapshot_items_snapshot_id
    ON v2_research.snapshot_items (snapshot_id)
    WHERE item_type = 'canonical_fact';

-- report claims lookup by report_id
CREATE INDEX IF NOT EXISTS idx_claims_report_id
    ON v2_report.claims (report_id);

-- audit events by type + run_id (diagnostics)
CREATE INDEX IF NOT EXISTS idx_audit_events_run_type
    ON v2_audit.events (run_id, event_type)
    WHERE run_id IS NOT NULL;

-- â”€â”€â”€ 9. Drop any redundant indexes from early v2 migrations â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- (None identified â€” indexes in migrations 016â€“020 are all production-relevant)

-- â”€â”€â”€ 10. Log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
INSERT INTO v2_audit.events
    (event_type, actor, target_table, payload_json)
VALUES
    ('schema_migration', 'migration_025', 'v2_fact,v2_ingest,v2_report',
     jsonb_build_object(
         'migration', '025_final_schema_constraints',
         'applied_at', NOW(),
         'changes', jsonb_build_array(
             'NOT NULL on canonical_facts critical columns',
             'confidence range CHECK on canonical_facts + observations',
             'source_tier range CHECK on canonical_facts',
             'NOT NULL on observations critical columns',
             'NOT NULL on source_documents critical columns',
             'NOT NULL on claims critical columns',
             'indexes: ticker+version+period, ticker+period+metric, snapshot_id, report_id, run_type'
         )
     ));

COMMIT;

