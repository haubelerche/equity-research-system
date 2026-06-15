"""Cron entrypoint: collect ticker-scoped news for the MVP pharma tickers.

Runs CafeF/VietStock ticker-channel discovery → fetch → LLM evidence → store, per
ticker. Idempotent: already-extracted articles are skipped, so it is safe to run on a
2–4h cron. One ticker failing never aborts the batch.

Usage:
    python scripts/collect_ticker_news.py                      # MVP tickers
    python scripts/collect_ticker_news.py --tickers DHG TRA     # space-separated
    python scripts/collect_ticker_news.py --tickers DHG,IMP     # comma-separated
    python scripts/collect_ticker_news.py --tickers DHG TRA --limit 5
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _company_lookup(ticker: str) -> tuple[str, str]:
    from backend.reporting.report_data_loader import _COMPANIES

    return _COMPANIES.get(ticker, (ticker, "HOSE"))


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    from backend.database.config import connect_with_retry, require_database_url
    from backend.news.runner import MVP_TICKERS, collect_for_tickers

    parser = argparse.ArgumentParser(description="Collect ticker-scoped news for tickers.")
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=list(MVP_TICKERS),
        help="Tickers, space- or comma-separated (default: MVP pharma set).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Collect the full configured ticker universe from the company registry.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Max articles to collect per ticker (passed to the collector).",
    )
    args = parser.parse_args(argv)
    if args.all:
        from backend.reporting.report_data_loader import _COMPANIES

        tickers = sorted(_COMPANIES)
    else:
        # Accept both `--tickers DHG TRA` and `--tickers DHG,TRA`.
        tickers = [
            t.strip().upper()
            for entry in args.tickers
            for t in str(entry).split(",")
            if t.strip()
        ]

    with connect_with_retry(require_database_url()) as conn:
        results = collect_for_tickers(
            conn, tickers, company_lookup=_company_lookup, max_articles=args.limit
        )

    failed = False
    for result in results:
        if "error" in result:
            failed = True
            print(f"[collect_ticker_news] {result['ticker']} FAILED: {result['error']}", file=sys.stderr)
        else:
            print(
                f"[collect_ticker_news] {result['ticker']}: "
                f"articles={result.get('articles', 0)} evidence={result.get('evidence', 0)}"
            )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
