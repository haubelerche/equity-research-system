"""Discovery vs citation allowlist split.

Automated discovery stays restricted to the four official sources, but a human-vetted
article from a wider set of reputable Vietnamese outlets (and official company/exchange
sites) may be cited. is_citation_allowed_url is the broader gate used by manual ingest.
"""
from __future__ import annotations

from backend.news.types import ALLOWED_DOMAINS, CITATION_ALLOWED_DOMAINS
from backend.news.whitelist import is_allowed_url, is_citation_allowed_url


def test_citation_set_is_a_superset_of_discovery_set() -> None:
    assert ALLOWED_DOMAINS <= CITATION_ALLOWED_DOMAINS


def test_reputable_media_is_citable_but_not_discoverable() -> None:
    url = "https://www.tinnhanhchungkhoan.vn/duoc-hau-giang-dhg-post389927.html"
    assert is_citation_allowed_url(url)
    assert not is_allowed_url(url)  # not in the automated-discovery whitelist


def test_official_company_site_is_citable() -> None:
    assert is_citation_allowed_url("https://dhgpharma.com.vn/vi/co-dong/bao-cao-thuong-nien-2025")


def test_non_whitelisted_domain_is_never_citable() -> None:
    assert not is_citation_allowed_url("https://evil.example.com/dhg")
    assert not is_citation_allowed_url("https://evil-tinnhanhchungkhoan.vn/x")
