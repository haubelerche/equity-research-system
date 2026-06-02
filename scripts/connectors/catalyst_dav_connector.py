from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from backend.dataset.config_io import ROOT, load_universe_tickers
from backend.dataset.dqf import infer_materiality, validate_catalyst_event
from backend.database.fact_store import PostgresFactStore
from backend.database.source_registry import SourceInput, SourceRegistry


CONNECTOR_VERSION = "catalyst_dav_connector_v1"
DAV_FEEDS = [
    "https://dav.gov.vn/thu-hoi-thuoc-n.html",
    "https://dav.gov.vn/phe-duyet-n.html",
]


def _event_id(source_url: str, title: str, occurred_at: str) -> str:
    return hashlib.sha256(f"{source_url}|{title}|{occurred_at}".encode("utf-8")).hexdigest()


def _guess_ticker(title: str, tickers: set[str]) -> str | None:
    words = {w.strip(".,:;()").upper() for w in title.split()}
    for ticker in tickers:
        if ticker in words:
            return ticker
    return None


def _parse_feed(url: str) -> list[dict[str, Any]]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict[str, Any]] = []
    for anchor in soup.select("a"):
        title = anchor.get_text(strip=True)
        href = anchor.get("href")
        if not title or not href:
            continue
        if len(title) < 8:
            continue
        rows.append(
            {
                "title": title,
                "source_url": urljoin(url, href),
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        )
    return rows


def sync_dav_connector(tickers: list[str] | None = None) -> int:
    tracked = set(tickers or load_universe_tickers())
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    now = datetime.now(UTC)
    all_events: list[dict[str, Any]] = []

    for feed in DAV_FEEDS:
        entries = _parse_feed(feed)
        raw_payload = json.dumps(entries, ensure_ascii=False).encode("utf-8")
        raw_path = ROOT / "data" / "raw" / "catalyst" / "regulatory" / now.date().isoformat() / "dav_feed.json"
        checksum = registry.save_raw_snapshot(raw_payload, raw_path)
        source_version_id = registry.register_source(
            SourceInput(
                logical_id="dav_regulatory",
                source_uri=feed,
                # Cục Quản lý Dược — Vietnamese government drug authority (Tier 0).
                source_type="regulatory_filing",
                source_tier=0,
                source_title="Cục Quản lý Dược (DAV) — Thông báo thu hồi / phê duyệt",
                checksum=checksum,
                connector_version=CONNECTOR_VERSION,
                raw_path=str(raw_path),
                published_at=now.isoformat(),
            )
        )
        registry.register_raw_payload(
            source_id=source_version_id,
            content_type="application/json",
            checksum=checksum,
            storage_path=str(raw_path),
            connector_name="catalyst_dav_connector",
            connector_version=CONNECTOR_VERSION,
            request_uri=feed,
        )

        for item in entries:
            title = item["title"]
            event_type = "regulatory"
            ticker = _guess_ticker(title, tracked)
            event = {
                "event_id": _event_id(item["source_url"], title, item["occurred_at"]),
                "event_type": event_type,
                "title": title,
                "summary": None,
                "occurred_at": item["occurred_at"],
                "effective_date": None,
                "ticker": ticker,
                "materiality_hint": infer_materiality(event_type=event_type, title=title),
                "source_url": item["source_url"],
                "source_id": source_version_id,
                "confidence": 0.8,
                "validation_status": "accepted",
                "ingested_at": now.isoformat(),
            }
            dqf = validate_catalyst_event(event)
            event["validation_status"] = dqf.status if dqf.status != "rejected" else "needs_review"
            event["confidence"] = dqf.confidence
            all_events.append(event)

    upserted = store.upsert_catalyst_events(all_events)
    print(f"[dav] upserted {upserted} events")
    return upserted


def sync_dav_for_ticker(ticker: str, **_kwargs) -> dict:
    """Per-ticker entry point for ingest_ticker.py; filters DAV scrape to one ticker."""
    count = sync_dav_connector(tickers=[ticker])
    return {"events": count}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl DAV regulatory announcements into catalyst_events.")
    parser.add_argument("--tickers", type=str, default="", help="Optional comma-separated ticker filter.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()] or None
    sync_dav_connector(tickers=tickers)


if __name__ == "__main__":
    main()

