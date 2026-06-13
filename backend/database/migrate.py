"""Migration runner for the VN pharma equity research DB.

Usage:
    python -m backend.database.migrate                  # apply all pending migrations
    python -m backend.database.migrate --check          # print pending list, exit 0
    python -m backend.database.migrate --version        # print highest applied version
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2

from backend.database.config import connect_with_retry, require_database_url

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
CURRENT_SCHEMA_VERSION = "039_news_ticker_sources"

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _value = _line.split("=", 1)
            os.environ.setdefault(_key.strip(), _value.strip().strip("\"'"))


def _bootstrap_migrations_table(conn) -> None:
    """Create public.schema_migrations if it does not exist.

    Called before any other query so the runner can safely read applied versions
    even on a brand-new database.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                version     VARCHAR(80)  NOT NULL PRIMARY KEY,
                applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                description TEXT
            )
            """
        )


def _pending_migrations(all_files: list[str], applied: set[str]) -> list[str]:
    """Return .sql filenames not yet applied, sorted lexicographically.

    Files inside _legacy/ subdirectory are ignored (only direct children counted).
    """
    return sorted(
        f for f in all_files
        if f.endswith(".sql") and Path(f).stem not in applied
    )


def _version_from_filename(filename: str) -> str:
    """Strip .sql suffix: '005_seed_reference_data.sql' -> '005_seed_reference_data'."""
    return Path(filename).stem


def _apply_migration(conn, path: Path, version: str) -> None:
    """Apply one migration file and record it in schema_migrations atomically.

    Migration files must not contain BEGIN/COMMIT â€” the runner owns the transaction.
    Strip them robustly with multiline flag in case any file accidentally contains them.
    """
    sql = path.read_text(encoding="utf-8")
    sql = re.sub(r"(?im)^\s*BEGIN\s*;\s*$", "", sql)
    sql = re.sub(r"(?im)^\s*COMMIT\s*;\s*$", "", sql)
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO public.schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            (version,),
        )


@contextmanager
def _connect(dsn: str):
    conn = connect_with_retry(dsn)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_applied_versions(dsn: str) -> set[str]:
    with _connect(dsn) as conn:
        _bootstrap_migrations_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM public.schema_migrations")
            return {row[0] for row in cur.fetchall()}


def run_migrations(dsn: str, dry_run: bool = False) -> list[str]:
    """Apply all pending migrations. Returns list of versions actually applied."""
    # Only .sql files directly in MIGRATIONS_DIR (not _legacy/ subfolder).
    all_files = sorted(f.name for f in MIGRATIONS_DIR.glob("*.sql"))
    applied = get_applied_versions(dsn)
    pending = _pending_migrations(all_files, applied)

    if not pending:
        print("No pending migrations.")
        return []

    applied_list = []
    for filename in pending:
        version = _version_from_filename(filename)
        path = MIGRATIONS_DIR / filename
        if dry_run:
            print(f"  [dry-run] would apply: {version}")
        else:
            print(f"  Applying: {version} ... ", end="", flush=True)
            with _connect(dsn) as conn:
                _bootstrap_migrations_table(conn)
                _apply_migration(conn, path, version)
            print("done")
            applied_list.append(version)
    return applied_list


def check_schema_version(dsn: str) -> None:
    """Raise RuntimeError if the DB schema version does not match CURRENT_SCHEMA_VERSION."""
    applied = get_applied_versions(dsn)
    if CURRENT_SCHEMA_VERSION not in applied:
        raise RuntimeError(
            f"Schema version mismatch: required '{CURRENT_SCHEMA_VERSION}' not in applied={sorted(applied)}. "
            "Run: python -m backend.database.migrate"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending DB migrations")
    parser.add_argument("--check", action="store_true", help="List pending migrations only; do not apply")
    parser.add_argument("--version", action="store_true", help="Print highest applied version and exit")
    args = parser.parse_args()

    try:
        dsn = require_database_url()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.version:
        applied = get_applied_versions(dsn)
        print(max(applied, default="(none)"))
        return

    if args.check:
        run_migrations(dsn, dry_run=True)
    else:
        run_migrations(dsn, dry_run=False)


if __name__ == "__main__":
    main()
