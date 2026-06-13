"""Unified ingestion entry point for a single ticker.

Usage:
    python scripts/ingest_ticker.py --ticker DHG --years 5
    python scripts/ingest_ticker.py --ticker IMP --years 3 --skip-catalysts

Requires:
    DATABASE_URL env var pointing to Supabase PostgreSQL
    vnstock installed (pip install vnstock)
"""
from __future__ import annotations

# Ensure the project root is on sys.path (needed when script is run directly).
import sys as _sys
from pathlib import Path as _Path
_PROJECT_ROOT = str(_Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
# Reorder so site-packages comes before '' (CWD) to prevent local vnstock/ shadowing pip package.
if "" in _sys.path:
    _sys.path = [p for p in _sys.path if p != ""] + [""]

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR

# Auto-load .env if present (allows running without exporting DATABASE_URL manually)
_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "artifacts" / "runs"

def _load_universe_segment(ticker: str) -> str:
    from backend.dataset.config_io import load_universe_rows

    for row in load_universe_rows():
        if row["ticker"].strip().upper() == ticker.upper():
            return row.get("segment", "pharma")
    return "pharma"


def _ingest_financials(
    ticker: str,
    store: Any,
    registry: Any,
    period: str = "year",
    from_year: int = DEFAULT_FROM_YEAR,
    to_year: int = DEFAULT_TO_YEAR,
    provider: str = "auto",
) -> dict[str, Any]:
    from scripts.connectors.vnstock_finance_connector import sync_financial_for_ticker
    from backend.database.canonical.fact_promotion import promote_accepted_facts

    try:
        inserted = sync_financial_for_ticker(
            ticker=ticker, store=store, registry=registry,
            period=period, from_year=from_year, to_year=to_year, provider=provider,
        )
        # v2 pipeline: observations were written by the connector; promote the
        # winner per (period, metric) into fact.canonical_facts so build_facts /
        # valuation can read them.
        promo = promote_accepted_facts(ticker=ticker, from_year=from_year, to_year=to_year)
        return {
            "status": "ok", "facts_upserted": inserted,
            "facts_promoted": promo.promoted,
            "promotion_skipped_low_confidence": promo.skipped_low_confidence,
            "promotion_warnings": promo.warnings[:10],
            "period": period, "from_year": from_year, "to_year": to_year, "provider": provider,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc), "facts_upserted": 0}


def _ingest_price(ticker: str, days_back: int, store: Any, registry: Any) -> dict[str, Any]:
    from scripts.connectors.vnstock_price_connector import sync_ticker_price

    end = datetime.now(UTC).date()
    start = end - timedelta(days=days_back)
    try:
        inserted = sync_ticker_price(ticker=ticker, start=start, end=end, store=store, registry=registry)
        return {"status": "ok", "rows_upserted": inserted, "start": start.isoformat(), "end": end.isoformat()}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc), "rows_upserted": 0}


def _ingest_company(ticker: str, segment: str, store: Any, registry: Any) -> dict[str, Any]:
    from scripts.connectors.vnstock_company_connector import sync_company_ticker

    try:
        stats = sync_company_ticker(ticker=ticker, segment=segment, store=store, registry=registry)
        return {"status": "ok", **stats}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


def _ingest_catalysts(ticker: str, store: Any, registry: Any) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for connector_name, module_path, fn_name in [
        ("hose", "scripts.connectors.catalyst_hose_connector", "sync_hose_for_ticker"),
        ("bhyt", "scripts.connectors.catalyst_bhyt_connector", "sync_bhyt_for_ticker"),
        ("tender", "scripts.connectors.catalyst_tender_connector", "sync_tender_for_ticker"),
        ("dav", "scripts.connectors.catalyst_dav_connector", "sync_dav_for_ticker"),
    ]:
        try:
            import importlib

            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name, None)
            if fn is None:
                results[connector_name] = {"status": "skipped", "reason": f"{fn_name} not found"}
                continue
            stats = fn(ticker=ticker, store=store, registry=registry)
            results[connector_name] = {"status": "ok", **(stats if isinstance(stats, dict) else {"result": stats})}
        except Exception as exc:  # noqa: BLE001
            results[connector_name] = {"status": "error", "error": str(exc)}
    return results


def _run_debug_coverage(ticker: str, years: int) -> dict[str, Any]:
    """Run the coverage debug script for one ticker and return completeness summary."""
    try:
        import importlib
        mod = importlib.import_module("scripts.debug_vnstock_financial_coverage")
        rows = mod.probe_ticker(ticker=ticker, years=years, verbose=False)
        completeness = mod._build_ticker_completeness(ticker=ticker, probe_rows=rows, years=years)
        return {"status": "ok", "overall_status": completeness["overall_status"], "statements": completeness["statements"]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


def _check_strict_completeness(financials: dict[str, Any]) -> bool:
    """Return True if financials meet the strict completeness gate (facts_upserted > 0 and no error)."""
    return financials.get("status") == "ok" and financials.get("facts_upserted", 0) > 0


def ingest_ticker(
    ticker: str,
    years: int,
    skip_catalysts: bool = False,
    period: str = "year",
    from_year: int = DEFAULT_FROM_YEAR,
    to_year: int = DEFAULT_TO_YEAR,
    provider: str = "auto",
    debug_coverage: bool = False,
    strict_completeness: bool = False,
) -> dict[str, Any]:
    from backend.database.fact_store import PostgresFactStore
    from backend.database.source_registry import SourceRegistry

    if period == "quarter":
        print(
            "[ingest] ERROR: Quarterly financial ingestion is disabled for MVP. Use --period year only."
        )
        sys.exit(1)

    ticker = ticker.strip().upper()
    days_back = years * 365
    segment = _load_universe_segment(ticker)

    store = PostgresFactStore()
    registry = SourceRegistry(store=store)

    started_at = datetime.now(UTC)
    print(
        f"[ingest] {ticker} — start "
        f"(period={period}, from_year={from_year}, to_year={to_year}, provider={provider})"
    )

    # Optional: run empirical coverage probe first
    coverage_result: dict[str, Any] = {}
    if debug_coverage:
        print(f"[ingest] {ticker} running coverage probe ...")
        coverage_result = _run_debug_coverage(ticker=ticker, years=years)
        print(f"[ingest] {ticker} coverage: {coverage_result.get('overall_status', 'unknown')}")

    financials = _ingest_financials(
        ticker=ticker, store=store, registry=registry,
        period=period, from_year=from_year, to_year=to_year, provider=provider,
    )
    print(f"[ingest] {ticker} financials: {financials}")

    price = _ingest_price(ticker=ticker, days_back=days_back, store=store, registry=registry)
    print(f"[ingest] {ticker} price: {price}")

    company = _ingest_company(ticker=ticker, segment=segment, store=store, registry=registry)
    print(f"[ingest] {ticker} company: {company}")

    catalysts: dict[str, Any] = {}
    if not skip_catalysts:
        catalysts = _ingest_catalysts(ticker=ticker, store=store, registry=registry)
        print(f"[ingest] {ticker} catalysts: {catalysts}")

    finished_at = datetime.now(UTC)
    elapsed_s = (finished_at - started_at).total_seconds()

    has_error = any(
        r.get("status") == "error"
        for r in [financials, price, company, *catalysts.values()]
    )

    # Strict completeness gate: exit non-zero if financial facts are missing.
    if strict_completeness and not _check_strict_completeness(financials):
        print(
            f"[ingest] STRICT COMPLETENESS FAIL — {ticker} financials: "
            f"facts_upserted={financials.get('facts_upserted', 0)} status={financials.get('status')}"
        )
        sys.exit(2)

    inventory: dict[str, Any] = {
        "ticker": ticker,
        "years_requested": years,
        "period": period,
        "from_year": from_year,
        "to_year": to_year,
        "provider": provider,
        "segment": segment,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "elapsed_s": round(elapsed_s, 2),
        "overall_status": "partial_error" if has_error else "ok",
        "financials": financials,
        "price": price,
        "company": company,
        "catalysts": catalysts,
        **({"coverage": coverage_result} if coverage_result else {}),
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = started_at.strftime("%Y%m%dT%H%M%S")
    out_path = ARTIFACTS_DIR / f"{ticker}_{ts}_inventory.json"
    out_path.write_text(json.dumps(inventory, indent=2, default=str), encoding="utf-8")
    print(f"[ingest] inventory saved: {out_path}")

    return inventory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest all available data for a single VN pharma ticker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument("--years", type=int, default=5, help="Years of price history to sync")
    parser.add_argument("--skip-catalysts", action="store_true", help="Skip catalyst connectors")
    parser.add_argument(
        "--period",
        choices=["year", "quarter"],
        default="year",
        help="Financial period type. MVP only accepts 'year' — 'quarter' is blocked.",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=DEFAULT_FROM_YEAR,
        dest="from_year",
        help=f"First fiscal year to target (default: {DEFAULT_FROM_YEAR}).",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=DEFAULT_TO_YEAR,
        dest="to_year",
        help=f"Last fiscal year to target (default: {DEFAULT_TO_YEAR}).",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        help="vnstock provider: 'auto' tries VCI then KBS; or specify 'VCI' / 'KBS' directly.",
    )
    parser.add_argument(
        "--debug-coverage",
        action="store_true",
        help="Run empirical coverage probe before ingestion and include results in inventory.",
    )
    parser.add_argument(
        "--strict-completeness",
        action="store_true",
        help="Exit with code 2 if no financial facts were upserted.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = ingest_ticker(
        ticker=args.ticker,
        years=args.years,
        skip_catalysts=args.skip_catalysts,
        period=args.period,
        from_year=args.from_year,
        to_year=args.to_year,
        provider=args.provider,
        debug_coverage=args.debug_coverage,
        strict_completeness=args.strict_completeness,
    )
    status = result["overall_status"]
    print(f"\n[ingest] done — status={status}")
    if status not in ("ok", "partial_error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
