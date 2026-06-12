-- Migration 031: add pgvector support to ingest.document_chunks.
--
-- Supabase/PostgreSQL stores embeddings in the same document_chunks table
-- that already holds chunk text and citation metadata.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE ingest.document_chunks
    ADD COLUMN IF NOT EXISTS content_hash CHAR(64),
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ingest_document_chunks_source_doc_chunk
    ON ingest.document_chunks(source_doc_id, chunk_index)
    WHERE source_doc_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ingest_document_chunks_embedding
    ON ingest.document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_031',
    'ingest.document_chunks',
    jsonb_build_object('migration', '031_pgvector_document_chunks')
);
