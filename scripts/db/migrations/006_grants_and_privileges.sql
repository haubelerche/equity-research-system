-- Migration: 006_grants_and_privileges.sql
-- Purpose: Supabase-compatible grants for application/service roles.
-- Transaction is owned by the migration runner; do not add BEGIN/COMMIT here.
-- Wrapped in DO $$ ... $$ so it is a no-op on non-Supabase (local) Postgres
-- where service_role / anon / authenticated roles may not exist.

DO $$
DECLARE
    r TEXT;
BEGIN
    -- service_role: full access to all four schemas.
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA ref, ingest, fact, research TO service_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ref TO service_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ingest TO service_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA fact TO service_role';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA research TO service_role';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ref TO service_role';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ingest TO service_role';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fact TO service_role';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA research TO service_role';
        -- Default privileges so future tables are automatically granted.
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ref GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ingest GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA fact GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA research GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ref GRANT USAGE, SELECT ON SEQUENCES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA ingest GRANT USAGE, SELECT ON SEQUENCES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA fact GRANT USAGE, SELECT ON SEQUENCES TO service_role';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA research GRANT USAGE, SELECT ON SEQUENCES TO service_role';
    END IF;

    -- anon and authenticated: minimal read access to ref schema only.
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('GRANT USAGE ON SCHEMA ref TO %I', r);
            EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA ref TO %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA ref GRANT SELECT ON TABLES TO %I', r);
        END IF;
    END LOOP;
END $$;
