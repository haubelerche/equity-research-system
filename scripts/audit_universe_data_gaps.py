"""Classify universe data gaps without manual market-price assumptions.

The audit answers three operational questions:
1. Which tickers can be repaired automatically from data/raw/market cache?
2. Which tickers need an alternative market connector because no quote cache exists?
3. Which tickers look like universe identity/fact-contract problems rather than
   simple ingestion misses?
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORE_FACTS = {
    "revenue.net",
    "net_income.parent",
    "capex.total",
    "cash_and_equivalents.ending",
}
DEBT_FACTS = {"short_term_debt.ending", "long_term_debt.ending"}
CASH_OR_EARNINGS_FACTS = {"operating_cash_flow.total", "profit_before_tax.total"}
BANK_SCHEMA_MARKERS = (
    "interest and similar income",
    "customer deposits",
    "loans to customers",
    "net interest income",
    "thu nhập lãi",
    "tiền gửi của khách hàng",
)


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


def _load_universe(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            {str(k): str(v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(handle)
            if str(row.get("ticker") or "").strip()
        ]


def _quote_files(raw_market_root: Path, ticker: str) -> list[Path]:
    return sorted(raw_market_root.glob(f"**/{ticker.upper()}_quote_history.json"))


def _overview_files(raw_market_root: Path, ticker: str) -> list[Path]:
    return sorted(raw_market_root.glob(f"**/{ticker.upper()}_overview.json"))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _cached_quote_status(raw_market_root: Path, ticker: str) -> dict[str, Any]:
    files = _quote_files(raw_market_root, ticker)
    row_count = 0
    latest_date = None
    errors: list[str] = []
    for path in files:
        try:
            payload = _read_json(path)
            records = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(records, list):
                records = []
            row_count += len(records)
            for record in records:
                if isinstance(record, dict):
                    raw_date = record.get("time") or record.get("date") or record.get("datetime")
                    if raw_date:
                        value = str(raw_date)[:10]
                        latest_date = max(latest_date or value, value)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    return {
        "cached_quote_files": [str(path) for path in files],
        "cached_quote_rows": row_count,
        "cached_quote_latest_date": latest_date,
        "cached_quote_errors": errors,
        "cached_quote_available": row_count > 0,
    }


def _overview_status(raw_market_root: Path, ticker: str) -> dict[str, Any]:
    files = _overview_files(raw_market_root, ticker)
    valid = False
    latest_payload: Any = None
    for path in files:
        try:
            payload = _read_json(path)
            latest_payload = payload
            records = payload if isinstance(payload, list) else [payload]
            for record in records:
                if not isinstance(record, dict):
                    continue
                if record.get("exchange") or record.get("listing_price") or record.get("listed_volume"):
                    valid = True
        except Exception:
            continue
    return {
        "overview_files": [str(path) for path in files],
        "overview_valid": valid,
        "overview_payload_sample": latest_payload[0] if isinstance(latest_payload, list) and latest_payload else latest_payload,
    }


def _raw_bctc_status(raw_bctc_root: Path, ticker: str) -> dict[str, Any]:
    ticker_dir = raw_bctc_root / ticker.upper()
    files = sorted(path for path in ticker_dir.glob("*.json") if not path.name.endswith(".sha256"))
    years: set[int] = set()
    marker_hits: set[str] = set()
    for path in files:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        years.update(int(value) for value in re.findall(r"\b(20[0-9]{2})\b", text))
        lowered = text.lower()
        marker_hits.update(marker for marker in BANK_SCHEMA_MARKERS if marker in lowered)
    scoped_years = sorted(year for year in years if 2022 <= year <= 2025)
    return {
        "raw_bctc_files": [str(path) for path in files],
        "raw_bctc_years": sorted(years),
        "raw_bctc_scoped_years": scoped_years,
        "raw_bctc_has_2022_2025": bool(scoped_years),
        "financial_institution_schema_markers": sorted(marker_hits),
    }


def _db_status(tickers: list[str], from_year: int, to_year: int) -> dict[str, dict[str, Any]]:
    try:
        from backend.database.config import connect_with_retry, require_database_url
    except Exception as exc:  # noqa: BLE001
        return {ticker: {"db_checked": False, "db_error": str(exc)} for ticker in tickers}

    status = {
        ticker: {
            "db_checked": True,
            "price_rows": 0,
            "latest_price_date": None,
            "production_fact_rows": 0,
            "production_metrics": [],
            "active_snapshot_count": 0,
            "latest_active_snapshot_facts": None,
        }
        for ticker in tickers
    }
    try:
        with connect_with_retry(require_database_url()) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ticker, COUNT(*) AS rows, MAX(trade_date) AS latest_date
                    FROM fact.price_history
                    WHERE ticker = ANY(%s)
                    GROUP BY ticker
                    """,
                    (tickers,),
                )
                for ticker, rows, latest_date in cur.fetchall():
                    item = status[str(ticker)]
                    item["price_rows"] = int(rows or 0)
                    item["latest_price_date"] = latest_date.isoformat() if latest_date else None

                cur.execute(
                    """
                    SELECT ticker, COUNT(*) AS rows, ARRAY_AGG(DISTINCT metric ORDER BY metric) AS metrics
                    FROM fact.production_facts
                    WHERE ticker = ANY(%s)
                      AND CAST(SUBSTRING(period, 1, 4) AS SMALLINT) BETWEEN %s AND %s
                    GROUP BY ticker
                    """,
                    (tickers, from_year, to_year),
                )
                for ticker, rows, metrics in cur.fetchall():
                    item = status[str(ticker)]
                    item["production_fact_rows"] = int(rows or 0)
                    item["production_metrics"] = list(metrics or [])

                cur.execute(
                    """
                    SELECT ticker, COUNT(*) AS snapshots, MAX(facts_count) AS latest_facts
                    FROM research.snapshots
                    WHERE ticker = ANY(%s)
                      AND status = 'active'
                      AND from_year <= %s
                      AND to_year >= %s
                    GROUP BY ticker
                    """,
                    (tickers, from_year, to_year),
                )
                for ticker, snapshots, latest_facts in cur.fetchall():
                    item = status[str(ticker)]
                    item["active_snapshot_count"] = int(snapshots or 0)
                    item["latest_active_snapshot_facts"] = int(latest_facts or 0) if latest_facts is not None else None
    except Exception as exc:  # noqa: BLE001
        return {ticker: {"db_checked": False, "db_error": str(exc)} for ticker in tickers}
    return status


def _minimum_fact_contract(metrics: list[str]) -> dict[str, Any]:
    metric_set = set(metrics)
    missing = sorted(CORE_FACTS - metric_set)
    has_debt = bool(metric_set & DEBT_FACTS)
    has_cash_or_earnings = bool(metric_set & CASH_OR_EARNINGS_FACTS)
    if not has_debt:
        missing.append("short_term_debt.ending_or_long_term_debt.ending")
    if not has_cash_or_earnings:
        missing.append("operating_cash_flow.total_or_profit_before_tax.total")
    return {
        "minimum_fact_contract_ready": not missing,
        "minimum_fact_contract_missing": missing,
    }


def _classification(row: dict[str, Any]) -> str:
    if row["identity_conflict_risk"]:
        return "universe_identity_conflict_risk"
    if not row["has_price_history"] and row["cached_quote_available"]:
        return "recoverable_from_cached_quote_history"
    if row["has_price_history"] and row["minimum_fact_contract_ready"] and row["has_active_snapshot"]:
        return "ready_for_render_base"
    if not row["has_price_history"]:
        return "needs_alternative_market_connector_or_universe_fix"
    if not row["minimum_fact_contract_ready"]:
        return "needs_financial_fact_connector_or_universe_fix"
    if not row["has_active_snapshot"]:
        return "needs_snapshot_backfill"
    return "needs_pipeline_backfill"


def audit_universe_data_gaps(
    *,
    universe_path: Path,
    raw_market_root: Path,
    raw_bctc_root: Path,
    from_year: int,
    to_year: int,
) -> dict[str, Any]:
    universe = _load_universe(universe_path)
    tickers = [row["ticker"].upper() for row in universe]
    db = _db_status(tickers, from_year, to_year)

    records: list[dict[str, Any]] = []
    for source_row in universe:
        ticker = source_row["ticker"].upper()
        db_row = db.get(ticker, {"db_checked": False})
        metrics = list(db_row.get("production_metrics") or [])
        fact_contract = _minimum_fact_contract(metrics)
        quote = _cached_quote_status(raw_market_root, ticker)
        overview = _overview_status(raw_market_root, ticker)
        bctc = _raw_bctc_status(raw_bctc_root, ticker)
        identity_conflict = bool(
            bctc["financial_institution_schema_markers"]
            and source_row.get("segment") not in {"bank", "financials", "financial_services"}
        )
        record = {
            "ticker": ticker,
            "company_name": source_row.get("company_name", ""),
            "exchange": source_row.get("exchange", ""),
            "segment": source_row.get("segment", ""),
            **db_row,
            **quote,
            **overview,
            **bctc,
            **fact_contract,
            "has_price_history": int(db_row.get("price_rows") or 0) > 0,
            "has_active_snapshot": int(db_row.get("active_snapshot_count") or 0) > 0,
            "identity_conflict_risk": identity_conflict,
        }
        record["classification"] = _classification(record)
        records.append(record)

    by_class: dict[str, list[str]] = {}
    for record in records:
        by_class.setdefault(record["classification"], []).append(record["ticker"])
    summary = {
        "universe_count": len(records),
        "from_year": from_year,
        "to_year": to_year,
        "price_history_count": sum(1 for row in records if row["has_price_history"]),
        "cached_quote_available_count": sum(1 for row in records if row["cached_quote_available"]),
        "minimum_fact_contract_count": sum(1 for row in records if row["minimum_fact_contract_ready"]),
        "active_snapshot_count": sum(1 for row in records if row["has_active_snapshot"]),
        "classification_counts": {key: len(value) for key, value in sorted(by_class.items())},
        "classification_tickers": {key: sorted(value) for key, value in sorted(by_class.items())},
    }
    return {"summary": summary, "records": records}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit universe gaps by DB state, raw market cache, and raw BCTC identity signals.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--universe", default="config/dataset/universe/pharma_vn_universe.csv")
    parser.add_argument("--raw-market-root", default="data/raw/market")
    parser.add_argument("--raw-bctc-root", default="data/raw/bctc")
    parser.add_argument("--from-year", type=int, default=2022)
    parser.add_argument("--to-year", type=int, default=2025)
    parser.add_argument("--write-json", default="output/universe_data_gap_audit.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    universe = Path(args.universe)
    raw_market_root = Path(args.raw_market_root)
    raw_bctc_root = Path(args.raw_bctc_root)
    if not universe.is_absolute():
        universe = ROOT / universe
    if not raw_market_root.is_absolute():
        raw_market_root = ROOT / raw_market_root
    if not raw_bctc_root.is_absolute():
        raw_bctc_root = ROOT / raw_bctc_root

    result = audit_universe_data_gaps(
        universe_path=universe,
        raw_market_root=raw_market_root,
        raw_bctc_root=raw_bctc_root,
        from_year=int(args.from_year),
        to_year=int(args.to_year),
    )
    out = Path(args.write_json)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"[data-gap-audit] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
