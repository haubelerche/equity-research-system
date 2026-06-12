from __future__ import annotations

import io

import pytest

from backend.storage.supabase_adapter import SupabaseStorageAdapter, SupabaseStorageError


def _adapter() -> SupabaseStorageAdapter:
    return SupabaseStorageAdapter(url="https://x.supabase.co", service_role_key="k")


class _Resp:
    status = 200

    def __init__(self, data: bytes = b"{}") -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *_a: object) -> bool:
        return False


def test_request_retries_on_connection_reset(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)
    calls = {"n": 0}

    def flaky(req, timeout=120):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")
        return _Resp(b'{"ok":true}')

    monkeypatch.setattr("backend.storage.supabase_adapter.urlopen", flaky)
    out = _adapter()._request("GET", "object/b/p")
    assert calls["n"] == 2
    assert out == b'{"ok":true}'


def test_request_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    def always(req, timeout=120):
        raise ConnectionResetError(10054, "reset")

    monkeypatch.setattr("backend.storage.supabase_adapter.urlopen", always)
    with pytest.raises(SupabaseStorageError):
        _adapter()._request("GET", "object/b/p")


def test_http_error_is_not_retried(monkeypatch):
    from urllib.error import HTTPError

    calls = {"n": 0}

    def http_err(req, timeout=120):
        calls["n"] += 1
        raise HTTPError("u", 404, "Not Found", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr("backend.storage.supabase_adapter.urlopen", http_err)
    with pytest.raises(SupabaseStorageError):
        _adapter()._request("GET", "object/b/p")
    assert calls["n"] == 1  # not retried — real HTTP response, not a transient reset
