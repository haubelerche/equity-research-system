"""Regression tests for vnstock finance fact collision resolution.

Root cause: vnstock VCI returns some balance-sheet concepts twice for one period
— a real figure plus a 0 placeholder sharing the same item_id (e.g. DHG
'Đầu tư ngắn hạn' → short_term_investments = [2024 bn, 0]). The old keep-last
dedup let the trailing 0 overwrite the real value, so net debt / equity bridge
silently dropped ~2,024 bn of short-term investments.
"""
from __future__ import annotations

from datetime import UTC, datetime

from backend.database.fact_store import FinancialFact
from scripts.connectors.vnstock_finance_connector import _resolve_fact_collisions


def _fact(line_item_code: str, value: float, *, ticker: str = "DHG",
          year: int = 2025, source_id: str = "src1") -> FinancialFact:
    return FinancialFact(
        ticker=ticker,
        fiscal_year=year,
        fiscal_period="FY",
        line_item_code=line_item_code,
        value=value,
        unit="vnd_bn",
        currency="VND",
        source_id=source_id,
        connector_version="vn_fin_parser_v1",
        validation_status="accepted",
        confidence=0.95,
        effective_date=None,
        ingested_at=datetime.now(UTC),
    )


def test_real_value_wins_over_trailing_zero_placeholder():
    # DHG order: real value first, 0 placeholder second (old bug kept the 0).
    facts = [
        _fact("short_term_investments.ending", 2024.0),
        _fact("short_term_investments.ending", 0.0),
    ]
    resolved = _resolve_fact_collisions(facts)
    assert len(resolved) == 1
    assert resolved[0].value == 2024.0


def test_real_value_wins_regardless_of_order():
    # Same collision but 0 placeholder appears first.
    facts = [
        _fact("short_term_investments.ending", 0.0),
        _fact("short_term_investments.ending", 2024.0),
    ]
    resolved = _resolve_fact_collisions(facts)
    assert len(resolved) == 1
    assert resolved[0].value == 2024.0


def test_negative_magnitude_value_wins_over_zero():
    # Provision-style line: real value is negative; |value| must still beat 0.
    facts = [
        _fact("provision.ending", 0.0),
        _fact("provision.ending", -19.5),
    ]
    resolved = _resolve_fact_collisions(facts)
    assert resolved[0].value == -19.5


def test_distinct_keys_are_all_preserved():
    facts = [
        _fact("short_term_investments.ending", 2024.0),
        _fact("cash_and_equivalents.ending", 129.9),
        _fact("total_assets.ending", 5173.9),
    ]
    resolved = _resolve_fact_collisions(facts)
    assert {f.line_item_code for f in resolved} == {
        "short_term_investments.ending",
        "cash_and_equivalents.ending",
        "total_assets.ending",
    }


def test_same_key_different_source_not_collapsed():
    # Different source_id ⇒ different upsert key ⇒ both kept.
    facts = [
        _fact("short_term_investments.ending", 2024.0, source_id="srcA"),
        _fact("short_term_investments.ending", 0.0, source_id="srcB"),
    ]
    resolved = _resolve_fact_collisions(facts)
    assert len(resolved) == 2


def test_conflicting_nonzero_keeps_larger_magnitude(capsys):
    facts = [
        _fact("revenue.net", 1198.0),
        _fact("revenue.net", 4500.0),
    ]
    resolved = _resolve_fact_collisions(facts)
    assert resolved[0].value == 4500.0
    out = capsys.readouterr().out
    assert "conflicting nonzero values" in out
