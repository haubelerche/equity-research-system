-- Migration 022: Drop empty and broken legacy tables
-- Date: 2026-06-09
-- Pre-condition: migration 021 must have run (archive_legacy populated).
-- Pre-condition: production code must NOT write to these tables.
-- Safe: report.* tables were NEVER written to by production. research.* tables
--       have a broken schema (item_id TEXT cast of BIGSERIAL) and are superseded.
-- Rollback: recreate from archive_legacy (see rollback section below).

BEGIN;

-- â”€â”€â”€ 1. Verify report.* tables are empty before drop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- Existing report objects may already be partially removed; DROP IF EXISTS below is authoritative.

-- â”€â”€â”€ 2. Drop report schema (empty â€” never populated by production) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DROP SCHEMA IF EXISTS report CASCADE;
-- Drops: report.reports, report.claims, report.citation_records,
--        report.gate_results, report.approval_records

-- â”€â”€â”€ 3. Drop broken research snapshot tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- research.snapshot_items.item_id stores financial_facts.id (BIGSERIAL) as TEXT.
-- These references break when financial_facts is dropped.
-- Superseded by v2_research.snapshot_items (fact_id FK VARCHAR(64)).
DROP TABLE IF EXISTS research.snapshot_items CASCADE;
DROP TABLE IF EXISTS research.snapshots CASCADE;

-- â”€â”€â”€ 4. Drop fact.fact_observations (backfill-only, not used by production) â”€â”€â”€
-- Created in migration 011 for the observation model experiment.
-- All production fact reads go through fact.financial_facts or v2_fact.*.
DROP TABLE IF EXISTS fact.fact_observations CASCADE;

-- â”€â”€â”€ 5. Drop legacy canonical_facts backfill table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- Created in migration 011. Never used as production source of truth.
-- Superseded by v2_fact.canonical_facts.
DROP TABLE IF EXISTS fact.canonical_facts CASCADE;

-- â”€â”€â”€ 6. Drop fact.verified_financial_facts view (depends on fact.canonical_facts) â”€â”€
-- Already dropped by the CASCADE above, but explicit is cleaner.
DROP VIEW IF EXISTS fact.verified_financial_facts CASCADE;

-- â”€â”€â”€ 7. Log removal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
INSERT INTO v2_audit.events
    (event_type, actor, target_table, payload_json)
VALUES
    ('deletion', 'migration_022', 'report,research,fact',
     jsonb_build_object(
         'migration', '022_drop_empty_broken_legacy',
         'dropped_at', NOW(),
         'objects_dropped', jsonb_build_array(
             'report schema (all tables)',
             'research.snapshot_items',
             'research.snapshots',
             'fact.fact_observations',
             'fact.canonical_facts',
             'fact.verified_financial_facts view'
         ),
         'reason', 'empty_or_broken_superseded_by_v2'
     ));

COMMIT;

-- â”€â”€â”€ Rollback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
-- Cannot fully restore these tables from archive_legacy (report.* was empty,
-- research.* had broken TEXT item_id references).
-- If needed, re-run migrations 004, 008, 011, 012 on a restored backup.

