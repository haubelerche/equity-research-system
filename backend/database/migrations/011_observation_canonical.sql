-- Migration: 011_observation_canonical.sql
-- Purpose: Phase 2 of Data Trust Layer — observation/canonical fact model.
--
--   1. fact.fact_observations — all candidate values per (ticker, period, metric)
--      from every source, before winner selection.
--   2. fact.canonical_facts   — selected winner per (ticker, period, metric) with
--      full lineage back to the observation that was chosen.
--   3. fact.fact_reconciliation — conflict records when 2+ sources disagree.
--   4. Backfill existing fact.financial_facts data into the new tables.
--   5. Create fact.financial_facts_legacy view for backward compat.
--
-- Migration strategy (Correction 6):
--   DO NOT replace fact.financial_facts. Create new tables in parallel, backfill,
--   then switch build_facts.py to read from canonical_facts. Old table deprecated
--   only after E2E diff passes.
--
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

-- ── 1. fact.fact_observations ─────────────────────────────────────────────────
-- One row per (ticker, period, metric, source_id) — all candidates, no winner
-- selection yet.  The canonical winner is chosen in fact.canonical_facts.

CREATE TABLE IF NOT EXISTS fact.fact_observations (
    observation_id      BIGSERIAL       PRIMARY KEY,
    ticker              VARCHAR(10)     NOT NULL REFERENCES ref.companies(ticker),
    period              VARCHAR(10)     NOT NULL
        CHECK (period ~ '^[0-9]{4}(FY|Q[1-4])$'),
    period_type         VARCHAR(5)      NOT NULL DEFAULT 'FY'
        CHECK (period_type IN ('FY', 'Q')),
    metric              VARCHAR(100)    NOT NULL REFERENCES ref.line_items(line_item_code),
    value               NUMERIC         NOT NULL,
    unit                VARCHAR(40)     NOT NULL,
    currency            CHAR(3)         NOT NULL DEFAULT 'VND',
    source_id           VARCHAR(64)     REFERENCES ingest.sources(source_id),
    raw_payload_id      BIGINT          REFERENCES ingest.raw_payloads(id),
    parser_run_id       BIGINT          REFERENCES ingest.parser_runs(parser_run_id),
    confidence          NUMERIC(5,4)    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    source_tier         SMALLINT        NOT NULL DEFAULT 3
        CHECK (source_tier BETWEEN 0 AND 3),
    extraction_method   VARCHAR(40)     DEFAULT 'api_structured'
        CHECK (extraction_method IN ('api_structured', 'pdf_ocr', 'manual', 'csv', 'legacy_api')),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, period, metric, source_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_obs_ticker_period
    ON fact.fact_observations(ticker, period);

CREATE INDEX IF NOT EXISTS idx_fact_obs_metric
    ON fact.fact_observations(ticker, metric, period);

CREATE INDEX IF NOT EXISTS idx_fact_obs_source_tier
    ON fact.fact_observations(source_tier, ticker);

-- ── 2. fact.canonical_facts ───────────────────────────────────────────────────
-- One selected winner per (ticker, period, metric, canonical_version).
-- canonical_version allows multiple valuation snapshots to coexist.

CREATE TABLE IF NOT EXISTS fact.canonical_facts (
    fact_id                 VARCHAR(64)     PRIMARY KEY,
    ticker                  VARCHAR(10)     NOT NULL REFERENCES ref.companies(ticker),
    period                  VARCHAR(10)     NOT NULL
        CHECK (period ~ '^[0-9]{4}(FY|Q[1-4])$'),
    period_type             VARCHAR(5)      NOT NULL DEFAULT 'FY'
        CHECK (period_type IN ('FY', 'Q')),
    canonical_version       VARCHAR(40)     NOT NULL,
    metric                  VARCHAR(100)    NOT NULL REFERENCES ref.line_items(line_item_code),
    value                   NUMERIC         NOT NULL,
    unit                    VARCHAR(40)     NOT NULL,
    currency                CHAR(3)         NOT NULL DEFAULT 'VND',
    selected_observation_id BIGINT          REFERENCES fact.fact_observations(observation_id),
    selection_policy        VARCHAR(80)     DEFAULT 'highest_tier_then_confidence',
    confidence              NUMERIC(5,4)    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    quality_status          VARCHAR(20)     NOT NULL DEFAULT 'accepted'
        CHECK (quality_status IN ('accepted', 'needs_review', 'rejected')),
    source_tier             SMALLINT        -- denormalized from selected observation for fast gate checks
        CHECK (source_tier IS NULL OR source_tier BETWEEN 0 AND 3),
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, period, metric, canonical_version)
);

CREATE INDEX IF NOT EXISTS idx_canonical_facts_ticker_period
    ON fact.canonical_facts(ticker, period, canonical_version);

CREATE INDEX IF NOT EXISTS idx_canonical_facts_metric
    ON fact.canonical_facts(ticker, metric);

CREATE INDEX IF NOT EXISTS idx_canonical_facts_source_tier
    ON fact.canonical_facts(source_tier, ticker);

-- ── 3. fact.fact_reconciliation ───────────────────────────────────────────────
-- One row per (ticker, period, metric) whenever 2+ observations exist for the
-- same metric/period.  Tracks which candidates competed and why one was chosen.

CREATE TABLE IF NOT EXISTS fact.fact_reconciliation (
    reconciliation_id           BIGSERIAL   PRIMARY KEY,
    ticker                      VARCHAR(10) NOT NULL REFERENCES ref.companies(ticker),
    period                      VARCHAR(10) NOT NULL
        CHECK (period ~ '^[0-9]{4}(FY|Q[1-4])$'),
    metric                      VARCHAR(100) NOT NULL REFERENCES ref.line_items(line_item_code),
    candidate_observation_ids   BIGINT[]    NOT NULL,
    selected_observation_id     BIGINT      REFERENCES fact.fact_observations(observation_id),
    variance_pct                NUMERIC(8,4),
    decision_reason             TEXT,
    requires_review             BOOLEAN     NOT NULL DEFAULT FALSE,
    review_status               VARCHAR(20) DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected')),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, period, metric)
);

CREATE INDEX IF NOT EXISTS idx_fact_reconciliation_review
    ON fact.fact_reconciliation(requires_review, ticker)
    WHERE requires_review = TRUE;

-- ── 4. Backfill existing data ─────────────────────────────────────────────────
-- Populate fact_observations from current fact.financial_facts.
-- All legacy rows get source_tier from the joined ingest.sources row (or 3).
-- extraction_method = 'legacy_api' marks these as pre-Phase-2 data.

INSERT INTO fact.fact_observations (
    ticker, period, period_type, metric, value, unit, currency,
    source_id, confidence, source_tier, extraction_method, created_at
)
SELECT
    f.ticker,
    CONCAT(f.fiscal_year::TEXT, f.fiscal_period)           AS period,
    CASE WHEN f.fiscal_period = 'FY' THEN 'FY' ELSE 'Q' END AS period_type,
    f.line_item_code                                        AS metric,
    f.value,
    f.unit,
    f.currency,
    f.source_id,
    f.confidence,
    COALESCE(s.source_tier, 3)                              AS source_tier,
    'legacy_api'                                            AS extraction_method,
    f.ingested_at                                           AS created_at
FROM fact.financial_facts f
LEFT JOIN ingest.sources s ON f.source_id = s.source_id
ON CONFLICT (ticker, period, metric, source_id) DO NOTHING;

-- Populate canonical_facts from accepted FY facts (the valuation-safe view).
-- canonical_version = 'v_legacy' marks these as pre-Phase-2 baselines.
-- fact_id uses md5 of the natural key to be deterministic.

INSERT INTO fact.canonical_facts (
    fact_id, ticker, period, period_type, canonical_version,
    metric, value, unit, currency,
    selected_observation_id, selection_policy, confidence,
    source_tier, quality_status, created_at, updated_at
)
SELECT
    encode(digest(
        f.ticker || '|' || f.fiscal_year::TEXT || 'FY|' || f.line_item_code || '|v_legacy',
        'sha256'
    ), 'hex')                                               AS fact_id,
    f.ticker,
    CONCAT(f.fiscal_year::TEXT, 'FY')                       AS period,
    'FY'                                                    AS period_type,
    'v_legacy'                                              AS canonical_version,
    f.line_item_code                                        AS metric,
    f.value,
    f.unit,
    f.currency,
    obs.observation_id                                      AS selected_observation_id,
    'legacy_highest_confidence'                             AS selection_policy,
    f.confidence,
    COALESCE(s.source_tier, 3)                              AS source_tier,
    'accepted'                                              AS quality_status,
    f.ingested_at                                           AS created_at,
    f.ingested_at                                           AS updated_at
FROM fact.financial_facts f
LEFT JOIN ingest.sources s ON f.source_id = s.source_id
LEFT JOIN fact.fact_observations obs
    ON  obs.ticker    = f.ticker
    AND obs.period    = CONCAT(f.fiscal_year::TEXT, f.fiscal_period)
    AND obs.metric    = f.line_item_code
    AND obs.source_id = f.source_id
WHERE f.validation_status = 'accepted'
  AND f.fiscal_period     = 'FY'
  AND f.is_current        = TRUE
ON CONFLICT (ticker, period, metric, canonical_version) DO NOTHING;

-- ── 5. Backward-compat view ───────────────────────────────────────────────────
-- Allows any existing code that still reads fact.financial_facts to continue
-- working after the table is eventually deprecated.

CREATE OR REPLACE VIEW fact.financial_facts_legacy AS
SELECT * FROM fact.financial_facts;

COMMENT ON VIEW fact.financial_facts_legacy IS
    'Backward-compat alias for fact.financial_facts. '
    'New code must read from fact.canonical_facts or fact.fact_observations. '
    'This view will be dropped once all callers are migrated.';
