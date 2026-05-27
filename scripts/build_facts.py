"""Phase 3 — Canonical Facts and Data Quality Gates.

Reads ingested financial facts from PostgreSQL, filters to FY-only periods
within the required MVP range (2021–2025), scores completeness, and saves
a structured fact-report artifact.

Usage:
    PYTHONUTF8=1 python scripts/build_facts.py --ticker DHG
    PYTHONUTF8=1 python scripts/build_facts.py --ticker DHG --strict-completeness
    PYTHONUTF8=1 python scripts/build_facts.py --ticker DHG --from-year 2021 --to-year 2025

Outputs:
    artifacts/facts/{ticker}_{timestamp}_fact_report.json
    stdout: completeness / freshness summary
"""
from __future__ import annotations

import re
import sys as _sys
from pathlib import Path as _Path

_PROJECT_ROOT = str(_Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
if "" in _sys.path:
    _sys.path = [p for p in _sys.path if p != ""] + [""]

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_env_file = _Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

ROOT = _Path(__file__).resolve().parents[1]
FACTS_DIR = ROOT / "artifacts" / "facts"
GOLDEN_DIR = ROOT / "dataset" / "golden" / "financials"

MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025

# Only accept "YYYYFY" where YYYY is in [2021, 2025]
_ALLOWED_FY_RE = re.compile(r"^(20\d{2})FY$")


def _is_allowed_fy(period_key: str, from_year: int, to_year: int) -> bool:
    m = _ALLOWED_FY_RE.match(period_key)
    if not m:
        return False
    return from_year <= int(m.group(1)) <= to_year


def _filter_facts(
    raw_facts: list[dict],
    from_year: int,
    to_year: int,
) -> tuple[list[dict], list[str]]:
    """Split raw_facts into (fy_only_facts, forbidden_period_keys).

    fy_only_facts: rows whose fiscal_period == 'FY' and fiscal_year in [from_year, to_year]
    forbidden_period_keys: unique period strings that were present but excluded
    """
    fy_facts: list[dict] = []
    forbidden_set: set[str] = set()
    for row in raw_facts:
        period_key = f"{row['fiscal_year']}{row['fiscal_period']}"
        if _is_allowed_fy(period_key, from_year, to_year):
            fy_facts.append(row)
        else:
            forbidden_set.add(period_key)
    return fy_facts, sorted(forbidden_set)


def _load_golden_fallback(
    ticker: str,
    from_year: int,
    to_year: int,
) -> list[dict]:
    """Load annual FY facts from dataset/golden/financials/{ticker}.csv.

    Only rows with period matching YYYYFY and fiscal_year in [from_year, to_year]
    are included.  Quarterly rows are silently skipped.
    Returns a list of dicts in the same shape as DB rows from fact_store.
    """
    import csv
    from datetime import UTC, datetime

    golden_path = GOLDEN_DIR / f"{ticker.upper()}.csv"
    if not golden_path.exists():
        return []

    facts: list[dict] = []
    now = datetime.now(UTC)
    with golden_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            period = row.get("period", "").strip()
            m = _ALLOWED_FY_RE.match(period)
            if not m:
                continue
            fy = int(m.group(1))
            if not (from_year <= fy <= to_year):
                continue
            try:
                value = float(row["value"])
            except (ValueError, KeyError):
                continue
            facts.append({
                "line_item_code": row["canonical_key"].strip(),
                "fiscal_year": fy,
                "fiscal_period": "FY",
                "value": value,
                "unit": row.get("unit", "vnd_bn").strip(),
                "currency": row.get("currency", "VND").strip(),
                "source_id": f"golden_csv_{ticker}_{fy}FY",
                "connector_version": "golden_csv_v1",
                "validation_status": row.get("validation_status", "needs_review").strip(),
                "confidence": float(row.get("confidence") or 0.75),
                "ingested_at": now,
            })
    return facts


def build_facts(
    ticker: str,
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    strict_completeness: bool = False,
) -> dict:
    from scripts.db.fact_store import PostgresFactStore
    from backend.facts.normalizer import build_fact_table, build_validation_status_table, compute_derived, periods_sorted
    from backend.facts.completeness import build_fy_validation_report

    ticker = ticker.strip().upper()
    generated_at = datetime.now(UTC)
    required_years = list(range(from_year, to_year + 1))
    required_periods = [f"{y}FY" for y in required_years]

    print(f"[build_facts] {ticker} — period_mode=year")
    print(f"[build_facts] {ticker} required periods: {', '.join(required_periods)}")

    store = PostgresFactStore()
    raw_facts = store.get_financial_facts_for_ticker(ticker)

    if not raw_facts:
        print(f"[build_facts] ERROR: No facts found for {ticker}. Run ingest_ticker.py first.")
        sys.exit(1)

    print(f"[build_facts] {ticker} — {len(raw_facts)} raw fact rows loaded from DB")

    # Merge golden fallback (adds years the API cannot provide, e.g. 2021FY)
    golden_facts = _load_golden_fallback(ticker=ticker, from_year=from_year, to_year=to_year)
    if golden_facts:
        golden_periods = sorted({f"{r['fiscal_year']}FY" for r in golden_facts})
        print(f"[build_facts] {ticker} golden fallback: {len(golden_facts)} facts for periods {golden_periods}")
        raw_facts = raw_facts + golden_facts
    else:
        print(f"[build_facts] {ticker} no golden fallback found at {GOLDEN_DIR / (ticker + '.csv')}")

    # Separate FY-only facts from forbidden periods
    fy_facts, forbidden_periods = _filter_facts(raw_facts, from_year, to_year)

    if forbidden_periods:
        print(f"[build_facts] {ticker} forbidden quarterly periods ignored: {', '.join(forbidden_periods)}")
    print(f"[build_facts] {ticker} — {len(fy_facts)} facts remain after FY-only filter")

    if not fy_facts:
        print(
            f"[build_facts] ERROR: No FY facts found for {ticker} in {from_year}–{to_year}. "
            "Re-ingest with --period year --from-year / --to-year."
        )
        sys.exit(1)

    # Build fact table from FY-only data
    base_table = build_fact_table(fy_facts)
    vstatus_table = build_validation_status_table(fy_facts)
    full_table = compute_derived(base_table)
    periods = periods_sorted(full_table)

    periods_available = [p for p in required_periods if p in periods]
    periods_missing = [p for p in required_periods if p not in periods]

    print(f"[build_facts] {ticker} periods available: {', '.join(periods_available) or 'none'}")
    if periods_missing:
        print(f"[build_facts] {ticker} periods missing: {', '.join(periods_missing)}")

    latest_fy = max((int(p[:4]) for p in periods_available), default=None)
    print(f"[build_facts] {ticker} latest fiscal year: {latest_fy}")

    # Build FY-aware validation report
    report = build_fy_validation_report(
        ticker=ticker,
        table=full_table,
        raw_facts=fy_facts,
        required_periods=required_periods,
        periods_available=periods_available,
        periods_missing=periods_missing,
        forbidden_periods=forbidden_periods,
        generated_at=generated_at,
        validation_status_table=vstatus_table,
    )

    print(f"[build_facts] {ticker} annual_reports_collected: {report['annual_reports_collected']}")
    print(f"[build_facts] {ticker} coverage_gate: {report['coverage_gate']}")
    print(f"[build_facts] {ticker} core_keys_gate: {report['core_keys_gate']}")
    print(f"[build_facts] {ticker} source_validation_gate: {report['source_validation_gate']}")
    print(f"[build_facts] {ticker} valuation_gate: {report['valuation_gate']}")
    print(f"[build_facts] {ticker} valuation_ready: {report['valuation_ready']}")
    print(f"[build_facts] {ticker} run_status: {report['run_status']}")
    if report.get("blocking_reasons"):
        for reason in report["blocking_reasons"]:
            print(f"[build_facts] {ticker} BLOCKED: {reason}")

    # Print fact table
    print(f"\n[build_facts] Fact table (base facts):")
    for key in sorted(base_table.keys()):
        values = base_table[key]
        row_str = "  ".join(f"{p}={v:,.1f}" for p, v in sorted(values.items()))
        print(f"  {key:<35} {row_str}")

    print(f"\n[build_facts] Derived metrics:")
    derived_keys = [k for k in full_table if k not in base_table]
    for key in sorted(derived_keys):
        values = full_table[key]
        row_str = "  ".join(f"{p}={v:.4f}" for p, v in sorted(values.items()))
        print(f"  {key:<35} {row_str}")

    artifact = {
        "ticker": ticker,
        "generated_at": generated_at.isoformat(),
        "source": "financial_facts (PostgreSQL)",
        "period_mode": "year",
        "from_year": from_year,
        "to_year": to_year,
        "required_periods": required_periods,
        "periods_available": periods_available,
        "periods_missing": periods_missing,
        "forbidden_periods_ignored": forbidden_periods,
        "facts": {k: dict(sorted(v.items())) for k, v in sorted(full_table.items())},
        "validation": report,
    }

    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = generated_at.strftime("%Y%m%dT%H%M%S")
    out_path = FACTS_DIR / f"{ticker}_{ts}_fact_report.json"
    out_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\n[build_facts] Artifact saved: {out_path}")

    # Persist DQ gate summary to DB
    try:
        from backend.dataops.quality_report import persist_dq_report
        dq_id = persist_dq_report(ticker=ticker, report=report, from_year=from_year, to_year=to_year)
        print(f"[build_facts] DQ report persisted: id={dq_id}")
    except Exception as _exc:  # noqa: BLE001
        print(f"[build_facts] WARNING: DQ report persistence skipped: {_exc}")

    # Create research snapshot if valuation gate passed
    if report.get("valuation_gate") == "pass":
        try:
            from backend.dataops.snapshot import create_snapshot
            snap = create_snapshot(ticker=ticker, from_year=from_year, to_year=to_year, created_by="build_facts")
            artifact["snapshot_id"] = snap["snapshot_id"]
            print(f"[build_facts] Snapshot created: {snap['snapshot_id']} ({snap['facts_count']} facts, periods={snap['periods']})")
        except Exception as _exc:  # noqa: BLE001
            print(f"[build_facts] WARNING: snapshot creation skipped: {_exc}")

    if strict_completeness and report["valuation_gate"] != "pass":
        print(
            f"[build_facts] STRICT COMPLETENESS FAIL — "
            f"valuation_gate={report['valuation_gate']} reasons={report.get('blocking_reasons', [])}"
        )
        sys.exit(2)

    return artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical fact report for a ticker (FY-only, 2021–2025).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument(
        "--from-year",
        type=int,
        default=MVP_FROM_YEAR,
        dest="from_year",
        help=f"First required fiscal year (default: {MVP_FROM_YEAR}).",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=MVP_TO_YEAR,
        dest="to_year",
        help=f"Last required fiscal year (default: {MVP_TO_YEAR}).",
    )
    parser.add_argument(
        "--strict-completeness",
        action="store_true",
        help="Exit code 2 if valuation_gate != pass (coverage < 3 FY periods, missing core keys, or unaccepted facts).",
    )
    # Legacy alias kept for backward compat
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Alias for --strict-completeness.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_facts(
        ticker=args.ticker,
        from_year=args.from_year,
        to_year=args.to_year,
        strict_completeness=args.strict_completeness or args.strict,
    )
    print("\n[build_facts] done")


if __name__ == "__main__":
    main()
