"""Article dedup helpers — canonical URL + content fingerprint (stdlib only).

The same article is often reachable at several URLs (tracking query params, a mobile
host). A canonical URL plus an md5 fingerprint of the article text let the store recognize
"same article" across URLs and keep a single row.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlencode, urlparse, urlunparse

_WHITESPACE = re.compile(r"\s+")
# Tracking params dropped from the canonical URL (anything utm_* plus these).
_TRACKING_PARAMS = {"ref", "fbclid", "gclid", "source", "cmp", "campaign"}


def canonicalize_url(url: str) -> str:
    """Normalize scheme/host and strip tracking query params + fragment.

    Lowercases the host, drops a leading 'm.' (mobile mirror), forces https, removes the
    fragment and utm_*/tracking query params while keeping meaningful ones (e.g. ?id=42).
    """
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("m."):
        host = host[2:]
    kept = [
        (k, v)
        for k, v in _parse_pairs(parsed.query)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(kept)
    scheme = "https" if parsed.scheme in ("http", "https", "") else parsed.scheme
    return urlunparse((scheme, host, parsed.path, "", query, ""))


def _parse_pairs(query: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        pairs.append((key, value))
    return pairs


def content_fingerprint(text: str) -> str:
    """Whitespace-insensitive md5 hex of article text (stable across reformatting)."""
    normalized = _WHITESPACE.sub(" ", (text or "").strip())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()
