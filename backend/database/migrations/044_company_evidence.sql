-- backend/database/migrations/044_company_evidence.sql
-- Qualitative company evidence extracted offline from annual-report PDFs
-- (backend/documents/llm_evidence_extractor). The linear pipeline collects
-- financial facts but no qualitative evidence, so build_company_research_pack
-- produced an empty pack and REPORT_QUALITY / PACKAGE / SENIOR_CRITIC gates failed.
-- One row per (ticker, fiscal_year): the full evidence pack as JSONB, sourced from
-- the official PDF (additive — vnstock/financials are untouched). The run loads the
-- latest year's pack into state.artifacts["evidence_pack"].
-- Idempotent.
CREATE TABLE IF NOT EXISTS research.company_evidence (
    ticker          TEXT        NOT NULL,
    fiscal_year     SMALLINT    NOT NULL,
    evidence_pack   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    source_doc_id   TEXT,
    model           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_company_evidence_ticker
    ON research.company_evidence (ticker, fiscal_year DESC);
