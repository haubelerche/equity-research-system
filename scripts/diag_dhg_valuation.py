"""Read-only DHG valuation diagnostic.

Does NOT run the pipeline, ingestion, OCR, or any LLM. It only:
  1. loads DHG production facts (vnstock + additive OCR) into a FactTable;
  2. runs the real run_valuation_preflight;
  3. reports which methods are ready/blocked and on exactly which fields;
  4. optionally fetches the current market price (vnstock VCI / CafeF fallback)
     to show how market_price availability flips the relative/target methods.

Usage:
    python scripts/diag_dhg_valuation.py --ticker DHG
    python scripts/diag_dhg_valuation.py --ticker DHG --no-market   # skip network price
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="DHG")
    parser.add_argument("--from-year", type=int, default=2022, dest="from_year")
    parser.add_argument("--to-year", type=int, default=2025, dest="to_year")
    parser.add_argument("--no-market", action="store_true", dest="no_market")
    args = parser.parse_args(argv)
    ticker = args.ticker.upper()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default
    except Exception:  # noqa: BLE001
        pass

    from backend.valuation.input_pack_builder import _load_fact_table_from_production
    from backend.valuation.data_availability import run_valuation_preflight

    print(f"=== {ticker} production facts ({args.from_year}-{args.to_year}) ===")
    fact_table = _load_fact_table_from_production(ticker, args.from_year, args.to_year)
    fy_periods = sorted({p for vals in fact_table.values() for p in vals if p.endswith("FY")})
    print(f"FY periods present: {fy_periods or '(none)'}")
    print(f"distinct metrics  : {len(fact_table)}")

    latest = fy_periods[-1] if fy_periods else None
    valuation_keys = [
        "shares_outstanding.ending", "shares_outstanding.weighted_avg",
        "total_debt.total", "short_term_debt.total", "long_term_debt.total",
        "proceeds_from_borrowings.total", "repayment_of_borrowings.total",
        "cash_and_equivalents.total", "capex.total", "operating_cash_flow.total",
        "net_income.total", "revenue.net", "ebit.total", "depreciation_amortization.total",
        "interest_expense.total", "tax_expense.total",
    ]
    if latest:
        print(f"\n--- valuation-critical metrics @ {latest} ---")
        for k in valuation_keys:
            entry = fact_table.get(k, {}).get(latest)
            val = getattr(entry, "value", None) if entry is not None else None
            tier = getattr(entry, "source_tier", None) if entry is not None else None
            mark = "OK " if val is not None else "MISS"
            print(f"  [{mark}] {k:<38} value={val} tier={tier}")

    current_price = None
    if not args.no_market:
        try:
            from backend.reporting.market_snapshot import get_market_snapshot

            snap = get_market_snapshot(ticker, persist=False, base_dir=None)
            if snap is not None:
                current_price = snap.last_price
                print(f"\n--- market snapshot ---")
                print(f"  last_price   = {snap.last_price}  (source={snap.provenance.get('last_price')})")
                print(f"  price_as_of  = {snap.price_as_of}")
                print(f"  shares_out   = {snap.shares_outstanding}")
                if snap.warnings:
                    print(f"  warnings     = {snap.warnings}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n--- market snapshot fetch failed: {type(exc).__name__}: {exc} ---")

    print(f"\n=== preflight (current_price={current_price}, peers=False) ===")
    pre = run_valuation_preflight(
        ticker=ticker,
        fact_table=fact_table,
        fy_periods=fy_periods,
        current_price_vnd=current_price,
        peer_dataset_available=False,
    )
    matrix = pre["data_completeness"]
    for method, avail in matrix.items():
        status = avail["status"].upper()
        missing = avail["missing_fields"]
        print(f"  [{status:<7}] {method:<14} ({avail['available_count']}/{avail['required_count']})"
              + (f"  missing={missing}" if missing else ""))

    gaps = pre["data_gap_report"]
    print(f"\nready_methods: {gaps['ready_methods']}")
    if gaps["gaps"]:
        print("\ngaps (field → fix):")
        seen = set()
        for g in gaps["gaps"]:
            key = (g["field"], g["classification"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  - {g['field']} [{g['classification']}]\n      {g['recommended_fix']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
