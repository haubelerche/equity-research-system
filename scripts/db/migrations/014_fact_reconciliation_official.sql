-- Migration: 014_fact_reconciliation_official.sql
-- Purpose: Source-Provenance Rebuild, Phase 4 — extend fact.fact_reconciliation to
-- record API-vs-official comparisons (the plan's "fact_reconciliation_results").
--
-- The table already records observation-winner selection. These additive columns let it
-- also store the api_value / official_value / diff / status of an API-vs-official check.
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='api_value') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN api_value NUMERIC;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='official_value') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN official_value NUMERIC;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='diff_abs') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN diff_abs NUMERIC;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='diff_pct') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN diff_pct NUMERIC;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='reconciliation_status') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN reconciliation_status VARCHAR(30)
            CHECK (reconciliation_status IS NULL OR reconciliation_status IN (
                'matched_official', 'mismatch', 'missing_official',
                'missing_api', 'manual_review_required', 'manual_reviewed'
            ));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='official_document_id') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN official_document_id BIGINT
            REFERENCES ingest.official_documents(official_document_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='acquisition_source_id') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN acquisition_source_id VARCHAR(64)
            REFERENCES ingest.sources(source_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='fact_reconciliation' AND column_name='tolerance_pct') THEN
        ALTER TABLE fact.fact_reconciliation ADD COLUMN tolerance_pct NUMERIC DEFAULT 0.5;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_fact_reconciliation_status
    ON fact.fact_reconciliation(reconciliation_status, ticker);
