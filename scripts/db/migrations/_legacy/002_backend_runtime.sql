BEGIN;

CREATE TABLE IF NOT EXISTS research_runs (
  run_id VARCHAR(64) PRIMARY KEY,
  ticker VARCHAR(10) NOT NULL,
  run_type VARCHAR(32) NOT NULL,
  objective TEXT NOT NULL,
  status VARCHAR(32) NOT NULL,
  current_state VARCHAR(64) NOT NULL,
  org_id VARCHAR(64),
  requested_by VARCHAR(128),
  flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_research_runs_ticker_created
  ON research_runs (ticker, created_at DESC);

CREATE TABLE IF NOT EXISTS run_steps (
  id BIGSERIAL PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  step_name VARCHAR(64) NOT NULL,
  agent_name VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  policy_reason TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  duration_ms BIGINT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_run_steps_run_started
  ON run_steps (run_id, started_at DESC);

CREATE TABLE IF NOT EXISTS run_artifacts (
  artifact_id VARCHAR(64) PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  artifact_type VARCHAR(64) NOT NULL,
  section_key VARCHAR(64),
  payload_json JSONB NOT NULL,
  evidence_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence NUMERIC(6, 4),
  created_by_agent VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_type
  ON run_artifacts (run_id, artifact_type, created_at DESC);

CREATE TABLE IF NOT EXISTS run_approvals (
  id BIGSERIAL PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  approval_stage VARCHAR(32) NOT NULL,
  decision VARCHAR(16) NOT NULL,
  reviewer VARCHAR(128),
  feedback_patch_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_approvals_run_stage
  ON run_approvals (run_id, approval_stage, created_at DESC);

CREATE TABLE IF NOT EXISTS run_budget_ledger (
  id BIGSERIAL PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  step_name VARCHAR(64) NOT NULL,
  model_name VARCHAR(80) NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
  budget_policy VARCHAR(32) NOT NULL,
  fallback_model VARCHAR(80),
  stop_reason VARCHAR(80),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_budget_ledger_run_step
  ON run_budget_ledger (run_id, step_name, created_at DESC);

CREATE TABLE IF NOT EXISTS run_audit_events (
  id BIGSERIAL PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL,
  actor VARCHAR(128) NOT NULL,
  action VARCHAR(64) NOT NULL,
  rule_reason TEXT,
  policy_reason TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_audit_events_run_created
  ON run_audit_events (run_id, created_at DESC);

COMMIT;
