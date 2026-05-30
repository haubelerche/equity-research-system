-- Migration 009 — Deduplicate ingest.sources for vnstock_company (listing_metadata) sources
--
-- Problem: vnstock_company sources accumulate one row per ingest run because the
-- company profile payload changes slightly (new fields, timestamps) → different
-- checksum → bypasses the (logical_id, source_uri, checksum) unique constraint.
--
-- Safety checks performed before this migration:
--   - vnstock_company candidate rows checked against ALL FK tables: no references found
--   - news sources: NOT cleaned here — referenced by fact.catalyst_events
--   - financial_statement: NOT touched — referenced by fact.financial_facts
--   - vnstock_price: NOT touched — referenced by fact.price_history
--
-- Keeps the LATEST row per (ticker, logical_id, source_type='vnstock_company').
-- Idempotent: safe to re-apply.

BEGIN;

DELETE FROM ingest.sources
WHERE source_id IN (
    SELECT source_id
    FROM (
        SELECT source_id,
               ROW_NUMBER() OVER (
                   PARTITION BY ticker, logical_id, source_type
                   ORDER BY ingested_at DESC
               ) AS rn
        FROM ingest.sources
        WHERE source_type = 'vnstock_company'
    ) ranked
    WHERE rn > 1
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'ingest'
          AND tablename  = 'sources'
          AND indexname  = 'sources_vnstock_company_dedup_idx'
    ) THEN
        CREATE UNIQUE INDEX sources_vnstock_company_dedup_idx
            ON ingest.sources (ticker, logical_id, source_type)
            WHERE source_type = 'vnstock_company';
    END IF;
END $$;

COMMIT;
