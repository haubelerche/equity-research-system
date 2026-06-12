-- Migration 028: create ingest.document_chunks for evidence retrieval index.
--
-- ingest.document_chunks stores text chunks extracted from source documents
-- (official PDFs, OCR artifacts, synthetic fact summaries) so that
-- backend/retrieval.py can serve FTS evidence to the report pipeline.
--
-- FK references ingest.source_documents (not the removed ingest.sources).
-- chunk_index is 0-based page or paragraph offset within the source document.

CREATE TABLE IF NOT EXISTS ingest.document_chunks (
    chunk_id        BIGSERIAL       PRIMARY KEY,
    source_doc_id   VARCHAR(64)     NOT NULL
                        REFERENCES ingest.source_documents(source_doc_id)
                        ON DELETE CASCADE,
    ticker          VARCHAR(10)     NOT NULL REFERENCES ref.companies(ticker),
    chunk_index     INTEGER         NOT NULL,
    section_title   TEXT,
    chunk_text      TEXT            NOT NULL,
    fiscal_year     SMALLINT,
    language        CHAR(2)         NOT NULL DEFAULT 'vi',
    metadata_json   JSONB           NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (source_doc_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_ticker
    ON ingest.document_chunks(ticker, fiscal_year DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_source_doc
    ON ingest.document_chunks(source_doc_id);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_fts
    ON ingest.document_chunks
    USING gin(to_tsvector('simple', chunk_text));

COMMENT ON TABLE ingest.document_chunks IS
    'Text evidence chunks for FTS retrieval. '
    'Written by scripts/build_index.py, read by backend/retrieval.py. '
    'FK to ingest.source_documents (replaces old FK to ingest.sources).';

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_028',
    'ingest.document_chunks',
    jsonb_build_object('migration', '028_ingest_document_chunks')
);
