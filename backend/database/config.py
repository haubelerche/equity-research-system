"""Database configuration for the Supabase-only runtime."""
from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import psycopg2

# Supabase's transaction pooler intermittently drops or refuses connections
# ("server closed the connection unexpectedly", "connection already closed").
# These are transient and succeed on a fresh connect, so connect attempts are
# retried with exponential backoff before surfacing the failure.
CONNECT_ATTEMPTS = 4
CONNECT_BASE_DELAY_SECONDS = 0.5


def require_database_url(dsn: str | None = None) -> str:
    """Return the configured Supabase PostgreSQL DSN and reject local fallbacks."""
    value = (os.getenv("DATABASE_URL") if dsn is None else dsn) or ""
    value = value.strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required and must point to Supabase PostgreSQL")

    host = (urlparse(value).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1", "db"}:
        raise RuntimeError(
            f"Local PostgreSQL is disabled; DATABASE_URL must point to Supabase, got host={host!r}"
        )
    if not (host.endswith(".supabase.com") or host.endswith(".supabase.co")):
        raise RuntimeError(f"DATABASE_URL must point to Supabase PostgreSQL, got host={host!r}")
    return value


def connect_with_retry(
    dsn: str,
    *,
    attempts: int = CONNECT_ATTEMPTS,
    base_delay: float = CONNECT_BASE_DELAY_SECONDS,
):
    """Drop-in psycopg2.connect that retries transient pooler disconnects."""
    last_exc: psycopg2.OperationalError | None = None
    for attempt in range(attempts):
        try:
            return psycopg2.connect(
                dsn,
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
        except psycopg2.OperationalError as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc  # pragma: no cover - loop always returns or raises above
