from __future__ import annotations

import argparse
from collections.abc import Callable

from scripts.connectors.catalyst_bhyt_connector import sync_bhyt_connector
from scripts.connectors.catalyst_dav_connector import sync_dav_connector
from scripts.connectors.catalyst_hose_connector import sync_hose_hnx_connector
from scripts.connectors.catalyst_tender_connector import sync_tender_connector
from scripts.connectors.vnstock_company_connector import sync_company_universe
from scripts.connectors.vnstock_finance_connector import sync_financial_for_universe
from scripts.connectors.vnstock_price_connector import sync_price_for_universe


def _price(tickers: list[str]) -> int:
    return sum(sync_price_for_universe(days_back=14, tickers=tickers).values())


def _finance(tickers: list[str]) -> int:
    return sum(sync_financial_for_universe(tickers=tickers).values())


def _company(tickers: list[str]) -> int:
    stats = sync_company_universe(tickers=tickers)
    return sum(v.get("events", 0) for v in stats.values())


def _dav(tickers: list[str]) -> int:
    return sync_dav_connector(tickers=tickers)


def _hose(_: list[str]) -> int:
    return sync_hose_hnx_connector()


def _tender(_: list[str]) -> int:
    return sync_tender_connector()


def _bhyt(_: list[str]) -> int:
    return sync_bhyt_connector()


SOURCE_MAP: dict[str, Callable[[list[str]], int]] = {
    "price_history": _price,
    "bctc_disclosure": _finance,
    "company_news": _company,
    "catalyst_dav": _dav,
    "catalyst_hose": _hose,
    "tender_results": _tender,
    "bhyt_policy": _bhyt,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual ad-hoc refresh for selected tickers/sources.")
    parser.add_argument("--ticker", type=str, default="", help="Single ticker to refresh.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated ticker list.")
    parser.add_argument("--sources", type=str, default="", help="Comma-separated sources from SOURCE_MAP.")
    parser.add_argument("--all-sources", action="store_true", help="Run every source refresh in SOURCE_MAP.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers: list[str] = []
    if args.ticker:
        tickers.append(args.ticker.strip().upper())
    if args.tickers:
        tickers.extend([x.strip().upper() for x in args.tickers.split(",") if x.strip()])
    tickers = list(dict.fromkeys(tickers))

    if args.all_sources:
        sources = list(SOURCE_MAP.keys())
    else:
        sources = [x.strip() for x in args.sources.split(",") if x.strip()]
    if not sources:
        raise SystemExit("No sources selected. Use --sources or --all-sources.")

    for source in sources:
        handler = SOURCE_MAP.get(source)
        if handler is None:
            print(f"[manual_refresh] skip unknown source: {source}")
            continue
        count = handler(tickers)
        print(f"[manual_refresh] {source}: {count}")


if __name__ == "__main__":
    main()

