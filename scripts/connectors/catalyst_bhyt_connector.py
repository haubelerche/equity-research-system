from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from backend.dataset.config_io import ROOT
from backend.dataset.dqf import infer_materiality, validate_catalyst_event
from backend.database.fact_store import PostgresFactStore
from backend.database.source_registry import SourceInput, SourceRegistry


CONNECTOR_VERSION = "catalyst_bhyt_connector_v1"
BHYT_FEED = "https://bhxhvn.gov.vn/Pages/danh-muc-thuoc.aspx"


def _event_id(source_url: str, title: str, occurred_at: str) -> str:
    return hashlib.sha256(f"{source_url}|{title}|{occurred_at}".encode("utf-8")).hexdigest()


def _classify_bhyt_event(title: str) -> str:
    lowered = title.lower()
    if any(k in lowered for k in ("bo sung", "them moi", "addition")):
        return "drug_registration"
    if any(k in lowered for k in ("loai bo", "cat giam", "removal")):
        return "regulatory"
    if any(k in lowered for k in ("ty le", "muc huong", "rate")):
        return "regulatory"
    return "regulatory"


def _parse_bhyt_page(base_url: str, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []
    for anchor in soup.select("a"):
        title = anchor.get_text(" ", strip=True)
        href = anchor.get("href")
        if not title or not href or len(title) < 10:
            continue
        if "thuoc" not in title.lower() and "bhyt" not in title.lower():
            continue
        events.append(
            {
                "title": title,
                "source_url": urljoin(base_url, href),
                "occurred_at": datetime.now(UTC).isoformat(),
                "event_type": _classify_bhyt_event(title),
            }
        )
    return events


def sync_bhyt_connector() -> int:
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    now = datetime.now(UTC)

    response = requests.get(BHYT_FEED, timeout=30)
    response.raise_for_status()
    html = response.text
    rows = _parse_bhyt_page(base_url=BHYT_FEED, html=html)

    raw_path = ROOT / "data" / "raw" / "catalyst" / "bhyt_policy" / now.date().isoformat() / "bhyt_feed.html"
    checksum = registry.save_raw_snapshot(html.encode("utf-8"), raw_path)
    source_version_id = registry.register_source(
        SourceInput(
            logical_id="bhyt_policy",
            source_uri=BHYT_FEED,
            # BHXH Vietnam government website — official regulatory documents (Tier 0).
            source_type="regulatory_filing",
            source_tier=0,
            source_title="BHXH Việt Nam — Danh mục thuốc BHYT",
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
        connector_name="catalyst_bhyt_connector",
        connector_version=CONNECTOR_VERSION,
        request_uri=BHYT_FEED,
    )

    events = []
    for row in rows:
        event_type = row["event_type"]
        event = {
            "event_id": _event_id(row["source_url"], row["title"], row["occurred_at"]),
            "event_type": event_type,
            "title": row["title"],
            "summary": None,
            "occurred_at": row["occurred_at"],
            "effective_date": None,
            "ticker": None,
            "materiality_hint": infer_materiality(event_type=event_type, title=row["title"]),
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
    print(f"[bhyt] upserted {upserted} events")
    return upserted


def sync_bhyt_for_ticker(ticker: str, **_kwargs) -> dict:
    """Per-ticker entry point for ingest_ticker.py; BHYT is industry-wide so runs the full sync."""
    count = sync_bhyt_connector()
    return {"events": count}


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl BHYT policy feed into catalyst_events.")
    parser.parse_args()
    sync_bhyt_connector()


if __name__ == "__main__":
    main()

