from __future__ import annotations

import pytest

from backend.database.config import require_database_url


@pytest.mark.parametrize(
    "dsn",
    [
        "",
        "postgresql://user:pass@localhost:5432/database",
        "postgresql://user:pass@db:5432/database",
        "postgresql://user:pass@example.com:5432/database",
    ],
)
def test_require_database_url_rejects_non_supabase_hosts(dsn: str) -> None:
    with pytest.raises(RuntimeError):
        require_database_url(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://user:pass@db.project.supabase.co:5432/postgres",
        "postgresql://user:pass@aws-1-region.pooler.supabase.com:6543/postgres",
    ],
)
def test_require_database_url_accepts_supabase_hosts(dsn: str) -> None:
    assert require_database_url(dsn) == dsn
