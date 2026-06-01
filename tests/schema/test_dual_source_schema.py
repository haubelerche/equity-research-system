"""Phase 1 — Dual-Source Schema verification (adapted onto Data Trust Layer).

Verifies the acquisition layer (ingest.sources / raw_payloads) is kept separate from
the verification layer (ingest.official_documents + fact.canonical_facts verification
linkage), and that a provider-only fact cannot be marked final-verified.

Skipped automatically when DATABASE_URL is not set. All writes happen inside a
transaction that is rolled back, so the live DB is never mutated.

Run:
    pytest tests/schema/test_dual_source_schema.py -v
"""
from __future__ import annotations

import os
import uuid

import psycopg2
import psycopg2.errors
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB schema tests",
)

_TEST_TICKER = "DHG"          # exists in ref.companies
_TEST_METRIC = "revenue.net"  # exists in ref.line_items


@pytest.fixture()
def db():
    """Function-scoped connection that ALWAYS rolls back — never mutates the DB."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _insert_official_document(cur, fiscal_year: int, title: str) -> int:
    cur.execute(
        """
        INSERT INTO ingest.official_documents
        (ticker, company_name, source_type, source_tier, issuer, title,
         url, fiscal_year, language, file_hash, status)
        VALUES (%s, %s, 'audited_financial_statement', 0, %s, %s, %s, %s, 'vi', %s, 'extracted')
        RETURNING official_document_id
        """,
        (_TEST_TICKER, "CTCP Dược Hậu Giang", "DHG Pharma", title,
         "https://example.test/bctc.pdf", fiscal_year, "deadbeef" * 8),
    )
    return cur.fetchone()[0]


def _insert_canonical_fact(cur, *, official_document_id, reconciliation_status, source_id=None):
    fact_id = uuid.uuid4().hex
    cur.execute(
        """
        INSERT INTO fact.canonical_facts
        (fact_id, ticker, period, period_type, canonical_version, metric, value, unit,
         currency, reconciliation_status, official_document_id)
        VALUES (%s, %s, '2099FY', 'FY', %s, %s, 1234.5, 'vnd_bn', 'VND', %s, %s)
        """,
        (fact_id, _TEST_TICKER, f"vtest_{fact_id[:8]}", _TEST_METRIC,
         reconciliation_status, official_document_id),
    )
    return fact_id


# ── Test 1: acquisition source can store vnstock/VCI metadata ──────────────────

def test_acquisition_source_stores_vnstock_vci(db):
    cur = db.cursor()
    sid = "test_" + uuid.uuid4().hex
    cur.execute(
        """
        INSERT INTO ingest.sources
        (source_id, logical_id, ticker, source_type, source_uri, source_title,
         reliability_tier, source_tier, connector_version, checksum)
        VALUES (%s, %s, %s, 'vnstock_financial',
                'vnstock://vci/finance/income_statement/DHG?period=year',
                'Income Statement (VCI)', 2, 3, 'vnstock-3.2', %s)
        """,
        (sid, "DHG_income", _TEST_TICKER, uuid.uuid4().hex),
    )
    cur.execute("SELECT source_tier, source_uri FROM ingest.sources WHERE source_id=%s", (sid,))
    tier, uri = cur.fetchone()
    assert tier == 3, "vnstock/VCI acquisition source must be Tier 3"
    assert uri.startswith("vnstock://vci/"), "acquisition URI preserved"


# ── Test 2: official_document can store a BCTC/disclosure ───────────────────────

def test_official_document_stores_bctc(db):
    cur = db.cursor()
    doc_id = _insert_official_document(cur, 2023, "BCTC kiểm toán DHG 2023 [test]")
    cur.execute(
        "SELECT source_type, source_tier, ticker FROM ingest.official_documents "
        "WHERE official_document_id=%s",
        (doc_id,),
    )
    stype, tier, ticker = cur.fetchone()
    assert stype == "audited_financial_statement"
    assert tier == 0, "audited BCTC must be Tier 0"
    assert ticker == _TEST_TICKER


def test_official_document_rejects_tier3(db):
    """The verification layer must not accept a Tier-3 source (range CHECK 0..2)."""
    cur = db.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO ingest.official_documents
            (ticker, source_type, source_tier, title, fiscal_year)
            VALUES (%s, 'annual_report', 3, 'bad tier [test]', 2023)
            """,
            (_TEST_TICKER,),
        )


# ── Test 3 & 5: verified fact requires official_document_id ─────────────────────

def test_verified_fact_requires_official_document_id(db):
    """A fact cannot be marked matched_official without an official_document_id."""
    cur = db.cursor()
    with pytest.raises(psycopg2.errors.CheckViolation):
        _insert_canonical_fact(cur, official_document_id=None,
                               reconciliation_status="matched_official")


def test_provider_only_fact_cannot_be_final_verified(db):
    """Provider-only canonical fact (no official doc) cannot be flipped to verified."""
    cur = db.cursor()
    # Insert a provider-only fact: allowed, status missing_official.
    fact_id = _insert_canonical_fact(cur, official_document_id=None,
                                     reconciliation_status="missing_official")
    cur.execute("SELECT reconciliation_status FROM fact.canonical_facts WHERE fact_id=%s", (fact_id,))
    assert cur.fetchone()[0] == "missing_official"
    # Now try to flip it to matched_official WITHOUT linking an official doc → must fail.
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute(
            "UPDATE fact.canonical_facts SET reconciliation_status='matched_official' "
            "WHERE fact_id=%s",
            (fact_id,),
        )


# ── Test 4: verified fact may reference acquisition source + official doc ───────

def test_verified_fact_links_official_and_appears_in_view(db):
    cur = db.cursor()
    doc_id = _insert_official_document(cur, 2098, "BCTC kiểm toán DHG view-test")
    fact_id = _insert_canonical_fact(cur, official_document_id=doc_id,
                                     reconciliation_status="matched_official")
    # The fact must surface in the final-safe verified_financial_facts view.
    cur.execute(
        "SELECT official_document_title, official_source_tier, reconciliation_status "
        "FROM fact.verified_financial_facts WHERE fact_id=%s",
        (fact_id,),
    )
    row = cur.fetchone()
    assert row is not None, "verified fact must appear in fact.verified_financial_facts view"
    assert row[1] == 0, "view exposes official source tier"
    assert row[2] == "matched_official"


def test_missing_official_fact_excluded_from_verified_view(db):
    cur = db.cursor()
    fact_id = _insert_canonical_fact(cur, official_document_id=None,
                                     reconciliation_status="missing_official")
    cur.execute("SELECT 1 FROM fact.verified_financial_facts WHERE fact_id=%s", (fact_id,))
    assert cur.fetchone() is None, "provider-only fact must NOT appear in verified view"
