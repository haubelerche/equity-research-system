"""Per-ticker news source registry rows (CafeF + VietStock channels)."""
from __future__ import annotations

from backend.news.runner import build_ticker_sources, ticker_listing_urls


def test_builds_cafef_and_vietstock_sources_with_priority() -> None:
    sources = build_ticker_sources("DHG", exchange_slug="hose")
    by_url = {s["source_url"]: s for s in sources}

    # Same URLs the runner crawls, now as registry rows.
    assert set(by_url) == set(ticker_listing_urls("DHG", "hose"))

    cafef_event = by_url["https://cafef.vn/du-lieu/tin-doanh-nghiep/dhg/Event.chn"]
    assert cafef_event["source_name"] == "CafeF"
    assert cafef_event["source_domain"] == "cafef.vn"
    assert cafef_event["source_type"] == "media"
    assert cafef_event["is_cron_enabled"] is True
    # CafeF event index is the proven static source → highest priority.
    assert cafef_event["priority"] >= by_url[
        "https://finance.vietstock.vn/DHG/tin-tuc-su-kien.htm"
    ]["priority"]


def test_every_source_has_required_registry_fields() -> None:
    for s in build_ticker_sources("IMP", exchange_slug="hose"):
        assert {"source_name", "source_domain", "source_type", "source_url",
                "priority", "is_cron_enabled"} <= set(s)
