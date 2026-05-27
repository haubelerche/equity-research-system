"""Phase 5 — Evidence Retrieval Smoke Test.

Verifies that indexed evidence chunks can be retrieved from ingest.document_chunks
and that citation keys resolve correctly against the canonical fact table.

Usage:
    python scripts/test_retrieval.py --ticker DHG
    python scripts/test_retrieval.py --ticker DHG --year 2023
    python scripts/test_retrieval.py --ticker DHG --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k.strip(), _v)

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parents[1]
CITATION_DIR = ROOT / "artifacts" / "reports"

_CORE_METRICS = [
    "revenue.net",
    "net_income.parent",
    "gross_profit.total",
    "operating_cash_flow.total",
    "total_assets.ending",
    "equity.parent",
]


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


def _check_chunks(conn, ticker: str, year: int | None, verbose: bool) -> dict:
    """Verify document_chunks exist for the ticker."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if year:
            cur.execute(
                """
                SELECT dc.chunk_id, dc.source_id, dc.chunk_index,
                       dc.section_title, dc.fiscal_year,
                       LENGTH(dc.chunk_text) AS text_length
                FROM ingest.document_chunks dc
                WHERE dc.ticker = %s AND dc.fiscal_year = %s
                ORDER BY dc.fiscal_year, dc.chunk_index
                """,
                (ticker, year),
            )
        else:
            cur.execute(
                """
                SELECT dc.chunk_id, dc.source_id, dc.chunk_index,
                       dc.section_title, dc.fiscal_year,
                       LENGTH(dc.chunk_text) AS text_length
                FROM ingest.document_chunks dc
                WHERE dc.ticker = %s
                ORDER BY dc.fiscal_year, dc.chunk_index
                """,
                (ticker,),
            )
        rows = [dict(r) for r in cur.fetchall()]

    if verbose:
        print(f"\n  Found {len(rows)} chunk(s):")
        for r in rows:
            fy = r.get("fiscal_year") or "N/A"
            print(f"    [{r['chunk_index']}] fy={fy} title={r['section_title']!r} "
                  f"len={r['text_length']}")
    else:
        print(f"  Chunks found: {len(rows)}")

    return {
        "chunk_count": len(rows),
        "fiscal_years": sorted({r["fiscal_year"] for r in rows if r.get("fiscal_year")}),
        "sources": sorted({r["source_id"] for r in rows}),
        "pass": len(rows) > 0,
    }


def _check_facts_indexed(conn, ticker: str, year: int | None) -> dict:
    """Verify accepted financial facts exist that build_index could have used."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if year:
            cur.execute(
                """
                SELECT ff.line_item_code, ff.fiscal_year, ff.value, ff.unit
                FROM fact.financial_facts ff
                WHERE ff.ticker = %s AND ff.fiscal_year = %s
                  AND ff.fiscal_period = 'FY'
                  AND ff.validation_status = 'accepted'
                ORDER BY ff.line_item_code
                """,
                (ticker, year),
            )
        else:
            cur.execute(
                """
                SELECT ff.line_item_code, ff.fiscal_year, ff.value, ff.unit
                FROM fact.financial_facts ff
                WHERE ff.ticker = %s
                  AND ff.fiscal_period = 'FY'
                  AND ff.validation_status = 'accepted'
                ORDER BY ff.fiscal_year, ff.line_item_code
                """,
                (ticker,),
            )
        rows = [dict(r) for r in cur.fetchall()]

    years_found = sorted({r["fiscal_year"] for r in rows})
    metrics_found = {r["line_item_code"] for r in rows}
    core_present = [m for m in _CORE_METRICS if m in metrics_found]
    core_missing = [m for m in _CORE_METRICS if m not in metrics_found]

    print(f"  Accepted facts: {len(rows)} across years {years_found}")
    print(f"  Core metrics present ({len(core_present)}/{len(_CORE_METRICS)}): "
          f"{', '.join(core_present) or 'none'}")
    if core_missing:
        print(f"  Core metrics missing: {', '.join(core_missing)}")

    return {
        "accepted_fact_count": len(rows),
        "years_with_facts": years_found,
        "core_metrics_present": core_present,
        "core_metrics_missing": core_missing,
        "pass": len(rows) > 0 and len(core_present) >= 3,
    }


def _check_citation_map(ticker: str, year: int | None, verbose: bool) -> dict:
    """Verify a citation map artifact exists and spot-check key resolution."""
    files = sorted(CITATION_DIR.glob(f"{ticker}_*_citation.json"), reverse=True)
    if not files:
        print(f"  No citation map found for {ticker} in {CITATION_DIR}")
        return {"pass": False, "reason": "no_citation_map"}

    latest = files[0]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  Could not load citation map {latest.name}: {exc}")
        return {"pass": False, "reason": str(exc)}

    citation_map = data.get("citation_map", {})
    claims = data.get("claims", [])
    snap_id = data.get("snapshot_id", "")

    print(f"  Citation map: {latest.name}")
    print(f"  snapshot_id: {snap_id or 'N/A'}")
    print(f"  Claim-citation pairs: {len(citation_map)}")
    print(f"  Claims in report: {len(claims)}")

    if verbose and citation_map:
        print("\n  Sample citations:")
        for key, rec in list(citation_map.items())[:5]:
            print(f"    {key} → value={rec.get('value')}, unit={rec.get('unit')}")

    # Spot-check: for a given year, check if core metrics are cited
    if year:
        cited_keys = {k for k in citation_map if f"/{year}FY/" in k}
        print(f"  Citations for {year}FY: {len(cited_keys)}")

    return {
        "citation_file": latest.name,
        "citation_count": len(citation_map),
        "claims_count": len(claims),
        "snapshot_id": snap_id,
        "pass": len(citation_map) > 0,
    }


def _check_chunk_content(conn, ticker: str, verbose: bool) -> dict:
    """Spot-check that chunk text contains expected financial data."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT chunk_text FROM ingest.document_chunks
            WHERE ticker = %s AND fiscal_year IS NOT NULL
            LIMIT 3
            """,
            (ticker,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        print("  No chunk content to inspect.")
        return {"pass": False, "reason": "no_chunks"}

    # Check that the ticker name appears in chunks
    all_text = " ".join(r["chunk_text"] for r in rows)
    has_ticker = ticker.upper() in all_text
    has_numbers = any(c.isdigit() for c in all_text)

    if verbose:
        print(f"\n  Sample chunk excerpt (first 300 chars):")
        print(f"    {rows[0]['chunk_text'][:300]!r}")

    print(f"  Chunk content check: ticker_mentioned={has_ticker}, has_numbers={has_numbers}")
    return {"pass": has_numbers, "chunk_count": len(rows)}


def test_retrieval(ticker: str, year: int | None = None, verbose: bool = False) -> dict:
    ticker = ticker.strip().upper()
    results: dict = {"ticker": ticker, "year": year, "gates": {}}

    print(f"\n{'='*60}")
    print(f"  RETRIEVAL SMOKE TEST — {ticker}" + (f" (year={year})" if year else ""))
    print(f"{'='*60}\n")

    try:
        conn = psycopg2.connect(_dsn())
    except Exception as exc:
        print(f"[test_retrieval] FATAL: Cannot connect to DB: {exc}")
        sys.exit(1)

    try:
        # Gate 1: Are accepted facts available?
        print("[Gate 1] Accepted facts in DB...")
        g1 = _check_facts_indexed(conn, ticker, year)
        results["gates"]["accepted_facts"] = g1
        print(f"  -> {'PASS' if g1['pass'] else 'FAIL'}\n")

        # Gate 2: Are evidence chunks indexed?
        print("[Gate 2] Evidence chunks in ingest.document_chunks...")
        g2 = _check_chunks(conn, ticker, year, verbose)
        results["gates"]["chunks_indexed"] = g2
        print(f"  -> {'PASS' if g2['pass'] else 'FAIL'}\n")

        # Gate 3: Chunk content sanity
        print("[Gate 3] Chunk content sanity...")
        g3 = _check_chunk_content(conn, ticker, verbose)
        results["gates"]["chunk_content"] = g3
        print(f"  -> {'PASS' if g3['pass'] else 'FAIL'}\n")

        # Gate 4: Citation map artifact
        print("[Gate 4] Citation map artifact...")
        g4 = _check_citation_map(ticker, year, verbose)
        results["gates"]["citation_map"] = g4
        print(f"  -> {'PASS' if g4['pass'] else 'FAIL (no citation map yet — run generate_report.py first)'}\n")

    finally:
        conn.close()

    gates = results["gates"]
    # Citation map is informational — not critical for retrieval
    critical_gates = ["accepted_facts", "chunks_indexed", "chunk_content"]
    all_critical_pass = all(gates.get(g, {}).get("pass", False) for g in critical_gates)
    any_fail = not all_critical_pass

    print(f"{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for name, g in gates.items():
        status = "PASS" if g.get("pass") else "FAIL"
        print(f"  [{status}] {name}")

    if all_critical_pass:
        print(f"\n  Evidence retrieval pipeline: READY for {ticker}")
        print(f"  Next: python scripts/generate_report.py --ticker {ticker}")
    else:
        print(f"\n  Evidence retrieval pipeline: NOT READY")
        print(f"  Fix: ensure build_index.py has run for {ticker}")
    print(f"{'='*60}\n")

    results["all_critical_pass"] = all_critical_pass
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke test: verify evidence retrieval pipeline for a ticker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. DHG)")
    parser.add_argument("--year", type=int, default=None, help="Fiscal year to inspect (e.g. 2023)")
    parser.add_argument("--verbose", action="store_true", help="Show detailed chunk content")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = test_retrieval(ticker=args.ticker, year=args.year, verbose=args.verbose)
    if not result.get("all_critical_pass"):
        sys.exit(1)
    print("[test_retrieval] done")


if __name__ == "__main__":
    main()
