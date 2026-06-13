-- Migration: 039_news_ticker_sources.sql
-- Purpose: Per-ticker news source registry (report-quality plan §4, 2026-06-13).
--
-- Discovery is ticker-scoped: each company has one or more news-channel URLs (CafeF event
-- index, VietStock ticker page, ...). This registry persists those sources with a priority,
-- an enable/disable flag for cron, and last-checked/last-success tracking for observability
-- as coverage scales from the MVP pharma set to the full universe.
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE TABLE IF NOT EXISTS news.ticker_news_sources (
    id               BIGSERIAL    PRIMARY KEY,
    ticker           VARCHAR(10)  NOT NULL,
    source_name      TEXT         NOT NULL,
    source_domain    VARCHAR(64)  NOT NULL,
    source_type      VARCHAR(20)  NOT NULL DEFAULT 'media'
        CHECK (source_type IN ('official_company', 'exchange', 'regulator', 'media', 'aggregator', 'manual')),
    source_url       TEXT         NOT NULL,
    priority         INT          NOT NULL DEFAULT 50,
    is_cron_enabled  BOOLEAN      NOT NULL DEFAULT TRUE,
    last_checked_at  TIMESTAMPTZ,
    last_success_at  TIMESTAMPTZ,
    failure_count    INT          NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, source_url)
);

CREATE INDEX IF NOT EXISTS idx_news_ticker_sources_ticker
    ON news.ticker_news_sources(ticker);

CREATE INDEX IF NOT EXISTS idx_news_ticker_sources_cron
    ON news.ticker_news_sources(ticker, priority DESC)
    WHERE is_cron_enabled;

COMMENT ON TABLE news.ticker_news_sources IS
    'Per-ticker news source registry (CafeF/VietStock channels). priority orders discovery; '
    'is_cron_enabled gates scheduled collection; last_* columns track health.';

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_039',
    'news.ticker_news_sources',
    jsonb_build_object('migration', '039_news_ticker_sources')
);
