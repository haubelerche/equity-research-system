"""Controlled document fetcher — Source-Provenance Rebuild, Phase 5.

Fetches a registered source URL and hands the bytes to document_store. Fetching is
abstracted behind a `fetch_fn` so the pipeline stays deterministic and testable (no
network in tests). Supported fetch methods:

  - manual:        read from a local file (data/source_documents/_manual/...)
  - http / https:  use the injected fetch_fn (defaults to urllib) — network
  - connector:<x>: delegated to an existing scripts/connectors/* connector (not auto-run
                   here; the orchestrator decides). Treated as manual for fetching bytes.

A fetched document always carries a raw_content_hash.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backend.sources.document_store import FetchedDocument, store_document
from backend.sources.source_registry import RegisteredSource


class FetchError(RuntimeError):
    pass


def _default_http_fetch(url: str, timeout: int = 20) -> bytes:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "maer-source-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def fetch_document(
    source: RegisteredSource,
    url: str,
    title: str,
    *,
    fetch_fn: Callable[[str], bytes] | None = None,
    local_file: Path | str | None = None,
    publisher: str | None = None,
    published_date: str | None = None,
    store_root: Path | None = None,
) -> FetchedDocument:
    """Fetch one document for a registered source. Returns a FetchedDocument (hashed).

    Args:
        source: the RegisteredSource (must be enabled).
        url: document URL (recorded as provenance even for manual fetches).
        title: document title.
        fetch_fn: override for HTTP fetching (tests inject a stub). Defaults to urllib.
        local_file: for manual/connector methods, read bytes from this path.
    """
    if not source.enabled:
        raise FetchError(f"source '{source.name}' is disabled — refusing to fetch")

    method = source.fetch_method
    if method == "manual" or method.startswith("connector:"):
        if local_file is None:
            raise FetchError(
                f"source '{source.name}' uses '{method}' — a local_file must be provided"
            )
        p = Path(local_file)
        if not p.exists():
            raise FetchError(f"local file not found: {p}")
        content = p.read_bytes()
    elif method in ("http", "https"):
        fn = fetch_fn or _default_http_fetch
        content = fn(url)
    else:
        raise FetchError(f"unknown fetch_method '{method}' for source '{source.name}'")

    if not content:
        raise FetchError(f"empty content fetched from {url}")

    return store_document(
        source_name=source.name, source_type=source.source_type,
        source_tier=source.source_tier, url=url, title=title, content=content,
        publisher=publisher, published_date=published_date, store_root=store_root,
    )
