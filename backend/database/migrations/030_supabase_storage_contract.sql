-- Supabase Storage contract: PostgreSQL stores metadata and object references only.

ALTER TABLE ingest.source_documents
    ADD COLUMN IF NOT EXISTS storage_bucket TEXT,
    ADD COLUMN IF NOT EXISTS storage_path TEXT,
    ADD COLUMN IF NOT EXISTS content_type TEXT,
    ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT,
    ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ;

ALTER TABLE ingest.source_documents ALTER COLUMN storage_path DROP NOT NULL;
UPDATE ingest.source_documents SET storage_path = NULL WHERE storage_bucket IS NULL;

ALTER TABLE ingest.source_documents
    DROP COLUMN IF EXISTS local_path;

ALTER TABLE research.run_artifacts
    ADD COLUMN IF NOT EXISTS storage_bucket TEXT,
    ADD COLUMN IF NOT EXISTS content_type TEXT,
    ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT;

ALTER TABLE research.run_artifacts ALTER COLUMN storage_path DROP NOT NULL;
UPDATE research.run_artifacts SET storage_path = NULL WHERE storage_bucket IS NULL;

ALTER TABLE ingest.source_documents
    ADD CONSTRAINT chk_source_documents_storage_bucket
    CHECK (storage_bucket IS NULL OR storage_bucket = 'sources'),
    ADD CONSTRAINT chk_source_documents_storage_reference
    CHECK ((storage_bucket IS NULL) = (storage_path IS NULL));

ALTER TABLE research.run_artifacts
    ADD CONSTRAINT chk_run_artifacts_storage_bucket
    CHECK (storage_bucket IS NULL OR storage_bucket = 'runs'),
    ADD CONSTRAINT chk_run_artifacts_storage_reference
    CHECK ((storage_bucket IS NULL) = (storage_path IS NULL));

CREATE INDEX IF NOT EXISTS idx_source_documents_storage_reference
    ON ingest.source_documents(storage_bucket, storage_path);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_storage_reference
    ON research.run_artifacts(storage_bucket, storage_path);

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_030',
    'ingest.source_documents,research.run_artifacts',
    jsonb_build_object('migration', '030_supabase_storage_contract')
);
