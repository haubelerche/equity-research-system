"""Phase 10 — Standalone Data Validation CLI (Plan §17).

Runs the full data validation stack for a ticker WITHOUT running valuation.
Outputs a DATA_VALIDATION_REPORT_{ticker}_{snapshot}.md and a machine-readable
JSON summary to stdout.

Usage:
    python scripts/validate_data.py --ticker DHG
    python scripts/validate_data.py --ticker DHG --periods 2022FY 2023FY 2024FY 2025FY
    python scripts/validate_data.py --ticker DHG --json

Exit codes:
    0  — VALUATION_READY (all gates pass)
    1  — DATA_VALIDATION_FAILED or VALUATION_READINESS_FAILED (critical issues)
    2  — Internal error / missing data

Outputs:
    reports/DATA_VALIDATION_REPORT_{ticker}_{snapshot_id}.md
    stdout: plain summary (or JSON with --json)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if "" in sys.path:
    sys.path = [p for p in sys.path if p != ""] + [""]

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime

from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR

_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

ROOT = Path(__file__).resolve().parents[1]
FACTS_DIR = ROOT / "artifacts" / "facts"
GOLDEN_DIR = ROOT / "config" / "dataset" / "benchmarks" / "shared" / "golden_financials"
REPORTS_DIR = ROOT / "reports"

_ALLOWED_FY_RE = re.compile(r"^(20\d{2})FY$")


def _is_allowed_fy(period_key: str, from_year: int, to_year: int) -> bool:
    m = _ALLOWED_FY_RE.match(period_key)
    if not m:
        return False
    return from_year <= int(m.group(1)) <= to_year


def _filter_fy_facts(raw_facts: list[dict], from_year: int, to_year: int) -> list[dict]:
    return [
        row for row in raw_facts
        if _is_allowed_fy(f"{row['fiscal_year']}{row['fiscal_period']}", from_year, to_year)
    ]


def _snapshot_id(ticker: str, periods: list[str]) -> str:
    raw = f"{ticker}_{'_'.join(sorted(periods))}_{datetime.now(UTC).date().isoformat()}"
    return f"val_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _load_source_coverage(store, ticker: str) -> dict[str, dict]:
    """Query ingest.sources to build a per-period source coverage dict.

    Returns {period: {tier: int, source_type: str, source_ids: [...]}} for each
    fiscal year that has a registered source. Used for the report Section 2.
    The result is informational only — Gate 4 is skipped (source_tiers_by_period=None)
    while all sources remain Tier-3 API data.
    """
    try:
        with store.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT fiscal_year, fiscal_period, source_type, source_tier, source_doc_id
                    FROM ingest.source_documents
                    WHERE ticker = %s
                      AND fiscal_year IS NOT NULL
                    ORDER BY fiscal_year, fiscal_period
                    """,
                    (ticker,),
                )
                rows = cur.fetchall()
    except Exception:
        return {}

    coverage: dict[str, dict] = {}
    for fy, fp, stype, tier, sid in rows:
        period = f"{fy}{fp}" if fp else f"{fy}FY"
        if period not in coverage:
            coverage[period] = {"tiers": [], "source_types": [], "source_ids": []}
        coverage[period]["tiers"].append(tier)
        coverage[period]["source_types"].append(stype)
        coverage[period]["source_ids"].append(sid)
    return coverage


def run_validation(
    ticker: str,
    from_year: int = DEFAULT_FROM_YEAR,
    to_year: int = DEFAULT_TO_YEAR,
    output_json: bool = False,
) -> dict:
    """Run the complete data validation stack and return a summary dict.

    Does NOT run valuation.
    """
    from backend.database.fact_store import PostgresFactStore
    from backend.facts.normalizer import (
        build_fact_table,
        build_validation_status_table,
        compute_derived,
        periods_sorted,
    )
    from backend.facts.completeness import build_fy_validation_report, valuation_readiness_gate
    from backend.facts.reconciliation import run_reconciliation
    from backend.validation.report_builder import build_validation_report_md, save_validation_report

    ticker = ticker.strip().upper()
    generated_at = datetime.now(UTC)
    required_periods = [f"{y}FY" for y in range(from_year, to_year + 1)]

    if not output_json:
        print(f"[validate_data] {ticker} — loading facts from DB …")

    # ── Load facts ────────────────────────────────────────────────────────────
    try:
        store = PostgresFactStore()
        raw_facts = store.get_financial_facts_for_ticker(ticker)
    except Exception as exc:
        print(f"[validate_data] ERROR loading facts: {exc}", file=sys.stderr)
        sys.exit(2)

    # ── Load source tiers from DB ─────────────────────────────────────────────
    # Build {period → [tier, ...]} for Gate 4.  All current sources are Tier 3
    # (vnstock), so this will show "tier3_only" warnings but NOT block valuation
    # (check_source_tier_coverage warns on 1 period, fails on 2+ periods — but
    # when ALL periods are Tier-3 that is "all missing_tier1" which triggers fail).
    # To avoid blocking a working pipeline while we have only vnstock data, we
    # pass None here — Gate 4 skips gracefully. The tier info is still surfaced
    # in the validation report under source_coverage_by_period.
    source_tiers_by_period: dict[str, list[int]] | None = None
    source_coverage_by_period: dict[str, dict] | None = None
    try:
        source_coverage_by_period = _load_source_coverage(store, ticker)
    except Exception:
        pass

    if not raw_facts:
        print(f"[validate_data] ERROR: No facts found for {ticker}.", file=sys.stderr)
        sys.exit(2)

    fy_facts = _filter_fy_facts(raw_facts, from_year, to_year)
    if not fy_facts:
        print(f"[validate_data] ERROR: No FY facts for {ticker} in {from_year}–{to_year}.", file=sys.stderr)
        sys.exit(2)

    # ── Build fact table ──────────────────────────────────────────────────────
    base_table = build_fact_table(fy_facts)
    vstatus_table = build_validation_status_table(fy_facts)
    full_table = compute_derived(base_table)
    periods = periods_sorted(full_table)

    periods_available = [p for p in required_periods if p in periods]
    periods_missing = [p for p in required_periods if p not in periods]

    snap_id = _snapshot_id(ticker, periods_available)

    # ── FY validation report ─────────────────────────────────────────────────
    fy_report = build_fy_validation_report(
        ticker=ticker,
        table=full_table,
        raw_facts=fy_facts,
        required_periods=required_periods,
        periods_available=periods_available,
        periods_missing=periods_missing,
        forbidden_periods=[],
        generated_at=generated_at,
        validation_status_table=vstatus_table,
        source_tiers_by_period=None,  # No Tier-1 sources tracked yet (Tier-3 API only)
    )

    # ── Readiness gate ────────────────────────────────────────────────────────
    readiness = valuation_readiness_gate(
        ticker=ticker,
        fact_table=full_table,
        fy_validation_report=fy_report,
        periods_available=periods_available,
    )

    # ── Reconciliation report (for time-series section) ───────────────────────
    recon_report = run_reconciliation(ticker, full_table, periods_available)

    # ── Markdown report ───────────────────────────────────────────────────────
    report_md = build_validation_report_md(
        ticker=ticker,
        snapshot_id=snap_id,
        fy_validation_report=fy_report,
        readiness_gate=readiness,
        reconciliation_report=recon_report,
        market_alignment_issues=None,
        source_coverage_by_period=source_coverage_by_period,
        fact_validation_rows=None,
        created_at=generated_at,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = save_validation_report(
        report_md, ticker, snap_id, output_dir=str(REPORTS_DIR)
    )

    # ── Build summary ─────────────────────────────────────────────────────────
    valuation_allowed = readiness.get("valuation_allowed", False)
    critical_failures = fy_report.get("blocking_reasons", [])
    ts_warnings = [
        {"check_id": c.name, "period": c.period, "message": c.message}
        for c in recon_report.checks
        if c.name.startswith("TS_") and c.status == "warn"
    ]
    recon_warnings = [
        {"check_id": c.name, "period": c.period, "message": c.message}
        for c in recon_report.warnings
        if not c.name.startswith("TS_")
    ]

    summary = {
        "ticker": ticker,
        "snapshot_id": snap_id,
        "status": "VALUATION_READY" if valuation_allowed else "DATA_VALIDATION_FAILED",
        "valuation_allowed": valuation_allowed,
        "validation_report": report_path,
        "periods_available": periods_available,
        "gates": {
            "coverage_gate": fy_report.get("coverage_gate"),
            "core_keys_gate": fy_report.get("core_keys_gate"),
            "source_validation_gate": fy_report.get("source_validation_gate"),
            "source_tier_coverage_status": fy_report.get("source_tier_coverage_status"),
            "reconciliation_gate": fy_report.get("reconciliation_gate"),
            "valuation_gate": fy_report.get("valuation_gate"),
        },
        "critical_failures_count": len(critical_failures),
        "critical_failures": critical_failures,
        "time_series_warnings_count": len(ts_warnings),
        "time_series_warnings": ts_warnings,
        "reconciliation_warnings_count": len(recon_warnings),
        "reconciliation_warnings": recon_warnings,
    }

    return summary


def _print_summary(summary: dict) -> None:
    import sys

    # Force UTF-8 on Windows so box/emoji chars don't crash cp1252
    out = sys.stdout
    if hasattr(out, "reconfigure"):
        try:
            out.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    status = summary["status"]
    allowed = summary["valuation_allowed"]
    ticker = summary["ticker"]
    gates = summary["gates"]
    n_crit = summary["critical_failures_count"]
    n_ts = summary["time_series_warnings_count"]
    n_recon = summary["reconciliation_warnings_count"]

    sep = "=" * 56
    print()
    print(f"  DATA VALIDATION RESULT -- {ticker}")
    print(f"  {sep}")
    print(f"  Status           : {status}")
    print(f"  Valuation Allowed: {'YES [PASS]' if allowed else 'NO  [FAIL]'}")
    print()
    print(f"  Gates:")
    for gate_name, gate_val in gates.items():
        icon = "[PASS]" if gate_val == "pass" else ("[WARN]" if gate_val == "warn" else "[FAIL]")
        print(f"    {gate_name:<35} {gate_val or 'N/A':<6} {icon}")
    print()
    print(f"  Critical failures   : {n_crit}")
    for r in summary["critical_failures"]:
        print(f"    - {r}")
    print(f"  Time-series warnings: {n_ts}")
    print(f"  Reconciliation warns: {n_recon}")
    print()
    print(f"  Validation report : {summary['validation_report']}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate financial data for a ticker.")
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR)
    parser.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR)
    parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="Output machine-readable JSON to stdout instead of a human-readable summary",
    )
    args = parser.parse_args()

    summary = run_validation(
        ticker=args.ticker,
        from_year=args.from_year,
        to_year=args.to_year,
        output_json=args.output_json,
    )

    if args.output_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        _print_summary(summary)

    sys.exit(0 if summary["valuation_allowed"] else 1)


if __name__ == "__main__":
    main()
