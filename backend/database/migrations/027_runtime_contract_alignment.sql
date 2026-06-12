-- Migration 027: align canonical research runtime tables with executable harness.

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    FOR constraint_name IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'research.run_artifacts'::regclass
          AND contype = 'c'
    LOOP
        EXECUTE format('ALTER TABLE research.run_artifacts DROP CONSTRAINT %I', constraint_name);
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_run_artifacts_section
    ON research.run_artifacts(run_id, section_key, version DESC);

INSERT INTO audit.events (event_type, actor, target_table, payload_json)
VALUES (
    'schema_migration',
    'migration_027',
    'research.run_artifacts',
    jsonb_build_object('migration', '027_runtime_contract_alignment')
);
