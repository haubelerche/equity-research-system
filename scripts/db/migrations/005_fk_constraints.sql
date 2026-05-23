-- Migration: 005_fk_constraints.sql
-- Purpose: Add missing FK constraints to public schema tables.
-- All constraints are idempotent (added only if not already present).
-- Requires: ref.companies seeded, research_runs empty or all child run_ids valid.

-- financial_facts.company_ticker → ref.companies.ticker
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'financial_facts'
          AND constraint_name = 'financial_facts_company_ticker_fkey'
    ) THEN
        ALTER TABLE public.financial_facts
            ADD CONSTRAINT financial_facts_company_ticker_fkey
            FOREIGN KEY (company_ticker) REFERENCES ref.companies (ticker);
    END IF;
END $$;

-- financial_facts.source_version_id → public.source_versions.id
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'financial_facts'
          AND constraint_name = 'financial_facts_source_version_id_fkey'
    ) THEN
        ALTER TABLE public.financial_facts
            ADD CONSTRAINT financial_facts_source_version_id_fkey
            FOREIGN KEY (source_version_id) REFERENCES public.source_versions (id);
    END IF;
END $$;

-- price_history.ticker → ref.companies.ticker
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'price_history'
          AND constraint_name = 'price_history_ticker_fkey'
    ) THEN
        ALTER TABLE public.price_history
            ADD CONSTRAINT price_history_ticker_fkey
            FOREIGN KEY (ticker) REFERENCES ref.companies (ticker);
    END IF;
END $$;

-- company_profiles.ticker → ref.companies.ticker
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'company_profiles'
          AND constraint_name = 'company_profiles_ticker_fkey'
    ) THEN
        ALTER TABLE public.company_profiles
            ADD CONSTRAINT company_profiles_ticker_fkey
            FOREIGN KEY (ticker) REFERENCES ref.companies (ticker);
    END IF;
END $$;

-- catalyst_events.company_ticker → ref.companies.ticker (nullable column)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'catalyst_events'
          AND constraint_name = 'catalyst_events_company_ticker_fkey'
    ) THEN
        ALTER TABLE public.catalyst_events
            ADD CONSTRAINT catalyst_events_company_ticker_fkey
            FOREIGN KEY (company_ticker) REFERENCES ref.companies (ticker);
    END IF;
END $$;

-- run_steps.run_id → research_runs.run_id
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'run_steps'
          AND constraint_name = 'run_steps_run_id_fkey'
    ) THEN
        ALTER TABLE public.run_steps
            ADD CONSTRAINT run_steps_run_id_fkey
            FOREIGN KEY (run_id) REFERENCES public.research_runs (run_id);
    END IF;
END $$;

-- run_artifacts.run_id → research_runs.run_id
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'run_artifacts'
          AND constraint_name = 'run_artifacts_run_id_fkey'
    ) THEN
        ALTER TABLE public.run_artifacts
            ADD CONSTRAINT run_artifacts_run_id_fkey
            FOREIGN KEY (run_id) REFERENCES public.research_runs (run_id);
    END IF;
END $$;

-- run_approvals.run_id → research_runs.run_id
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'run_approvals'
          AND constraint_name = 'run_approvals_run_id_fkey'
    ) THEN
        ALTER TABLE public.run_approvals
            ADD CONSTRAINT run_approvals_run_id_fkey
            FOREIGN KEY (run_id) REFERENCES public.research_runs (run_id);
    END IF;
END $$;

-- run_budget_ledger.run_id → research_runs.run_id
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'run_budget_ledger'
          AND constraint_name = 'run_budget_ledger_run_id_fkey'
    ) THEN
        ALTER TABLE public.run_budget_ledger
            ADD CONSTRAINT run_budget_ledger_run_id_fkey
            FOREIGN KEY (run_id) REFERENCES public.research_runs (run_id);
    END IF;
END $$;

-- run_audit_events.run_id → research_runs.run_id
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_schema = 'public' AND table_name = 'run_audit_events'
          AND constraint_name = 'run_audit_events_run_id_fkey'
    ) THEN
        ALTER TABLE public.run_audit_events
            ADD CONSTRAINT run_audit_events_run_id_fkey
            FOREIGN KEY (run_id) REFERENCES public.research_runs (run_id);
    END IF;
END $$;
