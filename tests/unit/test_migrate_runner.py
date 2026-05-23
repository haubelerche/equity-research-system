"""Unit tests for the migration runner (no live DB required)."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path


def test_pending_migrations_empty_when_all_applied():
    from scripts.db.migrate import _pending_migrations
    all_files = ["001_foo.sql", "002_bar.sql"]
    applied = {"001_foo", "002_bar"}
    assert _pending_migrations(all_files, applied) == []


def test_pending_migrations_returns_unapplied_in_order():
    from scripts.db.migrate import _pending_migrations
    all_files = ["001_foo.sql", "002_bar.sql", "003_baz.sql"]
    applied = {"001_foo"}
    result = _pending_migrations(all_files, applied)
    assert result == ["002_bar.sql", "003_baz.sql"]


def test_pending_migrations_order_is_lexicographic():
    from scripts.db.migrate import _pending_migrations
    all_files = ["003_c.sql", "001_a.sql", "002_b.sql"]
    applied = set()
    result = _pending_migrations(all_files, applied)
    assert result == ["001_a.sql", "002_b.sql", "003_c.sql"]


def test_pending_migrations_ignores_non_sql():
    from scripts.db.migrate import _pending_migrations
    all_files = ["001_a.sql", "README.md", "002_b.sql"]
    applied = set()
    result = _pending_migrations(all_files, applied)
    assert result == ["001_a.sql", "002_b.sql"]


def test_version_from_filename():
    from scripts.db.migrate import _version_from_filename
    assert _version_from_filename("005_fk_constraints.sql") == "005_fk_constraints"
    assert _version_from_filename("001_initial_schema.sql") == "001_initial_schema"
