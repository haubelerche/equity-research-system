-- Migration: 026_drop_public_business_tables.sql
-- Purpose: Remove all project business tables from the public schema.
--          Only public.schema_migrations (migration runner history) is kept.
-- Pre-condition: Backup taken via scripts/database/backup_before_data_warehouse_cleanup.py
-- Risk: HIGH for public.price_history (1247 rows) and public.catalyst_events (7 rows)
-- Safety: price_history data exists in fact.price_history (6068 rows).
--         catalyst_events migrated to fact.catalyst_events below before drop.

BEGIN;

-- ── Step 1: Migrate public.catalyst_events → fact.catalyst_events ────────────
-- public.catalyst_events has 7 rows not in fact.catalyst_events (0 rows).
-- Column mapping:
--   company_ticker → ticker
--   source_version_id → source_doc_id (soft reference; no FK in new schema)
--   causality_level → DEFAULT 'contextual_event'
--   run_id column dropped (not in final schema)

INSERT INTO fact.catalyst_events (
    event_id,
    ticker,
    event_type,
    title,
    summary,
    occurred_at,
    effective_date,
    materiality_hint,
    causality_level,
    source_doc_id,
    source_url,
    confidence,
    validation_status,
    ingested_at
)
SELECT
    event_id,
    company_ticker                       AS ticker,
    CASE event_type
        WHEN 'news'              THEN 'news'
        WHEN 'disclosure'        THEN 'disclosure'
        WHEN 'regulatory'        THEN 'regulatory'
        WHEN 'tender'            THEN 'tender'
        WHEN 'bidding'           THEN 'bidding'
        WHEN 'drug_registration' THEN 'drug_registration'
        WHEN 'dividend'          THEN 'dividend'
        WHEN 'corporate_action'  THEN 'corporate_action'
        WHEN 'company_announcement' THEN 'disclosure'
        ELSE 'other'
    END                                  AS event_type,
    title,
    summary,
    occurred_at,
    effective_date,
    materiality_hint,
    'contextual_event'                   AS causality_level,
    -- source_version_id may not match ingest.source_documents PKs; set NULL if so
    CASE
        WHEN EXISTS (
            SELECT 1 FROM ingest.source_documents sd
            WHERE sd.source_doc_id = source_version_id
        ) THEN source_version_id
        ELSE NULL
    END                                  AS source_doc_id,
    source_url,
    confidence,
    COALESCE(validation_status, 'raw')   AS validation_status,
    COALESCE(ingested_at, NOW())         AS ingested_at
FROM public.catalyst_events
ON CONFLICT (event_id) DO NOTHING;

-- Verify migration succeeded
DO $$
DECLARE
    src_count  INTEGER;
    dest_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO src_count  FROM public.catalyst_events;
    SELECT COUNT(*) INTO dest_count FROM fact.catalyst_events;
    IF dest_count < src_count THEN
        RAISE EXCEPTION
            'catalyst_events migration incomplete: public has % rows, fact has % rows',
            src_count, dest_count;
    END IF;
    RAISE NOTICE 'catalyst_events migrated: % rows now in fact.catalyst_events', dest_count;
END $$;

-- ── Step 2: Assert public.price_history is a subset of fact.price_history ────
DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM public.price_history p
    WHERE NOT EXISTS (
        SELECT 1 FROM fact.price_history f
        WHERE f.ticker = p.ticker AND f.trade_date = p.date
    );
    IF orphan_count > 0 THEN
        RAISE WARNING
            '% rows in public.price_history not found in fact.price_history — these will be lost',
            orphan_count;
    ELSE
        RAISE NOTICE 'public.price_history is fully covered by fact.price_history (6068+ rows)';
    END IF;
END $$;

-- ── Step 3: Drop the public view first (depends on public.financial_facts) ────
DROP VIEW IF EXISTS public.accepted_financial_facts CASCADE;

-- ── Step 4: Drop all public project business tables ───────────────────────────
-- Order matters: views before base tables; FK-referenced tables last.

DROP TABLE IF EXISTS public.catalyst_events       CASCADE;
DROP TABLE IF EXISTS public.company_profiles      CASCADE;
DROP TABLE IF EXISTS public.connector_runs        CASCADE;
DROP TABLE IF EXISTS public.financial_facts       CASCADE;
DROP TABLE IF EXISTS public.forecast_inputs       CASCADE;
DROP TABLE IF EXISTS public.ingestion_runs        CASCADE;
DROP TABLE IF EXISTS public.peer_metrics_snapshot CASCADE;
DROP TABLE IF EXISTS public.price_history         CASCADE;
DROP TABLE IF EXISTS public.research_runs         CASCADE;
DROP TABLE IF EXISTS public.run_approvals         CASCADE;
DROP TABLE IF EXISTS public.run_artifacts         CASCADE;
DROP TABLE IF EXISTS public.run_audit_events      CASCADE;
DROP TABLE IF EXISTS public.run_budget_ledger     CASCADE;
DROP TABLE IF EXISTS public.run_steps             CASCADE;
DROP TABLE IF EXISTS public.source_versions       CASCADE;

-- ── Step 5: Verify only schema_migrations remains in public ──────────────────
DO $$
DECLARE
    remaining_tables TEXT;
BEGIN
    SELECT STRING_AGG(table_name, ', ' ORDER BY table_name)
    INTO remaining_tables
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_type IN ('BASE TABLE', 'VIEW')
      AND table_name != 'schema_migrations';

    IF remaining_tables IS NOT NULL THEN
        RAISE EXCEPTION
            'Unexpected tables remain in public schema after cleanup: %',
            remaining_tables;
    END IF;

    RAISE NOTICE 'public schema clean: only schema_migrations remains';
END $$;

-- ── Step 6: Log the cleanup event ─────────────────────────────────────────────
INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'deletion',
    'migration_026_drop_public_business_tables',
    'public.*',
    jsonb_build_object(
        'action', 'drop_public_business_tables',
        'tables_dropped', ARRAY[
            'public.accepted_financial_facts',
            'public.catalyst_events',
            'public.company_profiles',
            'public.connector_runs',
            'public.financial_facts',
            'public.forecast_inputs',
            'public.ingestion_runs',
            'public.peer_metrics_snapshot',
            'public.price_history',
            'public.research_runs',
            'public.run_approvals',
            'public.run_artifacts',
            'public.run_audit_events',
            'public.run_budget_ledger',
            'public.run_steps',
            'public.source_versions'
        ],
        'catalyst_events_migrated_to', 'fact.catalyst_events',
        'price_history_preserved_in', 'fact.price_history'
    )
);

-- Record migration
INSERT INTO public.schema_migrations (version)
VALUES ('026_drop_public_business_tables')
ON CONFLICT DO NOTHING;

COMMIT;
