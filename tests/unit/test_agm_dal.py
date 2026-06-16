"""research.agm_resolutions DAL — upsert + load latest meeting.

DB round-trip is integration territory; here an injectable fake connection tests the
real logic: JSON (de)serialization, latest-meeting selection, and the empty contract.
"""
from __future__ import annotations

import json
from backend.database import agm_dal as dal


class _FakeCursor:
    def __init__(self, fetchone_result=None, sink=None):
        self._fetchone = fetchone_result
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if self._sink is not None:
            self._sink.append((sql, params))

    def fetchone(self):
        return self._fetchone


class _FakeConn:
    def __init__(self, fetchone_result=None, sink=None):
        self._fetchone = fetchone_result
        self._sink = sink

    def cursor(self):
        return _FakeCursor(self._fetchone, self._sink)


def test_upsert_serializes_pack_and_uses_on_conflict():
    sink: list = []
    dal.upsert_agm_resolutions(
        "dhg", 2026, {"approved_resolutions": [{"item_no": "1"}]},
        source_docs=[{"file": "DHG DHCD 2026(1).pdf"}], model="gpt-5-mini",
        conn=_FakeConn(sink=sink),
    )
    sql, params = sink[0]
    assert "research.agm_resolutions" in sql
    assert "ON CONFLICT" in sql.upper()
    assert params[0] == "DHG" and params[1] == 2026
    assert json.loads(params[2]) == {"approved_resolutions": [{"item_no": "1"}]}
    assert json.loads(params[3]) == [{"file": "DHG DHCD 2026(1).pdf"}]


def test_load_latest_returns_dict_from_json_string():
    pack = {"borrowing_plan": [{"year": 2026, "amount": 0.0}]}
    conn = _FakeConn(fetchone_result=(json.dumps(pack),))
    assert dal.load_latest_agm("DHG", conn=conn) == pack


def test_load_latest_accepts_dict_row():
    pack = {"targets_2026": {"revenue": 5500.0}}
    conn = _FakeConn(fetchone_result=(pack,))
    assert dal.load_latest_agm("DHG", conn=conn) == pack


def test_load_latest_returns_empty_when_no_row():
    assert dal.load_latest_agm("DHG", conn=_FakeConn(fetchone_result=None)) == {}


def test_load_latest_orders_by_meeting_year_desc():
    sink: list = []
    dal.load_latest_agm("DHG", conn=_FakeConn(fetchone_result=None, sink=sink))
    sql, _ = sink[0]
    assert "ORDER BY" in sql.upper() and "meeting_year DESC" in sql
