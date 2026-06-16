-- backend/database/migrations/045_agm_resolutions.sql
-- Forward-looking internal drivers extracted from AGM (ĐHCĐ) decision PDFs
-- (backend/documents/agm_extractor). Distinct from research.company_evidence
-- (migration 044, historical evidence from the annual report): these are the
-- shareholder-approved 2026 plans — what the board may invest/borrow/distribute and
-- which products/R&D to focus on — used as PRIORITY forecast drivers (with page
-- provenance, never a fake analyst-approved flag).
-- One row per (ticker, meeting_year): the full two-layer agm_pack as JSONB plus
-- source-document provenance (file names, sha256, text/ocr kind, page count).
-- Additive — historical vnstock/PDF facts are untouched. Idempotent.
CREATE TABLE IF NOT EXISTS research.agm_resolutions (
    ticker          TEXT        NOT NULL,
    meeting_year    SMALLINT    NOT NULL,
    agm_pack        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    source_docs     JSONB       NOT NULL DEFAULT '[]'::jsonb,
    model           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, meeting_year)
);

CREATE INDEX IF NOT EXISTS idx_agm_resolutions_ticker
    ON research.agm_resolutions (ticker, meeting_year DESC);
