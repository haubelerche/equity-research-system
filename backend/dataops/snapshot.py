"""Research snapshot service â€” v2 redirect shim.

All calls are forwarded to backend.database.canonical.snapshot_dal.
The legacy implementation (reading from superseded snapshot tables and financial fact tables)
has been removed as part of the Data Warehouse v2 cleanup.

Callers that imported from this module continue to work unchanged:
    from backend.dataops.snapshot import create_snapshot, load_snapshot_facts
"""
from __future__ import annotations

from backend.database.canonical.snapshot_dal import (  # noqa: F401  (re-export)
    create_snapshot,
    load_snapshot_facts,
    get_latest_snapshot,
)

__all__ = ["create_snapshot", "load_snapshot_facts", "get_latest_snapshot"]

