-- Migration: 002_ingest_schema.sql
-- Purpose: Source registry, raw payloads, document chunks, connector runs, validation issues.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.
-- Key design decisions:
--   - No global UNIQUE(checksum); use UNIQUE(logical_id, source_uri, checksum).
--   - ingest.document_chunks lives here, NOT in research.
--   - ingest.raw_payloads stores raw bytes metadata before normalization.

CREATE SCHEMA IF NOT EXISTS ingest;

CREATE TABLE IF NOT EXISTS ingest.sources (
    source_id         VARCHAR(64)  PRIMARY KEY,
    logical_id        VARCHAR(120) NOT NULL,
    ticker            VARCHAR(10)  REFERENCES ref.companies(ticker),
    source_type       VARCHAR(50)  NOT NULL CHECK (
        source_type IN (
            'vnstock_financial', 'vnstock_price', 'vnstock_company',
            'financial_statement', 'annual_report', 'disclosure', 'news',
            'regulatory', 'regulatory_filing', 'tender', 'bidding',
            'industry_report', 'market_reference', 'manual'
        )
    ),
    source_uri        TEXT         NOT NULL,
    source_title      TEXT,
    published_at      TIMESTAMPTZ,
    fiscal_year       SMALLINT,
    fiscal_period     VARCHAR(4)   CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
    reliability_tier  SMALLINT     NOT NULL DEFAULT 2 CHECK (reliability_tier BETWEEN 1 AND 3),
    connector_version VARCHAR(40)  NOT NULL,
    checksum          CHAR(64)     NOT NULL,
    raw_path          TEXT,
    metadata_json     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (logical_id, source_uri, checksum)
);

CREATE INDEX IF NOT EXISTS idx_ingest_sources_ticker
    ON ingest.sources(ticker, ingested_at DESC);

CREATE INDEX IF NOT EXISTS idx_ingest_sources_checksum
    ON ingest.sources(checksum);

CREATE INDEX IF NOT EXISTS idx_ingest_sources_type_year
    ON ingest.sources(source_type, fiscal_year);

-- Raw payload storage: one row per connector fetch, before normalization.
CREATE TABLE IF NOT EXISTS ingest.raw_payloads (
    id           BIGSERIAL    PRIMARY KEY,
    source_id    VARCHAR(64)  NOT NULL REFERENCES ingest.sources(source_id) ON DELETE CASCADE,
    content_type VARCHAR(80)  NOT NULL,
    payload_json JSONB,
    payload_text TEXT,
    storage_path TEXT,
    checksum     CHAR(64)     NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingest_raw_payloads_source
    ON ingest.raw_payloads(source_id);

CREATE INDEX IF NOT EXISTS idx_ingest_raw_payloads_checksum
    ON ingest.raw_payloads(checksum);

-- Document chunks for full-text retrieval and citation.
-- Lives in ingest (source-derived, reusable across research runs).
CREATE TABLE IF NOT EXISTS ingest.document_chunks (
    chunk_id      BIGSERIAL    PRIMARY KEY,
    source_id     VARCHAR(64)  NOT NULL REFERENCES ingest.sources(source_id) ON DELETE CASCADE,
    ticker        VARCHAR(10)  REFERENCES ref.companies(ticker),
    chunk_index   INTEGER      NOT NULL,
    section_title TEXT,
    chunk_text    TEXT         NOT NULL,
    fiscal_year   SMALLINT,
    language      VARCHAR(10)  NOT NULL DEFAULT 'vi',
    metadata_json JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_ingest_document_chunks_ticker
    ON ingest.document_chunks(ticker);

CREATE INDEX IF NOT EXISTS idx_ingest_document_chunks_metadata
    ON ingest.document_chunks USING GIN(metadata_json);

CREATE INDEX IF NOT EXISTS idx_ingest_document_chunks_fts
    ON ingest.document_chunks USING GIN(to_tsvector('simple', chunk_text));

-- Per-connector ingestion run tracking.
CREATE TABLE IF NOT EXISTS ingest.connector_runs (
    run_id          VARCHAR(64)  PRIMARY KEY,
    ticker          VARCHAR(10)  REFERENCES ref.companies(ticker),
    connector_name  VARCHAR(100) NOT NULL,
    status          VARCHAR(20)  NOT NULL CHECK (
        status IN ('running', 'completed', 'failed', 'partial', 'skipped')
    ),
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    sources_created INTEGER      NOT NULL DEFAULT 0,
    error_message   TEXT,
    stats_json      JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ingest_connector_runs_ticker
    ON ingest.connector_runs(ticker, started_at DESC);

-- Validation issues found during ingestion or normalization.
CREATE TABLE IF NOT EXISTS ingest.validation_issues (
    id               BIGSERIAL    PRIMARY KEY,
    source_id        VARCHAR(64)  REFERENCES ingest.sources(source_id) ON DELETE CASCADE,
    connector_run_id VARCHAR(64)  REFERENCES ingest.connector_runs(run_id),
    issue_type       VARCHAR(50)  NOT NULL CHECK (
        issue_type IN (
            'missing_value', 'out_of_range', 'failed_checksum', 'duplicate',
            'taxonomy_mismatch', 'stale_data', 'parse_error', 'unit_mismatch', 'other'
        )
    ),
    field_name       TEXT,
    description      TEXT         NOT NULL,
    severity         VARCHAR(10)  NOT NULL CHECK (severity IN ('blocking', 'error', 'warning', 'info')),
    details_json     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingest_validation_issues_source
    ON ingest.validation_issues(source_id);

-- Raw company snapshot JSON from vnstock (canonical identity lives in ref.companies).
CREATE TABLE IF NOT EXISTS ingest.company_snapshots (
    id                BIGSERIAL    PRIMARY KEY,
    ticker            VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    source_id         VARCHAR(64)  REFERENCES ingest.sources(source_id),
    overview_json     JSONB,
    shareholders_json JSONB,
    officers_json     JSONB,
    synced_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingest_company_snapshots_ticker
    ON ingest.company_snapshots(ticker, synced_at DESC);
