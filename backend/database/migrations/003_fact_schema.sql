-- Migration: 003_fact_schema.sql
-- Purpose: Canonical source-derived facts, market prices, catalyst events, accepted facts view.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.
-- Key design decisions:
--   - price_history uses trade_date (not date), traded_value (not value).
--   - catalyst_events.event_type has a controlled CHECK constraint.
--   - Partial unique index prevents duplicate accepted current facts.

CREATE SCHEMA IF NOT EXISTS fact;

-- Primary canonical fact table.
-- One row = one line item value from one source for one ticker/period.
-- Derived metrics (ROE, margins, FCF ratios) must NOT be stored here.
CREATE TABLE IF NOT EXISTS fact.financial_facts (
    id                BIGSERIAL    PRIMARY KEY,
    ticker            VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    fiscal_year       SMALLINT     NOT NULL,
    fiscal_period     VARCHAR(4)   NOT NULL CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
    line_item_code    VARCHAR(100) NOT NULL REFERENCES ref.line_items(line_item_code),
    value             NUMERIC      NOT NULL,
    unit              VARCHAR(40)  NOT NULL,
    currency          CHAR(3)      NOT NULL DEFAULT 'VND',
    source_id         VARCHAR(64)  NOT NULL REFERENCES ingest.sources(source_id),
    connector_version VARCHAR(40)  NOT NULL,
    validation_status VARCHAR(25)  NOT NULL CHECK (
        validation_status IN ('raw', 'validated', 'accepted', 'rejected', 'needs_review')
    ),
    confidence        NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    is_current        BOOLEAN      NOT NULL DEFAULT TRUE,
    effective_date    DATE,
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, fiscal_year, fiscal_period, line_item_code, source_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_financial_facts_ticker_period
    ON fact.financial_facts(ticker, fiscal_year, fiscal_period);

CREATE INDEX IF NOT EXISTS idx_fact_financial_facts_line_item
    ON fact.financial_facts(line_item_code, fiscal_year);

-- Only one accepted current row allowed per (ticker, year, period, line_item).
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_current_accepted
    ON fact.financial_facts(ticker, fiscal_year, fiscal_period, line_item_code)
    WHERE is_current = TRUE AND validation_status = 'accepted';

-- Market price history.
-- trade_date is the canonical column name (not 'date').
-- traded_value is the transaction value in VND (not ambiguous 'value').
CREATE TABLE IF NOT EXISTS fact.price_history (
    ticker         VARCHAR(10)  NOT NULL REFERENCES ref.companies(ticker),
    trade_date     DATE         NOT NULL,
    open           NUMERIC,
    high           NUMERIC,
    low            NUMERIC,
    close          NUMERIC,
    adjusted_close NUMERIC,
    volume         BIGINT,
    traded_value   NUMERIC,
    market_cap     NUMERIC,
    source_id      VARCHAR(64)  REFERENCES ingest.sources(source_id),
    ingested_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_fact_price_history_ticker_date
    ON fact.price_history(ticker, trade_date DESC);

-- Catalyst events and market-moving disclosures.
CREATE TABLE IF NOT EXISTS fact.catalyst_events (
    event_id          VARCHAR(64)  PRIMARY KEY,
    ticker            VARCHAR(10)  REFERENCES ref.companies(ticker),
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
    source_url        TEXT,
    source_id         VARCHAR(64)  NOT NULL REFERENCES ingest.sources(source_id),
    confidence        NUMERIC(5,4) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    validation_status VARCHAR(25)  NOT NULL CHECK (
        validation_status IN ('raw', 'validated', 'accepted', 'rejected', 'needs_review')
    ),
    ingested_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_catalyst_ticker_date
    ON fact.catalyst_events(ticker, occurred_at DESC);

-- Valuation-safe view: accepted, annual (FY), current facts only.
-- All valuation and reporting code must read from this view.
CREATE OR REPLACE VIEW fact.accepted_financial_facts AS
SELECT
    id,
    ticker,
    fiscal_year,
    fiscal_period,
    line_item_code,
    value,
    unit,
    currency,
    source_id,
    connector_version,
    confidence,
    effective_date,
    ingested_at
FROM fact.financial_facts
WHERE validation_status = 'accepted'
  AND fiscal_period      = 'FY'
  AND is_current         = TRUE;

COMMENT ON VIEW fact.accepted_financial_facts IS
    'Valuation-safe subset: accepted, FY, current facts only. Valuation/reporting code must read from this view.';
