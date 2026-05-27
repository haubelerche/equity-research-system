BEGIN;

CREATE TABLE IF NOT EXISTS financial_facts (
  id BIGSERIAL PRIMARY KEY,
  company_ticker VARCHAR(10) NOT NULL,
  fiscal_year SMALLINT NOT NULL,
  fiscal_period VARCHAR(4) NOT NULL CHECK (fiscal_period IN ('FY', 'Q1', 'Q2', 'Q3', 'Q4')),
  taxonomy_key VARCHAR(60) NOT NULL,
  value NUMERIC NOT NULL,
  unit VARCHAR(20) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'VND',
  source_version_id VARCHAR(64) NOT NULL,
  parser_version VARCHAR(20) NOT NULL,
  validation_status VARCHAR(25) NOT NULL,
  confidence NUMERIC(4, 3),
  effective_date DATE,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (company_ticker, fiscal_year, fiscal_period, taxonomy_key, source_version_id)
);
CREATE INDEX IF NOT EXISTS idx_financial_facts_period
  ON financial_facts (company_ticker, fiscal_year, fiscal_period);

CREATE TABLE IF NOT EXISTS price_history (
  ticker VARCHAR(10) NOT NULL,
  date DATE NOT NULL,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume BIGINT,
  value NUMERIC,
  source_version_id VARCHAR(64),
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date
  ON price_history (ticker, date DESC);

CREATE TABLE IF NOT EXISTS catalyst_events (
  event_id VARCHAR(64) PRIMARY KEY,
  event_type VARCHAR(50) NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  occurred_at TIMESTAMPTZ NOT NULL,
  effective_date DATE,
  company_ticker VARCHAR(10),
  materiality_hint VARCHAR(10),
  source_url TEXT NOT NULL,
  source_version_id VARCHAR(64) NOT NULL,
  confidence NUMERIC(4, 3),
  validation_status VARCHAR(25) NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_catalyst_events_company_occurred
  ON catalyst_events (company_ticker, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_catalyst_events_type_materiality
  ON catalyst_events (event_type, materiality_hint);

CREATE TABLE IF NOT EXISTS source_versions (
  id VARCHAR(64) PRIMARY KEY,
  source_id VARCHAR(50) NOT NULL,
  source_uri TEXT NOT NULL,
  source_type VARCHAR(40) NOT NULL,
  effective_date DATE,
  published_at TIMESTAMPTZ,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  checksum CHAR(64) NOT NULL,
  connector_version VARCHAR(20) NOT NULL,
  raw_path TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_versions_source
  ON source_versions (source_id, source_uri, ingested_at DESC);

CREATE TABLE IF NOT EXISTS company_profiles (
  ticker VARCHAR(10) PRIMARY KEY,
  company_name VARCHAR(200),
  exchange VARCHAR(10),
  segment VARCHAR(50),
  overview_json JSONB,
  shareholders_json JSONB,
  officers_json JSONB,
  last_synced_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS peer_metrics_snapshot (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  snapshot_period VARCHAR(8) NOT NULL,
  metric_key VARCHAR(60) NOT NULL,
  value NUMERIC,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  computation_run_id VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_peer_metrics_ticker_period
  ON peer_metrics_snapshot (ticker, snapshot_period);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  run_id VARCHAR(64) PRIMARY KEY,
  run_type VARCHAR(40) NOT NULL,
  status VARCHAR(20) NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  metadata_json JSONB
);

CREATE TABLE IF NOT EXISTS connector_runs (
  run_id VARCHAR(64) PRIMARY KEY,
  connector_name VARCHAR(100) NOT NULL,
  source_id VARCHAR(50) NOT NULL,
  status VARCHAR(20) NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  stats_json JSONB
);

CREATE TABLE IF NOT EXISTS forecast_inputs (
  id BIGSERIAL PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  scenario VARCHAR(20) NOT NULL DEFAULT 'base',
  metrics_json JSONB NOT NULL,
  analyst_id VARCHAR(64),
  effective_date DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_forecast_inputs_ticker_date
  ON forecast_inputs (ticker, effective_date DESC);

COMMIT;
