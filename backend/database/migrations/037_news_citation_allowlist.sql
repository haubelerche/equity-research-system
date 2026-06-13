-- Migration: 037_news_citation_allowlist.sql
-- Purpose: Separate automated DISCOVERY from CITATION (report-quality plan, 2026-06-13).
--
-- Automated discovery stays restricted to the four official sources, but a human-vetted
-- article (manual_url_ingest) may be cited from a wider set of reputable Vietnamese
-- financial outlets and official company / exchange sites. This migration widens the
-- defense-in-depth CHECK on news.raw_articles.source_domain to that citation allowlist.
--
-- The single source of truth for the allowlist remains the code (backend/news/types.py
-- CITATION_ALLOWED_DOMAINS); this CHECK must stay in sync with it.
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

ALTER TABLE news.raw_articles
    DROP CONSTRAINT IF EXISTS raw_articles_source_domain_check;

ALTER TABLE news.raw_articles
    ADD CONSTRAINT raw_articles_source_domain_check
    CHECK (source_domain IN (
        -- Automated-discovery sources (original whitelist)
        'vnexpress.net',
        'vneconomy.vn',
        'cafef.vn',
        'vietstock.vn',
        -- Reputable financial media (citation-only)
        'tinnhanhchungkhoan.vn',
        'mekongasean.vn',
        'baodautu.vn',
        -- Official company / exchange / regulator (citation-only)
        'dhgpharma.com.vn',
        'hsx.vn',
        'hnx.vn'
    ));

COMMENT ON COLUMN news.raw_articles.source_domain IS
    'DB-constrained to the citation allowlist (CITATION_ALLOWED_DOMAINS). Automated '
    'discovery uses the narrower ALLOWED_DOMAINS; manual ingest may use the wider set.';

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_037',
    'news.raw_articles',
    jsonb_build_object('migration', '037_news_citation_allowlist')
);
