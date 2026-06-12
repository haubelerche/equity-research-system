from __future__ import annotations
import psycopg2
import pytest
from unittest.mock import MagicMock, patch
from backend.runtime_store import RuntimeStore


def _store():
    # Pass a valid Supabase DSN directly so require_database_url accepts it.
    return RuntimeStore(dsn="postgresql://x.supabase.co/db")


def test_write_retries_on_operational_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)
    store = _store()
    calls = {"n": 0}
    from contextlib import contextmanager

    @contextmanager
    def fake_conn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        yield MagicMock()

    monkeypatch.setattr(store, "conn", fake_conn)
    result = store._write(lambda connection: "ok")
    assert result == "ok"
    assert calls["n"] == 2


def test_write_reraises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)
    store = _store()
    from contextlib import contextmanager

    @contextmanager
    def always_fail():
        raise psycopg2.OperationalError("server closed the connection unexpectedly")
        yield  # noqa: unreachable — required for @contextmanager protocol

    monkeypatch.setattr(store, "conn", always_fail)
    with pytest.raises(psycopg2.OperationalError):
        store._write(lambda connection: "never")
