from __future__ import annotations
from datetime import datetime, timedelta, UTC
from backend.dataops.snapshot_freshness import is_fresh


def test_active_recent_snapshot_is_fresh():
    snap = {"status": "active", "created_at": datetime.now(UTC) - timedelta(hours=2)}
    assert is_fresh(snap, ttl_hours=24) is True

def test_stale_status_is_not_fresh():
    snap = {"status": "stale", "created_at": datetime.now(UTC)}
    assert is_fresh(snap, ttl_hours=24) is False

def test_archived_status_is_not_fresh():
    snap = {"status": "archived", "created_at": datetime.now(UTC)}
    assert is_fresh(snap, ttl_hours=24) is False

def test_old_active_snapshot_is_not_fresh():
    snap = {"status": "active", "created_at": datetime.now(UTC) - timedelta(hours=48)}
    assert is_fresh(snap, ttl_hours=24) is False

def test_none_or_missing_created_at_is_not_fresh():
    assert is_fresh(None, ttl_hours=24) is False
    assert is_fresh({"status": "active"}, ttl_hours=24) is False

def test_naive_datetime_is_treated_as_utc():
    naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    assert is_fresh({"status": "active", "created_at": naive}, ttl_hours=24) is True
