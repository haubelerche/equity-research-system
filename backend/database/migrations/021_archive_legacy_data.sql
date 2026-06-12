-- Migration 021: Archive legacy data before schema removal
-- Date: 2026-06-09
-- Purpose: Create archive_legacy schema; copy valuable legacy data; preserve for 90-day review.
-- Safe: no legacy schema objects are dropped here. Only copying to archive.
-- Rollback: DROP SCHEMA archive_legacy CASCADE;

BEGIN;

-- â”€â”€â”€ 1. Create archive schema â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE SCHEMA IF NOT EXISTS archive_legacy;

COMMENT ON SCHEMA archive_legacy IS
    'Point-in-time copy of legacy tables taken before schema removal (2026-06-09). '
    'Read-only archive. Delete after 90-day review with HITL approval.';

-- â”€â”€â”€ 2. Archive ref.companies â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE TABLE IF NOT EXISTS archive_legacy.ref_companies AS
    SELECT * FROM ref.companies;

COMMENT ON TABLE archive_legacy.ref_companies IS
    'Copy of ref.companies at migration 021 (2026-06-09). '
    'Superseded by v2_ref.companies.';

-- â”€â”€â”€ 3. Archive ingest.sources â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE TABLE IF NOT EXISTS archive_legacy.ingest_sources AS
    SELECT * FROM ingest.sources;

COMMENT ON TABLE archive_legacy.ingest_sources IS
    'Copy of ingest.sources at migration 021 (2026-06-09). '
    'Superseded by v2_ingest.source_documents.';

-- â”€â”€â”€ 4. Archive ingest.official_documents â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE TABLE IF NOT EXISTS archive_legacy.ingest_official_documents AS
    SELECT * FROM ingest.official_documents;

COMMENT ON TABLE archive_legacy.ingest_official_documents IS
    'Copy of ingest.official_documents at migration 021 (2026-06-09). '
    'Merged into v2_ingest.source_documents as tier 0/1 records.';

-- â”€â”€â”€ 5. Archive fact.financial_facts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE TABLE IF NOT EXISTS archive_legacy.fact_financial_facts AS
    SELECT * FROM fact.financial_facts;

COMMENT ON TABLE archive_legacy.fact_financial_facts IS
    'Copy of fact.financial_facts at migration 021 (2026-06-09). '
    'Superseded by v2_fact.canonical_facts + v2_ingest.observations. '
    'Many rows have synthetic golden_csv_* source_id not present in ingest.sources.';

-- â”€â”€â”€ 6. Archive fact.canonical_facts (legacy backfill, not production) â”€â”€â”€â”€â”€â”€â”€
CREATE TABLE IF NOT EXISTS archive_legacy.fact_canonical_facts AS
    SELECT * FROM fact.canonical_facts;

COMMENT ON TABLE archive_legacy.fact_canonical_facts IS
    'Copy of legacy fact.canonical_facts backfill table (migration 011). '
    'Never used by production code. Superseded by v2_fact.canonical_facts.';

-- â”€â”€â”€ 7. Add row counts to audit log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DO $$
DECLARE
    v_ff_count  BIGINT;
    v_src_count BIGINT;
    v_od_count  BIGINT;
    v_ref_count BIGINT;
    v_cf_count  BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_ff_count  FROM archive_legacy.fact_financial_facts;
    SELECT COUNT(*) INTO v_src_count FROM archive_legacy.ingest_sources;
    SELECT COUNT(*) INTO v_od_count  FROM archive_legacy.ingest_official_documents;
    SELECT COUNT(*) INTO v_ref_count FROM archive_legacy.ref_companies;
    SELECT COUNT(*) INTO v_cf_count  FROM archive_legacy.fact_canonical_facts;

    INSERT INTO v2_audit.events
        (event_type, actor, target_table, payload_json)
    VALUES
        ('schema_migration', 'migration_021', 'archive_legacy',
         jsonb_build_object(
             'migration', '021_archive_legacy_data',
             'archived_at', NOW(),
             'row_counts', jsonb_build_object(
                 'fact_financial_facts',    v_ff_count,
                 'ingest_sources',          v_src_count,
                 'ingest_official_documents', v_od_count,
                 'ref_companies',           v_ref_count,
                 'fact_canonical_facts',    v_cf_count
             )
         ));
END $$;

COMMIT;

-- â”€â”€â”€ Rollback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- DROP SCHEMA archive_legacy CASCADE;

