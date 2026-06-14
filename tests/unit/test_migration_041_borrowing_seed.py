"""Migration 041 must register both financing codes in ref.line_items."""
from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "backend" / "database" / "migrations" / "041_seed_borrowing_line_items.sql"
)


def test_migration_file_exists():
    assert MIGRATION.exists()


def test_migration_seeds_both_codes_idempotently():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "proceeds_from_borrowings.total" in sql
    assert "repayment_of_borrowings.total" in sql
    assert "ref.line_items" in sql
    assert "ON CONFLICT" in sql  # idempotent re-run
