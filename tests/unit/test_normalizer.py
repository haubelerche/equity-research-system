"""Unit tests for backend.facts.normalizer."""
import pytest
from backend.facts.normalizer import build_fact_table, compute_derived, FactTable


def test_compute_derived_import():
    """Smoke: function exists and is importable."""
    assert callable(compute_derived)


def test_free_cash_flow_capex_sign_convention():
    """CAPEX is stored NEGATIVE (as a cash outflow from the cash flow statement).

    Therefore: FCF = OCF + CAPEX (where CAPEX is negative)

    NOT: FCF = OCF - CAPEX (which would incorrectly add the magnitude)

    Example:
    - OCF = 1213.0 (tỷ VND)
    - CAPEX = -31.1 (tỷ VND) — stored as negative because it's a CFS outflow
    - FCF should be: 1213.0 + (-31.1) = 1181.9
    - Wrong would be: 1213.0 - (-31.1) = 1244.1
    """
    table: FactTable = {
        "operating_cash_flow.total": {"2024FY": 1213.0},
        "capex.total": {"2024FY": -31.1},  # Negative: cash outflow
    }

    result = compute_derived(table)

    # FCF should be 1181.9, not 1244.1
    assert "free_cash_flow.total" in result
    assert "2024FY" in result["free_cash_flow.total"]
    fcf = result["free_cash_flow.total"]["2024FY"]

    # The correct formula is OCF + CAPEX (where CAPEX is negative)
    expected = 1213.0 + (-31.1)  # = 1181.9
    assert abs(fcf - expected) < 0.01, f"Expected {expected}, got {fcf}"


def test_free_cash_flow_missing_ocf():
    """When OCF is missing, FCF should not be derived."""
    table: FactTable = {
        "capex.total": {"2024FY": -31.1},
    }

    result = compute_derived(table)

    # FCF should not be present if OCF is missing
    assert "free_cash_flow.total" not in result


def test_free_cash_flow_missing_capex():
    """When CAPEX is missing, FCF should not be derived."""
    table: FactTable = {
        "operating_cash_flow.total": {"2024FY": 1213.0},
    }

    result = compute_derived(table)

    # FCF should not be present if CAPEX is missing
    assert "free_cash_flow.total" not in result


def test_free_cash_flow_multiple_periods():
    """FCF derivation should work across multiple periods."""
    table: FactTable = {
        "operating_cash_flow.total": {
            "2022FY": 1000.0,
            "2023FY": 1100.0,
            "2024FY": 1213.0,
        },
        "capex.total": {
            "2022FY": -20.0,
            "2023FY": -25.0,
            "2024FY": -31.1,
        },
    }

    result = compute_derived(table)

    assert "free_cash_flow.total" in result
    assert result["free_cash_flow.total"]["2022FY"] == 1000.0 + (-20.0)  # 980.0
    assert result["free_cash_flow.total"]["2023FY"] == 1100.0 + (-25.0)  # 1075.0
    assert abs(result["free_cash_flow.total"]["2024FY"] - 1181.9) < 0.01


def test_build_fact_table_basic():
    """Smoke: build_fact_table creates proper FactTable structure."""
    raw_facts = [
        {
            "taxonomy_key": "revenue.net",
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "value": 1000.0,
            "confidence": 0.9,
            "ingested_at": "2026-01-01T00:00:00+00:00",
        },
    ]

    table = build_fact_table(raw_facts)

    assert "revenue.net" in table
    assert "2024FY" in table["revenue.net"]
    assert table["revenue.net"]["2024FY"] == 1000.0


def test_build_fact_table_confidence_tie_break():
    """When confidence is equal, latest ingested_at wins."""
    raw_facts = [
        {
            "taxonomy_key": "revenue.net",
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "value": 1000.0,
            "confidence": 0.9,
            "ingested_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "taxonomy_key": "revenue.net",
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "value": 1500.0,
            "confidence": 0.9,  # Same confidence
            "ingested_at": "2026-01-02T00:00:00+00:00",  # Later
        },
    ]

    table = build_fact_table(raw_facts)

    # Latest ingested_at should win
    assert table["revenue.net"]["2024FY"] == 1500.0
