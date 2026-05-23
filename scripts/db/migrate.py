"""Migration runner for the VN pharma equity research DB.

Usage:
    python scripts/db/migrate.py                  # apply all pending migrations
    python scripts/db/migrate.py --check          # print pending list, exit 0
    python scripts/db/migrate.py --version        # print highest applied version
"""
from __future__ import annotations

import argparse
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
CURRENT_SCHEMA_VERSION = "006_accepted_facts_view"  # update when new migrations are added


def _pending_migrations(all_files: list[str], applied: set[str]) -> list[str]:
    """Return .sql filenames not yet applied, sorted lexicographically."""
    return sorted(
        f for f in all_files
        if f.endswith(".sql") and Path(f).stem not in applied
    )


def _version_from_filename(filename: str) -> str:
    """Strip .sql suffix: '005_fk_constraints.sql' -> '005_fk_constraints'."""
    return Path(filename).stem


def _apply_migration(conn, path: Path, version: str) -> None:
    """Apply one migration file and record it in schema_migrations.

    The migration SQL may contain its own BEGIN/COMMIT. We use autocommit=True
    on the connection before calling this so psycopg2 does not open an implicit
    transaction that conflicts with the file's own transaction block.
    After recording the version we commit the version-insert separately.
    """
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    # Record the version in a separate autocommit statement
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            (version,),
        )


@contextmanager
def _connect_autocommit(dsn: str):
    """Open a connection with autocommit=True to avoid nested transaction issues."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def get_applied_versions(dsn: str) -> set[str]:
    with _connect_autocommit(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM schema_migrations")
            return {row[0] for row in cur.fetchall()}


def run_migrations(dsn: str, dry_run: bool = False) -> list[str]:
    """Apply all pending migrations. Returns list of versions applied."""
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
            with _connect_autocommit(dsn) as conn:
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
            "Run: python scripts/db/migrate.py"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending DB migrations")
    parser.add_argument("--check", action="store_true", help="List pending migrations only; do not apply")
    parser.add_argument("--version", action="store_true", help="Print highest applied version and exit")
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL env var is not set.", file=sys.stderr)
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
