-- Migration 024: Drop legacy ingest and ref schemas
-- Date: 2026-06-09
-- Pre-conditions:
--   1. Migration 023 ran â€” fact schema dropped.
--   2. ingest.sources is no longer referenced by any production code.
--   3. Connectors write to v2_ingest.source_documents (not ingest.sources).
--   4. v2_ref.companies confirmed populated (â‰¥ 5 rows).
--   5. archive_legacy.ingest_sources and archive_legacy.ref_companies exist.
-- Rollback: restore from pg_dump backup.

BEGIN;

-- â”€â”€â”€ 1. Verify v2_ref.companies is populated â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DO $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count FROM v2_ref.companies;
    IF v_count < 5 THEN
        RAISE EXCEPTION
            'v2_ref.companies has only % rows. Populate v2_ref before dropping ref schema.', v_count;
    END IF;
END $$;

-- â”€â”€â”€ 2. Verify v2_ingest.source_documents has data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DO $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count FROM v2_ingest.source_documents;
    IF v_count = 0 THEN
        RAISE EXCEPTION
            'v2_ingest.source_documents is empty. Run migrate_clean_data_to_v2.py before dropping ingest schema.';
    END IF;
END $$;

-- â”€â”€â”€ 3. Drop remaining research schema objects â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- research.snapshots and research.snapshot_items were dropped in migration 022.
-- Drop remaining research objects (run_steps, run_artifacts, etc. from migration 004).
DROP SCHEMA IF EXISTS research CASCADE;
-- Drops: research.runs, research.run_steps, research.run_artifacts,
--        research.run_approvals, research.budget_ledger, research.audit_events
-- NOTE: v2_research.* supersedes all of these.

-- â”€â”€â”€ 4. Drop ingest schema â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DROP SCHEMA IF EXISTS ingest CASCADE;
-- Drops: ingest.sources, ingest.raw_payloads, ingest.parser_runs,
--        ingest.official_documents, ingest.company_snapshots

-- â”€â”€â”€ 5. Drop ref schema â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DROP SCHEMA IF EXISTS ref CASCADE;
-- Drops: ref.companies, ref.line_items, ref.formulas, ref.universe_members

-- â”€â”€â”€ 6. Log removal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
INSERT INTO v2_audit.events
    (event_type, actor, target_table, payload_json)
VALUES
    ('deletion', 'migration_024', 'ingest,ref,research',
     jsonb_build_object(
         'migration', '024_drop_legacy_ingest_ref_schemas',
         'dropped_at', NOW(),
         'schemas_dropped', jsonb_build_array('ingest', 'ref', 'research'),
         'superseded_by', jsonb_build_array('v2_ingest.*', 'v2_ref.*', 'v2_research.*'),
         'archive_location', 'archive_legacy.*'
     ));

COMMIT;

-- â”€â”€â”€ Rollback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- Restore from pg_dump backup taken before this migration.
-- Re-run migrations 001, 002, 004 to recreate schemas.
-- Restore data from archive_legacy.ingest_sources, archive_legacy.ref_companies.

