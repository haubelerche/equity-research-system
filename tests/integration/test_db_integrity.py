"""Live DB integrity checks — require DATABASE_URL env var.

Run manually:
    pytest tests/integration/test_db_integrity.py -v

These tests verify the Supabase database state matches expectations.
They are skipped automatically when DATABASE_URL is not set.
"""
import os
import pytest
import psycopg2
import psycopg2.extras

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
        SELECT conname FROM pg_constraint
        WHERE contype = 'f'
          AND conrelid IN (
            'public.run_steps'::regclass,
            'public.run_artifacts'::regclass,
            'public.run_approvals'::regclass,
            'public.run_budget_ledger'::regclass,
            'public.run_audit_events'::regclass
          )
    """)
    found = {row[0] for row in cur.fetchall()}
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


def test_check_schema_version_passes(db):
    """RuntimeStore.check_schema_version() must pass against the live database."""
    import os as _os
    with open('c:\\Users\\Admin\\Desktop\\multi-agent-equity-research\\.env') as f:
        for line in f:
            line = line.strip()
            if line.startswith('DATABASE_URL='):
                _os.environ['DATABASE_URL'] = line.split('=', 1)[1]
    from backend.runtime_store import RuntimeStore
    store = RuntimeStore()
    store.check_schema_version()  # must not raise
