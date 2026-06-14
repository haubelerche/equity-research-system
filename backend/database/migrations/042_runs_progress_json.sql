-- backend/database/migrations/042_runs_progress_json.sql
-- Fine-grained generation progress for the live progress modal. The 9 coarse
-- pipeline stages stay in research.runs.current_stage; this column carries the
-- within-stage detail (ingestion sub-step, human-readable label) and a
-- blocking_reason surfaced to the user when a run cannot produce a report.
-- Idempotent.
ALTER TABLE research.runs
    ADD COLUMN IF NOT EXISTS progress_json JSONB NOT NULL DEFAULT '{}'::jsonb;
