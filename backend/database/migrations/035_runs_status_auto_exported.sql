-- Migration 035: Add 'auto_exported' status to runs table.
--
-- The automated pipeline reaches publish with NO human sign-off, so naming the
-- terminal state 'approved' was misleading. Successful auto-render now sets
-- status='auto_exported' (public API maps it to PUBLISHED_DRAFT). 'approved' is
-- kept in the constraint for backward compatibility with existing rows.

-- research.runs
ALTER TABLE research.runs
    DROP CONSTRAINT IF EXISTS runs_status_check;

ALTER TABLE research.runs
    ADD CONSTRAINT runs_status_check CHECK (
        status IN (
            'initialized', 'running', 'data_ready', 'analysis_ready', 'valuation_ready',
            'report_ready', 'needs_human_review', 'blocked', 'approved', 'auto_exported',
            'failed', 'cancelled'
        )
    );

-- v2_research.runs (if exists)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'v2_research' AND table_name = 'runs') THEN
        EXECUTE 'ALTER TABLE v2_research.runs DROP CONSTRAINT IF EXISTS v2_runs_status_check';
        EXECUTE 'ALTER TABLE v2_research.runs ADD CONSTRAINT v2_runs_status_check CHECK (
            status IN (
                ''initialized'', ''running'', ''data_ready'', ''analysis_ready'', ''valuation_ready'',
                ''report_ready'', ''needs_human_review'', ''blocked'', ''approved'', ''auto_exported'',
                ''failed'', ''cancelled''
            )
        )';
    END IF;
END $$;
