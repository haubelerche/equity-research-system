"""URL canonicalization + content fingerprint for cross-URL article dedup.

The same article often appears at several URLs (tracking params, mobile host). Canonical
URL + a content fingerprint let storage recognize "same article" and store it once.
"""
from __future__ import annotations

from backend.news.dedup import canonicalize_url, content_fingerprint


def test_strips_tracking_query_and_fragment() -> None:
    url = "https://cafef.vn/duoc-hau-giang-thay-ceo-188251209.chn?utm_source=du-lieu&ref=x#top"
    assert canonicalize_url(url) == "https://cafef.vn/duoc-hau-giang-thay-ceo-188251209.chn"


def test_keeps_meaningful_query_params() -> None:
    url = "https://example.vn/news.php?id=42&utm_campaign=foo"
    assert canonicalize_url(url) == "https://example.vn/news.php?id=42"


def test_normalizes_mobile_host_and_scheme() -> None:
    assert canonicalize_url("http://m.cafef.vn/a-123.chn") == "https://cafef.vn/a-123.chn"


def test_content_fingerprint_is_whitespace_insensitive_and_stable() -> None:
    a = content_fingerprint("Dược  Hậu   Giang\n\nlãi lớn")
    b = content_fingerprint("Dược Hậu Giang lãi lớn")
    assert a == b
    assert len(a) == 32  # md5 hex
    assert content_fingerprint("khác") != a
