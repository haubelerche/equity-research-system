-- Migration 034: Add 'blocked' status to runs table, replace 'needs_human_review'
--
-- The automated pipeline no longer uses 'needs_human_review'. Critical gate
-- failures now set status='blocked' instead. Both values are kept in the
-- constraint for backward compatibility with existing rows.

-- research.runs
ALTER TABLE research.runs
    DROP CONSTRAINT IF EXISTS runs_status_check;

ALTER TABLE research.runs
    ADD CONSTRAINT runs_status_check CHECK (
        status IN (
            'initialized', 'running', 'data_ready', 'analysis_ready', 'valuation_ready',
            'report_ready', 'needs_human_review', 'blocked', 'approved', 'failed', 'cancelled'
        )
    );

-- v2_research.runs (if exists)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'v2_research' AND table_name = 'runs') THEN
        EXECUTE 'ALTER TABLE v2_research.runs DROP CONSTRAINT IF EXISTS runs_status_check';
        EXECUTE 'ALTER TABLE v2_research.runs ADD CONSTRAINT v2_runs_status_check CHECK (
            status IN (
                ''initialized'', ''running'', ''data_ready'', ''analysis_ready'', ''valuation_ready'',
                ''report_ready'', ''needs_human_review'', ''blocked'', ''approved'', ''failed'', ''cancelled''
            )
        )';
    END IF;
END $$;
