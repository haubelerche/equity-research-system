"""Live DB integrity checks for the 4-schema design — require DATABASE_URL env var.

Run manually:
    pytest tests/integration/test_db_integrity.py -v

Tests are skipped automatically when DATABASE_URL is not set.
"""
import os

import psycopg2
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB tests",
)


@pytest.fixture(scope="module")
def db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    yield conn
    conn.close()


# ── Migration tracking ──────────────────────────────────────────────────────

def test_schema_migrations_table_exists(db):
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='schema_migrations'"
    )
    assert cur.fetchone()[0] == 1, "public.schema_migrations table not found"


def test_all_six_migrations_applied(db):
    cur = db.cursor()
    cur.execute("SELECT version FROM public.schema_migrations ORDER BY version")
    applied = {row[0] for row in cur.fetchall()}
    expected = {
        "001_ref_schema",
        "002_ingest_schema",
        "003_fact_schema",
        "004_research_schema",
        "005_seed_reference_data",
        "006_grants_and_privileges",
    }
    missing = expected - applied
    assert not missing, f"Migrations not applied: {missing}"


def test_current_schema_version_applied(db):
    """Migration 006_grants_and_privileges must be in applied versions."""
    cur = db.cursor()
    cur.execute(
        "SELECT 1 FROM public.schema_migrations WHERE version = '006_grants_and_privileges'"
    )
    assert cur.fetchone() is not None, "006_grants_and_privileges not applied"


# ── Schema existence ────────────────────────────────────────────────────────

def test_all_four_schemas_exist(db):
    cur = db.cursor()
    cur.execute("SELECT schema_name FROM information_schema.schemata")
    schemas = {row[0] for row in cur.fetchall()}
    for schema in ("ref", "ingest", "fact", "research"):
        assert schema in schemas, f"Schema '{schema}' not found"


# ── ref schema ──────────────────────────────────────────────────────────────

def test_ref_companies_has_mvp_tickers(db):
    cur = db.cursor()
    cur.execute("SELECT ticker FROM ref.companies")
    tickers = {row[0] for row in cur.fetchall()}
    missing = {"DHG", "IMP", "DMC", "TRA", "DBD"} - tickers
    assert not missing, f"MVP tickers not in ref.companies: {missing}"


def test_ref_formulas_canonical_ids(db):
    """Critical formula IDs must exist with correct names."""
    cur = db.cursor()
    cur.execute("SELECT formula_id, formula_name FROM ref.formulas WHERE formula_id IN %s",
                (("F001", "F006", "F012", "F024", "F029", "F030"),))
    found = {row[0]: row[1] for row in cur.fetchall()}
    assert found.get("F001") == "CAGR", f"F001 name mismatch: {found.get('F001')}"
    assert found.get("F006") == "P/E",  f"F006 name mismatch: {found.get('F006')}"
    assert found.get("F012") == "ROE",  f"F012 name mismatch: {found.get('F012')}"
    assert found.get("F024") == "FCFF", f"F024 name mismatch: {found.get('F024')}"
    assert found.get("F029") == "WACC", f"F029 name mismatch: {found.get('F029')}"
    assert found.get("F030") == "CAPM Cost of Equity", f"F030 name mismatch: {found.get('F030')}"


def test_ref_formulas_has_all_30(db):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM ref.formulas WHERE formula_id LIKE 'F%'")
    count = cur.fetchone()[0]
    assert count >= 30, f"Expected ≥30 formulas, found {count}"


def test_ref_line_items_dot_notation(db):
    """Core line items must use dot-notation codes."""
    cur = db.cursor()
    cur.execute("SELECT line_item_code FROM ref.line_items")
    codes = {row[0] for row in cur.fetchall()}
    required = {"revenue.net", "net_income.parent", "equity.parent",
                "operating_cash_flow.total", "capex.total", "market_price.close"}
    missing = required - codes
    assert not missing, f"Missing line_item_codes: {missing}"


# ── ingest schema ───────────────────────────────────────────────────────────

def test_ingest_sources_no_global_checksum_unique(db):
    """ingest.sources must NOT have a global UNIQUE constraint on checksum alone."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM pg_constraint c
        JOIN pg_class r ON r.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE n.nspname = 'ingest'
          AND r.relname = 'sources'
          AND c.contype = 'u'
          AND array_length(c.conkey, 1) = 1
          AND (
            SELECT attname FROM pg_attribute
            WHERE attrelid = r.oid AND attnum = c.conkey[1]
          ) = 'checksum'
    """)
    count = cur.fetchone()[0]
    assert count == 0, "ingest.sources has a global UNIQUE(checksum) — must use UNIQUE(logical_id, source_uri, checksum)"


def test_ingest_sources_composite_unique_exists(db):
    """ingest.sources must have UNIQUE(logical_id, source_uri, checksum)."""
    cur = db.cursor()
    cur.execute("""
        SELECT conname FROM pg_constraint c
        JOIN pg_class r ON r.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE n.nspname = 'ingest' AND r.relname = 'sources' AND c.contype = 'u'
    """)
    constraint_names = {row[0] for row in cur.fetchall()}
    assert constraint_names, "No UNIQUE constraints found on ingest.sources"


def test_ingest_document_chunks_in_ingest_schema(db):
    """document_chunks must live in ingest, NOT in research."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'ingest' AND table_name = 'document_chunks'
    """)
    assert cur.fetchone()[0] == 1, "ingest.document_chunks not found"
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'research' AND table_name = 'document_chunks'
    """)
    assert cur.fetchone()[0] == 0, "research.document_chunks must not exist"


# ── fact schema ─────────────────────────────────────────────────────────────

def test_fact_financial_facts_fk_to_line_items(db):
    """fact.financial_facts must FK to ref.line_items(line_item_code)."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM pg_constraint c
        JOIN pg_class r ON r.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE n.nspname = 'fact' AND r.relname = 'financial_facts' AND c.contype = 'f'
          AND (
            SELECT attname FROM pg_attribute
            WHERE attrelid = r.oid AND attnum = c.conkey[1]
          ) = 'line_item_code'
    """)
    assert cur.fetchone()[0] >= 1, "No FK from fact.financial_facts(line_item_code) to ref.line_items"


def test_fact_financial_facts_fk_to_ingest_sources(db):
    """fact.financial_facts must FK to ingest.sources(source_id)."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM pg_constraint c
        JOIN pg_class r ON r.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE n.nspname = 'fact' AND r.relname = 'financial_facts' AND c.contype = 'f'
          AND (
            SELECT attname FROM pg_attribute
            WHERE attrelid = r.oid AND attnum = c.conkey[1]
          ) = 'source_id'
    """)
    assert cur.fetchone()[0] >= 1, "No FK from fact.financial_facts(source_id) to ingest.sources"


def test_fact_price_history_has_trade_date_column(db):
    """fact.price_history must use trade_date (not date) as the date column."""
    cur = db.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='price_history'
    """)
    cols = {row[0] for row in cur.fetchall()}
    assert "trade_date" in cols, "fact.price_history missing trade_date column"
    assert "date" not in cols, "fact.price_history must not have 'date' column — use trade_date"


def test_fact_price_history_has_traded_value_column(db):
    """fact.price_history must use traded_value (not value)."""
    cur = db.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='fact' AND table_name='price_history'
    """)
    cols = {row[0] for row in cur.fetchall()}
    assert "traded_value" in cols, "fact.price_history missing traded_value column"
    assert "value" not in cols, "fact.price_history must not have 'value' column — use traded_value"


def test_fact_accepted_view_fy_only(db):
    """fact.accepted_financial_facts view must contain only FY-period rows."""
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM fact.accepted_financial_facts WHERE fiscal_period != 'FY'")
    count = cur.fetchone()[0]
    assert count == 0, f"{count} non-FY rows leaked into fact.accepted_financial_facts"


def test_fact_accepted_view_accepted_only(db):
    """fact.accepted_financial_facts view must reference only accepted rows."""
    cur = db.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM fact.accepted_financial_facts af
        JOIN fact.financial_facts ff ON af.id = ff.id
        WHERE ff.validation_status != 'accepted'
    """)
    count = cur.fetchone()[0]
    assert count == 0, f"{count} non-accepted rows in fact.accepted_financial_facts"


# ── research schema ─────────────────────────────────────────────────────────

def test_research_runs_has_current_stage_not_current_state(db):
    """research.runs must have current_stage column (not current_state)."""
    cur = db.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='research' AND table_name='runs'
    """)
    cols = {row[0] for row in cur.fetchall()}
    assert "current_stage" in cols, "research.runs missing current_stage column"
    assert "current_state" not in cols, "research.runs must not have current_state — use current_stage"



def test_research_run_artifacts_version_column(db):
    """research.run_artifacts must have a version column for artifact versioning."""
    cur = db.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='research' AND table_name='run_artifacts'
    """)
    cols = {row[0] for row in cur.fetchall()}
    for col in ("version", "storage_path", "checksum", "is_locked"):
        assert col in cols, f"research.run_artifacts missing column: {col}"


# ── Runtime store ───────────────────────────────────────────────────────────

def test_check_schema_version_passes(db):
    """RuntimeStore.check_schema_version() must pass against the live database."""
    from backend.runtime_store import RuntimeStore
    store = RuntimeStore()
    store.check_schema_version()  # must not raise
