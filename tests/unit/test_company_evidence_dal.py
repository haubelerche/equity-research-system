"""Phase 1: research.company_evidence DAL — upsert + load latest year.

DB round-trip is integration territory; here we use an injectable fake connection
to test the real logic: JSON (de)serialization, latest-year selection, and the
empty-result contract.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

from backend.database import company_evidence_dal as dal


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


def test_upsert_serializes_pack_to_json_and_uses_on_conflict():
    sink: list = []
    dal.upsert_company_evidence(
        "dhg", 2025, {"business_evidence": {"x": 1}}, source_doc_id="doc1", model="gpt-5-mini",
        conn=_FakeConn(sink=sink),
    )
    sql, params = sink[0]
    assert "research.company_evidence" in sql
    assert "ON CONFLICT" in sql.upper()
    assert params[0] == "DHG" and params[1] == 2025
    # evidence_pack param is a JSON string
    assert json.loads(params[2]) == {"business_evidence": {"x": 1}}


def test_load_latest_returns_dict_from_json_string():
    pack = {"business_evidence": {"business_segments": {"OTC": {"value": "x"}}}}
    conn = _FakeConn(fetchone_result=(json.dumps(pack),))
    assert dal.load_latest_company_evidence("DHG", conn=conn) == pack


def test_load_latest_accepts_dict_row():
    pack = {"company_plans": {"borrowing_plan": []}}
    conn = _FakeConn(fetchone_result=(pack,))
    assert dal.load_latest_company_evidence("DHG", conn=conn) == pack


def test_load_latest_returns_empty_when_no_row():
    assert dal.load_latest_company_evidence("DHG", conn=_FakeConn(fetchone_result=None)) == {}


def test_load_latest_orders_by_fiscal_year_desc():
    sink: list = []
    dal.load_latest_company_evidence("DHG", conn=_FakeConn(fetchone_result=None, sink=sink))
    sql, _ = sink[0]
    assert "ORDER BY" in sql.upper() and "fiscal_year DESC" in sql
