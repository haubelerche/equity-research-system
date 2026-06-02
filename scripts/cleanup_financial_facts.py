"""Cleanup script — remove quarterly financial facts from the database.

MVP only accepts annual FY periods (2021FY–2025FY).  Any quarterly rows
(fiscal_period != 'FY') that may have been ingested previously should be
removed with this script.

Usage (dry-run — default, no rows deleted):
    PYTHONUTF8=1 python scripts/cleanup_financial_facts.py --ticker DHG --remove-quarterly --dry-run

Usage (actual delete — requires --confirm):
    PYTHONUTF8=1 python scripts/cleanup_financial_facts.py --ticker DHG --remove-quarterly --confirm
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_PROJECT_ROOT = str(_Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
if "" in _sys.path:
    _sys.path = [p for p in _sys.path if p != ""] + [""]

import argparse
import os
import sys

_env_file = _Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))


def cleanup(ticker: str, dry_run: bool = True) -> None:
    from backend.database.fact_store import PostgresFactStore

    ticker = ticker.strip().upper()
    store = PostgresFactStore()

    quarterly_rows = store.list_quarterly_facts(ticker)

    if not quarterly_rows:
        print(f"[cleanup] {ticker}: No quarterly facts found — nothing to remove.")
        return

    print(f"[cleanup] {ticker}: Quarterly periods found:")
    for row in quarterly_rows:
        period_label = f"{row['fiscal_year']}{row['fiscal_period']}"
        print(f"  {period_label}  ({row['fact_count']} facts)")

    total_rows = store.delete_quarterly_facts(ticker=ticker, dry_run=True)
    print(f"\n[cleanup] {ticker}: {total_rows} fact row(s) would be removed.")

    if dry_run:
        print("\n[cleanup] No rows deleted because --dry-run is active.")
        print("[cleanup] Re-run with --confirm to delete.")
        return

    print(f"\n[cleanup] {ticker}: Deleting {total_rows} quarterly fact row(s) ...")
    deleted = store.delete_quarterly_facts(ticker=ticker, dry_run=False)
    print(f"[cleanup] {ticker}: Deleted {deleted} row(s). Done.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove quarterly financial facts for a ticker (MVP FY-only enforcement).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. DHG")
    parser.add_argument(
        "--remove-quarterly",
        action="store_true",
        required=True,
        help="Required flag: confirms intent to remove quarterly facts.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="List rows to remove without deleting (default).",
    )
    mode.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Actually delete rows. Cannot be combined with --dry-run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dry_run = not args.confirm
    cleanup(ticker=args.ticker, dry_run=dry_run)


if __name__ == "__main__":
    main()
