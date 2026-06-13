"""HTML-listing discovery: extract article candidates from a listing page (stdlib only).

Complements RSS discovery for sites whose listing pages are plain HTML (e.g. CafeF .chn,
VnExpress kinh-doanh). Only whitelisted, article-shaped URLs become candidates.
"""
from __future__ import annotations

from backend.news.discovery_html import discover_from_listings, parse_listing_anchors

_LISTING_HTML = """
<html><body>
  <div class="tlitem">
    <a href="/duoc-hau-giang-lai-quy-1-20260505123456.chn">DHG báo lãi quý I tăng mạnh</a>
  </div>
  <div class="tlitem">
    <a href="https://cafef.vn/vn-index-phien-sang-20260613999999.chn">VN-Index phiên sáng</a>
  </div>
  <a href="/thi-truong-chung-khoan.chn">Chứng khoán</a>            <!-- section nav, no id -->
  <a href="https://evil.com/dhg-20260101000000.chn">spam</a>       <!-- not whitelisted -->
</body></html>
"""


def test_parses_article_anchors_and_resolves_relative_urls() -> None:
    cands = parse_listing_anchors(_LISTING_HTML, source_domain="cafef.vn")
    urls = [c.source_url for c in cands]
    assert urls == [
        "https://cafef.vn/duoc-hau-giang-lai-quy-1-20260505123456.chn",
        "https://cafef.vn/vn-index-phien-sang-20260613999999.chn",
    ]
    assert cands[0].title == "DHG báo lãi quý I tăng mạnh"
    assert cands[0].source_name == "CafeF"
    assert cands[0].discovery_method == "html_listing"


def test_skips_section_nav_and_non_whitelisted() -> None:
    cands = parse_listing_anchors(_LISTING_HTML, source_domain="cafef.vn")
    urls = [c.source_url for c in cands]
    assert "https://cafef.vn/thi-truong-chung-khoan.chn" not in urls  # no article id
    assert all("evil.com" not in u for u in urls)


def test_discover_from_listings_aggregates_and_dedupes() -> None:
    def fetch(url: str) -> str:
        return _LISTING_HTML

    cands = discover_from_listings(
        ["https://cafef.vn/thi-truong-chung-khoan.chn"], fetch_html=fetch
    )
    # Two distinct article candidates from the one listing.
    assert len(cands) == 2
