"""Backup public.* business tables to JSON before the cleanup migration.

Run this BEFORE applying migration 026_drop_public_business_tables.sql.

Usage:
    python scripts/database/backup_before_data_warehouse_cleanup.py

Output:
    storage/archive/dw_cleanup_backup_{timestamp}/
      manifest.json
      public_catalyst_events.json
      public_company_profiles.json
      public_financial_facts.json
      public_price_history.json
      public_source_versions.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import psycopg2
import psycopg2.extras

from backend.database.config import require_database_url

DSN = require_database_url()

# Tables with data worth backing up (zero-row tables skipped for size).
# Format: (schema, table_name, output_filename)
BACKUP_TARGETS = [
    ("public", "catalyst_events",   "public_catalyst_events.json"),
    ("public", "company_profiles",  "public_company_profiles.json"),
    ("public", "financial_facts",   "public_financial_facts.json"),
    ("public", "price_history",     "public_price_history.json"),
    ("public", "source_versions",   "public_source_versions.json"),
    # Zero-row tables — backed up as empty arrays for completeness
    ("public", "connector_runs",    "public_connector_runs.json"),
    ("public", "forecast_inputs",   "public_forecast_inputs.json"),
    ("public", "ingestion_runs",    "public_ingestion_runs.json"),
    ("public", "peer_metrics_snapshot", "public_peer_metrics_snapshot.json"),
    ("public", "research_runs",     "public_research_runs.json"),
    ("public", "run_approvals",     "public_run_approvals.json"),
    ("public", "run_artifacts",     "public_run_artifacts.json"),
    ("public", "run_audit_events",  "public_run_audit_events.json"),
    ("public", "run_budget_ledger", "public_run_budget_ledger.json"),
    ("public", "run_steps",         "public_run_steps.json"),
]


def _serialize(obj):
    """JSON serializer for Postgres types."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


def backup_table(cur, schema: str, table: str) -> list[dict]:
    """Dump all rows from schema.table as list of dicts."""
    try:
        cur.execute(f"SELECT * FROM {schema}.{table}")  # noqa: S608
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: could not read {schema}.{table}: {exc}")
        return []


def main() -> None:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(_PROJECT_ROOT) / "storage" / "archive" / f"dw_cleanup_backup_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Backup directory: {out_dir}")
    print(f"Connecting to database...")

    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    manifest = {
        "timestamp": timestamp,
        "database": DSN.split("@")[-1] if "@" in DSN else DSN,
        "backup_dir": str(out_dir),
        "tables": [],
    }

    total_rows = 0
    for schema, table, filename in BACKUP_TARGETS:
        print(f"  Backing up {schema}.{table}...", end=" ")
        rows = backup_table(cur, schema, table)
        row_count = len(rows)
        total_rows += row_count

        out_path = out_dir / filename
        out_path.write_text(
            json.dumps(rows, default=_serialize, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        manifest["tables"].append({
            "schema": schema,
            "table": table,
            "file": filename,
            "row_count": row_count,
        })
        print(f"{row_count} rows -> {filename}")

    cur.close()
    conn.close()

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, default=_serialize, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nBackup complete: {total_rows} total rows across {len(BACKUP_TARGETS)} tables")
    print(f"Manifest: {manifest_path}")
    print(f"\nRestore command (if needed):")
    print(f"  python scripts/database/restore_from_backup.py {out_dir}")


if __name__ == "__main__":
    main()
