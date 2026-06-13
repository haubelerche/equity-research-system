"""Ticker-scoped news discovery URLs (CafeF primary, VietStock secondary).

Discovery is per-ticker, not broad market listings: the CafeF company event index is
the proven static source; the CafeF/VietStock ticker pages are included per the source
plan. Broad VnExpress/VnEconomy crawling is deliberately excluded here.
"""
from __future__ import annotations

from backend.news.runner import ticker_listing_urls


def test_builds_cafef_event_index_and_vietstock_ticker_urls() -> None:
    urls = ticker_listing_urls("DHG", exchange_slug="hose")
    assert "https://cafef.vn/du-lieu/tin-doanh-nghiep/dhg/Event.chn" in urls
    assert "https://cafef.vn/du-lieu/hose/dhg-tin-tuc.chn" in urls
    assert "https://finance.vietstock.vn/DHG/tin-tuc-su-kien.htm" in urls


def test_no_broad_market_listings_included() -> None:
    urls = ticker_listing_urls("IMP", exchange_slug="hose")
    assert all("thi-truong-chung-khoan" not in u for u in urls)
    assert all("vnexpress.net" not in u for u in urls)
    assert all("vneconomy.vn" not in u for u in urls)
    # Every URL is ticker-scoped (mentions the ticker).
    assert all("imp" in u.lower() for u in urls)
