"""Unit tests for the migration runner (no live DB required)."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path


def test_pending_migrations_empty_when_all_applied():
    from backend.database.migrate import _pending_migrations
    all_files = ["001_foo.sql", "002_bar.sql"]
    applied = {"001_foo", "002_bar"}
    assert _pending_migrations(all_files, applied) == []


def test_pending_migrations_returns_unapplied_in_order():
    from backend.database.migrate import _pending_migrations
    all_files = ["001_foo.sql", "002_bar.sql", "003_baz.sql"]
    applied = {"001_foo"}
    result = _pending_migrations(all_files, applied)
    assert result == ["002_bar.sql", "003_baz.sql"]


def test_pending_migrations_order_is_lexicographic():
    from backend.database.migrate import _pending_migrations
    all_files = ["003_c.sql", "001_a.sql", "002_b.sql"]
    applied = set()
    result = _pending_migrations(all_files, applied)
    assert result == ["001_a.sql", "002_b.sql", "003_c.sql"]


def test_pending_migrations_ignores_non_sql():
    from backend.database.migrate import _pending_migrations
    all_files = ["001_a.sql", "README.md", "002_b.sql"]
    applied = set()
    result = _pending_migrations(all_files, applied)
    assert result == ["001_a.sql", "002_b.sql"]


def test_version_from_filename():
    from backend.database.migrate import _version_from_filename
    assert _version_from_filename("005_fk_constraints.sql") == "005_fk_constraints"
    assert _version_from_filename("001_initial_schema.sql") == "001_initial_schema"


def test_apply_migration_strips_begin_commit_and_inserts_version(tmp_path):
    from backend.database.migrate import _apply_migration
    sql_file = tmp_path / "005_test.sql"
    sql_file.write_text("BEGIN;\nCREATE TABLE foo (id INT);\nCOMMIT;", encoding="utf-8")

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    _apply_migration(mock_conn, sql_file, "005_test")

    calls = [str(c) for c in mock_cur.execute.call_args_list]
    # SQL should not contain BEGIN or COMMIT
    assert not any("BEGIN" in c for c in calls), "BEGIN should be stripped"
    assert not any("COMMIT" in c for c in calls), "COMMIT should be stripped"
    # Version insert must be present
    assert any("schema_migrations" in c for c in calls), "Version insert missing"


def test_run_migrations_dry_run_returns_empty_list():
    from backend.database.migrate import run_migrations
    with patch("backend.database.migrate.get_applied_versions", return_value=set()):
        with patch("backend.database.migrate.MIGRATIONS_DIR") as mock_dir:
            mock_dir.glob.return_value = []
            result = run_migrations("fake_dsn", dry_run=True)
    assert result == []
