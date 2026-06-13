-- Migration: 040_news_article_content_hash.sql
-- Purpose: Cross-URL article dedup via content hash + canonical URL (report-quality plan §5).
--
-- The same article often appears at several URLs (tracking params, mobile host). A content
-- fingerprint + canonical URL let save_raw_article recognize "same article" and keep one row.
-- Additive columns on the existing news.raw_articles (source_url stays UNIQUE).
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

ALTER TABLE news.raw_articles ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32);
ALTER TABLE news.raw_articles ADD COLUMN IF NOT EXISTS canonical_url TEXT;

-- Backfill content_hash for existing rows (whitespace-collapsed md5 of raw_text),
-- approximating backend/news/dedup.content_fingerprint.
UPDATE news.raw_articles
   SET content_hash = md5(trim(regexp_replace(COALESCE(raw_text, ''), '\s+', ' ', 'g')))
 WHERE content_hash IS NULL;

CREATE INDEX IF NOT EXISTS idx_news_articles_content_hash
    ON news.raw_articles(content_hash);

COMMENT ON COLUMN news.raw_articles.content_hash IS
    'md5 of whitespace-collapsed raw_text; used to dedup the same article across URLs.';
COMMENT ON COLUMN news.raw_articles.canonical_url IS
    'Tracking-param/fragment-stripped, host-normalized URL (see news.dedup.canonicalize_url).';

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_040',
    'news.raw_articles',
    jsonb_build_object('migration', '040_news_article_content_hash')
);
