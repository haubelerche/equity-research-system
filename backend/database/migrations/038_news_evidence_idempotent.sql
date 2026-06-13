-- Migration: 038_news_evidence_idempotent.sql
-- Purpose: Make news evidence storage idempotent so repeated (cron) collection runs
-- for the same ticker do not duplicate identical claims (report-quality plan, 2026-06-13).
--
-- Before this, save_evidence did a plain INSERT, so re-running a ticker's collection
-- re-inserted every claim. A unique index on (article_id, md5(claim)) lets save_evidence
-- use ON CONFLICT DO NOTHING — same article + same claim text is stored once.
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE UNIQUE INDEX IF NOT EXISTS uq_news_evidence_article_claim
    ON news.extracted_evidence (article_id, md5(claim));

COMMENT ON INDEX news.uq_news_evidence_article_claim IS
    'Idempotency guard: one evidence row per (article, claim text). Lets repeated '
    'collection runs use INSERT ... ON CONFLICT DO NOTHING.';

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_038',
    'news.extracted_evidence',
    jsonb_build_object('migration', '038_news_evidence_idempotent')
);
