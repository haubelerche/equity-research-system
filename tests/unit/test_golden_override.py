"""Tests for golden CSV override logging and blocking."""
from __future__ import annotations


def test_golden_override_detection_at_3_pct():
    """Spec §1.2: Golden override with >2% variance should be detected."""
    from scripts.build_facts import _detect_golden_overrides

    db_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 100.0, "source_tier": 3, "source_id": "api_src"},
    ]
    golden_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 103.0, "source_tier": 0, "source_id": "golden_csv_TEST_2023FY"},
    ]

    overrides = _detect_golden_overrides(db_facts, golden_facts)
    assert len(overrides) >= 1
    assert overrides[0]["variance_pct"] > 2.0
    assert overrides[0]["is_blocking"] is False  # 3% < 10%


def test_golden_override_blocks_at_15_pct():
    """Spec §1.2: Golden override with >10% variance must be blocking."""
    from scripts.build_facts import _detect_golden_overrides

    db_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 100.0, "source_tier": 3, "source_id": "api_src"},
    ]
    golden_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 115.0, "source_tier": 0, "source_id": "golden_csv_TEST_2023FY"},
    ]

    overrides = _detect_golden_overrides(db_facts, golden_facts)
    assert len(overrides) >= 1
    assert overrides[0]["variance_pct"] > 10.0
    assert overrides[0]["is_blocking"] is True


def test_golden_no_overlap_no_override():
    """No overlapping (metric, period) → no overrides detected."""
    from scripts.build_facts import _detect_golden_overrides

    db_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 100.0, "source_tier": 3, "source_id": "api_src"},
    ]
    golden_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2022, "fiscal_period": "FY",
         "value": 90.0, "source_tier": 0, "source_id": "golden_csv_TEST_2022FY"},
    ]

    overrides = _detect_golden_overrides(db_facts, golden_facts)
    assert len(overrides) == 0
