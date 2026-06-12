from __future__ import annotations
from unittest.mock import patch
from backend.database import config


def test_connect_passes_keepalives():
    with patch("backend.database.config.psycopg2.connect") as mock_connect:
        mock_connect.return_value = object()
        config.connect_with_retry("postgresql://x.supabase.co/db")
        _, kwargs = mock_connect.call_args
        assert kwargs.get("keepalives") == 1
        assert kwargs.get("keepalives_idle") == 30
        assert kwargs.get("connect_timeout") == 10
