from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scripts.dataset.config_io import ROOT, load_universe_tickers
from scripts.dataset.dqf import infer_materiality, validate_catalyst_event
from scripts.db.fact_store import PostgresFactStore
from scripts.db.source_registry import SourceInput, SourceRegistry


CONNECTOR_VERSION = "catalyst_hose_connector_v1"
HOSE_URL = "https://www.hsx.vn/Modules/CMS/Web/ArticleList"
HNX_URL = "https://hnx.vn/cong-bo-thong-tin"


def _event_id(source_url: str, title: str, occurred_at: str) -> str:
    return hashlib.sha256(f"{source_url}|{title}|{occurred_at}".encode("utf-8")).hexdigest()


def _parse_anchors(base_url: str, html: str, tracked_tickers: set[str]) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    for anchor in soup.select("a"):
        text = anchor.get_text(" ", strip=True)
        href = anchor.get("href")
        if not text or not href or len(text) < 10:
            continue
        tokens = {token.strip(".,:;()").upper() for token in text.split()}
        ticker = next((t for t in tracked_tickers if t in tokens), None)
        if ticker is None:
            continue
        results.append(
            {
                "ticker": ticker,
                "title": text,
                "source_url": urljoin(base_url, href),
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        )
    return results


def sync_hose_hnx_connector(tickers: list[str] | None = None) -> int:
    tracked = set(tickers or load_universe_tickers())
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    now = datetime.now(UTC)

    responses = []
    for url in (HOSE_URL, HNX_URL):
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        responses.append((url, response.text))

    all_events: list[dict] = []
    for url, html in responses:
        entries = _parse_anchors(base_url=url, html=html, tracked_tickers=tracked)
        raw_path = ROOT / "dataset" / "raw" / "catalyst" / "company_news" / now.date().isoformat() / f"{'hose' if 'hsx' in url else 'hnx'}_announcements.html"
        exchange_label = "hose" if "hsx" in url else "hnx"
        checksum = registry.save_raw_snapshot(html.encode("utf-8"), raw_path)
        source_version_id = registry.register_source(
            SourceInput(
                logical_id="company_news",
                source_uri=url,
                # Exchange disclosure pages are Tier 0 — official exchange publications.
                source_type="disclosure",
                source_tier=0,
                source_title=f"{'HOSE' if exchange_label == 'hose' else 'HNX'} Công bố thông tin",
                checksum=checksum,
                connector_version=CONNECTOR_VERSION,
                raw_path=str(raw_path),
                published_at=now.isoformat(),
            )
        )
        registry.register_raw_payload(
            source_id=source_version_id,
            content_type="text/html",
            checksum=checksum,
            storage_path=str(raw_path),
            connector_name="catalyst_hose_connector",
            connector_version=CONNECTOR_VERSION,
            request_uri=url,
        )

        for row in entries:
            title = row["title"]
            event_type = "disclosure" if "ke hoach" in title.lower() or "guidance" in title.lower() else "news"
            event = {
                "event_id": _event_id(row["source_url"], title, row["occurred_at"]),
                "event_type": event_type,
                "title": title,
                "summary": None,
                "occurred_at": row["occurred_at"],
                "effective_date": None,
                "ticker": row["ticker"],
                "materiality_hint": infer_materiality(event_type=event_type, title=title),
                "source_url": row["source_url"],
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
    print(f"[hose_hnx] upserted {upserted} events")
    return upserted


def sync_hose_for_ticker(ticker: str, **_kwargs) -> dict:
    """Per-ticker entry point for ingest_ticker.py; filters the HOSE/HNX scrape to one ticker."""
    count = sync_hose_hnx_connector(tickers=[ticker])
    return {"events": count}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl HOSE/HNX disclosures into catalyst_events.")
    parser.add_argument("--tickers", type=str, default="", help="Optional ticker override.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()] or None
    sync_hose_hnx_connector(tickers=tickers)


if __name__ == "__main__":
    main()

