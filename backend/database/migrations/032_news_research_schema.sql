-- Migration: 032_news_research_schema.sql
-- Purpose: Whitelisted news collection + editor warehouse (NEWS_CRAWLER_EDITOR_AGENT_PLAN §5).
--
-- A controlled news-research subsystem that collects information ONLY from the four
-- approved official sources and feeds verified evidence to the news Editor agent. It is
-- isolated in its own `news` schema so it never mixes with the canonical financial-fact
-- layer (`fact.*`) or the official-document verification layer (`ingest.*`).
--
-- Defense-in-depth: the whitelist is enforced in code (backend/news/whitelist.py) AND as a
-- DB CHECK on news.raw_articles.source_domain — a non-whitelisted article physically cannot
-- be stored (plan §4.3 mandatory rule).
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS news;

-- ── 1. news.research_runs ─────────────────────────────────────────────────────
-- One row per news-research request. research_run_id may equal a harness run_id when
-- the news flow is launched from a full research run, or a standalone deterministic id.

CREATE TABLE IF NOT EXISTS news.research_runs (
    research_run_id   VARCHAR(64)   PRIMARY KEY,
    user_id           VARCHAR(64),
    topic             TEXT          NOT NULL,
    ticker            VARCHAR(10),
    company_name      TEXT,
    query             TEXT,
    keywords          JSONB         NOT NULL DEFAULT '[]'::jsonb,
    allowed_domains   JSONB         NOT NULL,
    status            VARCHAR(20)   NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'needs_review')),
    started_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    finished_at       TIMESTAMPTZ,
    error_message     TEXT
);

CREATE INDEX IF NOT EXISTS idx_news_runs_ticker
    ON news.research_runs(ticker);

COMMENT ON TABLE news.research_runs IS
    'One row per whitelisted news-research request and its execution history.';

-- ── 2. news.raw_articles ──────────────────────────────────────────────────────
-- Crawled + extracted articles. source_domain is whitelist-constrained at the DB layer.

CREATE TABLE IF NOT EXISTS news.raw_articles (
    article_id        BIGSERIAL     PRIMARY KEY,
    source_name       TEXT          NOT NULL,
    source_domain     VARCHAR(64)   NOT NULL
        CHECK (source_domain IN (
            'vnexpress.net',
            'vneconomy.vn',
            'cafef.vn',
            'vietstock.vn'
        )),
    source_url        TEXT          NOT NULL UNIQUE,
    title             TEXT,
    summary           TEXT,
    published_at      TIMESTAMPTZ,
    accessed_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    raw_text          TEXT,
    raw_html_path     TEXT,
    discovery_method  VARCHAR(20),
    extraction_method VARCHAR(20),
    crawl_status      VARCHAR(20)   NOT NULL DEFAULT 'success'
        CHECK (crawl_status IN ('success', 'failed', 'skipped')),
    error_message     TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_articles_domain
    ON news.raw_articles(source_domain);

CREATE INDEX IF NOT EXISTS idx_news_articles_published_at
    ON news.raw_articles(published_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_news_articles_title_fts
    ON news.raw_articles USING gin(to_tsvector('simple', COALESCE(title, '')));

CREATE INDEX IF NOT EXISTS idx_news_articles_text_fts
    ON news.raw_articles USING gin(to_tsvector('simple', COALESCE(raw_text, '')));

COMMENT ON TABLE news.raw_articles IS
    'Crawled + extracted whitelisted news articles. source_domain is DB-constrained to the '
    'four approved domains (defense-in-depth for the code-level whitelist gate).';

-- ── 3. news.extracted_evidence ────────────────────────────────────────────────
-- Factual claims extracted from articles. This is the table the Editor agent reads from.
-- source_* are denormalized from the parent article so an evidence packet is self-contained.

CREATE TABLE IF NOT EXISTS news.extracted_evidence (
    evidence_id       BIGSERIAL     PRIMARY KEY,
    article_id        BIGINT        NOT NULL
                        REFERENCES news.raw_articles(article_id) ON DELETE CASCADE,
    topic             TEXT,
    ticker            VARCHAR(10),
    company_name      TEXT,
    claim             TEXT          NOT NULL,
    evidence_text     TEXT          NOT NULL,
    evidence_type     VARCHAR(40),
    source_name       TEXT          NOT NULL,
    source_domain     VARCHAR(64)   NOT NULL,
    source_url        TEXT          NOT NULL,
    published_at      TIMESTAMPTZ,
    accessed_at       TIMESTAMPTZ,
    confidence        VARCHAR(10)   NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('low', 'medium', 'high')),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_evidence_ticker
    ON news.extracted_evidence(ticker);

CREATE INDEX IF NOT EXISTS idx_news_evidence_topic
    ON news.extracted_evidence(topic);

CREATE INDEX IF NOT EXISTS idx_news_evidence_article
    ON news.extracted_evidence(article_id);

CREATE INDEX IF NOT EXISTS idx_news_evidence_published_at
    ON news.extracted_evidence(published_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_news_evidence_claim_fts
    ON news.extracted_evidence
    USING gin(to_tsvector('simple', COALESCE(claim, '') || ' ' || COALESCE(evidence_text, '')));

COMMENT ON TABLE news.extracted_evidence IS
    'Factual claims extracted from whitelisted articles, each with supporting evidence_text '
    'and source provenance. The news Editor agent may ONLY synthesize from rows in this table.';

-- ── 4. news.research_run_articles ─────────────────────────────────────────────
-- Links a research run to the articles considered/selected during that run.

CREATE TABLE IF NOT EXISTS news.research_run_articles (
    id                BIGSERIAL     PRIMARY KEY,
    research_run_id   VARCHAR(64)   NOT NULL
                        REFERENCES news.research_runs(research_run_id) ON DELETE CASCADE,
    article_id        BIGINT        NOT NULL
                        REFERENCES news.raw_articles(article_id) ON DELETE CASCADE,
    relevance_score   NUMERIC,
    selected          BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (research_run_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_news_run_articles_run
    ON news.research_run_articles(research_run_id);

COMMENT ON TABLE news.research_run_articles IS
    'Junction table: which articles a given news-research run discovered and selected.';

-- ── 5. news.editor_outputs ────────────────────────────────────────────────────
-- Generated editorial outputs (the synthesized, citation-validated report).

CREATE TABLE IF NOT EXISTS news.editor_outputs (
    id                BIGSERIAL     PRIMARY KEY,
    research_run_id   VARCHAR(64)   NOT NULL
                        REFERENCES news.research_runs(research_run_id) ON DELETE CASCADE,
    title             TEXT,
    report_markdown   TEXT          NOT NULL,
    citation_count    INTEGER       NOT NULL DEFAULT 0,
    status            VARCHAR(20)   NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'validated', 'published', 'rejected')),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_editor_outputs_run
    ON news.editor_outputs(research_run_id);

COMMENT ON TABLE news.editor_outputs IS
    'Editor-agent synthesized news reports. A row reaches status=validated only after the '
    'code-based citation validator passes (every cited URL is whitelisted and in-evidence).';

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_032',
    'news.research_runs',
    jsonb_build_object('migration', '032_news_research_schema')
);
