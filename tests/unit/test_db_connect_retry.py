"""Regression: transient Supabase pooler disconnects must be retried, not fatal."""
from __future__ import annotations

import psycopg2
import pytest

from backend.database import config


def test_connect_with_retry_recovers_after_transient_disconnect(monkeypatch):
    calls = {"n": 0}
    sentinel = object()

    def fake_connect(dsn, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        return sentinel

    monkeypatch.setattr(config.psycopg2, "connect", fake_connect)
    monkeypatch.setattr(config.time, "sleep", lambda _s: None)

    conn = config.connect_with_retry("postgresql://x.supabase.com/db", attempts=4, base_delay=0)
    assert conn is sentinel
    assert calls["n"] == 3


def test_connect_with_retry_raises_after_exhausting_attempts(monkeypatch):
    calls = {"n": 0}

    def always_fail(dsn, **kwargs):
        calls["n"] += 1
        raise psycopg2.OperationalError("connection already closed")

    monkeypatch.setattr(config.psycopg2, "connect", always_fail)
    monkeypatch.setattr(config.time, "sleep", lambda _s: None)

    with pytest.raises(psycopg2.OperationalError):
        config.connect_with_retry("postgresql://x.supabase.com/db", attempts=3, base_delay=0)
    assert calls["n"] == 3


def test_connect_with_retry_does_not_swallow_non_operational_errors(monkeypatch):
    def fake_connect(dsn, **kwargs):
        raise ValueError("bad dsn")

    monkeypatch.setattr(config.psycopg2, "connect", fake_connect)

    with pytest.raises(ValueError):
        config.connect_with_retry("postgresql://x.supabase.com/db", attempts=3, base_delay=0)
