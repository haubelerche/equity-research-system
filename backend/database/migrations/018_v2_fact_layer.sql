-- Migration: 018_v2_fact_layer.sql
-- Purpose: Data Warehouse v2, Step 3 — create v2_fact schema.
-- Creates: canonical_facts (single production fact table), price_history, catalyst_events.
-- Backfills observations from legacy financial_facts, then promotes accepted ones to canonical_facts.
-- Does NOT drop any legacy table.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.

CREATE SCHEMA IF NOT EXISTS v2_fact;

-- ── v2_fact.canonical_facts ───────────────────────────────────────────────────
-- THE single production source of truth for all validated financial facts.
-- Replaces both fact.financial_facts (legacy write target) and fact.canonical_facts (backfill).
-- Written ONLY by the fact_promotion module. Never by connectors or LLM.

CREATE TABLE IF NOT EXISTS v2_fact.canonical_facts (
    fact_id                 VARCHAR(64)     PRIMARY KEY,
    ticker                  VARCHAR(10)     NOT NULL REFERENCES v2_ref.companies(ticker),
    period                  VARCHAR(10)     NOT NULL
        CHECK (period ~ '^[0-9]{4}(FY|Q[1-4])$'),
    period_type             VARCHAR(5)      NOT NULL DEFAULT 'FY'
        CHECK (period_type IN ('FY', 'Q')),
    canonical_version       VARCHAR(40)     NOT NULL,
    metric                  VARCHAR(100)    NOT NULL REFERENCES v2_ref.line_items(line_item_code),
    value                   NUMERIC         NOT NULL,
    unit                    VARCHAR(40)     NOT NULL,
    currency                CHAR(3)         NOT NULL DEFAULT 'VND',
    -- Lineage: links back to the selected candidate observation
    selected_observation_id BIGINT          REFERENCES v2_ingest.observations(observation_id),
    selection_policy        VARCHAR(80)     NOT NULL DEFAULT 'highest_tier_then_confidence',
    confidence              NUMERIC(5,4)    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    quality_status          VARCHAR(20)     NOT NULL DEFAULT 'accepted'
        CHECK (quality_status IN ('accepted', 'needs_review', 'rejected')),
    source_tier             SMALLINT        CHECK (source_tier IS NULL OR source_tier BETWEEN 0 AND 3),
    -- Official document verification
    official_document_id    VARCHAR(64)     REFERENCES v2_ingest.source_documents(source_doc_id),
    reconciliation_status   VARCHAR(30)     NOT NULL DEFAULT 'missing_official'
        CHECK (reconciliation_status IN (
            'matched_official', 'mismatch', 'missing_official',
            'missing_api', 'manual_review_required', 'manual_reviewed'
        )),
    verified_by             VARCHAR(80),
    verified_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, period, metric, canonical_version),
    -- A fact cannot claim official verification without actually linking to an official document.
    CONSTRAINT chk_v2_verified_requires_official_doc
        CHECK (
            reconciliation_status NOT IN ('matched_official', 'manual_reviewed')
            OR official_document_id IS NOT NULL
        )
);

CREATE INDEX IF NOT EXISTS idx_v2_canonical_ticker_period
    ON v2_fact.canonical_facts(ticker, period, canonical_version);

CREATE INDEX IF NOT EXISTS idx_v2_canonical_metric
    ON v2_fact.canonical_facts(ticker, metric);

CREATE INDEX IF NOT EXISTS idx_v2_canonical_source_tier
    ON v2_fact.canonical_facts(source_tier, ticker);

CREATE INDEX IF NOT EXISTS idx_v2_canonical_reconciliation
    ON v2_fact.canonical_facts(reconciliation_status, ticker);

CREATE INDEX IF NOT EXISTS idx_v2_canonical_official_doc
    ON v2_fact.canonical_facts(official_document_id)
    WHERE official_document_id IS NOT NULL;

COMMENT ON TABLE v2_fact.canonical_facts IS
    'v2: THE production canonical fact table. '
    'Written only by fact_promotion.py. Never by connectors, LLM, or report modules. '
    'canonical_version=''v2_prod'' for live production data. '
    'All valuation and reporting must read from v2_fact.production_facts view.';

-- ── v2_fact.production_facts (view) ───────────────────────────────────────────
-- Valuation-safe subset: accepted FY facts with confidence ≥ 0.80.
-- All valuation and reporting code must read from this view, never directly from canonical_facts.

CREATE OR REPLACE VIEW v2_fact.production_facts AS
SELECT
    fact_id,
    ticker,
    period,
    period_type,
    canonical_version,
    metric,
    value,
    unit,
    currency,
    selected_observation_id,
    confidence,
    source_tier,
    official_document_id,
    reconciliation_status,
    created_at,
    updated_at
FROM v2_fact.canonical_facts
WHERE quality_status    = 'accepted'
  AND period_type       = 'FY'
  AND (confidence IS NULL OR confidence >= 0.80);

COMMENT ON VIEW v2_fact.production_facts IS
    'v2: Valuation-safe canonical facts. Accepted, FY, confidence >= 0.80. '
    'Valuation and reporting code must read from this view.';

-- ── v2_fact.price_history ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_fact.price_history (
    ticker         VARCHAR(10)  NOT NULL REFERENCES v2_ref.companies(ticker),
    trade_date     DATE         NOT NULL,
    open           NUMERIC,
    high           NUMERIC,
    low            NUMERIC,
    close          NUMERIC,
    adjusted_close NUMERIC,
    volume         BIGINT,
    traded_value   NUMERIC,
    market_cap     NUMERIC,
    source_doc_id  VARCHAR(64)  REFERENCES v2_ingest.source_documents(source_doc_id),
    ingested_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_v2_price_history_ticker_date
    ON v2_fact.price_history(ticker, trade_date DESC);

-- Migrate price history from legacy table.
INSERT INTO v2_fact.price_history (
    ticker, trade_date, open, high, low, close, adjusted_close,
    volume, traded_value, market_cap, ingested_at
)
SELECT
    ph.ticker, ph.trade_date, ph.open, ph.high, ph.low, ph.close, ph.adjusted_close,
    ph.volume, ph.traded_value, ph.market_cap, ph.ingested_at
FROM fact.price_history ph
WHERE ph.ticker IN (SELECT ticker FROM v2_ref.companies)
ON CONFLICT (ticker, trade_date) DO NOTHING;

-- ── v2_fact.catalyst_events ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS v2_fact.catalyst_events (
    event_id          VARCHAR(64)  PRIMARY KEY,
    ticker            VARCHAR(10)  REFERENCES v2_ref.companies(ticker),
    event_type        VARCHAR(50)  NOT NULL CHECK (
        event_type IN (
            'news', 'disclosure', 'regulatory', 'tender', 'bidding',
            'drug_registration', 'dividend', 'corporate_action', 'other'
        )
    ),
    title             TEXT         NOT NULL,
    summary           TEXT,
    occurred_at       TIMESTAMPTZ  NOT NULL,
    effective_date    DATE,
    materiality_hint  VARCHAR(10)  CHECK (materiality_hint IN ('high', 'medium', 'low', 'unknown')),
    causality_level   VARCHAR(40)  NOT NULL DEFAULT 'contextual_event' CHECK (
        causality_level IN (
            'contextual_event', 'potential_driver',
            'management_disclosed_driver', 'validated_driver'
        )
    ),
    source_doc_id     VARCHAR(64)  REFERENCES v2_ingest.source_documents(source_doc_id),
    source_url        TEXT,
    confidence        NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    validation_status VARCHAR(25)  NOT NULL CHECK (
        validation_status IN ('raw', 'validated', 'accepted', 'rejected', 'needs_review')
    ),
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_v2_catalyst_ticker_date
    ON v2_fact.catalyst_events(ticker, occurred_at DESC);

-- Migrate catalyst events (accepted only; raw events should be re-ingested).
INSERT INTO v2_fact.catalyst_events (
    event_id, ticker, event_type, title, summary, occurred_at, effective_date,
    materiality_hint, causality_level, source_url, confidence, validation_status, ingested_at
)
SELECT
    ce.event_id, ce.ticker, ce.event_type, ce.title, ce.summary, ce.occurred_at, ce.effective_date,
    ce.materiality_hint,
    COALESCE(ce.causality_level, 'contextual_event') AS causality_level,
    ce.source_url, ce.confidence, ce.validation_status, ce.ingested_at
FROM fact.catalyst_events ce
WHERE ce.validation_status IN ('accepted', 'validated')
  AND ce.ticker IN (SELECT ticker FROM v2_ref.companies)
ON CONFLICT (event_id) DO NOTHING;

-- ── Backfill v2_ingest.observations from fact.financial_facts ─────────────────
-- Insert legacy API facts as observations with extraction_method='legacy_import'.
-- source_doc_id is looked up from the v2_ingest.source_documents migration above.
-- Only FY facts with validation_status IN ('accepted', 'validated', 'raw') are migrated.
-- Rejected facts are skipped.

INSERT INTO v2_ingest.observations (
    ticker, period, period_type, metric, value, unit, currency,
    source_doc_id, source_tier, extraction_method, confidence, created_at
)
SELECT
    ff.ticker,
    CONCAT(ff.fiscal_year::TEXT, ff.fiscal_period)           AS period,
    CASE WHEN ff.fiscal_period = 'FY' THEN 'FY' ELSE 'Q' END AS period_type,
    ff.line_item_code                                         AS metric,
    ff.value,
    ff.unit,
    ff.currency,
    -- Lookup the migrated source_doc_id from the source mapping
    sd.source_doc_id,
    COALESCE(sd.source_tier, 3)                              AS source_tier,
    'legacy_import'                                           AS extraction_method,
    ff.confidence,
    ff.ingested_at                                           AS created_at
FROM fact.financial_facts ff
LEFT JOIN (
    SELECT
        source_doc_id,
        source_tier,
        (metadata_json->>'legacy_source_id') AS legacy_source_id
    FROM v2_ingest.source_documents
    WHERE metadata_json ? 'legacy_source_id'
) sd ON sd.legacy_source_id = ff.source_id
WHERE ff.fiscal_period      = 'FY'
  AND ff.validation_status  IN ('accepted', 'validated', 'raw')
  AND ff.ticker              IN (SELECT ticker FROM v2_ref.companies)
  AND ff.line_item_code      IN (SELECT line_item_code FROM v2_ref.line_items)
ON CONFLICT (ticker, period, metric, source_doc_id) DO NOTHING;

-- ── Promote accepted observations to v2_fact.canonical_facts ──────────────────
-- Only accepted FY observations with confidence >= 0.80 become canonical.
-- canonical_version = 'v2_legacy_import' marks these as pre-v2 baseline data.
-- fact_id is deterministic: SHA256 of (ticker|period|metric|canonical_version).

INSERT INTO v2_fact.canonical_facts (
    fact_id,
    ticker, period, period_type, canonical_version,
    metric, value, unit, currency,
    selected_observation_id, selection_policy, confidence,
    source_tier, quality_status, reconciliation_status,
    created_at, updated_at
)
SELECT
    encode(digest(
        obs.ticker || '|' || obs.period || '|' || obs.metric || '|v2_legacy_import',
        'sha256'
    ), 'hex')                                              AS fact_id,
    obs.ticker,
    obs.period,
    obs.period_type,
    'v2_legacy_import'                                     AS canonical_version,
    obs.metric,
    -- Winner: for each (ticker, period, metric), pick the highest-tier, highest-confidence observation
    obs.value,
    obs.unit,
    obs.currency,
    obs.observation_id                                     AS selected_observation_id,
    'highest_tier_then_confidence'                         AS selection_policy,
    obs.confidence,
    obs.source_tier,
    'accepted'                                             AS quality_status,
    'missing_official'                                     AS reconciliation_status,
    obs.created_at,
    obs.created_at                                         AS updated_at
FROM (
    -- Deduplicate: one winner per (ticker, period, metric) using best tier/confidence
    SELECT DISTINCT ON (ticker, period, metric)
        observation_id, ticker, period, period_type, metric, value, unit, currency,
        source_doc_id, source_tier, confidence, created_at
    FROM v2_ingest.observations
    WHERE period_type = 'FY'
      AND (confidence IS NULL OR confidence >= 0.80)
    ORDER BY ticker, period, metric, source_tier ASC, confidence DESC NULLS LAST
) obs
-- Only promote if the same fact doesn't already exist at this version
WHERE NOT EXISTS (
    SELECT 1 FROM v2_fact.canonical_facts cf
    WHERE cf.ticker = obs.ticker
      AND cf.period = obs.period
      AND cf.metric = obs.metric
      AND cf.canonical_version = 'v2_legacy_import'
)
ON CONFLICT (ticker, period, metric, canonical_version) DO NOTHING;
