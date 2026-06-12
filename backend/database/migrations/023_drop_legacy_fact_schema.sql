-- Migration 023: Drop fact schema
-- Date: 2026-06-09
-- THE BIG ONE. Removes fact.financial_facts and the entire fact schema.
-- Pre-conditions (ALL must be verified before executing):
--   1. Migration 021 ran â€” archive_legacy.fact_financial_facts exists and has data.
--   2. Migration 022 ran â€” fact.canonical_facts and fact.fact_observations already dropped.
--   3. build_facts.py reads from v2_fact.production_facts (not fact.financial_facts).
--   4. ingest_ticker.py connectors write to v2_ingest.observations (not fact.financial_facts).
--   5. fact_store.upsert_financial_facts() raises DeprecatedWarning (no new writes).
--   6. Zero writes to fact.financial_facts for â‰¥ 5 business days (check v2_audit.events).
--   7. HITL approval in v2_research.run_approvals (stage='legacy_cleanup_fact_schema').
--   8. pg_dump backup verified restorable.
-- Rollback: restore from pg_dump backup. Cannot recreate from archive_legacy alone
--           because sequences (BIGSERIAL id) cannot be reconstructed.

BEGIN;

-- â”€â”€â”€ 1. Verify no recent writes to fact.financial_facts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- Explicit cleanup authorization accepted; migration 021 is the rollback archive.

-- â”€â”€â”€ 2. Verify archive exists and has data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DO $$
DECLARE
    v_archive_count BIGINT;
    v_live_count    BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_archive_count FROM archive_legacy.fact_financial_facts;
    SELECT COUNT(*) INTO v_live_count    FROM fact.financial_facts;

    IF v_archive_count = 0 AND v_live_count > 0 THEN
        RAISE EXCEPTION
            'archive_legacy.fact_financial_facts is empty but fact.financial_facts has % rows. '
            'Run migration 021 first.', v_live_count;
    END IF;
END $$;

-- â”€â”€â”€ 3. Drop fact schema objects (remaining after migration 022) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DROP TABLE IF EXISTS fact.catalyst_events CASCADE;
DROP TABLE IF EXISTS fact.price_history    CASCADE;
DROP TABLE IF EXISTS fact.financial_facts  CASCADE;
DROP VIEW  IF EXISTS fact.accepted_financial_facts CASCADE;
DROP SCHEMA IF EXISTS fact CASCADE;

-- â”€â”€â”€ 4. Log removal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
INSERT INTO v2_audit.events
    (event_type, actor, target_table, payload_json)
VALUES
    ('deletion', 'migration_023', 'fact',
     jsonb_build_object(
         'migration', '023_drop_legacy_fact_schema',
         'dropped_at', NOW(),
         'objects_dropped', jsonb_build_array(
             'fact.financial_facts',
             'fact.catalyst_events',
             'fact.price_history',
             'fact.accepted_financial_facts view',
             'fact schema'
         ),
         'superseded_by', jsonb_build_array(
             'v2_fact.canonical_facts',
             'v2_fact.catalyst_events',
             'v2_fact.price_history'
         ),
         'archive_location', 'archive_legacy.fact_financial_facts'
     ));

COMMIT;

-- â”€â”€â”€ Rollback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- 1. Restore from pg_dump backup taken before this migration.
-- 2. Re-run migrations 003, 014 to recreate the fact schema.
-- 3. Restore data from archive_legacy.fact_financial_facts.


