from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scripts.dataset.config_io import ROOT
from scripts.dataset.dqf import infer_materiality, validate_catalyst_event
from scripts.db.fact_store import PostgresFactStore
from scripts.db.source_registry import SourceInput, SourceRegistry


CONNECTOR_VERSION = "catalyst_tender_connector_v1"
TENDER_FEED = "https://muasamcong.mpi.gov.vn"


def _event_id(source_url: str, title: str, occurred_at: str) -> str:
    return hashlib.sha256(f"{source_url}|{title}|{occurred_at}".encode("utf-8")).hexdigest()


def _parse_tender_page(base_url: str, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    for anchor in soup.select("a"):
        text = anchor.get_text(" ", strip=True)
        href = anchor.get("href")
        if not text or not href or len(text) < 12:
            continue
        lowered = text.lower()
        if not any(k in lowered for k in ("thuoc", "goi thau", "dau thau", "trung thau")):
            continue
        events.append(
            {
                "title": text,
                "source_url": urljoin(base_url, href),
                "occurred_at": datetime.now(UTC).isoformat(),
                "event_type": "tender" if "trung thau" in lowered else "bidding",
            }
        )
    return events


def sync_tender_connector() -> int:
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    now = datetime.now(UTC)

    response = requests.get(TENDER_FEED, timeout=30)
    response.raise_for_status()
    html = response.text
    rows = _parse_tender_page(base_url=TENDER_FEED, html=html)

    raw_path = ROOT / "dataset" / "raw" / "catalyst" / "tender" / now.date().isoformat() / "tender_feed.html"
    checksum = registry.save_raw_snapshot(html.encode("utf-8"), raw_path)
    source_version_id = registry.register_source(
        SourceInput(
            logical_id="tender_results",
            source_uri=TENDER_FEED,
            source_type="tender",
            source_tier=3,
            source_title="Hệ thống mua sắm công — muasamcong.mpi.gov.vn",
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
        connector_name="catalyst_tender_connector",
        connector_version=CONNECTOR_VERSION,
        request_uri=TENDER_FEED,
    )

    events = []
    for row in rows:
        event = {
            "event_id": _event_id(row["source_url"], row["title"], row["occurred_at"]),
            "event_type": row["event_type"],
            "title": row["title"],
            "summary": None,
            "occurred_at": row["occurred_at"],
            "effective_date": None,
            "ticker": None,
            "materiality_hint": infer_materiality(row["event_type"], row["title"]),
            "source_url": row["source_url"],
            "source_id": source_version_id,
            "confidence": 0.75,
            "validation_status": "accepted",
            "ingested_at": now.isoformat(),
        }
        dqf = validate_catalyst_event(event)
        event["validation_status"] = dqf.status if dqf.status != "rejected" else "needs_review"
        event["confidence"] = dqf.confidence
        events.append(event)

    upserted = store.upsert_catalyst_events(events)
    print(f"[tender] upserted {upserted} events")
    return upserted


def sync_tender_for_ticker(ticker: str, **_kwargs) -> dict:
    """Per-ticker entry point for ingest_ticker.py; tender data is industry-wide so runs the full sync."""
    count = sync_tender_connector()
    return {"events": count}


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl tender portal into catalyst_events.")
    parser.parse_args()
    sync_tender_connector()


if __name__ == "__main__":
    main()

