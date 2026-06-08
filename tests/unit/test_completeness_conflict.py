"""Tests for core metric conflict blocking valuation."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.facts.completeness import CORE_FY_KEYS, build_fy_validation_report


def _base_table():
    """Minimal fact table with all CORE_FY_KEYS present for 3 periods."""
    from backend.facts.normalizer import FactEntry
    periods = ["2022FY", "2023FY", "2024FY"]
    table = {}
    for key in CORE_FY_KEYS:
        table[key] = {p: FactEntry(value=100.0, source_tier=0) for p in periods}
    return table, periods


def _base_raw_facts(periods):
    """Raw facts with no conflicts."""
    facts = []
    for key in CORE_FY_KEYS:
        for p in periods:
            facts.append({
                "line_item_code": key,
                "fiscal_year": int(p[:4]),
                "fiscal_period": "FY",
                "value": 100.0,
                "source_tier": 0,
                "confidence": 0.95,
                "ingested_at": datetime.now(UTC).isoformat(),
                "validation_status": "accepted",
            })
    return facts


def test_core_conflict_blocks_valuation():
    """Conflict on a CORE_FY_KEY metric must set valuation_gate=fail."""
    table, periods = _base_table()
    raw_facts = _base_raw_facts(periods)

    # Inject a conflicting fact for revenue.net @ 2023FY from a different source
    raw_facts.append({
        "line_item_code": "revenue.net",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "value": 200.0,  # 100% different from existing 100.0
        "source_tier": 1,
        "source_id": "conflict_source",
        "confidence": 0.90,
        "ingested_at": datetime.now(UTC).isoformat(),
        "validation_status": "accepted",
    })

    validation_status_table = {
        key: {p: "accepted" for p in periods}
        for key in CORE_FY_KEYS
    }
    source_tiers = {p: [0] for p in periods}

    report = build_fy_validation_report(
        ticker="TEST",
        table=table,
        raw_facts=raw_facts,
        required_periods=periods,
        periods_available=periods,
        periods_missing=[],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=validation_status_table,
        source_tiers_by_period=source_tiers,
    )

    assert report["valuation_gate"] == "fail", (
        f"Core metric conflict on revenue.net must block valuation, got: {report['valuation_gate']}"
    )
    blocking = report["blocking_reasons"]
    assert any("core_metric_conflict" in r for r in blocking), (
        f"Expected core_metric_conflict in blocking_reasons, got: {blocking}"
    )


def test_non_core_conflict_does_not_block():
    """Conflict on a non-core key must NOT block valuation."""
    table, periods = _base_table()
    raw_facts = _base_raw_facts(periods)

    # Inject conflict on a non-core key
    raw_facts.append({
        "line_item_code": "sga.total",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "value": 999.0,
        "source_tier": 1,
        "source_id": "conflict_source",
        "confidence": 0.90,
        "ingested_at": datetime.now(UTC).isoformat(),
        "validation_status": "accepted",
    })

    validation_status_table = {
        key: {p: "accepted" for p in periods}
        for key in CORE_FY_KEYS
    }
    source_tiers = {p: [0] for p in periods}

    report = build_fy_validation_report(
        ticker="TEST",
        table=table,
        raw_facts=raw_facts,
        required_periods=periods,
        periods_available=periods,
        periods_missing=[],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=validation_status_table,
        source_tiers_by_period=source_tiers,
    )

    # Non-core conflict should not add core_metric_conflict blocking reason
    blocking = report.get("blocking_reasons", [])
    assert not any("core_metric_conflict" in r for r in blocking), (
        f"Non-core conflict should not block valuation, got: {blocking}"
    )
