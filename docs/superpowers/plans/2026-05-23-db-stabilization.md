# DB Stabilization Sprint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Supabase database from a prototype flat schema into a contract-enforced foundation by adding migration versioning, FK constraints, an accepted-facts view, and removing runtime self-migration.

**Architecture:** Keep the existing `public` schema tables in place; layer on FK constraints that reference `ref.companies` (already seeded with 53 tickers). Add a `schema_migrations` tracking table and a dedicated `migrate.py` runner so runtime code never auto-applies DDL. Add an `accepted_financial_facts` view as the single valuation-safe entry point to facts.

**Tech Stack:** PostgreSQL (Supabase), psycopg2, pytest, raw SQL migration files.

---

## Current Supabase State (DB-0 Audit — already completed)

- `public` schema: 15 tables, zero FK constraints, only PK/UNIQUE/CHECK
- `ref.companies`: 53 rows (seeded), has UNIQUE(ticker) — safe FK target
- All data is DHG-only, referentially clean (no orphan source_version_ids)
- `research_runs`: 0 rows — safe to add FKs to run_* tables immediately
- No versioning table exists in project schemas
- `financial_facts.run_id` and `source_versions.run_id` (added by migration 003) are loose VARCHAR columns, not FK'd — **do not rename** (the connector generates them as `ticker_timestamp` strings, not UUIDs; they are audit strings, not relational keys)

---

## Files

### Created
- `scripts/db/migrations/004_schema_versioning.sql` — adds `schema_migrations` tracking table
- `scripts/db/migrations/005_fk_constraints.sql` — adds all missing FK constraints
- `scripts/db/migrations/006_accepted_facts_view.sql` — adds `accepted_financial_facts` view
- `scripts/db/migrate.py` — migration runner script (CLI + importable)
- `tests/unit/test_migrate_runner.py` — unit tests for migration runner logic
- `tests/integration/test_db_integrity.py` — live DB integrity checks (marked, manual run)

### Modified
- `backend/runtime_store.py` — remove `ensure_schema()` self-migration; add passive version check
- `scripts/db/fact_store.py` — add `query_accepted_facts()` method using the new view

---

## Task 1: Migration 004 — schema_migrations table

**Files:**
- Create: `scripts/db/migrations/004_schema_versioning.sql`

- [ ] **Step 1.1: Write migration SQL**

```sql
-- Migration: 004_schema_versioning.sql
-- Purpose: Add migration version tracking table.
-- Idempotent: uses IF NOT EXISTS.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(80)  NOT NULL PRIMARY KEY,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    description TEXT
);

-- Seed all migrations that were already applied to this database
-- before versioning was introduced (migrations 001-003).
INSERT INTO schema_migrations (version, description) VALUES
    ('001_initial_schema',       'Core fact/price/company/source tables')
  , ('002_backend_runtime',      'research_runs, run_steps, run_artifacts, approvals, budget, audit')
  , ('003_lineage_enhancements', 'Add run_id and embedding_version to fact/source/catalyst tables')
ON CONFLICT (version) DO NOTHING;

COMMIT;
```

- [ ] **Step 1.2: Apply this migration manually via Supabase SQL editor or psql**

```bash
python -c "
import psycopg2, pathlib, os
dsn = os.environ['DATABASE_URL']
sql = pathlib.Path('scripts/db/migrations/004_schema_versioning.sql').read_text()
conn = psycopg2.connect(dsn)
conn.autocommit = False
cur = conn.cursor()
cur.execute(sql)
conn.commit()
print('004 applied')
conn.close()
"
```

Expected output: `004 applied`

- [ ] **Step 1.3: Verify**

```bash
python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT version, applied_at FROM schema_migrations ORDER BY applied_at')
for row in cur.fetchall(): print(row)
conn.close()
"
```

Expected: 4 rows: `001_initial_schema`, `002_backend_runtime`, `003_lineage_enhancements`, `004_schema_versioning`.

- [ ] **Step 1.4: Commit**

```bash
git add scripts/db/migrations/004_schema_versioning.sql
git commit -m "feat(db): add schema_migrations versioning table, seed migrations 001-003"
```

---

## Task 2: Migration runner script

**Files:**
- Create: `scripts/db/migrate.py`
- Create: `tests/unit/test_migrate_runner.py`

- [ ] **Step 2.1: Write the failing test**

```python
# tests/unit/test_migrate_runner.py
"""Unit tests for the migration runner (no live DB required)."""
import pytest
from unittest.mock import MagicMock, call, patch
from scripts.db.migrate import _pending_migrations, _apply_migration, MIGRATIONS_DIR


def test_pending_migrations_empty_when_all_applied():
    all_files = ["001_foo.sql", "002_bar.sql"]
    applied = {"001_foo", "002_bar"}
    assert _pending_migrations(all_files, applied) == []


def test_pending_migrations_returns_unapplied_in_order():
    all_files = ["001_foo.sql", "002_bar.sql", "003_baz.sql"]
    applied = {"001_foo"}
    result = _pending_migrations(all_files, applied)
    assert result == ["002_bar.sql", "003_baz.sql"]


def test_pending_migrations_order_is_lexicographic():
    all_files = ["003_c.sql", "001_a.sql", "002_b.sql"]
    applied = set()
    result = _pending_migrations(all_files, applied)
    assert result == ["001_a.sql", "002_b.sql", "003_c.sql"]


def test_pending_migrations_ignores_non_sql():
    all_files = ["001_a.sql", "README.md", "002_b.sql"]
    applied = set()
    result = _pending_migrations(all_files, applied)
    assert result == ["001_a.sql", "002_b.sql"]


def test_apply_migration_records_version():
    mock_conn = MagicMock()
    mock_cur = mock_conn.cursor.return_value.__enter__.return_value
    with patch("builtins.open", MagicMock(return_value=MagicMock(
        __enter__=lambda s: s, __exit__=MagicMock(return_value=False),
        read=lambda: "CREATE TABLE foo (id INT);"
    ))):
        _apply_migration(mock_conn, MIGRATIONS_DIR / "001_foo.sql", "001_foo")
    # Should execute the SQL content
    mock_cur.execute.assert_any_call("CREATE TABLE foo (id INT);")
    # Should record the version
    assert any(
        "INSERT INTO schema_migrations" in str(c)
        for c in mock_cur.execute.call_args_list
    )
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
pytest tests/unit/test_migrate_runner.py -v
```

Expected: `ImportError: cannot import name '_pending_migrations'`

- [ ] **Step 2.3: Write the migration runner**

```python
# scripts/db/migrate.py
"""Migration runner for the VN pharma equity research DB.

Usage:
    python scripts/db/migrate.py                  # apply all pending migrations
    python scripts/db/migrate.py --check          # print pending list, exit 0
    python scripts/db/migrate.py --version        # print highest applied version
"""
from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
CURRENT_SCHEMA_VERSION = "006_accepted_facts_view"  # update when new migrations are added


def _pending_migrations(all_files: list[str], applied: set[str]) -> list[str]:
    """Return .sql filenames not yet applied, sorted lexicographically."""
    return sorted(
        f for f in all_files
        if f.endswith(".sql") and Path(f).stem not in applied
    )


def _version_from_filename(filename: str) -> str:
    """Strip .sql suffix: '005_fk_constraints.sql' → '005_fk_constraints'."""
    return Path(filename).stem


def _apply_migration(conn, path: Path, version: str) -> None:
    """Apply one migration file and record it in schema_migrations."""
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            (version,),
        )


@contextmanager
def _connect(dsn: str):
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_applied_versions(dsn: str) -> set[str]:
    with _connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations")
            return {row[0] for row in cur.fetchall()}


def run_migrations(dsn: str, dry_run: bool = False) -> list[str]:
    """Apply all pending migrations. Returns list of versions applied."""
    all_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    all_names = [f.name for f in all_files]
    applied = get_applied_versions(dsn)
    pending_names = _pending_migrations(all_names, applied)

    if not pending_names:
        print("No pending migrations.")
        return []

    applied_list = []
    for filename in pending_names:
        version = _version_from_filename(filename)
        path = MIGRATIONS_DIR / filename
        if dry_run:
            print(f"  [dry-run] would apply: {version}")
        else:
            print(f"  Applying: {version} ... ", end="", flush=True)
            with _connect(dsn) as conn:
                _apply_migration(conn, path, version)
            print("done")
        applied_list.append(version)
    return applied_list


def check_schema_version(dsn: str) -> None:
    """Raise RuntimeError if the DB schema version does not match CURRENT_SCHEMA_VERSION."""
    applied = get_applied_versions(dsn)
    if CURRENT_SCHEMA_VERSION not in applied:
        raise RuntimeError(
            f"Schema version mismatch: required '{CURRENT_SCHEMA_VERSION}' not in applied={sorted(applied)}. "
            "Run: python scripts/db/migrate.py"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending DB migrations")
    parser.add_argument("--check", action="store_true", help="List pending migrations only; do not apply")
    parser.add_argument("--version", action="store_true", help="Print highest applied version and exit")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL env var is not set.", file=sys.stderr)
        sys.exit(1)

    if args.version:
        applied = get_applied_versions(dsn)
        print(max(applied, default="(none)"))
        return

    if args.check:
        run_migrations(dsn, dry_run=True)
    else:
        run_migrations(dsn, dry_run=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
pytest tests/unit/test_migrate_runner.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 2.5: Commit**

```bash
git add scripts/db/migrate.py tests/unit/test_migrate_runner.py
git commit -m "feat(db): add migration runner with version tracking"
```

---

## Task 3: Migration 005 — FK constraints

**Files:**
- Create: `scripts/db/migrations/005_fk_constraints.sql`

- [ ] **Step 3.1: Write the FK constraint migration**

```sql
-- Migration: 005_fk_constraints.sql
-- Purpose: Add missing FK constraints to public schema tables.
-- All constraints are idempotent (added only if not already present).
-- ref.companies must be seeded before applying this migration.
-- research_runs must be empty or all run_* child rows must have valid run_ids.

BEGIN;

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

-- catalyst_events.company_ticker → ref.companies.ticker (DEFERRABLE: company_ticker is nullable)
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

COMMIT;
```

- [ ] **Step 3.2: Apply via the migration runner**

```bash
python scripts/db/migrate.py
```

Expected output:
```
  Applying: 005_fk_constraints ... done
```

- [ ] **Step 3.3: Verify FK constraints exist**

```bash
python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('''
    SELECT c.conrelid::regclass, c.conname, pg_get_constraintdef(c.oid)
    FROM pg_constraint c
    JOIN pg_namespace n ON n.oid = c.connamespace
    WHERE n.nspname = 'public' AND c.contype = 'f'
    ORDER BY 1, 2
''')
for row in cur.fetchall(): print(row)
conn.close()
"
```

Expected: 10 FK rows — financial_facts (×2), price_history, company_profiles, catalyst_events, run_steps, run_artifacts, run_approvals, run_budget_ledger, run_audit_events.

- [ ] **Step 3.4: Commit**

```bash
git add scripts/db/migrations/005_fk_constraints.sql
git commit -m "feat(db): add FK constraints linking public tables to ref.companies and source_versions"
```

---

## Task 4: Migration 006 — accepted_financial_facts view

**Files:**
- Create: `scripts/db/migrations/006_accepted_facts_view.sql`

- [ ] **Step 4.1: Write the view migration**

```sql
-- Migration: 006_accepted_facts_view.sql
-- Purpose: Provide a valuation-safe view of financial_facts.
-- Only rows with validation_status='accepted' AND fiscal_period='FY' are exposed.
-- Valuation scripts MUST read this view, not the base table.

BEGIN;

CREATE OR REPLACE VIEW public.accepted_financial_facts AS
SELECT
    id,
    company_ticker,
    fiscal_year,
    fiscal_period,
    taxonomy_key,
    value,
    unit,
    currency,
    source_version_id,
    parser_version,
    confidence,
    effective_date,
    ingested_at
FROM public.financial_facts
WHERE validation_status = 'accepted'
  AND fiscal_period = 'FY';

COMMENT ON VIEW public.accepted_financial_facts IS
    'Valuation-safe subset: accepted status, annual (FY) periods only. '
    'All valuation and reporting code must read from this view.';

COMMIT;
```

- [ ] **Step 4.2: Apply via migration runner**

```bash
python scripts/db/migrate.py
```

Expected output:
```
  Applying: 006_accepted_facts_view ... done
```

- [ ] **Step 4.3: Verify view returns data**

```bash
python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM public.accepted_financial_facts')
print('accepted_financial_facts rows:', cur.fetchone()[0])
cur.execute(\"SELECT COUNT(*) FROM public.financial_facts WHERE validation_status != 'accepted' OR fiscal_period != 'FY'\")
print('rows excluded from view:', cur.fetchone()[0])
conn.close()
"
```

Expected: view row count ≤ total financial_facts count.

- [ ] **Step 4.4: Commit**

```bash
git add scripts/db/migrations/006_accepted_facts_view.sql
git commit -m "feat(db): add accepted_financial_facts view for valuation-safe fact access"
```

---

## Task 5: Add query_accepted_facts to PostgresFactStore

**Files:**
- Modify: `scripts/db/fact_store.py`

- [ ] **Step 5.1: Add the method**

In [scripts/db/fact_store.py](scripts/db/fact_store.py), add after `get_financial_facts_for_ticker` (line ~363):

```python
def get_accepted_financial_facts(self, ticker: str) -> list[dict[str, Any]]:
    """Return only accepted, FY-period facts for a ticker (valuation-safe).

    Reads from the accepted_financial_facts view, which filters
    validation_status='accepted' AND fiscal_period='FY'.
    """
    with self.conn() as connection:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT taxonomy_key, fiscal_year, fiscal_period, value, unit, currency,
                       source_version_id, parser_version, confidence, ingested_at
                FROM public.accepted_financial_facts
                WHERE company_ticker = %s
                ORDER BY fiscal_year ASC, taxonomy_key ASC
                """,
                (ticker,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
```

- [ ] **Step 5.2: Verify it runs against Supabase**

```bash
python -c "
from scripts.db.fact_store import PostgresFactStore
store = PostgresFactStore()
rows = store.get_accepted_financial_facts('DHG')
print(f'Accepted FY facts for DHG: {len(rows)}')
if rows: print('Sample:', rows[0])
"
```

Expected: prints a count ≥ 0 without error.

- [ ] **Step 5.3: Commit**

```bash
git add scripts/db/fact_store.py
git commit -m "feat(db): add get_accepted_financial_facts() reading from accepted_financial_facts view"
```

---

## Task 6: Fix RuntimeStore.ensure_schema()

**Files:**
- Modify: `backend/runtime_store.py`

- [ ] **Step 6.1: Replace ensure_schema with a passive version check**

Replace the existing `ensure_schema` method ([backend/runtime_store.py:32-38](backend/runtime_store.py#L32-L38)) with:

```python
REQUIRED_SCHEMA_VERSION = "006_accepted_facts_view"

def check_schema_version(self) -> None:
    """Raise RuntimeError if the required schema version is not applied.

    Does NOT apply migrations — run scripts/db/migrate.py first.
    """
    with self.conn() as connection:
        with connection.cursor() as cur:
            try:
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = %s",
                    (REQUIRED_SCHEMA_VERSION,),
                )
                if cur.fetchone() is None:
                    raise RuntimeError(
                        f"DB schema out of date: version '{REQUIRED_SCHEMA_VERSION}' not applied. "
                        "Run: python scripts/db/migrate.py"
                    )
            except Exception as exc:
                if "schema_migrations" in str(exc):
                    raise RuntimeError(
                        "schema_migrations table missing — run: python scripts/db/migrate.py"
                    ) from exc
                raise
```

Also add `REQUIRED_SCHEMA_VERSION` as a module-level constant at the top of the class, just before `__init__`.

- [ ] **Step 6.2: Update any callers of `ensure_schema`**

```bash
grep -rn "ensure_schema" . --include="*.py"
```

For each caller found, replace `ensure_schema()` with `check_schema_version()`.

- [ ] **Step 6.3: Verify the check passes against Supabase (after migrations 004-006 are applied)**

```bash
python -c "
from backend.runtime_store import RuntimeStore
store = RuntimeStore()
store.check_schema_version()
print('Schema version check passed.')
"
```

Expected: `Schema version check passed.`

- [ ] **Step 6.4: Commit**

```bash
git add backend/runtime_store.py
git commit -m "fix(db): replace ensure_schema() self-migration with passive check_schema_version()"
```

---

## Task 7: DB integrity tests

**Files:**
- Create: `tests/integration/test_db_integrity.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 7.1: Create the integration test file**

```python
# tests/integration/test_db_integrity.py
"""Live DB integrity checks — require DATABASE_URL env var.

Run manually:
    pytest tests/integration/test_db_integrity.py -v

These tests verify the Supabase database state matches expectations.
They are NOT run in CI automatically (they require live DB access).
"""
import os
import pytest
import psycopg2

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB tests",
)


@pytest.fixture(scope="module")
def db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    yield conn
    conn.close()


def test_schema_migrations_table_exists(db):
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='schema_migrations'"
    )
    assert cur.fetchone()[0] == 1, "schema_migrations table not found"


def test_expected_migrations_applied(db):
    cur = db.cursor()
    cur.execute("SELECT version FROM schema_migrations ORDER BY version")
    applied = {row[0] for row in cur.fetchall()}
    expected = {
        "001_initial_schema",
        "002_backend_runtime",
        "003_lineage_enhancements",
        "004_schema_versioning",
        "005_fk_constraints",
        "006_accepted_facts_view",
    }
    missing = expected - applied
    assert not missing, f"Migrations not applied: {missing}"


def test_no_orphan_financial_facts_source_version(db):
    """Every financial_fact.source_version_id must exist in source_versions."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM public.financial_facts ff
        LEFT JOIN public.source_versions sv ON ff.source_version_id = sv.id
        WHERE sv.id IS NULL
    """)
    count = cur.fetchone()[0]
    assert count == 0, f"{count} financial_facts have orphan source_version_id"


def test_no_orphan_financial_facts_ticker(db):
    """Every financial_fact.company_ticker must exist in ref.companies."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM public.financial_facts ff
        LEFT JOIN ref.companies c ON ff.company_ticker = c.ticker
        WHERE c.ticker IS NULL
    """)
    count = cur.fetchone()[0]
    assert count == 0, f"{count} financial_facts have company_ticker not in ref.companies"


def test_no_quarterly_facts_in_accepted_view(db):
    """The accepted_financial_facts view must contain only FY-period rows."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM public.accepted_financial_facts
        WHERE fiscal_period != 'FY'
    """)
    count = cur.fetchone()[0]
    assert count == 0, f"{count} non-FY rows leaked into accepted_financial_facts view"


def test_no_non_accepted_facts_in_view(db):
    """The accepted_financial_facts view must contain only validation_status='accepted'."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM public.accepted_financial_facts af
        JOIN public.financial_facts ff ON af.id = ff.id
        WHERE ff.validation_status != 'accepted'
    """)
    count = cur.fetchone()[0]
    assert count == 0, f"{count} non-accepted rows leaked into accepted_financial_facts view"


def test_fk_constraints_exist_for_financial_facts(db):
    """FK constraints on financial_facts must exist."""
    cur = db.cursor()
    cur.execute("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'public.financial_facts'::regclass AND contype = 'f'
    """)
    constraints = {row[0] for row in cur.fetchall()}
    assert "financial_facts_company_ticker_fkey" in constraints
    assert "financial_facts_source_version_id_fkey" in constraints


def test_fk_constraints_exist_for_run_tables(db):
    """FK constraints on run_steps and run_artifacts to research_runs must exist."""
    cur = db.cursor()
    cur.execute("""
        SELECT conrelid::regclass::text, conname FROM pg_constraint
        WHERE contype = 'f'
          AND conrelid IN (
            'public.run_steps'::regclass,
            'public.run_artifacts'::regclass,
            'public.run_approvals'::regclass,
            'public.run_budget_ledger'::regclass,
            'public.run_audit_events'::regclass
          )
    """)
    found = {row[1] for row in cur.fetchall()}
    expected = {
        "run_steps_run_id_fkey",
        "run_artifacts_run_id_fkey",
        "run_approvals_run_id_fkey",
        "run_budget_ledger_run_id_fkey",
        "run_audit_events_run_id_fkey",
    }
    missing = expected - found
    assert not missing, f"Missing FK constraints: {missing}"


def test_ref_companies_has_pharma_mvp_tickers(db):
    """MVP pharma tickers must exist in ref.companies."""
    cur = db.cursor()
    cur.execute("SELECT ticker FROM ref.companies")
    tickers = {row[0] for row in cur.fetchall()}
    mvp = {"DHG", "IMP", "DMC", "TRA", "DBD"}
    missing = mvp - tickers
    assert not missing, f"MVP tickers not in ref.companies: {missing}"
```

```python
# tests/integration/__init__.py
```

- [ ] **Step 7.2: Run the integration tests**

```bash
pytest tests/integration/test_db_integrity.py -v
```

Expected: all 9 tests PASS (requires `DATABASE_URL` set in environment).

If running without `DATABASE_URL`:
```
SKIPPED - DATABASE_URL not set
```

- [ ] **Step 7.3: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_db_integrity.py
git commit -m "test(db): add live DB integrity tests for FK constraints, view, and migration state"
```

---

## Task 8: Run full test suite and verify

- [ ] **Step 8.1: Run unit tests**

```bash
pytest tests/unit/ -v
```

Expected: all existing unit tests PASS (gate invariant tests and migrate runner tests).

- [ ] **Step 8.2: Run integration tests (live DB)**

```bash
pytest tests/integration/test_db_integrity.py -v
```

Expected: all 9 integration tests PASS.

- [ ] **Step 8.3: Verify migration runner --check shows no pending**

```bash
python scripts/db/migrate.py --check
```

Expected: `No pending migrations.`

- [ ] **Step 8.4: Verify schema version check passes**

```bash
python -c "from backend.runtime_store import RuntimeStore; RuntimeStore().check_schema_version(); print('OK')"
```

Expected: `OK`

- [ ] **Step 8.5: Final commit if any loose files**

```bash
git status
git add -p  # review any remaining changes
git commit -m "chore(db): db stabilization sprint complete"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| Migration versioning table | Task 1 (004_schema_versioning.sql) |
| Migration runner script | Task 2 (migrate.py) |
| FK: financial_facts → ref.companies | Task 3 (005_fk_constraints.sql) |
| FK: financial_facts → source_versions | Task 3 |
| FK: price_history → ref.companies | Task 3 |
| FK: company_profiles → ref.companies | Task 3 |
| FK: catalyst_events → ref.companies | Task 3 |
| FK: run_* tables → research_runs | Task 3 |
| accepted_financial_facts view | Task 4 (006_accepted_facts_view.sql) |
| query_accepted_facts() Python method | Task 5 |
| Remove RuntimeStore self-migration | Task 6 |
| Orphan source_version_id test | Task 7 |
| Invalid ticker test | Task 7 |
| Non-FY facts blocked by view test | Task 7 |
| FK constraint existence tests | Task 7 |
| Migration state tests | Task 7 |

### Notes

- `financial_facts.run_id` and `source_versions.run_id` (from migration 003) are **not FK'd** and **not renamed** — by design. They are connector audit strings (`ticker_YYYYMMDDTHHMMSS`), not relational run IDs. Linking them to `ingestion_runs` would require the connector to pre-create an `ingestion_runs` row, which is a separate improvement beyond this sprint's scope.
- The `connector_runs` and `ingestion_runs` tables in `public` have no FK to each other — also intentional for now; they serve different scopes and will be unified in a future sprint.
- `raw/canonical/derived/governance/ops` schemas from the worktree design are **not applied** in this sprint. The decision to migrate the full multi-schema design is deferred and should be a separate plan after this sprint passes all integrity tests.
