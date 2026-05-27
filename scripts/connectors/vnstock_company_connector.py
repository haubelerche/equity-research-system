from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

# Ensure pip-installed vnstock is found before the local vnstock/ namespace folder.
if "" in sys.path:
    sys.path = [p for p in sys.path if p != ""] + [""]

import pandas as pd
from vnstock.api.company import Company

from scripts.dataset.config_io import ROOT, load_universe_rows
from scripts.dataset.dqf import infer_materiality, validate_catalyst_event
from scripts.db.fact_store import PostgresFactStore
from scripts.db.source_registry import SourceInput, SourceRegistry


CONNECTOR_VERSION = "vn_company_v1"


def _to_records(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, pd.DataFrame):
        return data.fillna("").to_dict(orient="records")
    if isinstance(data, list):
        return [x if isinstance(x, dict) else {"value": x} for x in data]
    if isinstance(data, dict):
        return [data]
    return [{"value": data}]


def _register_payload(
    registry: SourceRegistry,
    ticker: str,
    endpoint: str,
    payload_obj: Any,
) -> str:
    payload = json.dumps(payload_obj, ensure_ascii=False, default=str).encode("utf-8")
    source_uri = f"vnstock://kbs/company/{endpoint}/{ticker}"
    raw_path = ROOT / "dataset" / "raw" / "market" / datetime.now(UTC).date().isoformat() / f"{ticker}_{endpoint}.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)
    return registry.register_source(
        SourceInput(
            logical_id="company_news" if endpoint in {"news", "events"} else "listing_metadata",
            ticker=ticker,
            source_uri=source_uri,
            source_type="news" if endpoint in {"news", "events"} else "vnstock_company",
            checksum=checksum,
            connector_version=CONNECTOR_VERSION,
            raw_path=str(raw_path),
            published_at=datetime.now(UTC).isoformat(),
        )
    )


def _event_id(ticker: str, title: str, occurred_at: str, source_url: str) -> str:
    raw = f"{ticker}|{title}|{occurred_at}|{source_url}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _build_events(
    ticker: str,
    rows: list[dict[str, Any]],
    source_version_id: str,
    event_type: str,
) -> list[dict[str, Any]]:
    # Map caller event_type values to DB CHECK constraint values.
    _type_map = {
        "company_announcement": "news",
        "company_news": "news",
        "corporate_event": "corporate_action",
    }
    db_event_type = _type_map.get(event_type, event_type)
    now = datetime.now(UTC)
    output: list[dict[str, Any]] = []
    for row in rows:
        title = str(row.get("title") or row.get("headline") or row.get("event") or "N/A").strip()
        if title == "N/A":
            continue
        published_at = row.get("publishedDate") or row.get("published_at") or row.get("time") or now.isoformat()
        source_url = str(row.get("url") or row.get("link") or f"vnstock://{ticker}/company/{event_type}")
        event = {
            "event_id": _event_id(ticker=ticker, title=title, occurred_at=str(published_at), source_url=source_url),
            "event_type": db_event_type,
            "title": title,
            "summary": str(row.get("text") or row.get("summary") or "")[:3000] or None,
            "occurred_at": published_at,
            "effective_date": None,
            "ticker": ticker,
            "materiality_hint": infer_materiality(event_type=db_event_type, title=title),
            "source_url": source_url,
            "source_id": source_version_id,
            "confidence": 0.8,
            "validation_status": "raw",
            "ingested_at": now.isoformat(),
        }
        dqf = validate_catalyst_event(event)
        event["validation_status"] = dqf.status if dqf.status != "rejected" else "needs_review"
        event["confidence"] = dqf.confidence
        if dqf.materiality is not None:
            event["materiality_hint"] = dqf.materiality
        output.append(event)
    return output


def sync_company_ticker(ticker: str, segment: str, store: PostgresFactStore, registry: SourceRegistry) -> dict[str, int]:
    client = Company(source="KBS", symbol=ticker)
    overview = _to_records(client.overview())
    shareholders = _to_records(client.shareholders())
    officers = _to_records(client.officers())
    news = _to_records(client.news())
    events = _to_records(client.events())

    overview_version = _register_payload(registry=registry, ticker=ticker, endpoint="overview", payload_obj=overview)
    _register_payload(registry=registry, ticker=ticker, endpoint="shareholders", payload_obj=shareholders)
    _register_payload(registry=registry, ticker=ticker, endpoint="officers", payload_obj=officers)
    news_version = _register_payload(registry=registry, ticker=ticker, endpoint="news", payload_obj=news)
    events_version = _register_payload(registry=registry, ticker=ticker, endpoint="events", payload_obj=events)

    first_overview = overview[0] if overview else {}
    store.upsert_company_snapshot(
        ticker=ticker,
        company_name_vi=first_overview.get("companyName") or first_overview.get("company_name") or ticker,
        company_name_en=None,
        exchange=first_overview.get("exchange"),
        sector=segment,
        subsector=None,
        overview_json=overview,
        shareholders_json=shareholders,
        officers_json=officers,
    )

    catalyst_rows = _build_events(ticker=ticker, rows=news, source_version_id=news_version, event_type="news")
    catalyst_rows.extend(_build_events(ticker=ticker, rows=events, source_version_id=events_version, event_type="news"))
    event_count = store.upsert_catalyst_events(catalyst_rows)
    return {"profiles": 1, "events": event_count, "source_versions": 5}


def sync_company_universe(tickers: Iterable[str] | None = None) -> dict[str, dict[str, int]]:
    rows = load_universe_rows()
    selected = {t.upper() for t in tickers} if tickers else None

    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    results: dict[str, dict[str, int]] = {}
    for row in rows:
        ticker = row["ticker"].strip().upper()
        if selected and ticker not in selected:
            continue
        stats = sync_company_ticker(ticker=ticker, segment=row.get("segment", ""), store=store, registry=registry)
        results[ticker] = stats
        print(f"[company] {ticker}: profiles={stats['profiles']} events={stats['events']}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync company profile/news/events from vnstock into PostgreSQL.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated ticker override.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()] or None
    sync_company_universe(tickers=tickers)


if __name__ == "__main__":
    main()

