"""Whitelist gate — block every URL outside the approved domains (plan §4.3).

Mandatory rule: a URL that does not pass this gate must not be crawled, stored, or used
in any report. The gate is intentionally strict — only http(s) URLs whose host is exactly an
approved domain (or a true subdomain of one) pass. Look-alike domains (evil-vneconomy.vn) and
path-embedded domains (evil.com/vneconomy.vn) are rejected.
"""
from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from backend.news.types import ALLOWED_DOMAINS


def url_domain(url: str) -> str | None:
    """Return the lowercased host of an http(s) URL with a leading 'www.' stripped, else None."""
    try:
        parsed = urlparse(url.strip())
    except (ValueError, AttributeError):
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.hostname  # excludes port and userinfo
    if not host:
        return None
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_allowed_url(url: str, allowed_domains: Iterable[str] = ALLOWED_DOMAINS) -> bool:
    """True if url's host is exactly an approved domain or a true subdomain of one."""
    host = url_domain(url)
    if host is None:
        return False
    allowed = {d.lower() for d in allowed_domains}
    return any(host == d or host.endswith("." + d) for d in allowed)


def filter_allowed_urls(
    urls: Iterable[str], allowed_domains: Iterable[str] = ALLOWED_DOMAINS
) -> list[str]:
    """Keep only whitelisted URLs, preserving first-seen order and dropping duplicates."""
    allowed = set(allowed_domains)
    seen: set[str] = set()
    kept: list[str] = []
    for url in urls:
        if url in seen:
            continue
        if is_allowed_url(url, allowed):
            seen.add(url)
            kept.append(url)
    return kept
